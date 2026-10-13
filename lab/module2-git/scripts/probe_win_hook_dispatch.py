# -*- coding: utf-8 -*-
r"""probe_win_hook_dispatch.py - measure how git dispatches hooks on Windows.

WHY THIS SCRIPT EXISTS
======================
The question "does my pre-commit gate actually stop a commit?" is usually
answered by installing a hook and watching a commit fail. That answer is worth
nothing on its own, because the commit can fail for reasons that have nothing
to do with the gate - see PART C of scripts/demo_gate.py, where an MSYS `sh`
that cannot start blocks *every* commit, including one whose hook exits 0.

So this script measures git's *dispatch* instead, using a hook that contains no
logic at all: a compiled executable that logs the fact that it ran, logs its
arguments, and exits with a code taken from the environment.

It answers five questions by experiment rather than by quoting the manual:

  1. Which hook filenames does git actually execute on Windows?
  2. In what order do pre-commit / prepare-commit-msg / commit-msg / post-commit
     run for a plain commit?
  3. What does `git commit --no-verify` really skip?
  4. When a hook exits non-zero, what exit code does `git commit` itself report?
  5. Does a message-rewriting hook receive a real, existing file?

Everything runs in throwaway repositories under module2-git/_scratch.

USAGE
    ..\.venv\Scripts\python.exe scripts\probe_win_hook_dispatch.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_ROOT = HERE.parent

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gate_lab as lab  # noqa: E402  (path set up above on purpose)

PROBE_SRC = MODULE_ROOT / "tools" / "hookprobe" / "HookProbe.cs"
PROBE_BUILD = MODULE_ROOT / "tools" / "hookprobe" / "build_hookprobe.ps1"
PROBE_EXE = MODULE_ROOT / "tools" / "hookprobe" / "hookprobe.exe"

#: The four client-side hooks a `git commit` can trigger, in git's order.
ALL_HOOKS = ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit")

_failures = []


def _force_utf8() -> None:
    """Make the console survive box-drawing / check characters.

    Same reason spec-kit reconfigures stdio on win32
    (src/specify_cli/__init__.py:502-517): the default console code page on
    this box is GBK, and printing a character outside it raises
    UnicodeEncodeError *after* the work is done, which loses the result.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def banner(title: str) -> None:
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


def check(label: str, ok: bool, detail: str = "") -> None:
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", label,
                           "" if ok else "  -- " + detail))
    if not ok:
        _failures.append(label)


# ---------------------------------------------------------------------------
# building the probe
# ---------------------------------------------------------------------------
def find_powershell():
    for name in ("pwsh", "powershell"):
        exe = shutil.which(name)
        if exe:
            return exe
    return None


def ensure_probe() -> bool:
    if PROBE_EXE.exists():
        return True
    shell = find_powershell()
    if shell is None:
        print("no PowerShell found; cannot build the probe")
        return False

    print("compiling %s ..." % PROBE_SRC.name)
    proc = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PROBE_BUILD)],
        capture_output=True,
        check=False,
    )
    out = proc.stdout.decode("utf-8", "replace").strip()
    err = proc.stderr.decode("utf-8", "replace").strip()
    if out:
        print("  " + out)
    if proc.returncode != 0 or not PROBE_EXE.exists():
        print("  compile failed (exit %d): %s" % (proc.returncode, err[:400]))
        return False
    return True


# ---------------------------------------------------------------------------
# running one scenario
# ---------------------------------------------------------------------------
class Run:
    def __init__(self, repo, commit_exit, hooks_ran, commit_created, log_lines, stderr=""):
        self.repo = repo
        self.commit_exit = commit_exit
        self.hooks_ran = hooks_ran
        self.commit_created = commit_created
        self.log_lines = log_lines
        self.stderr = stderr


def scenario(
    name: str,
    *,
    exe_hooks=(),
    noext_hooks=(),
    extra_files=(),
    exit_codes=None,
    commit_args=("-m", "probe"),
    stage=True,
):
    """Build a repo, install hooks, attempt one commit, report what ran."""
    repo = lab.make_repo("probe_" + name)
    if stage:
        lab.git(repo, "add", "-A")

    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # The measured rule on Windows: install the program at `<hooks-dir>/<name>.exe`
    # and nothing else. git resolves the hook name by appending `.exe`, spawns
    # that, and runs it.
    for hook in exe_hooks:
        shutil.copy2(PROBE_EXE, hooks_dir / (hook + ".exe"))

    # The deliberately-wrong layout, kept as an experiment of its own: an
    # extensionless PE file. git *finds* it (so it is no longer "no hook") but
    # then cannot spawn it, because CreateProcess only ever runs `<name>.exe`.
    for hook in noext_hooks:
        shutil.copy2(PROBE_EXE, hooks_dir / hook)

    for filename, content in extra_files:
        (hooks_dir / filename).write_text(content, encoding="utf-8")

    log = repo / "probe.log"

    env = {"PROBE_LOG": str(log)}
    for hook, code in (exit_codes or {}).items():
        env["PROBE_EXIT_" + hook.replace("-", "_").upper()] = str(code)

    # Through lab.run rather than lab.git: the probe reads its instructions from
    # the environment, so this is the one place that needs a custom env.
    obs = lab.run(["git", "commit", *commit_args], repo, env=env)

    hooks_ran = []
    log_lines = []
    if log.exists():
        log_lines = log.read_text(encoding="utf-8").splitlines()
        hooks_ran = [line.split("|")[0] for line in log_lines]

    created = (
        lab.git(repo, "rev-parse", "--verify", "--quiet", "HEAD", check=False).exit_code
        == 0
    )
    return Run(repo, obs.exit_code, hooks_ran, created, log_lines, obs.stderr)


# ---------------------------------------------------------------------------
def part_a_filename_rules() -> None:
    banner("PART A  which hook FILENAMES does git execute on Windows?")

    plain = scenario("a_none")
    check("no hook installed -> commit succeeds", plain.commit_exit == 0 and plain.commit_created,
          "exit=%d created=%s" % (plain.commit_exit, plain.commit_created))
    check("no hook installed -> nothing ran", plain.hooks_ran == [],
          repr(plain.hooks_ran))

    exe = scenario("a_exe", exe_hooks=("pre-commit",))
    check("a native executable installed as `pre-commit.exe` IS executed "
          "(and that alone is enough)",
          exe.hooks_ran == ["pre-commit"], repr(exe.hooks_ran))
    check("pre-commit exiting 0 -> commit succeeds",
          exe.commit_created and exe.commit_exit == 0,
          "exit=%d created=%s" % (exe.commit_exit, exe.commit_created))

    noext = scenario("a_noext", noext_hooks=("pre-commit",))
    print("  extensionless PE hook -> git said: %r" % (noext.stderr.strip()[:160],))
    check("an extensionless hook file is found but cannot be spawned",
          not noext.commit_created and noext.hooks_ran == [],
          "exit=%d created=%s ran=%s" % (noext.commit_exit, noext.commit_created, noext.hooks_ran))

    bat = scenario(
        "a_bat",
        extra_files=[("pre-commit.bat", "@echo off\r\nexit /b 1\r\n")],
    )
    check("pre-commit.bat is IGNORED (commit succeeds, nothing ran)",
          bat.commit_created and bat.hooks_ran == [],
          "exit=%d created=%s ran=%s" % (bat.commit_exit, bat.commit_created, bat.hooks_ran))

    ps1 = scenario(
        "a_ps1",
        extra_files=[("pre-commit.ps1", "exit 1\n")],
    )
    check("pre-commit.ps1 is IGNORED (commit succeeds, nothing ran)",
          ps1.commit_created and ps1.hooks_ran == [],
          "exit=%d created=%s ran=%s" % (ps1.commit_exit, ps1.commit_created, ps1.hooks_ran))

    print()
    print("  the measured rule on Windows:")
    print("    * the program must be at `<hooks-dir>/<name>.exe`; that alone is")
    print("      enough, because git resolves the hook name with `.exe`.")
    print("    * an extensionless file is treated as a hook (git finds it) but")
    print("      cannot be spawned - CreateProcess only ever runs `.exe` - so the")
    print("      commit aborts with `error: cannot spawn ...`.")
    print("    * `.bat` and `.ps1` hook files are ignored outright.")
    print("    * a `#!`-script hook is handed to `sh`, which needs a working")
    print("      MSYS shell - the one thing this machine does not have.")


def part_b_order() -> None:
    banner("PART B  order of the four client-side hooks for a plain commit")

    plain = scenario("b_order", exe_hooks=ALL_HOOKS)
    print("  hooks that ran: %s" % (" -> ".join(plain.hooks_ran) or "(none)"))
    check("all four hooks ran", plain.hooks_ran == list(ALL_HOOKS),
          repr(plain.hooks_ran))
    check("a plain commit is created when every hook exits 0", plain.commit_created)

    for line in plain.log_lines:
        print("    " + line)

    arg_info = {}
    for line in plain.log_lines:
        parts = line.split("|")
        if len(parts) >= 4:
            arg_info[parts[0]] = (parts[1], parts[2])
    check("prepare-commit-msg receives an existing file as $1",
          arg_info.get("prepare-commit-msg", ("", ""))[1] == "file",
          repr(arg_info.get("prepare-commit-msg")))
    check("commit-msg receives an existing file as $1",
          arg_info.get("commit-msg", ("", ""))[1] == "file",
          repr(arg_info.get("commit-msg")))


def part_c_no_verify() -> None:
    banner("PART C  what does `git commit --no-verify` actually skip?")

    bypass = scenario("c_no_verify", exe_hooks=ALL_HOOKS,
                      commit_args=("--no-verify", "-m", "probe"))
    print("  hooks that ran: %s" % " -> ".join(bypass.hooks_ran))
    check("--no-verify skips pre-commit", "pre-commit" not in bypass.hooks_ran,
          repr(bypass.hooks_ran))
    check("--no-verify skips commit-msg", "commit-msg" not in bypass.hooks_ran,
          repr(bypass.hooks_ran))
    check("--no-verify does NOT skip prepare-commit-msg",
          "prepare-commit-msg" in bypass.hooks_ran, repr(bypass.hooks_ran))
    check("--no-verify does NOT skip post-commit",
          "post-commit" in bypass.hooks_ran, repr(bypass.hooks_ran))
    check("--no-verify still creates the commit", bypass.commit_created)

    print()
    print("  consequence: `--no-verify` is documented as bypassing pre-commit")
    print("               and commit-msg. A guard installed as")
    print("               prepare-commit-msg survives the bypass - and can still")
    print("               block by exiting non-zero. That is a real design")
    print("               choice, not a loophole in someone else's code.")


def part_d_failure() -> None:
    banner("PART D  what does a non-zero hook do to `git commit`?")

    pre = scenario("d_pre_fail", exe_hooks=ALL_HOOKS,
                   exit_codes={"pre-commit": 7})
    print("  pre-commit exits 7 -> hooks that ran: %s" % (pre.hooks_ran,))
    print("  git commit exit code: %d" % pre.commit_exit)
    check("a failing pre-commit aborts the commit", not pre.commit_created)
    check("no later hook runs after pre-commit fails",
          pre.hooks_ran == ["pre-commit"], repr(pre.hooks_ran))
    check("git reports its own failure code, not the hook's 7",
          pre.commit_exit == 1,
          "git exit was %d" % pre.commit_exit)

    msg = scenario("d_msg_fail", exe_hooks=ALL_HOOKS,
                   exit_codes={"commit-msg": 7})
    print("  commit-msg exits 7 -> hooks that ran: %s" % (msg.hooks_ran,))
    check("a failing commit-msg aborts the commit", not msg.commit_created)
    check("post-commit does not run when the commit was aborted",
          "post-commit" not in msg.hooks_ran, repr(msg.hooks_ran))

    print()
    print("  consequence for gate design: git collapses every hook failure to")
    print("  exit code 1. The hook's own exit code is therefore useful to the")
    print("  hook, and useless to git. If a caller must distinguish 'policy")
    print("  violation' from 'the checker crashed', that distinction has to be")
    print("  carried in the output, not in the exit code.")


def part_e_summary() -> None:
    banner("PART E  summary table")

    rows = [
        ("no hooks", (), (), (), (), True),
        ("pre-commit.exe exit 0", ("pre-commit",), (), {}, (), True),
        ("pre-commit.exe exit 7", ("pre-commit",), (), {"pre-commit": 7}, (), False),
        ("pre-commit.bat exit 1", (), (("pre-commit.bat", "@echo off\r\nexit /b 1\r\n"),), (), (), True),
        ("pre-commit.ps1 exit 1", (), (("pre-commit.ps1", "exit 1\n"),), (), (), True),
        ("all four, exit 0", ALL_HOOKS, (), {}, (), True),
        ("all four, --no-verify", ALL_HOOKS, (), {}, ("--no-verify", "-m", "probe"), True),
        ("commit-msg exit 7", ALL_HOOKS, (), {"commit-msg": 7}, (), False),
    ]

    print("  %-26s %-8s %-7s %s" % ("scenario", "commit", "git exit", "hooks that ran"))
    print("  " + "-" * 70)
    for label, exe_hooks, extra, codes, commit_args, expect_created in rows:
        run = scenario(
            "e_" + label.replace(" ", "_").replace(".", "_").replace(",", ""),
            exe_hooks=exe_hooks,
            extra_files=extra,
            exit_codes=codes,
            commit_args=commit_args or ("-m", "probe"),
        )
        print("  %-26s %-8s %-7d %s" % (
            label,
            "created" if run.commit_created else "ABORTED",
            run.commit_exit,
            " -> ".join(run.hooks_ran) or "(none)",
        ))
        check("%s -> commit%s" % (label, " created" if expect_created else " aborted"),
              run.commit_created == expect_created,
              "exit=%d ran=%s" % (run.commit_exit, run.hooks_ran))


def main() -> int:
    _force_utf8()
    banner("git hook dispatch probe (Windows)")

    if not ensure_probe():
        print("RESULT: cannot run - the probe could not be built.")
        return 1

    try:
        part_a_filename_rules()
        part_b_order()
        part_c_no_verify()
        part_d_failure()
        part_e_summary()
    finally:
        lab.cleanup()

    banner("RESULT")
    if _failures:
        print("  %d assertion(s) failed:" % len(_failures))
        for label in _failures:
            print("    - " + label)
        return 1
    print("  all assertions held: measured on git %s" % git_version())
    return 0


def git_version() -> str:
    proc = subprocess.run(["git", "--version"], capture_output=True, check=False)
    return proc.stdout.decode("utf-8", "replace").strip() or "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
