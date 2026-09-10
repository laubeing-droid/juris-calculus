"""jc-business-root/1 wire-contract acceptance (ROUTE1 J01, BC01-BC03/BC10/BC16).

Covers the closed typed codec, the digest-stable optional extension, the
20-dimension context roundtrip, and fail-closed rejection of lossy carriers
(floats, booleans as integers, duplicate JSON keys, unknown fields).
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from compiler_core.canonical_serialization import (
    CanonicalizationError,
    DigestV4,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    BusinessAtomPairV1,
    BusinessAtomStateV1,
    BusinessContextV1,
    BusinessFormulaV1,
    BusinessModelInputsV1,
    BusinessPaymentV1,
    BusinessSpecV1,
    BusinessSourceSpanV1,
    BusinessTaskInputV1,
    BusinessTaskV1,
    BusinessWorldV1,
    BusinessWorldWeightV1,
    CaseRequestV4,
    ContractV4Error,
)


SOURCE = "合成示例：已到期本金1000元；争议清偿300元；只计算条件本金余额。"


def _context(**overrides) -> BusinessContextV1:
    values = dict(
        request="DEMO-PRINCIPAL-01",
        jurisdiction="TEST",
        event_time="2026-08-01",
        decision_time="2026-09-09",
        procedure="conditional_analysis",
        stage="analysis",
        party="claimant",
        issue="principal-balance",
        scenario="finite-conditional-completions",
        profile="grounded",
        law_version="source-snapshot-example",
        interpretation="explicit-reference",
        rulepack_version="test-1",
        engine_version="reference-2.1",
        model_version="synthetic-model-1",
        evidence_version="test-evidence-1",
        target="award_at_least_threshold",
        semantic_scope="height_bounded",
        assumptions=("仅付款认定作为分支", "示例前提：债权成立且已到期"),
        max_depth=2,
    )
    values.update(overrides)
    return BusinessContextV1(**values)


def _spec(principal: str = "1000") -> BusinessSpecV1:
    return BusinessSpecV1(
        relation_id="principal-claim",
        creditor="甲公司",
        debtor="乙公司",
        debt_id="DEBT-1",
        principal=principal,
        due_day="2026-08-01",
        asof_day="2026-09-09",
        sources=(BusinessSourceSpanV1("SYNTHETIC-BASIS", "1", SOURCE, 0, len(SOURCE), SOURCE),),
        payments=(BusinessPaymentV1(
            "P1", "300", "2026-08-20", "乙公司", "甲公司", "DEBT-1",
            "payment_recognized", "SYNTHETIC-BASIS",
        ),),
        facts=(BusinessAtomStateV1("payment_recognized", None),),
        constraint=BusinessFormulaV1("true"),
        approved_policy="SYNTHETIC-CONDITIONAL-PRINCIPAL/1",
    )


def _model(**overrides) -> BusinessModelInputsV1:
    wt = BusinessWorldV1((BusinessAtomPairV1("payment_recognized", True),))
    wf = BusinessWorldV1((BusinessAtomPairV1("payment_recognized", False),))
    values = dict(
        weights=(BusinessWorldWeightV1(wt, "2/5"), BusinessWorldWeightV1(wf, "3/5")),
        threshold="800",
        costs=("100", "60", "10", "10"),
        legal_options=("600", "850", "1100"),
        basis="SYNTHETIC-SETTLEMENT-GRID/1",
    )
    values.update(overrides)
    return BusinessModelInputsV1(**values)


def _task(**overrides) -> BusinessTaskV1:
    values = dict(
        task_id="task-1",
        issue_id="principal-balance",
        requirement_id="SYNTHETIC_EXACT_PRINCIPAL_ANALYTICS_TWO_FILES/1",
        profile="SYNTHETIC-CONDITIONAL-PRINCIPAL/1",
        selection_ref=DigestV4(digest_value({"selection": "task-1"})),
        input=BusinessTaskInputV1(context=_context(), spec=_spec(), model=_model()),
    )
    values.update(overrides)
    return BusinessTaskV1(**values)


# ---------------------------------------------------------------------------
# BC01 — legacy local/1 requests keep their exact canonical identity.
# ---------------------------------------------------------------------------


def _legacy_request() -> CaseRequestV4:
    return CaseRequestV4.from_dict({
        "request_id": "req-1",
        "schema_version": "jc/5.0",
        "legal_context": {"jurisdiction": "CN", "governing_law": "PRC"},
        "decision_time": {"wire": "2026-09-11T00:00:00Z"},
        "source_bundle_ref": {"kind": "source-bundle", "digest": "sha256:" + "0" * 64},
        "evidence_manifest_ref": {
            "kind": "evidence-manifest", "digest": "sha256:" + "1" * 64,
        },
        "fact_attestation_refs": [],
        "rule_pack_ref": {"kind": "rule-pack", "digest": "sha256:" + "2" * 64},
        "requested_outputs": [
            {"kind": "semantic_result", "format": "json", "locale": "zh-CN"},
        ],
        "proposal_refs": [],
    })


def test_bc01_legacy_request_wire_has_no_business_key_and_stable_digest() -> None:
    request = _legacy_request()
    payload = request.to_dict()
    assert "business_tasks_v1" not in payload
    assert request.canonical_digest() == CaseRequestV4.from_dict(payload).canonical_digest()


def test_bc16_digest_stable_extension_empty_list_equals_absent() -> None:
    legacy = _legacy_request().to_dict()
    explicit = CaseRequestV4.from_dict({**legacy, "business_tasks_v1": []})
    absent = CaseRequestV4.from_dict(dict(legacy))
    assert explicit.canonical_digest() == absent.canonical_digest()
    assert "business_tasks_v1" not in explicit.to_dict()


# ---------------------------------------------------------------------------
# BC02 — canonical structure roundtrip and lossy carrier rejection.
# ---------------------------------------------------------------------------


def test_bc02_business_task_roundtrip_is_lossless() -> None:
    task = _task()
    payload = task.to_dict()
    decoded = BusinessTaskV1.from_dict(json.loads(json.dumps(payload, ensure_ascii=False)))
    assert decoded == task
    context = _context()
    assert BusinessContextV1.from_json_text(context.canonical_json()) == context


def test_bc02_rejects_float_amount() -> None:
    with pytest.raises(ContractV4Error):
        BusinessSpecV1.from_dict({**_spec().to_dict(), "principal": "1000.0"})


def test_bc02_rejects_noncanonical_rationals() -> None:
    for bad in ("+300", "3e2", "0300", "300/0", "3 / 5", 300, True, None, "2/4"):
        with pytest.raises(ContractV4Error):
            BusinessPaymentV1.from_dict({
                **_spec().payments[0].to_dict(), "amount": bad,
            })


def test_bc02_rejects_bool_integers_in_context_depth() -> None:
    with pytest.raises(ContractV4Error):
        _context(max_depth=True)


def test_bc02_rejects_duplicate_json_keys() -> None:
    payload = _task().to_dict()
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    duplicate = text.replace('"task_id":"task-1"', '"task_id":"task-1","task_id":"task-2"')
    assert duplicate != text
    with pytest.raises(CanonicalizationError):
        parse_json_document(duplicate)


def test_bc02_rejects_unknown_and_missing_fields() -> None:
    payload = _task().to_dict()
    with pytest.raises(ContractV4Error):
        BusinessTaskV1.from_dict({**payload, "expected": "880"})
    missing = deepcopy(payload)
    del missing["requirement_id"]
    with pytest.raises(ContractV4Error):
        BusinessTaskV1.from_dict(missing)


def test_bc02_rejects_expected_answer_carried_in_model() -> None:
    with pytest.raises(ContractV4Error):
        BusinessModelInputsV1.from_dict({
            **_model().to_dict(), "expected_balance": "880",
        })


# ---------------------------------------------------------------------------
# BC03 — subject/assumption identity separation.
# ---------------------------------------------------------------------------


def test_bc03_context_assumption_order_is_canonical_and_distinct() -> None:
    straight = _context(assumptions=("a", "b"))
    # The wire form rejects unsorted assumptions instead of silently sorting.
    with pytest.raises(ContractV4Error):
        _context(assumptions=("b", "a"))
    different = _context(assumptions=("a", "c"))
    assert straight != different
    assert straight.canonical_json() != different.canonical_json()


def test_bc03_same_request_different_issue_or_model_cannot_compose() -> None:
    task = _task()
    other_issue = BusinessTaskV1.from_dict({
        **task.to_dict(),
        "input": BusinessTaskInputV1(
            context=_context(issue="other-issue"), spec=_spec(), model=_model(),
        ).to_dict(),
    })
    assert task.input.context != other_issue.input.context
    other_model = BusinessTaskV1.from_dict({
        **task.to_dict(),
        "input": BusinessTaskInputV1(
            context=task.input.context,
            spec=task.input.spec,
            model=_model(threshold="700"),
        ).to_dict(),
    })
    assert task.input.model != other_model.input.model
    assert task.canonical_digest() != other_model.canonical_digest()
    with pytest.raises(ContractV4Error):
        BusinessTaskInputV1(
            context=_context(event_time="2026-08-02"),
            spec=task.input.spec,
            model=task.input.model,
        )


# ---------------------------------------------------------------------------
# BC10 — unsupported capability is refused with a typed error, never dropped.
# ---------------------------------------------------------------------------


def test_bc10_unsupported_profile_is_refused_not_silently_ignored() -> None:
    payload = _task().to_dict()
    payload["profile"] = "SOME-OTHER-PROFILE/9"
    with pytest.raises(ContractV4Error) as caught:
        BusinessTaskV1.from_dict(payload)
    assert caught.value.code == "BUSINESS_PROFILE"


def test_bc10_unsupported_requirement_is_refused() -> None:
    payload = _task().to_dict()
    payload["requirement_id"] = "DOCX_UNLIMITED/1"
    with pytest.raises(ContractV4Error) as caught:
        BusinessTaskV1.from_dict(payload)
    assert caught.value.code == "BUSINESS_REQUIREMENT"


def test_bc10_unsupported_model_basis_is_refused() -> None:
    with pytest.raises(ContractV4Error):
        _model(basis="FREE-FORM-SCORES/1")


def test_bc10_solve_budget_must_be_positive_integer() -> None:
    input_payload = BusinessTaskInputV1(
        context=_context(), spec=_spec(), model=_model(),
    ).to_dict()
    with pytest.raises(ContractV4Error):
        BusinessTaskInputV1.from_dict({**input_payload, "solve_budget": 0})
    with pytest.raises(ContractV4Error):
        BusinessTaskInputV1.from_dict({**input_payload, "solve_budget": True})
