#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""check_tests_touched.py - "changed src/, did not touch tests/" guard.

WHY THIS FILE EXISTS
====================
This is the only place in module 2 with real logic. Both hook flavours
(hooks/pre-commit for bash, hooks/pre-commit.ps1 for PowerShell) are thin
wrappers that call this file and forward its exit code. One implementation
means the rule cannot drift between two shells.

=====================================================================
EXIT CODE CONTRACT  (this is what makes a hook able to stop a commit)
=====================================================================
    0 = ALLOW   nothing to complain about
    1 = BLOCK   src/ files are staged and no tests/ file is staged
    2 = USAGE   bad arguments / not a git work tree / git itself failed

git itself only ever looks at the exit code, so the contract above is the
real interface. Everything else is decoration.

STREAM DISCIPLINE
=================
    stdout -> PAYLOAD ONLY (the JSON document, when --json is given)
    stderr -> "ERROR: ..." lines only

Why so strict? Because the caller is a *machine* (git, or CI), not a reader.
git reads only the exit code; a CI job may want to parse stdout. If human
chatter and payload share stdout, every downstream consumer has to guess
where the payload starts. So:
  * machines read exit code + stdout,
  * humans read stderr (git prints a failing hook's stderr right at the
    terminal where the person typed `git commit`).
Under --json there is nothing at all on stderr when the run succeeds,
and stdout is a single parseable JSON document in every case.

WHY `-z` (NUL separated) AND NOT PLAIN `--name-only`
====================================================
`git diff --name-only` C-quotes any path that is not plain ASCII. Measured on
git 2.53.0.windows.2 in the lab repo:

    $ git diff --cached --name-only
    src/app.py
    "src/\344\270\255\346\226\207.py"     <- one file; that is not its name
    tests/t.py

A naive checker that string-matches "tests/" / "src/" against that output is
comparing against a byte-escaped rendering, not against the path. Two ways
that bites:
  1. A real change under src/ arrives as `"src/\346..."`; prefix matching on
     the raw text silently fails -> the guard lets the commit through.
  2. A crafted name can be made to *look* like it is under tests/ while the
     file really lives somewhere else.
`-z` makes git emit the raw bytes, NUL terminated, with no quoting at all.
We split on NUL and decode with os.fsdecode() (UTF-8 + surrogateescape;
git stores index paths as UTF-8 and PEP 529 makes Windows agree), so prefix
matching sees the true path.

This is also why the code never does `out.splitlines()` on diff output -
I/O newline handling and C-quoting both disappear when NUL is the separator.

EDGE CASES HANDLED
==================
* Fresh `git init`, no commit yet (unborn HEAD):
    - staged mode: `git diff --cached` still works and diffs the index
      against the empty tree, so no special case is needed.
    - --all mode: `git diff HEAD` dies with exit 128, "fatal: ambiguous
      argument 'HEAD'". We probe HEAD first and fall back to the empty tree.
* Nothing staged / nothing changed at all -> exit 0, reason "no changes".
  (This is the "no trackable changes" boundary: an empty diff is not a
  violation, it just means there is nothing to gate.)
* Empty prefix ("") -> exit 2, because an empty prefix would match every
  path and turn the guard into noise.
* Backslash prefixes (`--src-prefix src\`) are normalised to '/', since git
  always reports paths with forward slashes.
* Untracked files never appear in a diff. `--all` sees tracked+staged only;
  use `git add -N <path>` if an untracked file must be considered.

USAGE
=====
    python check_tests_touched.py [--all] [--json]
                                  [--src-prefix src/] [--tests-prefix tests/]

Run it by hand to see what the hook would decide:

    python scripts/check_tests_touched.py --json ; echo "exit=$?"
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

TOOL_NAME = "check_tests_touched"
DEFAULT_SRC_PREFIX = "src/"
DEFAULT_TESTS_PREFIX = "tests/"

EXIT_ALLOW = 0
EXIT_BLOCK = 1
EXIT_USAGE = 2

#: How many paths to name in a human-facing message before saying "(+N more)".
LIST_LIMIT = 10


class UsageError(Exception):
    """Bad arguments or an environment we cannot evaluate -> exit code 2."""


# ---------------------------------------------------------------------------
# stream helpers
# ---------------------------------------------------------------------------
def configure_streams() -> None:
    """Stop a non-encodable character from turning a verdict into a traceback.

    The console on this box is GBK (cp936). Only `errors` is changed here: the
    stream keeps its own encoding, so the terminal still renders Chinese
    correctly, but a character the encoding cannot represent degrades to '?'
    instead of raising UnicodeEncodeError *after* the verdict was already
    computed. A guard that crashes is worse than a guard that prints '?'.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:  # detached / exotic stream: nothing we can do
            pass


def eprint(message: str) -> None:
    """Human-facing output. Always stderr, always 'ERROR: ' prefixed."""
    print("ERROR: " + message, file=sys.stderr)


def summarise(paths):
    """Render a path list compactly: 'a, b, c (+7 more)' or '-' if empty."""
    if not paths:
        return "-"
    shown = paths[:LIST_LIMIT]
    text = ", ".join(shown)
    if len(paths) > len(shown):
        text += " (+%d more)" % (len(paths) - len(shown))
    return text


def usage_text() -> str:
    return """\
{name} - block a commit that changes {src} but stages no test.

usage:
  python check_tests_touched.py [options]

options:
  --all                  diff the index+worktree against HEAD instead of
                         diffing the index against HEAD. Use this outside a
                         commit (CI, review bots); the default staged mode is
                         what a pre-commit hook needs.
  --json                 write a machine-readable payload to stdout.
  --src-prefix PREFIX    path prefix that counts as "source"   (default {src})
  --tests-prefix PREFIX  path prefix that counts as "tests"    (default {tests})
  -h, --help             print this text (to stdout) and exit 0.

exit codes:
  0  allow  - nothing staged that needs a test, or tests were touched too.
  1  block  - source staged without any staged test.
  2  usage  - bad option, not a git work tree, or git failed.

streams:
  stdout  payload only (JSON with --json), never advice.
  stderr  "ERROR: " lines only.

examples:
  python scripts/check_tests_touched.py --json
  python scripts/check_tests_touched.py --all --src-prefix packages/api/
""".format(
        name=TOOL_NAME,
        src=DEFAULT_SRC_PREFIX,
        tests=DEFAULT_TESTS_PREFIX,
    )


# ---------------------------------------------------------------------------
# argument parsing (hand rolled: argparse would print its own usage wording to
# stderr and we promised stderr carries only "ERROR: " lines)
# ---------------------------------------------------------------------------
def parse_args(argv):
    opts = {
        "mode": "staged",
        "json": False,
        "src_prefix": DEFAULT_SRC_PREFIX,
        "tests_prefix": DEFAULT_TESTS_PREFIX,
        "help": False,
    }
    value_targets = {
        "--src-prefix": "src_prefix",
        "--tests-prefix": "tests_prefix",
    }

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            opts["help"] = True
        elif arg == "--all":
            opts["mode"] = "head"
        elif arg == "--json":
            opts["json"] = True
        elif arg in value_targets or "=" in arg and arg.split("=", 1)[0] in value_targets:
            if "=" in arg:
                key, value = arg.split("=", 1)
            else:
                key = arg
                i += 1
                if i >= len(argv):
                    raise UsageError("%s needs a value" % key)
                value = argv[i]
            opts[value_targets[key]] = value
        elif arg.startswith("-"):
            raise UsageError("unknown option: %s" % arg)
        else:
            raise UsageError("unexpected positional argument: %s" % arg)
        i += 1

    for key, flag in (("src_prefix", "--src-prefix"), ("tests_prefix", "--tests-prefix")):
        prefix = opts[key].strip().replace("\\", "/")
        while prefix.startswith("./"):
            prefix = prefix[2:]
        prefix = prefix.lstrip("/")
        if not prefix:
            raise UsageError("%s must not be empty (an empty prefix matches everything)" % flag)
        # Treat the value as a directory prefix: "src" and "src/" must behave
        # identically, otherwise --src-prefix src would also match "src2/x.py".
        if not prefix.endswith("/"):
            prefix += "/"
        opts[key] = prefix

    return opts


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------
def run_git(args, cwd=None):
    """Run git, return raw stdout bytes. Any failure is a usage error (2)."""
    cmd = ["git"] + list(args)
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        raise UsageError("git executable not found on PATH")
    except OSError as exc:
        raise UsageError("could not run git: %s" % exc)

    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip() or "(no stderr)"
        raise UsageError(
            "git %s failed with exit %d: %s" % (" ".join(args), proc.returncode, detail)
        )
    return proc.stdout


def find_repo_root():
    """Absolute path of the work tree root, or UsageError.

    We always diff from the repo root: `git diff` reports paths relative to the
    current directory, so running the checker from a subdirectory would make
    "src/" mean something different. Pinning cwd to the top level keeps the
    prefix semantics absolute and reproducible no matter where the caller is.
    """
    cmd = ["git", "rev-parse", "--show-toplevel"]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
        )
    except FileNotFoundError:
        raise UsageError("git executable not found on PATH")
    except OSError as exc:
        raise UsageError("could not run git: %s" % exc)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise UsageError("not inside a git work tree: %s" % (detail or "rev-parse failed"))
    return os.fsdecode(proc.stdout.strip())


def head_exists(root):
    """True when HEAD resolves (i.e. the repo has at least one commit)."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.returncode == 0


def changed_paths(root, mode, have_head):
    """Return (paths, base_description) for the requested comparison."""
    if mode == "head":
        if have_head:
            args = ["diff", "HEAD", "--name-only", "-z", "--"]
            base = "work tree + index vs HEAD"
        else:
            # Unborn HEAD: `git diff HEAD` exits 128 with "ambiguous argument
            # 'HEAD'". The only well defined "everything that changed" is the
            # index against the empty tree.
            args = ["diff", "--cached", "--name-only", "-z", "--"]
            base = "index vs empty tree (HEAD is unborn)"
    else:
        # Works with or without HEAD: with no commits git compares the index
        # against the empty tree, which is exactly what we want on `git init`.
        args = ["diff", "--cached", "--name-only", "-z", "--"]
        base = "index vs HEAD" if have_head else "index vs empty tree (HEAD is unborn)"

    raw = run_git(args, cwd=root)
    # -z output: <path>NUL<path>NUL... with no quoting, so this split sees the
    # real bytes. os.fsdecode keeps undecodable bytes as surrogates instead of
    # raising, so a weird path can never crash the guard.
    paths = [os.fsdecode(chunk) for chunk in raw.split(b"\0") if chunk]
    return paths, base


def prefix_match(path, prefix):
    """git always uses '/' in diff output; be forgiving if it ever does not."""
    return path.replace("\\", "/").startswith(prefix)


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------
def evaluate(paths, src_prefix, tests_prefix):
    src_files = [p for p in paths if prefix_match(p, src_prefix)]
    tests_files = [p for p in paths if prefix_match(p, tests_prefix)]
    violation = bool(src_files) and not tests_files
    return src_files, tests_files, violation


def decide_reason(mode, paths, src_files, tests_files, violation):
    if violation:
        return "source changed without a staged test change"
    if not paths:
        return "nothing staged" if mode == "staged" else "no trackable changes vs HEAD"
    if not src_files:
        return "no source files touched"
    return "source and tests both touched"


def report_violation(mode, src_files, tests_files):
    eprint("source files are staged but no test file is staged.")
    eprint("  staged under source prefix (%d): %s" % (len(src_files), summarise(src_files)))
    eprint("  staged under tests  prefix (%d): %s" % (len(tests_files), summarise(tests_files)))
    eprint("fix: stage the test that covers this change, e.g. git add tests/test_app.py")
    eprint("     or skip this hook once with: git commit --no-verify")


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def main(argv):
    configure_streams()

    try:
        opts = parse_args(argv)
    except UsageError as exc:
        eprint(str(exc))
        eprint("run with --help for usage")
        return EXIT_USAGE

    if opts["help"]:
        sys.stdout.write(usage_text())
        return EXIT_ALLOW

    try:
        root = find_repo_root()
        have_head = head_exists(root)
        paths, base = changed_paths(root, opts["mode"], have_head)
    except UsageError as exc:
        eprint(str(exc))
        return EXIT_USAGE

    src_files, tests_files, violation = evaluate(
        paths, opts["src_prefix"], opts["tests_prefix"]
    )
    reason = decide_reason(opts["mode"], paths, src_files, tests_files, violation)
    exit_code = EXIT_BLOCK if violation else EXIT_ALLOW

    if opts["json"]:
        payload = {
            "tool": TOOL_NAME,
            "mode": "staged" if opts["mode"] == "staged" else "all",
            "base": base,
            "repo_root": root,
            "src_prefix": opts["src_prefix"],
            "tests_prefix": opts["tests_prefix"],
            "changed": paths,
            "changed_count": len(paths),
            "src_files": src_files,
            "src_count": len(src_files),
            "tests_files": tests_files,
            "tests_count": len(tests_files),
            "violation": violation,
            "reason": reason,
            "exit_code": exit_code,
        }
        # ensure_ascii defaults to True on purpose: the payload stays pure
        # ASCII, so it survives a GBK console, a PowerShell pipe and a CI log
        # without anyone having to agree on an encoding.
        sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")

    if violation:
        report_violation(opts["mode"], src_files, tests_files)

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(EXIT_USAGE)
    except Exception as exc:  # never hand a traceback to a hook: exit 2 instead
        eprint("internal error: %s: %s" % (type(exc).__name__, exc))
        sys.exit(EXIT_USAGE)
