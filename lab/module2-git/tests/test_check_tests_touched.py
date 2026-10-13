# -*- coding: utf-8 -*-
"""Tests for scripts/check_tests_touched.py - the pre-commit gate's one brain.

Why this file exists
====================
The gate is the thing that decides whether a commit is allowed to exist. If
the gate itself is wrong, every downstream guarantee is worthless, and a
broken gate is invisible precisely when it fails OPEN. So the gate gets the
same treatment as the code it guards: a table of positive and negative cases
with the expected exit code written down.

Two layers:

  * SCENARIO tests (from scripts/gate_lab.py) build real git repositories and
    run the checker as a subprocess, asserting the exit code AND the reason
    string. These are the ones that would catch a real regression.
  * UNIT tests cover the pure helpers (argument normalisation, prefix
    matching, path summarising) where a subprocess round trip is overkill.

The exit-code contract under test:
    0 allow | 1 block | 2 usage/environment error
"""

from __future__ import annotations

import json

import pytest

import gate_lab as lab

# ---------------------------------------------------------------------------
# scenario layer
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("scenario", lab.SCENARIOS, ids=lambda s: s.id)
def test_scenario(scenario):
    """Every scenario must produce its documented exit code and reason."""
    try:
        obs = lab.observe(scenario)
    finally:
        lab.cleanup()
    problems = lab.matches(scenario, obs)
    assert not problems, "%s: %s\nrepo: %s\nstdout:\n%s\nstderr:\n%s" % (
        scenario.title,
        "; ".join(problems),
        obs.repo,
        obs.stdout,
        obs.stderr,
    )


@pytest.fixture(autouse=True)
def _cleanup_scratch():
    yield
    lab.cleanup()


# ---------------------------------------------------------------------------
# stream discipline
# ---------------------------------------------------------------------------
def test_violation_without_json_keeps_stdout_empty_and_writes_errors_to_stderr():
    """Without --json, stdout must stay empty so a consumer never mis-parses.

    Note that `lab.observe()` would add --json here (the scenario records an
    expected reason), so this test drives the checker directly: the point is
    what the *default* invocation leaves on each stream.
    """
    scenario = next(s for s in lab.SCENARIOS if s.id == "src_only_blocked")
    obs = lab.run_checker(lab.build(scenario))

    assert obs.exit_code == 1
    assert obs.stdout == "", "payload promised on stdout must not be prose"
    assert obs.stderr.lstrip().startswith("ERROR:"), obs.stderr
    assert "git add tests/test_app.py" in obs.stderr, "the fix must be spelled out"
    assert "git commit --no-verify" in obs.stderr, "the escape hatch must be named"


def test_violation_with_json_emits_payload_and_still_reports_on_stderr():
    """--json adds a payload; it does not silence the human-readable report.

    A hook that is being debugged must still see *why* it was blocked even if
    the calling script only reads stdout.
    """
    scenario = next(s for s in lab.SCENARIOS if s.id == "src_only_blocked")
    obs = lab.run_checker(lab.build(scenario), ["--json"])

    assert obs.exit_code == 1
    assert obs.payload is not None, obs.stdout
    assert "ERROR:" in obs.stderr


def test_success_is_silent_on_both_streams():
    scenario = next(s for s in lab.SCENARIOS if s.id == "src_and_tests_allowed")
    obs = lab.run_checker(lab.build(scenario))

    assert obs.exit_code == 0
    assert obs.stdout == ""
    assert obs.stderr == ""


def test_help_goes_to_stdout_not_stderr():
    scenario = next(s for s in lab.SCENARIOS if s.id == "help_is_success")
    obs = lab.observe(scenario)

    assert obs.exit_code == 0
    assert "usage:" in obs.stdout
    assert obs.stderr == ""


def test_usage_error_never_touches_stdout():
    scenario = next(s for s in lab.SCENARIOS if s.id == "unknown_option_usage")
    obs = lab.observe(scenario)

    assert obs.exit_code == 2
    assert obs.stdout == ""
    assert "ERROR:" in obs.stderr


# ---------------------------------------------------------------------------
# the --json payload
# ---------------------------------------------------------------------------
EXPECTED_KEYS = {
    "tool", "mode", "base", "repo_root", "src_prefix", "tests_prefix",
    "changed", "changed_count", "src_files", "src_count",
    "tests_files", "tests_count", "violation", "reason", "exit_code",
}


def test_json_payload_shape_and_self_consistency():
    scenario = next(s for s in lab.SCENARIOS if s.id == "src_only_blocked")
    obs = lab.observe(scenario)
    payload = json.loads(obs.stdout)

    assert EXPECTED_KEYS <= set(payload)
    assert payload["tool"] == "check_tests_touched"
    assert payload["mode"] == "staged"
    assert payload["violation"] is True
    assert payload["exit_code"] == obs.exit_code == 1
    assert payload["src_files"] == ["src/app.py"]
    assert payload["tests_files"] == []
    assert payload["changed_count"] == len(payload["changed"])


def test_json_payload_is_pure_ascii_even_for_non_ascii_paths():
    """The payload must survive a GBK console and a CI log unchanged."""
    scenario = next(s for s in lab.SCENARIOS if s.id == "non_ascii_src_blocked")
    obs = lab.observe(scenario)

    assert obs.stdout.isascii(), obs.stdout
    payload = json.loads(obs.stdout)
    assert payload["src_files"] == ["src/\u4e2d\u6587\u6a21\u5757.py"]


def test_all_mode_reports_the_comparison_base():
    scenario = next(s for s in lab.SCENARIOS if s.id == "all_mode_sees_worktree")
    obs = lab.observe(scenario)
    payload = json.loads(obs.stdout)

    assert payload["mode"] == "all"
    assert payload["base"] == "work tree + index vs HEAD"


def test_unborn_head_all_mode_names_the_empty_tree_fallback():
    scenario = next(s for s in lab.SCENARIOS if s.id == "unborn_head_all_mode")
    obs = lab.observe(scenario)
    payload = json.loads(obs.stdout)

    assert payload["base"] == "index vs empty tree (HEAD is unborn)"
    assert payload["exit_code"] == 1


# ---------------------------------------------------------------------------
# why -z: the C-quoting hazard
# ---------------------------------------------------------------------------
def test_plain_name_only_output_is_c_quoted_for_non_ascii_paths():
    """Documents the hazard the checker's `-z` exists to avoid.

    If this test ever fails (git changed its quoting rules), the `-z` design
    still holds - but the *reason* stated in the code comments would need
    revisiting, so the failure is informative rather than noise.
    """
    scenario = next(s for s in lab.SCENARIOS if s.id == "non_ascii_src_blocked")
    repo = lab.build(scenario)

    plain = lab.git(repo, "diff", "--cached", "--name-only").stdout
    raw = lab.git(repo, "diff", "--cached", "--name-only", "-z").stdout

    assert plain.splitlines()[0].startswith('"'), plain
    assert not plain.splitlines()[0].startswith("src/"), plain
    assert raw.split("\0")[0] == "src/\u4e2d\u6587\u6a21\u5757.py"
    # The whole point: naive `startswith("src/")` on `plain` would fail open.
    assert not plain.splitlines()[0].startswith("src/")


# ---------------------------------------------------------------------------
# documented limits
# ---------------------------------------------------------------------------
def test_untracked_files_are_invisible_to_both_modes():
    """A known limit, pinned so nobody mistakes it for a supported feature.

    A guard that silently ignores untracked files is a guard with a hole; the
    hole is documented (README) and the mitigation is a CI run over the whole
    branch, not a cleverer diff.
    """
    scenario = next(s for s in lab.SCENARIOS if s.id == "untracked_source_invisible")
    assert lab.observe(scenario).exit_code == 0

    # Same repository, --all mode: still invisible, because a diff against HEAD
    # compares tracked content only.
    repo = lab.build(scenario)
    res = lab.run_checker(repo, ["--all", "--json"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["src_count"] == 0


# ---------------------------------------------------------------------------
# unit layer: the pure helpers
# ---------------------------------------------------------------------------
def test_prefix_matching_is_exact_on_directory_boundaries():
    paths = ["src/app.py", "src2/app.py", "srcs/app.py", "other/src/app.py"]
    matched = [p for p in paths if p.startswith("src/")]
    assert matched == ["src/app.py"]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("src", "src/"),
        ("src/", "src/"),
        ("src\\", "src/"),
        ("./src", "src/"),
        ("/src/", "src/"),
        ("packages/api", "packages/api/"),
    ],
)
def test_prefix_normalisation(checker, raw, expected):
    opts = checker.parse_args(["--src-prefix", raw])
    assert opts["src_prefix"] == expected


@pytest.mark.parametrize("raw", ["", "   ", "/", "./"])
def test_empty_prefix_is_a_usage_error(checker, raw):
    """An empty prefix matches everything, which turns the gate into noise."""
    with pytest.raises(checker.UsageError):
        checker.parse_args(["--src-prefix", raw])


def test_default_prefixes_are_src_and_tests(checker):
    opts = checker.parse_args([])
    assert opts["src_prefix"] == "src/"
    assert opts["tests_prefix"] == "tests/"
    assert opts["mode"] == "staged"
    assert opts["json"] is False


@pytest.mark.parametrize(
    "flags, mode",
    [([], "staged"), (["--all"], "head")],
)
def test_mode_selection(checker, flags, mode):
    assert checker.parse_args(flags)["mode"] == mode


def test_evaluate_flags_only_src_without_tests(checker):
    src, tests, violation = checker.evaluate(
        ["src/a.py", "docs/readme.md"], "src/", "tests/"
    )
    assert src == ["src/a.py"]
    assert tests == []
    assert violation is True

    src, tests, violation = checker.evaluate(
        ["src/a.py", "tests/test_a.py"], "src/", "tests/"
    )
    assert violation is False


def test_evaluate_ignores_unrelated_paths(checker):
    src, tests, violation = checker.evaluate(["docs/x.md", "README.md"], "src/", "tests/")
    assert (src, tests, violation) == ([], [], False)


def test_summarise_truncates_long_lists(checker):
    many = ["src/f%02d.py" % i for i in range(14)]
    text = checker.summarise(many)
    assert text.endswith("(+4 more)"), text
    assert text.count(",") == checker.LIST_LIMIT - 1


def test_summarise_empty_is_a_dash(checker):
    assert checker.summarise([]) == "-"


def test_exit_code_constants_are_the_documented_contract(checker):
    """Pinned so a careless refactor cannot quietly renumber the interface."""
    assert (checker.EXIT_ALLOW, checker.EXIT_BLOCK, checker.EXIT_USAGE) == (0, 1, 2)
