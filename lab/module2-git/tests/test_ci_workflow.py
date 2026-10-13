"""Contract tests for the sample CI workflow in ``ci/quality-gate.yml``.

Why test a YAML teaching artefact at all
----------------------------------------
Because an example that does not parse is worse than no example: it teaches a
syntax that fails. And because the interesting claims in that file are
*structural*, not cosmetic:

* the ``on:`` block must have **no** ``paths:`` filter -- the single most
  expensive way to break a required status check (see the long comment in the
  workflow, and ``spec-kit/.github/workflows/extension-version-guard.yml:13-16``);
* the step that is the gate must actually block, i.e. it must reach a non-zero
  ``exit`` on the violation path;
* the checker step must capture the checker's own exit status rather than the
  status of the command substitution that produced its stdout -- the same trap
  ``spec-kit/scripts/bash/check-prerequisites.sh:186`` works around;
* every ``CHECKER`` path the workflow names must exist in this repository.

The tests are written against the *document* the workflow declares, not against
its formatting, so reformatting or rewording does not break them.

PyYAML is not a dependency of the lab's checker (that one is pure stdlib). The
whole module is skipped when PyYAML is missing rather than silently passing:
run ``python lab/_pip_install.py pyyaml`` to enable it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml not installed; run: python lab/_pip_install.py pyyaml")

MODULE_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = MODULE_ROOT / "ci" / "quality-gate.yml"
# ci/ -> module2-git/ -> lab/ -> <repo root>
REPO_ROOT = MODULE_ROOT.parents[1]


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def triggers(doc: dict) -> dict:
    """Return the ``on:`` mapping.

    YAML 1.1 (which PyYAML implements) reads the bare key ``on`` as the boolean
    ``True``. Real workflow files therefore come back under the key ``True``,
    which is a classic source of "but my key is right there" confusion - so we
    accept both spellings instead of pretending it does not happen.
    """
    for key in (True, "on"):
        if key in doc:
            return doc[key] or {}
    raise AssertionError("workflow has no `on:` trigger block")


def all_mapping_keys(node) -> list:
    """Every mapping key appearing anywhere in the document, nested included."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append(key)
            found.extend(all_mapping_keys(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(all_mapping_keys(item))
    return found


def test_workflow_parses_as_yaml_and_declares_a_job():
    doc = load()
    assert isinstance(doc, dict)
    assert doc.get("name")
    assert "jobs" in doc and doc["jobs"], "the sample must declare at least one job"


def test_it_is_a_pull_request_gate_not_a_live_pipeline_in_this_repo():
    """It lives in the lab on purpose; it must not be wired up here."""
    assert not (REPO_ROOT / ".github" / "workflows").exists() or not any(
        p.name == "quality-gate.yml"
        for p in (REPO_ROOT / ".github" / "workflows").glob("*.yml")
    ), "the sample must NOT be installed under .github/workflows/ in this repository"


def test_no_paths_filter_on_the_trigger():
    """The `paths:` trap. This is the assertion the whole file exists for."""
    trig = triggers(load())
    assert "paths" not in trig, (
        "a `paths:` filter on a required check makes it report nothing at all, "
        "leaving every unaffected PR stuck in 'Expected' forever"
    )
    assert "paths" not in all_mapping_keys(load()), (
        "`paths:` found somewhere in the workflow; if it is intentional, it must "
        "not be part of the trigger that the required check depends on"
    )


def test_trigger_shape_is_pull_request_plus_manual():
    trig = triggers(load())
    assert "pull_request" in trig
    assert "workflow_dispatch" in trig, "a manual escape hatch is what you use to re-run it"


def test_permissions_are_minimal():
    assert load().get("permissions") == {"contents": "read"}


def test_prefixes_are_declared_once_at_the_top():
    env = load().get("env") or {}
    assert env.get("SRC_PREFIX") == "src/"
    assert env.get("TESTS_PREFIX") == "tests/"
    assert env.get("CHECKER"), "the checker path must be declared, not repeated inline"


def test_the_declared_checker_exists_relative_to_the_repo_root():
    env = load()["env"]
    declared = REPO_ROOT / env["CHECKER"]
    assert declared.is_file(), f"workflow names a checker that does not exist: {declared}"
    assert declared.name == "check_tests_touched.py"


def test_the_gate_step_actually_blocks():
    """A gate that cannot exit non-zero is not a gate."""
    doc = load()
    runs = [
        step["run"]
        for job in doc["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
    ]
    blocking = [r for r in runs if "exit 1" in r]
    assert blocking, "no step in the workflow ever exits 1, so nothing is gated"
    assert any("::error" in r for r in blocking), (
        "the failing step should emit a ::error:: annotation, otherwise the "
        "failure is only visible in a log nobody opens"
    )


def test_the_gate_step_checks_the_real_staged_range():
    doc = load()
    runs = "\n".join(
        step["run"]
        for job in doc["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
    )
    # CI has no index of its own, so the PR range is rebuilt into one.
    assert "reset" in runs and "--soft" in runs
    assert "diff --cached" in runs


def test_the_checker_step_preserves_the_checkers_exit_code():
    """`out=$(cmd)` throws cmd's status away; you must capture it first."""
    doc = load()
    steps = [s for job in doc["jobs"].values() for s in job.get("steps", [])]
    checker_steps = [s for s in steps if isinstance(s.get("run"), str) and '"$CHECKER"' in s["run"]]
    assert checker_steps, "no step runs the declared checker"
    run = checker_steps[0]["run"]
    assert "status=$?" in run, "the checker's exit code must be captured into a variable"
    assert 'exit "$status"' in run, "and re-exited unchanged, or the gate is decorative"


def test_every_run_block_is_a_non_empty_string():
    doc = load()
    for job_name, job in doc["jobs"].items():
        assert job.get("runs-on"), f"job {job_name} has no runner"
        assert job.get("steps"), f"job {job_name} has no steps"
        for i, step in enumerate(job["steps"]):
            has_run = "run" in step
            has_uses = "uses" in step
            assert has_run != has_uses, (
                f"job {job_name} step {i} must have exactly one of `run` / `uses`"
            )
            if has_run:
                assert isinstance(step["run"], str) and step["run"].strip()


def test_third_party_actions_are_pinned_to_a_major_version():
    doc = load()
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            uses = step.get("uses")
            if uses:
                assert "@" in uses, f"action {uses} is not pinned"
