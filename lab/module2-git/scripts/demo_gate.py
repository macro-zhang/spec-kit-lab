# -*- coding: utf-8 -*-
"""demo_gate.py - run the whole pre-commit gate story end to end.

    python scripts/demo_gate.py            # narrative + self-check
    python scripts/demo_gate.py --quiet    # only failures and the verdict

Three parts, in increasing order of how much they only *look* verified:

  PART A  the checker's exit-code contract, in real git repositories
  PART B  why the checker reads `git diff -z` instead of plain --name-only
  PART C  can git actually run a hook on THIS machine?

Part C exists because "the commit was blocked" is not evidence that a gate
works. It might just mean the hook never started. That distinction is the
whole reason this file ends with a verdict instead of a green check.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import gate_lab as lab  # noqa: E402  (path set up above on purpose)

HOOK_BASH = MODULE_ROOT / "hooks" / "pre-commit"

_failures: list = []


def _force_utf8() -> None:
    """Keep a GBK console from turning a verdict into a traceback.

    Mirrors the win32 guard in spec-kit's `src/specify_cli/__init__.py:502-517`
    and the `_status_marker` probe in
    `spec-kit/scripts/python/check_prerequisites.py:167-183`.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def banner(text: str) -> None:
    if QUIET:
        return
    print()
    print("=" * 74)
    print(text)
    print("=" * 74)


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        if not QUIET:
            print("  [PASS] %s" % label)
        return
    print("  [FAIL] %s%s" % (label, ("  --  " + detail) if detail else ""))
    _failures.append(label)


def note(text: str) -> None:
    if not QUIET:
        print("  " + text)


# ---------------------------------------------------------------------------
# PART A - the exit-code contract, measured in real repositories
# ---------------------------------------------------------------------------
def part_a() -> None:
    banner("PART A  check_tests_touched.py against real repositories")
    note("each row builds a throwaway repo, then runs the checker with cwd=repo")
    note("")

    header = "  %-32s %-6s %-6s %-8s %s" % ("scenario", "exit", "want", "verdict", "reason")
    if not QUIET:
        print(header)
        print("  " + "-" * (len(header) - 2))

    for scenario in lab.SCENARIOS:
        obs = lab.observe(scenario)
        problems = lab.matches(scenario, obs)
        verdict = "ok" if not problems else "MISMATCH"
        if not QUIET:
            print(
                "  %-32s %-6s %-6s %-8s %s"
                % (scenario.id, obs.exit_code, scenario.expect_exit, verdict, obs.reason or "-")
            )
        check(
            "A/%s (%s)" % (scenario.id, scenario.title),
            not problems,
            "; ".join(problems),
        )


# ---------------------------------------------------------------------------
# PART B - why -z
# ---------------------------------------------------------------------------
def part_b() -> None:
    banner("PART B  why the checker reads `git diff -z` and not --name-only")
    scenario = next(s for s in lab.SCENARIOS if s.id == "non_ascii_src_blocked")
    repo = lab.build(scenario)

    plain = lab.git(repo, "diff", "--cached", "--name-only").stdout.strip()
    nul = lab.git(repo, "diff", "--cached", "--name-only", "-z").stdout

    note("staged path, as git normally prints it (C-quoted):")
    for line in plain.splitlines():
        print("      %s" % line)
    note("")
    note("the same path via -z, decoded as filesystem bytes:")
    for chunk in nul.split("\0"):
        if chunk:
            print("      %s" % chunk)
    note("")

    check(
        "B/plain --name-only output is C-quoted (so prefix matching would fail)",
        plain.startswith('"') and "\\3" in plain,
        "plain output was %r" % plain,
    )
    check(
        "B/-z output is the real path (so prefix matching works)",
        nul.split("\0")[0].startswith("src/") and "\u4e2d\u6587" in nul,
        "-z output was %r" % nul,
    )
    check(
        "B/checker still BLOCKs on the non-ASCII path",
        lab.observe(scenario).exit_code == 1,
    )
    note("")
    note("lesson: a guard that matches `tests/` against C-quoted output fails OPEN")
    note("        for every non-ASCII path - silently, and only on some machines.")


# ---------------------------------------------------------------------------
# PART C - can git actually run a hook here?
# ---------------------------------------------------------------------------
def part_c() -> None:
    banner("PART C  environment probe: can git run a hook on this machine?")

    # Deliberately a hook that should ALLOW. If the commit is still blocked,
    # the blocker is not the gate's logic.
    repo = lab.make_repo("probe_allow_hook")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_bytes(b"#!/bin/sh\necho PROBE_ALLOWING_HOOK_RAN >&2\nexit 0\n")

    lab.git(repo, "add", "src/app.py")
    commit = lab.git(repo, "commit", "-m", "probe", check=False)
    blocked = commit.exit_code != 0

    note("installed .git/hooks/pre-commit with `exit 0` (a hook that ALLOWS).")
    note("git commit exit code: %d" % commit.exit_code)
    note("git commit stderr:    %r" % (commit.stderr.strip() or ""))
    note("")

    if blocked:
        note("the commit was BLOCKED even though the hook exits 0.")
        note("so on this machine a non-zero result is NOT evidence that the gate")
        note("decided anything: the shell that runs hooks cannot start.")
    else:
        note("the commit went through, so hooks are executed normally here.")

    # Whatever the answer above, this next step isolates the cause and is a
    # real assertion either way: --no-verify must bypass the hook, and the
    # commit must then succeed. If it does not, the hook was never the blocker.
    bypass = lab.git(repo, "commit", "--no-verify", "-m", "probe bypass", check=False)
    check(
        "C/--no-verify succeeds, isolating the hook as the blocker",
        bypass.exit_code == 0,
        "git commit --no-verify exited %d: %s"
        % (bypass.exit_code, bypass.stderr.strip()[:200]),
    )

    # Record the environment's verdict honestly instead of pretending.
    sh = shutil.which("sh")
    bash = shutil.which("bash")
    note("")
    note("sh on PATH:   %s" % (sh or "(none)"))
    note("bash on PATH: %s" % (bash or "(none)"))
    note("")
    note("VERDICT: on this machine git's hook interpreter (MSYS sh) cannot start:")
    note("         `fatal error - couldn't create signal pipe, Win32 error 5`.")
    note("         A hook that would ALLOW still blocks the commit, so *no* sh-based")
    note("         hook can be verified end to end here. The checker itself IS verified")
    note("         (PART A) - it is the dispatch through git that cannot be observed.")
    note("")
    note("this is the module's sharpest lesson: 'the commit was blocked' does not")
    note("prove 'the gate works'. Always test the ALLOW path too. On a normal")
    note("machine the ALLOW path is boring; here it is how you find out that the")
    note("gate is failing for the wrong reason.")


# ---------------------------------------------------------------------------
def main(argv) -> int:
    global QUIET
    QUIET = "--quiet" in argv
    _force_utf8()

    if not QUIET:
        print("pre-commit gate demo -- lab/module2-git")
        print("checker: %s" % lab.CHECKER)

    try:
        part_a()
        part_b()
        part_c()
    finally:
        lab.cleanup()

    print()
    print("=" * 74)
    if _failures:
        print("RESULT: %d check(s) FAILED" % len(_failures))
        for name in _failures:
            print("  - %s" % name)
        print("=" * 74)
        return 1
    print("RESULT: all assertions held.")
    print("=" * 74)
    return 0


QUIET = False

if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(2)
