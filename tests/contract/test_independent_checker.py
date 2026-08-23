from __future__ import annotations

from collections.abc import Callable

import pytest

from compiler_core.backends import (
    AAF_PROVIDER_ID,
    EXACT_PROVIDER_ID,
    HORN_PROVIDER_ID,
    execute_aaf,
    execute_exact,
    execute_horn,
)
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    parse_json_document,
)
from compiler_core.contracts import ContentRefV4
from compiler_core.independent_checker import (
    ARGUMENT_GRAPH_KIND,
    BACKEND_PROBLEM_KIND,
    BACKEND_PROOF_KIND,
    BACKEND_RESULT_KIND,
    BACKEND_SCOPE,
    CHECKER_REPORT_KIND,
    CHECKER_SCOPE,
    PROVIDER_VERSION,
    IndependentCheckerV4,
    _exact_outputs,
    _graph_and_evaluation,
    _horn_analysis,
    _semantic_state_graph,
)
from compiler_core.rule_packs import JSON_MEDIA_TYPE
from tests.contract.test_backend_router import (
    DIRECT_START,
    _conditioned_aaf_problem,
    _constraint,
    _direct_clause,
    _direct_fact,
    _direct_problem,
    _execute,
    _provider,
)
from tests.integration.test_trust_chain import _ChainHarness


def _checker(harness: _ChainHarness) -> IndependentCheckerV4:
    return IndependentCheckerV4(
        harness.resolver,
        harness.trust,
        receipt_issuer="synthetic-service-issuer",
        receipt_signer=harness._sign_receipt,
    )


def _raw(
    harness: _ChainHarness,
    reference: ContentRefV4,
    *,
    kind: str,
    scope: str,
) -> bytes:
    return harness.resolver.resolve_content(
        reference,
        expected_artifact_kind=kind,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=scope,
        max_bytes=harness.resolver.max_artifact_bytes,
    )


def _json(
    harness: _ChainHarness,
    reference: ContentRefV4,
    *,
    kind: str,
    scope: str,
) -> dict[str, object]:
    value = parse_json_document(_raw(harness, reference, kind=kind, scope=scope))
    assert type(value) is dict
    return value


def _independent_bytes(
    problem: dict[str, object],
) -> tuple[bytes, bytes, dict[str, object]]:
    problem_ref = ContentRefV4(
        BACKEND_PROBLEM_KIND,
        DigestV4.from_bytes(canonical_bytes(problem)),
    )
    analysis = _horn_analysis(problem)
    provider_id = problem["provider_id"]
    if provider_id == HORN_PROVIDER_ID:
        outcome = "FIXPOINT"
        outputs = {
            "derived_atoms": sorted(analysis["known"] - analysis["initial_true"]),
            "derived_refs": analysis["fired_refs"],
            "applicable_norms": analysis["applicable_norms"],
            "false_fact_keys": analysis["false_facts"],
            "missing_fact_keys": sorted(
                analysis["required"] - analysis["known"] - set(analysis["facts"])
            ),
            "inactive_rule_ids": sorted(
                row["ivl_id"] for row in analysis["intervals"] if not row["active"]
            ),
        }
        witness = {
            "bound": analysis["bound"],
            "trace": analysis["trace"],
            "least_fixpoint": sorted(analysis["known"]),
            "fired_rule_ids": analysis["fired_rule_ids"],
            "applicable_rule_ids": analysis["applicable_rule_ids"],
            "effective_intervals": analysis["intervals"],
        }
        graph = _semantic_state_graph(
            provider_id=provider_id,
            problem_ref=problem_ref,
            outcome=outcome,
            outputs=outputs,
        )
    elif provider_id == AAF_PROVIDER_ID:
        graph, outputs, condition_evidence = _graph_and_evaluation(problem, analysis)
        outcome = outputs["state"]
        witness = {
            "graph": graph,
            "evaluation": outputs,
            "relation_condition_evidence": condition_evidence,
            "applicable_rule_ids": analysis["applicable_rule_ids"],
            "effective_intervals": analysis["intervals"],
        }
    else:
        assert provider_id == EXACT_PROVIDER_ID
        outcome = "EXACT"
        outputs = _exact_outputs(problem, analysis)
        witness = outputs
        graph = _semantic_state_graph(
            provider_id=provider_id,
            problem_ref=problem_ref,
            outcome=outcome,
            outputs=outputs,
        )
    result = {
        "schema_version": "jc/backend-result/1.0",
        "provider_id": provider_id,
        "provider_version": PROVIDER_VERSION,
        "input_digest": str(problem_ref.digest),
        "status": "COMPLETED",
        "outcome": outcome,
        "outputs": outputs,
    }
    result_bytes = canonical_bytes(result)
    proof = {
        "schema_version": "jc/backend-proof/1.0",
        "provider_id": provider_id,
        "provider_version": PROVIDER_VERSION,
        "input_digest": str(problem_ref.digest),
        "result_digest": str(DigestV4.from_bytes(result_bytes)),
        "witness": witness,
    }
    return result_bytes, canonical_bytes(proof), graph


def _horn_problem() -> dict[str, object]:
    return _direct_problem(
        HORN_PROVIDER_ID,
        facts=[_direct_fact("seed", True), _direct_fact("denied", False)],
        clauses=[
            _direct_clause(
                "constitutive", premise_keys=("seed",), conclusion_key="derived"
            ),
            _direct_clause(
                "obligation",
                modality="OBLIGATION",
                premise_keys=("derived",),
                conclusion_key="must",
            ),
        ],
    )


def _empty_aaf_problem() -> dict[str, object]:
    return _direct_problem(
        AAF_PROVIDER_ID,
        facts=[_direct_fact("unrelated", True)],
        clauses=[
            _direct_clause(
                "inactive-norm",
                modality="OBLIGATION",
                premise_keys=("missing",),
            )
        ],
    )


def _exact_problem() -> dict[str, object]:
    temporal = _constraint(
        "rule-temporal-constraint",
        "exact-time",
        "exact",
        {
            "schema_version": "jc/rule-temporal-constraint/1.0",
            "rule_id": "exact",
            "target_rule_id": "exact",
            "operation": "interval",
            "start": "2026-08-22T11:00:00.000000001Z",
            "end": "2026-08-22T11:00:01Z",
        },
    )
    numeric = _constraint(
        "rule-numeric-constraint",
        "exact-ratio",
        "exact",
        {
            "schema_version": "jc/rule-numeric-constraint/1.0",
            "rule_id": "exact",
            "target_rule_id": "exact",
            "operation": "integer_multiply_ratio",
            "fact_key": "amount",
            "ratio": {"numerator": 3, "denominator": 2},
        },
    )
    return _direct_problem(
        EXACT_PROVIDER_ID,
        facts=[_direct_fact("amount", 10)],
        clauses=[
            _direct_clause(
                "exact",
                modality="OBLIGATION",
                effective_from=DIRECT_START,
                temporal_constraints=[temporal],
                numeric_constraints=[numeric],
            )
        ],
    )


def test_real_horn_execution_issues_and_verifies_bound_receipt() -> None:
    harness, _, _, _, _, executions = _execute("synthetic-positive")
    solver = _provider(executions, HORN_PROVIDER_ID)
    checker = _checker(harness)

    checked = checker.check(
        run_identity_ref=harness.run_identity_ref,
        solver_receipt_ref=solver.receipt_ref,
        now=harness.now,
    )
    assert checker.verify_receipt(checked.receipt_ref, now=harness.now) == checked.receipt
    assert checked.receipt.run_identity_ref == harness.run_identity_ref
    assert checked.receipt.subject_ref == solver.receipt_ref
    assert checked.receipt.backend_result_ref == solver.receipt.backend_result_ref
    assert checked.receipt.status == "PASS"
    assert checked.receipt.output_digest == checked.report_ref.digest
    assert checked.receipt.signature.subject_digest == solver.receipt_ref.digest
    assert checked.receipt.signature.evidence_refs == checked.receipt.witness_refs

    report = _json(
        harness,
        checked.report_ref,
        kind=CHECKER_REPORT_KIND,
        scope=CHECKER_SCOPE,
    )
    graph = _json(
        harness,
        checked.receipt.argument_graph_ref,
        kind=ARGUMENT_GRAPH_KIND,
        scope=CHECKER_SCOPE,
    )
    assert report["status"] == "PASS"
    assert report["subject_ref"] == solver.receipt_ref.to_dict()
    assert graph["provider_id"] == HORN_PROVIDER_ID
    assert graph["problem_ref"] == solver.problem_ref.to_dict()
    assert graph["arguments"] == []

    problem = _json(
        harness,
        solver.problem_ref,
        kind=BACKEND_PROBLEM_KIND,
        scope=BACKEND_SCOPE,
    )
    result_bytes, proof_bytes, _ = _independent_bytes(problem)
    assert _raw(
        harness,
        solver.receipt.backend_result_ref,
        kind=BACKEND_RESULT_KIND,
        scope=BACKEND_SCOPE,
    ) == result_bytes
    assert solver.receipt.proof_ref is not None
    assert _raw(
        harness,
        solver.receipt.proof_ref,
        kind=BACKEND_PROOF_KIND,
        scope=BACKEND_SCOPE,
    ) == proof_bytes


@pytest.mark.parametrize(
    ("problem_factory", "provider"),
    (
        (_horn_problem, execute_horn),
        (lambda: _conditioned_aaf_problem(True), execute_aaf),
        (_empty_aaf_problem, execute_aaf),
        (_exact_problem, execute_exact),
    ),
    ids=("horn", "aaf", "empty-aaf", "exact"),
)
def test_direct_backend_bytes_equal_independent_recomputation(
    problem_factory: Callable[[], dict[str, object]],
    provider: Callable[[bytes], object],
) -> None:
    problem = problem_factory()
    claimed = provider(canonical_bytes(problem))
    result_bytes, proof_bytes, graph = _independent_bytes(problem)

    assert claimed.result_bytes == result_bytes
    assert claimed.proof_bytes == proof_bytes
    if problem["provider_id"] != AAF_PROVIDER_ID:
        assert graph["arguments"] == []
        assert graph["semantic_state"]["outcome"] in {"FIXPOINT", "EXACT"}
    elif problem_factory is _empty_aaf_problem:
        result = parse_json_document(result_bytes)
        assert result["outcome"] == "empty"
        assert graph["arguments"] == []
