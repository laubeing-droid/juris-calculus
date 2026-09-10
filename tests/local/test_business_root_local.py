"""End-to-end jc-business-root/1 acceptance over the real local runtime.

ROUTE1 first batch (J02-J07, J15): every test drives the installed public
facade — ``create_local_client`` → ``local_case_bundle`` →
``evaluate_harness_bundle`` → ``local_read_run`` → ``business_delivery_documents``
→ ``verify_business_delivery`` — with one Application evaluation per request
and zero evaluations on the verify-only path. All samples are SYNTHETIC.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from compiler_core.canonical_serialization import DigestV4, digest_value
from compiler_core.client import ClientV4Error, create_local_client
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
)
from tests.local.test_local_runtime import _rule_root


SOURCE = "合成示例：已到期本金1000元；争议清偿300元；只计算条件本金余额。"
REQUIREMENT = "SYNTHETIC_EXACT_PRINCIPAL_ANALYTICS_TWO_FILES/1"
PROFILE = "SYNTHETIC-CONDITIONAL-PRINCIPAL/1"
MAIN_EXPECTED = {
    "expected_balance": "880",
    "expected_overpayment": "0",
    "expected_residual": "880",
    "event_probability": "3/5",
    "lower": "790",
    "upper": "930",
    "mutually_acceptable": ["850"],
    "selected": "850",
}


def _context(**overrides) -> BusinessContextV1:
    values = dict(
        request="SYNTHETIC-BUSINESS-CASE-1",
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
        approved_policy=PROFILE,
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


def _selection(label: str) -> DigestV4:
    return DigestV4(digest_value({"host-selection": label}))


def _task(
    task_id: str = "task-1",
    *,
    selection: DigestV4 | None = None,
    spec: BusinessSpecV1 | None = None,
    model: BusinessModelInputsV1 | None = None,
    budget: int | None = None,
) -> BusinessTaskV1:
    return BusinessTaskV1(
        task_id=task_id,
        issue_id="principal-balance",
        requirement_id=REQUIREMENT,
        profile=PROFILE,
        selection_ref=selection if selection is not None else _selection(task_id),
        input=BusinessTaskInputV1(
            context=_context(),
            spec=spec if spec is not None else _spec(),
            model=model if model is not None else _model(),
            solve_budget=budget,
        ),
    )


def _client(tmp_path: Path):
    return create_local_client(tmp_path / "state", _rule_root(tmp_path))


def _run_business(client, task: BusinessTaskV1, *, case_id="business-case"):
    bundle = client.local_case_bundle(
        case_id=case_id,
        decision_time="2026-09-11T00:00:00Z",
        business_tasks=(task,),
    )
    return client.evaluate_harness_bundle(
        bundle, case_id=case_id, issue_queries=[],
    )


# ---------------------------------------------------------------------------
# BC11 — one evaluation per business request; no fake Horn machinery.
# ---------------------------------------------------------------------------


def test_bc11_single_evaluation_and_no_horn_facts(tmp_path: Path) -> None:
    client = _client(tmp_path)
    result = _run_business(client, _task())
    assert result["evaluation_count"] == 1
    assert result["horn"]["mode"] == "not_run"
    assert result["issues"] == []
    assert result["admitted_fact_keys"] == []
    assert result["signature_status"] == "not_used"


# ---------------------------------------------------------------------------
# BC13 — the frozen main example (SYNTHETIC_ONLY).
# ---------------------------------------------------------------------------


def test_bc13_frozen_main_case_numbers(tmp_path: Path) -> None:
    client = _client(tmp_path)
    result = _run_business(client, _task())
    row = result["business_results"][0]
    assert row["completion"] == "exact_finite_scenarios"
    assert row["representation"] == "exact_finite_worlds"
    balances = sorted(
        (outcome["world"]["atoms"][0]["value"], outcome["principal_balance"])
        for outcome in row["outcomes"]
    )
    assert balances[0][1] == "1000" and balances[1][1] == "700"
    assert all(row["analytics"][key] == value for key, value in MAIN_EXPECTED.items())
    assert row["checker_version"] == "jc-business-checker/1"
    assert row["formal_evidence"] == "CROSS_VALIDATED_GENERAL_ALGORITHM_PENDING_KERNEL"
    assert row["witness_ref"] is not None


# ---------------------------------------------------------------------------
# BC14 — overpayment semantics keep E[C], E[U], E[R] separate.
# ---------------------------------------------------------------------------


def test_bc14_overpay_case_distinguishes_clipped_and_raw(tmp_path: Path) -> None:
    client = _client(tmp_path)
    model = _model(threshold="0", costs=("0", "0", "0", "0"), legal_options=("60",))
    result = _run_business(client, _task("task-overpay", spec=_spec("100"), model=model))
    row = result["business_results"][0]
    analytics = row["analytics"]
    assert analytics["expected_balance"] == "60"
    assert analytics["expected_overpayment"] == "80"
    assert analytics["expected_residual"] == "-20"
    assert analytics["selected"] == "60"
    # No refund claim: the run stays a conditional analysis with no claims
    # and no formal certificate.
    assert result["decision_status"] == "hypothetical_result"
    assert result["issues"] == []
    read = client.local_read_run(result["run_identity_ref"])
    assert read["certificate_kind"] == "none"


# ---------------------------------------------------------------------------
# BC15 — budget-limited solving keeps pending worlds and no full analytics.
# ---------------------------------------------------------------------------


def test_bc15_partial_worlds_keep_pending_and_refuse_analytics(tmp_path: Path) -> None:
    client = _client(tmp_path)
    result = _run_business(client, _task("task-partial", budget=1))
    row = result["business_results"][0]
    assert row["completion"] == "partial_scenarios"
    assert len(row["outcomes"]) == 1
    assert len(row["pending_worlds"]) == 1
    assert row["analytics"] is None
    obligations = [item["code"] for item in row["open_obligations"]]
    assert "BUSINESS_PARTIAL_SCENARIOS" in obligations
    assert result["completeness"] == "partial"


# ---------------------------------------------------------------------------
# BC16 — inconsistent Omega is its own typed state, not an empty result.
# ---------------------------------------------------------------------------


def test_bc16_inconsistent_omega_is_typed_not_empty(tmp_path: Path) -> None:
    client = _client(tmp_path)
    spec = replace(_spec(), constraint=BusinessFormulaV1("false"))
    result = _run_business(client, _task("task-omega", spec=spec))
    row = result["business_results"][0]
    assert row["completion"] == "inconsistent_assumptions"
    assert row["outcomes"] == [] and row["pending_worlds"] == []
    assert row["analytics"] is None


# ---------------------------------------------------------------------------
# BC18 — weights need world identity and coverage, not just sum-to-one.
# ---------------------------------------------------------------------------


def test_bc18_weight_coverage_rejects_duplicate_and_missing_worlds(tmp_path: Path) -> None:
    client = _client(tmp_path)
    wf = BusinessWorldV1((BusinessAtomPairV1("payment_recognized", False),))
    duplicated = _model(weights=(
        BusinessWorldWeightV1(wf, "2/5"), BusinessWorldWeightV1(wf, "3/5"),
    ))
    result = _run_business(client, _task("task-dup", model=duplicated))
    row = result["business_results"][0]
    assert row["completion"] == "failed"
    assert row["error_code"] == "MODEL_WORLD_COVERAGE"


def test_bc18_zero_weight_world_stays_in_coverage(tmp_path: Path) -> None:
    client = _client(tmp_path)
    wt = BusinessWorldV1((BusinessAtomPairV1("payment_recognized", True),))
    wf = BusinessWorldV1((BusinessAtomPairV1("payment_recognized", False),))
    zeroed = _model(weights=(
        BusinessWorldWeightV1(wt, "0"), BusinessWorldWeightV1(wf, "1"),
    ))
    result = _run_business(client, _task("task-zero", model=zeroed))
    row = result["business_results"][0]
    assert row["completion"] == "exact_finite_scenarios"
    assert len(row["outcomes"]) == 2
    assert {item["probability"] for item in row["analytics"]["weights"]} == {"0", "1"}


# ---------------------------------------------------------------------------
# BC19 — the settlement grid: interior points outside the grid stay ineligible.
# ---------------------------------------------------------------------------


def test_bc19_grid_midpoint_is_not_eligible(tmp_path: Path) -> None:
    client = _client(tmp_path)
    result = _run_business(client, _task())
    analytics = result["business_results"][0]["analytics"]
    lower, upper = int(analytics["lower"]), int(analytics["upper"])
    assert lower <= 860 <= upper
    assert 860 not in {600, 850, 1100}
    assert analytics["mutually_acceptable"] == ["850"]
    assert analytics["selected"] == "850"


def test_bc19_empty_intersection_yields_null_selection(tmp_path: Path) -> None:
    client = _client(tmp_path)
    model = _model(legal_options=("5",))
    result = _run_business(client, _task("task-empty-grid", model=model))
    analytics = result["business_results"][0]["analytics"]
    assert analytics["mutually_acceptable"] == []
    assert analytics["selected"] is None


# ---------------------------------------------------------------------------
# BC04/BC05/BC36 — same-version parameter changes need a new host selection.
# ---------------------------------------------------------------------------


def test_bc04_replays_with_changed_model_reject_original_selection(tmp_path: Path) -> None:
    client = _client(tmp_path)
    selection = _selection("host-revision-1")
    task = _task("task-1", selection=selection)
    first = _run_business(client, task)
    assert first["business_results"][0]["completion"] == "exact_finite_scenarios"

    changed_model = _model(threshold="700")
    tampered = _task("task-1", selection=selection, model=changed_model)
    second = _run_business(client, tampered)
    row = second["business_results"][0]
    # The recompute is self-consistent for the changed model but cannot pass
    # itself off as the previously selected input.
    assert row["selection_ref"] == str(selection)
    verdict = client.verify_business_delivery(
        run_identity_ref=second["run_identity_ref"],
        business_task_id="task-1",
        selected_input_ref=selection,
        artifacts={
            "conditional_principal.txt": b"x",
            "calculation.json": b"y",
        },
    )
    assert verdict["status"] == "REJECTED"


def test_bc05_new_selection_is_a_new_task_and_old_run_stays_readable(tmp_path: Path) -> None:
    client = _client(tmp_path)
    first = _run_business(client, _task("task-1", selection=_selection("rev-1")))
    second = _run_business(
        client, _task("task-1", selection=_selection("rev-2"), model=_model(threshold="700"))
    )
    assert first["run_identity_ref"] != second["run_identity_ref"]
    old = client.local_read_run(first["run_identity_ref"])
    assert old["decision_status"] == "hypothetical_result"
    assert old["files"]["result.json"]["business_results_v1"][0]["task_id"] == "task-1"


def test_bc36_changed_model_yields_new_results_not_cached_ones(tmp_path: Path) -> None:
    client = _client(tmp_path)
    first = _run_business(client, _task("task-1", selection=_selection("rev-1")))
    second = _run_business(
        client, _task("task-1", selection=_selection("rev-2"), model=_model(threshold="600"))
    )
    first_analytics = first["business_results"][0]["analytics"]
    second_analytics = second["business_results"][0]["analytics"]
    assert first_analytics["event_probability"] != second_analytics["event_probability"]


# ---------------------------------------------------------------------------
# BC22/BC23/BC24/BC25/BC28 — verify-only two-file delivery checking.
# ---------------------------------------------------------------------------


def _docs_and_verdict(client, task: BusinessTaskV1, result):
    docs = client.business_delivery_documents(
        run_identity_ref=result["run_identity_ref"], business_task_id=task.task_id,
    )
    verdict = client.verify_business_delivery(
        run_identity_ref=result["run_identity_ref"],
        business_task_id=task.task_id,
        selected_input_ref=task.selection_ref,
        artifacts=docs,
    )
    return docs, verdict


def test_bc25_clean_delivery_accepted_then_verifies_without_rerunning(tmp_path: Path) -> None:
    client = _client(tmp_path)
    task = _task()
    result = _run_business(client, task)
    docs, verdict = _docs_and_verdict(client, task, result)
    assert verdict["status"] == "ACCEPTED", verdict
    bindings = verdict["artifact_bindings"]
    assert bindings and all(
        binding["artifact_name"] in ("conditional_principal.txt", "calculation.json")
        for binding in bindings
    )
    application = client._application
    counter = {"n": 0}
    original = application.evaluate

    def counted(*args, **kwargs):
        counter["n"] += 1
        return original(*args, **kwargs)

    application.evaluate = counted
    try:
        for _ in range(3):
            repeat = client.verify_business_delivery(
                run_identity_ref=result["run_identity_ref"],
                business_task_id=task.task_id,
                selected_input_ref=task.selection_ref,
                artifacts=docs,
            )
            assert repeat["status"] == "ACCEPTED"
    finally:
        del application.evaluate
    assert counter["n"] == 0


def test_bc22_tampered_principal_text_is_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    task = _task()
    result = _run_business(client, task)
    docs, _ = _docs_and_verdict(client, task, result)
    tampered = dict(docs)
    tampered["conditional_principal.txt"] = docs["conditional_principal.txt"].replace(
        "1000".encode("utf-8"), "1200".encode("utf-8"),
    )
    verdict = client.verify_business_delivery(
        run_identity_ref=result["run_identity_ref"],
        business_task_id=task.task_id,
        selected_input_ref=task.selection_ref,
        artifacts=tampered,
    )
    assert verdict["status"] == "REJECTED"
    assert "PRINCIPAL_FILE_READBACK" in verdict["reasons"]


@pytest.mark.parametrize(
    "mutate",
    [
        # probability tamper
        lambda payload: payload["decision_inputs"]["weights"][0].update(probability="1/2"),
        # cost tamper
        lambda payload: payload["decision_inputs"].update(costs=["999", "60", "10", "10"]),
        # threshold tamper
        lambda payload: payload["decision_inputs"].update(threshold="700"),
        # eligible tamper
        lambda payload: payload["analytics"].update(mutually_acceptable=["600", "850"]),
        # subject tamper
        lambda payload: payload["relation"].update(creditor="丙公司"),
    ],
    ids=["probability", "cost", "threshold", "eligible", "subject"],
)
def test_bc23_tampered_calculation_json_is_rejected(tmp_path: Path, mutate) -> None:
    client = _client(tmp_path)
    task = _task()
    result = _run_business(client, task)
    docs, _ = _docs_and_verdict(client, task, result)
    payload = json.loads(docs["calculation.json"].decode("utf-8"))
    mutate(payload)
    tampered = dict(docs)
    tampered["calculation.json"] = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    verdict = client.verify_business_delivery(
        run_identity_ref=result["run_identity_ref"],
        business_task_id=task.task_id,
        selected_input_ref=task.selection_ref,
        artifacts=tampered,
    )
    assert verdict["status"] == "REJECTED"
    assert "ANALYTICS_FILE_READBACK" in verdict["reasons"]


def test_bc23_duplicate_key_and_nan_json_are_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    task = _task()
    result = _run_business(client, task)
    docs = client.business_delivery_documents(
        run_identity_ref=result["run_identity_ref"], business_task_id=task.task_id,
    )
    text = docs["calculation.json"].decode("utf-8")
    target = '"threshold": "800"'
    assert target in text
    duplicates = text.replace(target, target + ', "threshold": "800"', 1)
    nan_text = text.replace(target, '"threshold": NaN', 1)
    for broken in (duplicates, nan_text):
        assert broken != text
        verdict = client.verify_business_delivery(
            run_identity_ref=result["run_identity_ref"],
            business_task_id=task.task_id,
            selected_input_ref=task.selection_ref,
            artifacts={
                "conditional_principal.txt": docs["conditional_principal.txt"],
                "calculation.json": broken.encode("utf-8"),
            },
        )
        assert verdict["status"] == "REJECTED"


def test_bc24_consistent_files_of_another_input_are_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    task = _task()
    result = _run_business(client, task)
    # Fully consistent two-file delivery of a DIFFERENT selected input.
    other = _task("task-other", selection=_selection("host-revision-other"), model=_model(threshold="700"))
    other_result = _run_business(client, other, case_id="business-case-other")
    other_docs = client.business_delivery_documents(
        run_identity_ref=other_result["run_identity_ref"], business_task_id="task-other",
    )
    verdict = client.verify_business_delivery(
        run_identity_ref=result["run_identity_ref"],
        business_task_id=task.task_id,
        selected_input_ref=task.selection_ref,
        artifacts=other_docs,
    )
    assert verdict["status"] == "REJECTED"
    assert "ANALYTICS_FILE_READBACK" in verdict["reasons"] or "PRINCIPAL_FILE_READBACK" in verdict["reasons"]


def test_bc24_selection_ref_binding_is_enforced(tmp_path: Path) -> None:
    client = _client(tmp_path)
    task = _task()
    result = _run_business(client, task)
    docs = client.business_delivery_documents(
        run_identity_ref=result["run_identity_ref"], business_task_id=task.task_id,
    )
    verdict = client.verify_business_delivery(
        run_identity_ref=result["run_identity_ref"],
        business_task_id=task.task_id,
        selected_input_ref=_selection("never-selected"),
        artifacts=docs,
    )
    assert verdict["status"] == "REJECTED"
    assert verdict["reasons"] == ["SELECTION_REF_MISMATCH"]


def test_bc28_sealed_run_stays_verifiable_after_delivery_checks(tmp_path: Path) -> None:
    client = _client(tmp_path)
    task = _task()
    result = _run_business(client, task)
    before = client.local_read_run(result["run_identity_ref"])
    docs, first = _docs_and_verdict(client, task, result)
    _, second = _docs_and_verdict(client, task, result)
    assert first["status"] == second["status"] == "ACCEPTED"
    # Content-addressed records are idempotent for identical checks; the
    # sealed run bundle itself is never rewritten by a delivery check.
    assert first["verification_record_ref"] == second["verification_record_ref"]
    after = client.local_read_run(result["run_identity_ref"])
    assert before["files"]["result.json"] == after["files"]["result.json"]
    from hashlib import sha256

    bindings = {
        item["artifact_name"]: item["sha256"] for item in first["artifact_bindings"]
    }
    assert bindings["conditional_principal.txt"] == sha256(
        docs["conditional_principal.txt"]
    ).hexdigest()


# ---------------------------------------------------------------------------
# BC29 — typed errors: stage, code, and unaffected sibling tasks.
# ---------------------------------------------------------------------------


def test_bc29_typed_error_rows_keep_sibling_tasks_intact(tmp_path: Path) -> None:
    client = _client(tmp_path)
    good = _task("task-good")
    # Wire-valid task whose business validation fails in-stage: the payment
    # event day is after the as-of day.
    late_payment = replace(
        _spec().payments[0], event_day="2026-09-10",
    )
    late_spec = replace(_spec(), payments=(late_payment,))
    broken = _task("task-broken", spec=late_spec)
    bundle = client.local_case_bundle(
        case_id="business-case-mixed",
        decision_time="2026-09-11T00:00:00Z",
        business_tasks=(good, broken),
    )
    result = client.evaluate_harness_bundle(
        bundle, case_id="business-case-mixed", issue_queries=[],
    )
    rows = {row["task_id"]: row for row in result["business_results"]}
    assert rows["task-good"]["completion"] == "exact_finite_scenarios"
    assert rows["task-broken"]["completion"] == "failed"
    assert rows["task-broken"]["error_stage"]
    assert rows["task-broken"]["error_code"] == "FUTURE_PAYMENT"
    obligations = [item["code"] for item in rows["task-broken"]["open_obligations"]]
    assert obligations == ["FUTURE_PAYMENT"]
    # The business gap never blocks the transport of the healthy results.
    assert result["run_status"] == "success"


# ---------------------------------------------------------------------------
# BC07/BC09/BC33 — capability metadata is not proof, review or legal basis.
# ---------------------------------------------------------------------------


def test_bc07_bc33_business_rows_never_claim_formal_or_legal_authority(tmp_path: Path) -> None:
    client = _client(tmp_path)
    result = _run_business(client, _task())
    row = result["business_results"][0]
    assert row["legal_basis_status"] == "DECLARED_SYNTHETIC_BASIS_NOT_LEGAL_REVIEW"
    assert row["empirical_status"] == "NO_REAL_DATA"
    assert row["formal_evidence"] == "CROSS_VALIDATED_GENERAL_ALGORITHM_PENDING_KERNEL"
    assert "kernel" not in row["formal_evidence"].lower() or "pending" in row["formal_evidence"].lower()
    obligations = [item["code"] for item in row["open_obligations"]]
    assert "BUSINESS_CONDITIONAL_SCOPE" in obligations
    caps = client.business_capabilities()
    assert caps["capability"] == "jc-business-root/1"
    assert caps["semantic_scope"] == "SYNTHETIC_CONDITIONAL_MODEL_NOT_LITIGATION_FORECAST"
    assert caps["verify_only"] is True
    assert caps["profiles"] == (PROFILE,)


def test_bc09_synthetic_basis_keeps_normative_path_unaffected(tmp_path: Path) -> None:
    """A business run neither creates claims nor touches the rule path."""

    client = _client(tmp_path)
    result = _run_business(client, _task())
    assert result["business_results"]
    assert result["issues"] == []
    assert result["horn"]["mode"] == "not_run"
    # The normative path of the same client still evaluates normally.
    from tests.local.test_local_runtime import FULL_FACTS, QUERIES, _issue_queries

    pack_info = client.local_pack()
    claims = {row["rule_id"]: row["claim"] for row in pack_info["rules"]}
    bundle = client.local_case_bundle(
        case_id="normative-case",
        decision_time="2026-09-01T00:00:00Z",
        facts=FULL_FACTS,
        queries=[
            {"query_id": q["query_id"], "claim": claims[q["claim"]], "profile": q["profile"]}
            for q in QUERIES
        ],
    )
    normative = client.evaluate_harness_bundle(
        bundle,
        case_id="normative-case",
        issue_queries=[
            {"issue_id": q["query_id"], "claim": claims[q["claim"]], "profile": q["profile"]}
            for q in QUERIES
        ],
    )
    assert normative["business_results"] == []
    assert normative["evaluation_count"] == 1


def test_mixed_request_attaches_business_rows_to_formal_result(tmp_path: Path) -> None:
    """Normative issues and the conditional task coexist without merging."""

    from tests.local.test_local_runtime import FULL_FACTS, QUERIES, _issue_queries

    client = _client(tmp_path)
    pack_info = client.local_pack()
    claims = {row["rule_id"]: row["claim"] for row in pack_info["rules"]}
    queries = _issue_queries(claims)
    bundle = client.local_case_bundle(
        case_id="mixed-case",
        decision_time="2026-09-01T00:00:00Z",
        facts=FULL_FACTS,
        queries=queries,
        business_tasks=(_task("task-mixed"),),
    )
    result = client.evaluate_harness_bundle(
        bundle, case_id="mixed-case", issue_queries=queries,
    )
    assert result["evaluation_count"] == 1
    assert len(result["issues"]) == len(QUERIES)
    rows = {row["task_id"]: row for row in result["business_results"]}
    assert rows["task-mixed"]["completion"] == "exact_finite_scenarios"
    # A formal claim and a conditional row are different result kinds; the
    # business row never upgrades the normative answer.
    assert result["decision_status"] != "hypothetical_result"
    read = client.local_read_run(result["run_identity_ref"])
    sealed_rows = read["files"]["result.json"]["business_results_v1"]
    assert sealed_rows[0]["task_id"] == "task-mixed"


# ---------------------------------------------------------------------------
# Verify surface guards.
# ---------------------------------------------------------------------------


def test_delivery_verification_requires_exact_artifact_set(tmp_path: Path) -> None:
    client = _client(tmp_path)
    task = _task()
    result = _run_business(client, task)
    with pytest.raises(ClientV4Error):
        client.verify_business_delivery(
            run_identity_ref=result["run_identity_ref"],
            business_task_id=task.task_id,
            selected_input_ref=task.selection_ref,
            artifacts={"conditional_principal.txt": b"only-one-file"},
        )


def test_delivery_verification_rejects_unknown_task(tmp_path: Path) -> None:
    client = _client(tmp_path)
    task = _task()
    result = _run_business(client, task)
    docs = client.business_delivery_documents(
        run_identity_ref=result["run_identity_ref"], business_task_id=task.task_id,
    )
    verdict = client.verify_business_delivery(
        run_identity_ref=result["run_identity_ref"],
        business_task_id="task-not-in-run",
        selected_input_ref=task.selection_ref,
        artifacts=docs,
    )
    assert verdict["status"] == "REJECTED"
    assert verdict["reasons"] == ["BUSINESS_TASK_NOT_IN_RUN"]
