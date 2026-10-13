# -*- coding: utf-8 -*-
"""gate_lab.py - shared scaffolding for exercising check_tests_touched.py.

This module exists so that the narrative demo (scripts/demo_gate.py) and the
CI test suite (tests/test_check_tests_touched.py) drive the checker through
*exactly the same* scenarios. Two consumers, one table - the same
"one implementation" principle the checker itself is built on.

WHAT A SCENARIO IS
==================
A scenario is a description of a real git repository state plus the arguments
to hand the checker:

    id             stable name, also used as the pytest parameter id
    title          one line a human can read in a demo transcript
    setup(repo)    makes the repository state (write / stage / commit)
    args           extra argv for the checker
    expect_exit    0 / 1 / 2 - the whole point of the exercise
    expect_reason  the checker's own `reason` string, so that a wrong *reason*
                   is caught too and not just a wrong exit code

Everything runs in a throwaway repository under a scratch directory; nothing
here touches the lab's own working tree.

WHY THE CHECKER IS INVOKED AS A SUBPROCESS
==========================================
Not because importing it would be hard, but because the contract under test
is "what this program leaves in the environment": an exit code on the
process, a payload on stdout, diagnostics on stderr. Importing main() and
reading its return value would not test the thing that gates a commit.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable, NamedTuple, Optional

HERE = Path(__file__).resolve().parent
MODULE_ROOT = HERE.parent
CHECKER = HERE / "check_tests_touched.py"

#: Scratch repositories live here and are removed by cleanup().
SCRATCH = MODULE_ROOT / "_scratch"

# git prints this warning on this box because the sandbox denies access to a
# global ignore file. It is noise, and left in place it would pollute every
# stderr assertion, so it is filtered out of captured stderr.
_NOISE = ("unable to access", ".config/git/ignore")


class Result(NamedTuple):
    exit_code: int
    stdout: str
    stderr: str

    @property
    def payload(self) -> Optional[dict]:
        """stdout parsed as the JSON document --json promises, or None."""
        try:
            parsed = json.loads(self.stdout)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None


# ---------------------------------------------------------------------------
# process helpers
# ---------------------------------------------------------------------------
def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def _denoise(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not any(n in line for n in _NOISE)
    )


def _capture(cmd, cwd, env=None) -> Result:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=full_env,
    )
    return Result(proc.returncode, _decode(proc.stdout), _denoise(_decode(proc.stderr)))


def git(repo, *args, check=True) -> Result:
    """Run git in `repo` and capture its output."""
    res = _capture(["git", *args], repo)
    if check and res.exit_code != 0:
        raise RuntimeError(
            "git %s failed (%d) in %s\nstdout:\n%s\nstderr:\n%s"
            % (" ".join(args), res.exit_code, repo, res.stdout, res.stderr)
        )
    return res


def run_checker(repo, args=(), env=None) -> Result:
    """Invoke the checker with cwd=repo, exactly as a git hook would."""
    return _capture([sys.executable, str(CHECKER), *args], repo, env)


def run(cmd, cwd, env=None) -> Result:
    """Run an arbitrary command and capture its three channels.

    Exposed for the hook-wrapper tests: a hook is observed the same way the
    checker is - by what the process leaves behind, not by what it returns to
    a caller that imported it.
    """
    return _capture(list(cmd), cwd, env)


# ---------------------------------------------------------------------------
# repository scaffolding
# ---------------------------------------------------------------------------
def write(repo, relpath: str, text: str = "x = 1\n") -> Path:
    path = Path(repo) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_repo(name: str, *, baseline: bool = False) -> Path:
    """Create a fresh single-purpose git repository under SCRATCH.

    Committing here never meets a hook: these repositories have no hooks
    installed, which is also why `baseline` can commit at all.
    """
    repo = SCRATCH / name
    _rmtree(repo)
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "gate-lab")
    git(repo, "config", "user.email", "gate-lab@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")

    write(repo, "src/app.py")
    write(repo, "tests/test_app.py")

    if baseline:
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "baseline")
    return repo


def _force_writable(func, path, exc_info) -> None:
    """rmtree error handler: clear the read-only bit and retry once.

    Git marks everything under .git/objects as read-only, and Windows cannot
    delete a read-only file, so a plain rmtree leaves the scratch repository
    behind. That leftover then makes the *next* run fail with FileExistsError -
    a classic case of the cleanup being the flakiest part of a test harness.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _rmtree(path) -> None:
    if Path(path).exists():
        shutil.rmtree(path, onerror=_force_writable)


def cleanup() -> None:
    _rmtree(SCRATCH)


# ---------------------------------------------------------------------------
# setup functions (one per repository state we care about)
# ---------------------------------------------------------------------------
def _stage_src(repo):
    git(repo, "add", "src/app.py")


def _stage_src_and_tests(repo):
    git(repo, "add", "src/app.py", "tests/test_app.py")


def _stage_tests_only(repo):
    git(repo, "add", "tests/test_app.py")


def _stage_nothing(repo):
    return None


def _untracked_source(repo):
    # Written but never `git add`-ed. An untracked file cannot appear in a
    # diff, so the guard must not see it. This is a documented limit, not a
    # bug: enforce it with a CI run over the branch instead.
    write(repo, "src/never_staged.py")


def _stage_non_ascii_src(repo):
    write(repo, "src/\u4e2d\u6587\u6a21\u5757.py")
    git(repo, "add", "src/\u4e2d\u6587\u6a21\u5757.py")


def _stage_srcish_dir(repo):
    # "src2/" must NOT be treated as living under "src/".
    write(repo, "src2/app.py")
    git(repo, "add", "src2/app.py")


def _modify_tracked_in_worktree(repo):
    write(repo, "src/app.py", "x = 2\n")   # unstaged modification of a tracked file


def _stage_custom_layout(repo):
    write(repo, "packages/api/handler.py")
    git(repo, "add", "packages/api/handler.py")


def _stage_custom_layout_and_tests(repo):
    write(repo, "packages/api/handler.py")
    write(repo, "test/test_handler.py")
    git(repo, "add", "packages/api/handler.py", "test/test_handler.py")


# ---------------------------------------------------------------------------
# the scenario table
# ---------------------------------------------------------------------------
class Scenario(NamedTuple):
    id: str
    title: str
    setup: Callable[[Path], object]
    args: tuple
    expect_exit: int
    expect_reason: str = ""
    outside_repo: bool = False
    baseline: bool = False


SCENARIOS = (
    # --- the rule itself ---------------------------------------------------
    Scenario(
        "src_only_blocked",
        "src/ staged, no test staged -> BLOCK",
        _stage_src, (), 1, "source changed without a staged test change",
    ),
    Scenario(
        "src_and_tests_allowed",
        "src/ + tests/ staged -> ALLOW",
        _stage_src_and_tests, (), 0, "source and tests both touched",
    ),
    Scenario(
        "tests_only_allowed",
        "only tests/ staged -> ALLOW (no source change to guard)",
        _stage_tests_only, (), 0, "no source files touched",
    ),
    Scenario(
        "nothing_staged_allowed",
        "clean index -> ALLOW (nothing to gate)",
        _stage_nothing, (), 0, "nothing staged",
    ),
    Scenario(
        "all_mode_clean_allowed",
        "--all with no changes vs HEAD -> ALLOW",
        _stage_nothing, ("--all",), 0, "no trackable changes vs HEAD",
        baseline=True,
    ),
    Scenario(
        "all_mode_sees_worktree",
        "--all sees an unstaged edit (staged mode would not) -> BLOCK",
        _modify_tracked_in_worktree, ("--all",), 1,
        "source changed without a staged test change",
        baseline=True,
    ),
    # --- path handling -----------------------------------------------------
    Scenario(
        "non_ascii_src_blocked",
        "non-ASCII path under src/ -> BLOCK (this is why -z is used)",
        _stage_non_ascii_src, (), 1, "source changed without a staged test change",
    ),
    Scenario(
        "srcish_dir_ignored",
        "src2/ is not src/ -> ALLOW",
        _stage_srcish_dir, (), 0, "no source files touched",
    ),
    Scenario(
        "srcish_dir_without_slash_prefix",
        "--src-prefix src must not swallow src2/ -> ALLOW",
        _stage_srcish_dir, ("--src-prefix", "src"), 0, "no source files touched",
    ),
    Scenario(
        "backslash_prefix_normalised",
        "--src-prefix src\\\\ is normalised to src/ -> ALLOW",
        _stage_src_and_tests, ("--src-prefix", "src\\"), 0,
        "source and tests both touched",
    ),
    Scenario(
        "untracked_source_invisible",
        "untracked file under src/ -> ALLOW (a diff cannot see it; documented limit)",
        _untracked_source, (), 0, "nothing staged",
    ),
    # --- project layouts other than src/ + tests/ --------------------------
    Scenario(
        "custom_layout_blocked",
        "packages/api/ staged, custom prefixes, no test -> BLOCK",
        _stage_custom_layout,
        ("--src-prefix", "packages/api/", "--tests-prefix", "test/"),
        1, "source changed without a staged test change",
    ),
    Scenario(
        "custom_layout_allowed",
        "packages/api/ + test/ staged, custom prefixes -> ALLOW",
        _stage_custom_layout_and_tests,
        ("--src-prefix", "packages/api/", "--tests-prefix", "test/"),
        0, "source and tests both touched",
    ),
    # --- unborn HEAD (fresh `git init`) ------------------------------------
    Scenario(
        "unborn_head_all_mode",
        "first commit ever: --all falls back to the empty tree -> BLOCK",
        _stage_src, ("--all",), 1,
        "source changed without a staged test change",
    ),
    # --- payload and usage -------------------------------------------------
    Scenario(
        "json_payload_exit_code",
        "--json on a violation prints a payload AND still exits 1",
        _stage_src, ("--json",), 1, "source changed without a staged test change",
    ),
    Scenario(
        "help_is_success",
        "--help prints usage to stdout and exits 0",
        _stage_src, ("--help",), 0,
    ),
    Scenario(
        "empty_prefix_usage",
        "--src-prefix '' -> USAGE (an empty prefix matches everything)",
        _stage_src, ("--src-prefix", ""), 2,
    ),
    Scenario(
        "unknown_option_usage",
        "--bogus -> USAGE",
        _stage_src, ("--bogus",), 2,
    ),
    Scenario(
        "missing_value_usage",
        "--src-prefix with no value -> USAGE",
        _stage_src, ("--src-prefix",), 2,
    ),
    Scenario(
        "positional_usage",
        "a stray positional argument -> USAGE",
        _stage_src, ("oops",), 2,
    ),
    Scenario(
        "outside_repo_usage",
        "not inside a git work tree -> USAGE",
        _stage_nothing, (), 2, "", True,
    ),
)


def build(scenario: Scenario) -> Path:
    """Materialise a scenario's repository and return its path."""
    repo = make_repo(scenario.id, baseline=scenario.baseline)
    scenario.setup(repo)
    return repo


class Observation(NamedTuple):
    exit_code: int
    reason: Optional[str]
    stdout: str
    stderr: str
    repo: Optional[Path]


def observe(scenario: Scenario) -> Observation:
    """Run one scenario and report what the checker actually did.

    `--json` is added whenever a reason is expected, because the reason string
    only exists in the machine payload; adding it keeps the reason assertion
    independent of how the prose report happens to be worded.
    """
    if scenario.outside_repo:
        # `outside` sits below the scratch root, which we declare a ceiling so
        # upward discovery cannot escape into the lab's own repository.
        outside = SCRATCH / "outside"
        outside.mkdir(parents=True, exist_ok=True)
        res = run_checker(
            outside, scenario.args, env={"GIT_CEILING_DIRECTORIES": str(SCRATCH)}
        )
        return Observation(res.exit_code, None, res.stdout, res.stderr, outside)

    args = list(scenario.args)
    if scenario.expect_reason and "--json" not in args:
        args.append("--json")

    repo = build(scenario)
    res = run_checker(repo, args)
    payload = res.payload
    reason = payload.get("reason") if payload else None
    return Observation(res.exit_code, reason, res.stdout, res.stderr, repo)


def matches(scenario: Scenario, obs: Observation):
    """Return a list of human-readable mismatches (empty == passed)."""
    problems = []
    if obs.exit_code != scenario.expect_exit:
        problems.append(
            "exit code %s, expected %s" % (obs.exit_code, scenario.expect_exit)
        )
    if scenario.expect_reason and obs.reason != scenario.expect_reason:
        problems.append(
            "reason %r, expected %r" % (obs.reason, scenario.expect_reason)
        )
    return problems
