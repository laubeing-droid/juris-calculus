"""The closed Harness-facing contract (G05) over the sole formal spine.

``evaluate_for_harness`` is the stable integration surface the Legal
Harness will call: one request in, one readable result out, everything else
addressed through audit artifacts. The three integration samples (normal,
incremental, priority-blocked) live in examples/harness and are executed by
these tests.
"""
from __future__ import annotations

from base64 import b64decode
from pathlib import Path

from compiler_core.application import HORN_SUBJECT_STATE_KIND_V5
from compiler_core.canonical_serialization import DigestV4, parse_json_document
from compiler_core.contracts import ContentRefV4, IncrementalParentV5
from compiler_core.harness_contract import (
    HARNESS_CONTRACT_VERSION,
    HarnessQueryInput,
    HarnessRunRequest,
    evaluate_for_harness,
)

from tests.contract.test_v5_profile_chain import (
    EXCEPTION_FACTS,
    _application,
    _seed_with_v5,
    _v5_inputs,
)
from tests.contract.test_v5_final_remediation import PRIORITY_CONDITION_FACT
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness

REPO = Path(__file__).resolve().parents[2]


def _horn_state(store, harness, run_ref) -> dict:
    capability = store.capability_for(run_ref)
    verified = store.verify_run(capability, now=harness.now)
    for name in sorted(verified.files):
        try:
            payload = parse_json_document(verified.files[name])
        except ValueError:
            continue
        if type(payload) is not dict or type(payload.get("artifacts")) is not list:
            continue
        for item in payload["artifacts"]:
            if item.get("artifact_kind") == HORN_SUBJECT_STATE_KIND_V5:
                return parse_json_document(b64decode(item["content_base64"], validate=True))
    raise AssertionError("horn state missing")


def _harness_run(tmp_path, fact_keys, *, profiles=("grounded",)):
    harness = _ChainHarness()
    policy, queries, claim = _v5_inputs(harness, profiles=profiles)
    harness_queries = tuple(
        HarnessQueryInput(
            issue_id=query.query_id, claim=query.claim, profile=query.profile,
        )
        for query in queries
    )
    seed, request_ref, _, run_ref = _seed_with_v5(
        harness, policy=policy, queries=queries, extra_fact_keys=fact_keys,
    )
    application, store = _application(tmp_path, harness)
    run_request = HarnessRunRequest(
        case_id=f"case-{seed.request_id}",
        request=seed,
        queries=harness_queries,
    )
    result = evaluate_for_harness(
        application, run_request,
        request_ref=request_ref, run_ref=run_ref, case_scope=CASE_SCOPE,
    )
    return result, store, harness, run_ref, seed


def test_harness_normal_request_projection(tmp_path: Path) -> None:
    result, _store, _harness, _run_ref, _seed = _harness_run(
        tmp_path, EXCEPTION_FACTS + ("synthetic-horn.a",),
    )
    assert result.run_status == "success"
    assert result.decision_status == "accepted_formal_result"
    assert result.completeness == "complete"
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.conclusion_status() == "accepted"
    assert issue.accepted is True
    assert issue.acceptance_witnesses
    assert issue.branch_refs
    assert result.procedure_kinds == ("pending_legal_judgment",)
    assert result.open_obligations == ()
    assert result.horn_mode == "full_recompute"
    assert result.horn_solver_work >= 1
    assert result.horn_checker_work >= 1
    assert result.artifact_refs
    payload = result.to_dict()
    assert payload["harness_contract_version"] == HARNESS_CONTRACT_VERSION
    assert payload["issues"][0]["conclusion_status"] == "accepted"


def test_harness_incremental_request_projection(tmp_path: Path) -> None:
    """The parent reference rides the closed request contract; the full
    cross-instance incremental semantics are pinned in the F-series tests."""

    parent_result, store, harness, run_ref, seed = _harness_run(
        tmp_path / "parent", EXCEPTION_FACTS + ("synthetic-horn.a",),
    )
    assert parent_result.horn_mode == "full_recompute"

    parent_state = _horn_state(store, harness, run_ref)
    parent_ref = IncrementalParentV5(
        parent_run_ref=run_ref,
        parent_state_ref=ContentRefV4(
            HORN_SUBJECT_STATE_KIND_V5,
            DigestV4(parent_state["subject_digest"]),
        ),
        parent_subject_digest=DigestV4(parent_state["subject_digest"]),
    )
    request_payload = HarnessRunRequest(
        case_id="case-incremental",
        request=seed,
        queries=(),
        incremental_parent=parent_ref,
    ).to_dict()
    assert (
        request_payload["incremental_parent"]["parent_subject_digest"]
        == parent_state["subject_digest"]
    )
    assert request_payload["harness_contract_version"] == HARNESS_CONTRACT_VERSION


def test_harness_priority_blocked_projection(tmp_path: Path) -> None:
    result, _store, _harness, _run_ref, _seed = _harness_run(
        tmp_path, EXCEPTION_FACTS + (PRIORITY_CONDITION_FACT,),
    )
    assert result.run_status == "success"
    assert result.completeness == "partial"
    issue = result.issues[0]
    assert issue.conclusion_status() == "incomplete"
    assert issue.mapping_complete is False
    assert any(
        item.code == "priority_policy_missing" for item in result.open_obligations
    )
    assert result.assurance_specs
    assert all(spec == "openObligations" for spec in result.assurance_specs)


def test_examples_run_and_match_contract(tmp_path: Path) -> None:
    """G05: the three committed samples run and speak the same contract."""

    import subprocess
    import sys

    samples = {
        "examples/harness/sample_normal.py": ("harness_contract_version", "accepted"),
        "examples/harness/sample_incremental.py": ('"horn_mode": "incremental"',),
        "examples/harness/sample_priority_blocked.py": ('"completeness": "partial"',),
    }
    for sample, markers in samples.items():
        path = REPO / sample
        assert path.is_file(), sample
        completed = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(REPO),
            timeout=600,
            env={
                **__import__("os").environ,
                "PYTHONIOENCODING": "utf-8",
            },
        )
        assert completed.returncode == 0, (
            f"{sample} failed:\n{completed.stdout}\n{completed.stderr}"
        )
        for marker in markers:
            assert marker in completed.stdout, (sample, marker)
