"""Packaging contract for the C06 cross-repo verification lanes.

The cross-repo lane is a release-flow obligation: with both repositories
checked out at pinned subjects, the LMM full-release artifacts are
re-derived, the JC public-entry receipts are produced, and the LMM
independent checker accepts them in its own process.
"""
from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
CROSS = ROOT / ".github" / "workflows" / "cross-repo-verification.yml"
AUTO_RELEASE = ROOT / ".github" / "workflows" / "auto-release.yml"
ACTION_PIN = "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5"
SUBJECT = "5084f25e69ae27332404dc9f341a61d46ef0fc53"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on_block(document: dict) -> dict:
    # YAML 1.1 parses the bare key `on:` as boolean True under safe_load.
    return document.get("on") or document.get(True) or {}


def test_cross_repo_workflow_has_the_pinned_subject_shape() -> None:
    document = _load(CROSS)
    triggers = _on_block(document)
    assert "workflow_dispatch" in triggers
    assert "workflow_call" in triggers
    inputs = triggers["workflow_call"]["inputs"]
    for name in ("lmm_repository", "lmm_ref", "runtime_ref"):
        assert name in inputs
    text = CROSS.read_text(encoding="utf-8")
    assert ACTION_PIN in text
    runs = "\n".join(
        step.get("run", "")
        for job in document["jobs"].values()
        for step in job.get("steps", [])
    )
    assert "verify_c06_integration.py" in runs
    assert "lmm_ref" in runs or any(
        "${{ inputs.lmm_ref }}" in json_dumps for json_dumps in (text,)
    )


def test_cross_repo_workflow_verifies_both_sides_fail_closed() -> None:
    runs = "\n".join(
        step.get("run", "")
        for job in _load(CROSS)["jobs"].values()
        for step in job.get("steps", [])
    )
    assert 'test "$(git -C legal-math-modeling rev-parse HEAD)"' in runs
    assert "lean-toolchain" in runs
    assert "lake-manifest" in runs
    assert "verify_c06_integration.py" in runs


def test_release_flow_invokes_the_cross_repo_lane() -> None:
    document = _load(AUTO_RELEASE)
    text = AUTO_RELEASE.read_text(encoding="utf-8")
    assert "cross-repo-verification.yml" in text
    assert SUBJECT in text
    jobs = document["jobs"]
    callers = [
        job for job in jobs.values()
        if str(job.get("uses", "")).endswith("cross-repo-verification.yml")
    ]
    assert callers, "auto-release must call the cross-repo verification lane"
    caller = callers[0]
    with_inputs = caller.get("with", {})
    assert with_inputs.get("runtime_ref") == "c79e03b8d0cfed85c43cc013bf8a0b50326bc858"
