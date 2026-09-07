"""Shared synthetic JC adapter for the Harness integration samples.

Engineering synthetic materials only: the adapter reuses the repository's
signed synthetic pack and test trust context to mint the admission artifacts
the formal spine requires (evidence, attestations, requests, run identities).
The Legal Harness will replace this adapter with its own admitted materials;
the JC-side contract (harness_contract.py) stays unchanged.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from compiler_core.application import ApplicationV4
from compiler_core.harness_contract import (
    HarnessQueryInput,
    HarnessRunRequest,
    evaluate_for_harness,
)

from tests.contract.test_v5_profile_chain import (
    _application,
    _seed_with_v5,
    _v5_inputs,
)
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


def run_case(
    *,
    case_suffix: str,
    fact_keys: tuple[str, ...],
    profiles: tuple[str, ...] = ("grounded",),
    incremental_parent=None,
):
    """One public Harness -> JC -> Harness evaluation on synthetic materials."""

    harness = _ChainHarness()
    policy, queries, claim = _v5_inputs(harness, profiles=profiles)
    harness_queries = tuple(
        HarnessQueryInput(
            issue_id=query.query_id, claim=query.claim, profile=query.profile,
        )
        for query in queries
    )
    seed, request_ref, _, run_ref = _seed_with_v5(
        harness,
        policy=policy,
        queries=queries,
        extra_fact_keys=fact_keys,
        incremental_parent=incremental_parent,
    )
    tmp = Path(tempfile.mkdtemp(prefix=f"jc-sample-{case_suffix}-"))
    application, store = _application(tmp, harness)
    run_request = HarnessRunRequest(
        case_id=f"synthetic-case-{caseSuffix(case_suffix)}",
        request=seed,
        queries=harness_queries,
        incremental_parent=incremental_parent,
    )
    result = evaluate_for_harness(
        application, run_request,
        request_ref=request_ref, run_ref=run_ref, case_scope=CASE_SCOPE,
    )
    return result, store, harness, run_ref


def caseSuffix(value: str) -> str:
    return value.replace("_", "-")


def run_incremental_pair(
    *,
    parent_facts: tuple[str, ...],
    child_facts: tuple[str, ...],
    profiles: tuple[str, ...] = ("grounded",),
):
    """Parent and child as two separate service instances sharing only the
    persistent audit store (the cross-process shape)."""

    from base64 import b64decode

    from compiler_core.application import HORN_SUBJECT_STATE_KIND_V5
    from compiler_core.canonical_serialization import DigestV4, parse_json_document
    from compiler_core.contracts import ContentRefV4, IncrementalParentV5

    from tests.contract.test_v5_incremental_chain import _second_application

    tmp = Path(tempfile.mkdtemp(prefix="jc-sample-incremental-"))
    parent_harness = _ChainHarness()
    policy, queries, _claim = _v5_inputs(parent_harness, profiles=profiles)
    harness_queries = tuple(
        HarnessQueryInput(
            issue_id=query.query_id, claim=query.claim, profile=query.profile,
        )
        for query in queries
    )
    seed, request_ref, _, run_ref = _seed_with_v5(
        parent_harness, policy=policy, queries=queries, extra_fact_keys=parent_facts,
    )
    parent_application, parent_store = _application(tmp, parent_harness)
    parent_request = HarnessRunRequest(
        case_id="synthetic-case-incremental", request=seed, queries=harness_queries,
    )
    parent_result = evaluate_for_harness(
        parent_application, parent_request,
        request_ref=request_ref, run_ref=run_ref, case_scope=CASE_SCOPE,
    )

    capability = parent_store.capability_for(run_ref)
    verified = parent_store.verify_run(capability, now=parent_harness.now)
    state_row = None
    for name in sorted(verified.files):
        try:
            payload = parse_json_document(verified.files[name])
        except ValueError:
            continue
        if type(payload) is not dict or type(payload.get("artifacts")) is not list:
            continue
        for item in payload["artifacts"]:
            if item.get("artifact_kind") == HORN_SUBJECT_STATE_KIND_V5:
                state_row = item
    assert state_row is not None
    state = parse_json_document(b64decode(state_row["content_base64"], validate=True))
    parent_input = IncrementalParentV5(
        parent_run_ref=run_ref,
        parent_state_ref=ContentRefV4.from_dict(state_row["content_ref"]),
        parent_subject_digest=DigestV4(state["subject_digest"]),
    )

    child_harness = _ChainHarness()
    child_policy, child_queries, _ = _v5_inputs(child_harness, profiles=profiles)
    child_seed, child_request_ref, _, child_run_ref = _seed_with_v5(
        child_harness,
        policy=child_policy,
        queries=child_queries,
        extra_fact_keys=child_facts,
        incremental_parent=parent_input,
    )
    child_application, child_store = _second_application(
        tmp, child_harness, (tmp / "state").resolve(),
    )
    child_request = HarnessRunRequest(
        case_id="synthetic-case-incremental",
        request=child_seed,
        queries=harness_queries,
        incremental_parent=parent_input,
    )
    child_result = evaluate_for_harness(
        child_application, child_request,
        request_ref=child_request_ref, run_ref=child_run_ref, case_scope=CASE_SCOPE,
    )
    return parent_result, child_result


def human_projection(result) -> str:
    """The lawyer-facing one-liner the Harness may display verbatim."""

    issue = result.issues[0] if result.issues else None
    status = issue.conclusion_status() if issue else "no-issue"
    if result.completeness != "complete":
        return (
            f"暂时不能确认该问题已完整解决（状态：{status}）。"
            f"未决事项：{[item.code for item in result.open_obligations]}"
        )
    return f"该问题在本场景下结论状态：{status}。"


if __name__ == "__main__":
    import json

    result, *_ = run_case(case_suffix="smoke", fact_keys=())
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
