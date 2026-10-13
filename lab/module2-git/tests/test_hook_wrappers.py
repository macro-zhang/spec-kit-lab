# -*- coding: utf-8 -*-
r"""Parity tests for the two hook wrappers: hooks/pre-commit (bash) and
hooks/pre-commit.ps1 (PowerShell).

WHY THIS FILE EXISTS
====================
There are three programs in this module that can stop a commit:

    hooks/pre-commit       bash        thin wrapper
    hooks/pre-commit.ps1   PowerShell  thin wrapper
    scripts/check_tests_touched.py     the only real logic

A wrapper that forgets to forward the exit code is indistinguishable from a
gate that approves everything - and it would be *silent*, which is the worst
failure mode a guard can have. So each wrapper gets the same two cases:

    BLOCK case:  src/ staged, tests/ not staged  -> must exit non-zero
    ALLOW case:  src/ and tests/ staged          -> must exit 0

The ALLOW case is not decoration. A wrapper that always exits non-zero also
"blocks", and testing only the BLOCK case would call that success. (This is not
hypothetical: on the machine this lab was written on, MSYS `sh.exe` cannot
start at all, so *every* bash hook "blocks" - for entirely the wrong reason.)

spec-kit solves the same problem the same way: bash / PowerShell / Python
mirrors of every core script, pinned together by parity tests in
tests/test_check_prerequisites_python_parity.py, with bash as the oracle.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

import gate_lab as lab

BASH_HOOK = lab.MODULE_ROOT / "hooks" / "pre-commit"
PS1_HOOK = lab.MODULE_ROOT / "hooks" / "pre-commit.ps1"

PS_CANDIDATES = ("pwsh", "powershell")


# ---------------------------------------------------------------------------
# capability probes (mirrors spec-kit's tests/conftest.py `requires_bash`)
# ---------------------------------------------------------------------------
def _probe_sh():
    """Can a POSIX shell actually start here?

    Checking that `sh` is on PATH is not enough: on this box it is on PATH and
    dies on startup with `couldn't create signal pipe, Win32 error 5`. A test
    that only checked PATH would fail confusingly instead of skipping with a
    reason.
    """
    exe = shutil.which("sh")
    if not exe:
        return None, "sh is not on PATH"
    try:
        proc = subprocess.run(
            [exe, "-c", "exit 0"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except OSError as exc:
        return None, "sh could not be started: %s" % exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().replace("\n", " ")
        return None, "sh exists but cannot start (exit %d): %s" % (
            proc.returncode,
            detail[:160],
        )
    return exe, ""


def _probe_powershell():
    for name in PS_CANDIDATES:
        exe = shutil.which(name)
        if not exe:
            continue
        try:
            proc = subprocess.run(
                [exe, "-NoProfile", "-Command", "exit 0"],
                capture_output=True,
                timeout=60,
                check=False,
            )
        except OSError:
            continue
        if proc.returncode == 0:
            return exe, ""
    return None, "neither pwsh nor powershell could be run"


SH, SH_REASON = _probe_sh()
PS, PS_REASON = _probe_powershell()

requires_sh = pytest.mark.skipif(SH is None, reason="no usable sh: %s" % SH_REASON)
requires_ps = pytest.mark.skipif(
    PS is None, reason="no usable PowerShell: %s" % PS_REASON
)


@pytest.fixture(autouse=True)
def _cleanup_scratch():
    yield
    lab.cleanup()


# ---------------------------------------------------------------------------
# invocation
# ---------------------------------------------------------------------------
def _run_bash(repo, extra=(), env=None):
    full = {"TESTS_TOUCHED_CHECKER": str(lab.CHECKER)}
    full.update(env or {})
    return lab.run([SH, str(BASH_HOOK), *extra], repo, env=full)


def _run_ps(repo, extra=(), env=None):
    full = {"TESTS_TOUCHED_CHECKER": str(lab.CHECKER)}
    full.update(env or {})
    return lab.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PS1_HOOK),
            *extra,
        ],
        repo,
        env=full,
    )


def _blocked_repo():
    scenario = next(s for s in lab.SCENARIOS if s.id == "src_only_blocked")
    return lab.build(scenario)


def _allowed_repo():
    scenario = next(s for s in lab.SCENARIOS if s.id == "src_and_tests_allowed")
    return lab.build(scenario)


# ---------------------------------------------------------------------------
# the PowerShell wrapper: verifiable on this machine
# ---------------------------------------------------------------------------
@requires_ps
def test_powershell_wrapper_blocks_and_says_why():
    obs = _run_ps(_blocked_repo())

    assert obs.exit_code == 1, "a violation must reach git as a non-zero code"
    assert obs.stdout == "", "stdout is payload-only, and no payload was asked for"
    assert "ERROR:" in obs.stderr
    assert "git add tests/test_app.py" in obs.stderr


@requires_ps
def test_powershell_wrapper_allows_a_compliant_commit():
    """The case that separates 'the gate works' from 'the gate always says no'."""
    obs = _run_ps(_allowed_repo())

    assert obs.exit_code == 0, obs.stderr
    assert obs.stdout == ""
    assert "ERROR" not in obs.stderr


@requires_ps
def test_powershell_wrapper_quiets_the_ok_line_on_request():
    obs = _run_ps(_allowed_repo(), env={"TESTS_TOUCHED_QUIET": "1"})

    assert obs.exit_code == 0
    assert obs.stderr == "", "TESTS_TOUCHED_QUIET=1 must silence the ok line"


@requires_ps
def test_powershell_wrapper_forwards_a_usage_error_as_a_block():
    """Exit 2 is not 'special': anything non-zero stops the commit."""
    obs = _run_ps(_blocked_repo(), extra=["--bogus"])

    assert obs.exit_code == 2
    assert "ERROR:" in obs.stderr


@requires_ps
def test_powershell_wrapper_fails_closed_when_the_checker_is_missing():
    """A hook that cannot find its own logic must not wave the commit through."""
    obs = _run_ps(
        _blocked_repo(),
        env={"TESTS_TOUCHED_CHECKER": str(lab.SCRATCH / "does-not-exist.py")},
    )

    assert obs.exit_code == 1
    assert "ERROR:" in obs.stderr
    assert "check_tests_touched.py" in obs.stderr


@requires_ps
def test_powershell_wrapper_passes_the_json_payload_through_on_stdout():
    obs = _run_ps(_blocked_repo(), extra=["--json"])

    assert obs.exit_code == 1
    payload = obs.payload
    assert payload is not None, obs.stdout
    assert payload["violation"] is True
    assert payload["reason"] == "source changed without a staged test change"


# ---------------------------------------------------------------------------
# the bash wrapper
# ---------------------------------------------------------------------------
@requires_sh
def test_bash_wrapper_blocks_and_says_why():
    obs = _run_bash(_blocked_repo())

    assert obs.exit_code == 1
    assert obs.stdout == ""
    assert "ERROR:" in obs.stderr


@requires_sh
def test_bash_wrapper_allows_a_compliant_commit():
    obs = _run_bash(_allowed_repo())

    assert obs.exit_code == 0, obs.stderr


# ---------------------------------------------------------------------------
# parity: the two wrappers must agree, case by case
# ---------------------------------------------------------------------------
@requires_sh
@requires_ps
@pytest.mark.parametrize(
    "case, args",
    [
        ("blocked", ()),
        ("allowed", ()),
        ("usage", ("--bogus",)),
    ],
)
def test_wrappers_agree_on_the_exit_code(case, args):
    """Bash is the oracle; PowerShell must not drift from it.

    Both wrappers call the same Python checker, so they cannot disagree about
    the *rule* - only about forwarding. Which is exactly the thing worth
    pinning, because forwarding is the part each shell re-implements.
    """
    if case == "allowed":
        repo = _allowed_repo()
    else:
        repo = _blocked_repo()

    bash_obs = _run_bash(repo, extra=list(args))
    ps_obs = _run_ps(repo, extra=list(args))

    assert bash_obs.exit_code == ps_obs.exit_code, (
        "bash exited %d, PowerShell exited %d\nbash stderr:\n%s\nps stderr:\n%s"
        % (bash_obs.exit_code, ps_obs.exit_code, bash_obs.stderr, ps_obs.stderr)
    )


def test_the_capability_probes_report_their_reason():
    """Make the environment's limits visible instead of silently skipping.

    On the machine this lab was written on the bash half of the suite skips,
    and the reason string is the finding: MSYS binaries cannot start in this
    sandbox. Printing it keeps a skipped test from reading as 'all good'.
    """
    if SH is None:
        print("\nbash wrapper tests SKIPPED: %s" % SH_REASON)
    else:
        print("\nbash wrapper tests running with %s" % SH)
    if PS is None:
        print("PowerShell wrapper tests SKIPPED: %s" % PS_REASON)
    else:
        print("PowerShell wrapper tests running with %s" % PS)
