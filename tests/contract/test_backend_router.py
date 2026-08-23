from __future__ import annotations

from copy import deepcopy

import pytest

from compiler_core.backend_router import (
    BACKEND_CAPABILITY_KIND,
    BACKEND_PROOF_KIND,
    BACKEND_RESULT_KIND,
    BACKEND_SCOPE,
    BackendRouterV4,
)
from compiler_core.backends import (
    AAF_PROVIDER_ID,
    EXACT_PROVIDER_ID,
    HORN_PROVIDER_ID,
    PROVIDER_VERSION,
    ProviderV4Error,
    execute_aaf,
    execute_exact,
    execute_horn,
    provider_runtime_identity,
)
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import ContentRefV4, ResourceLimitsV4
from compiler_core.legal_ir import LegalIRCompilerV4
from compiler_core.rule_packs import JSON_MEDIA_TYPE
from tests.integration.test_trust_chain import FACT_KEY, _ChainHarness


DIRECT_TIME = "2026-08-22T11:00:00.5Z"
DIRECT_START = "2026-01-01T00:00:00Z"


def _ref(kind: str, label: str) -> dict[str, str]:
    return ContentRefV4(kind, digest_value({"direct-ref": label})).to_dict()


def _direct_fact(
    proposition: str,
    value: object,
    *,
    label: str | None = None,
) -> dict[str, object]:
    return {
        "admission_receipt_ref": _ref(
            "fact-admission-receipt", f"receipt-{label or proposition}"
        ),
        "fact_ref": _ref("admitted-fact-v4", label or proposition),
        "case_scope": "direct-case",
        "proposition": proposition,
        "value_kind": "boolean" if type(value) is bool else "integer",
        "value": value,
    }


def _direct_clause(
    ivl_id: str,
    *,
    modality: str = "CONSTITUTIVE",
    premise_keys: tuple[str, ...] = (),
    conclusion_key: str | None = None,
    effective_from: str = DIRECT_START,
    effective_to: str | None = None,
    relations: list[dict[str, object]] | None = None,
    temporal_constraints: list[dict[str, object]] | None = None,
    numeric_constraints: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    premise_refs = [
        _ref("rule-premise", f"{ivl_id}-premise-{index}-{key}")
        for index, key in enumerate(premise_keys)
    ]
    conclusion_ref = _ref("rule-conclusion", f"{ivl_id}-conclusion")
    return {
        "ivl_id": ivl_id,
        "ivl_ref": _ref("legal-ivl-v4", ivl_id),
        "rule_ref": _ref("rule-v4", ivl_id),
        "translation_receipt_refs": [
            _ref("rule-to-spec-receipt", ivl_id),
            _ref("spec-to-ivl-receipt", ivl_id),
        ],
        "premise_refs": premise_refs,
        "premises": [
            {
                "schema_version": "jc/rule-premise/1.0",
                "rule_id": ivl_id,
                "fact_key": key,
                "required": True,
            }
            for key in premise_keys
        ],
        "conclusion_ref": conclusion_ref,
        "conclusion": {
            "schema_version": "jc/rule-conclusion/1.0",
            "rule_id": ivl_id,
            "fact_key": conclusion_key or f"{ivl_id}.conclusion",
        },
        "derivation_refs": [_ref("legal-ir-proof-obligation", ivl_id)],
        "modality": modality,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "relations": [] if relations is None else relations,
        "temporal_constraints": (
            [] if temporal_constraints is None else temporal_constraints
        ),
        "numeric_constraints": [] if numeric_constraints is None else numeric_constraints,
    }


def _direct_problem(
    provider_id: str,
    *,
    facts: list[dict[str, object]],
    clauses: list[dict[str, object]],
    decision_time: str = DIRECT_TIME,
) -> dict[str, object]:
    return {
        "schema_version": "jc/backend-problem/1.0",
        "provider_id": provider_id,
        "run_identity_ref": _ref("run-identity-v4", "direct-run"),
        "request_ref": _ref("case-request-v4", "direct-request"),
        "case_scope": "direct-case",
        "limits_ref": _ref("backend-limits-v4", "direct-limits"),
        "decision_time": decision_time,
        "seed": 0,
        "features": {
            "conflict_structure": provider_id == AAF_PROVIDER_ID,
            "temporal_constraints": provider_id == EXACT_PROVIDER_ID,
            "numeric_constraints": provider_id == EXACT_PROVIDER_ID,
        },
        "facts": facts,
        "clauses": clauses,
    }


def _run_document(raw: bytes) -> dict[str, object]:
    value = parse_json_document(raw)
    assert type(value) is dict
    return value


def _provider_error_code(call) -> str:
    with pytest.raises(ProviderV4Error) as caught:
        call()
    return caught.value.code


def _relation(
    kind: str,
    source: str,
    target: str,
    *,
    condition: str,
) -> dict[str, object]:
    if kind == "attack":
        return {
            "kind": "attack",
            "source_ref": _ref("rule-exception", f"{source}-attack"),
            "attack_type": "exception",
            "target_aspect": "rule_applicability",
            "source": source,
            "target": target,
            "condition_fact_key": condition,
        }
    return {
        "kind": "priority",
        "source_ref": _ref("rule-priority", f"{source}-priority"),
        "source": source,
        "target": target,
        "condition": condition,
    }


def _conditioned_aaf_problem(
    condition_value: bool | None,
    *,
    reverse: bool = False,
) -> dict[str, object]:
    relations = [
        _relation("attack", "norm-a", "norm-b", condition="attack-on"),
        _relation("priority", "norm-a", "norm-b", condition="priority-on"),
    ]
    clauses = [
        _direct_clause(
            "norm-a",
            modality="OBLIGATION",
            premise_keys=("seed-a",),
            conclusion_key="claim-a",
            relations=list(reversed(relations)) if reverse else relations,
        ),
        _direct_clause(
            "norm-b",
            modality="OBLIGATION",
            premise_keys=("seed-b",),
            conclusion_key="claim-b",
        ),
    ]
    facts = [_direct_fact("seed-a", True), _direct_fact("seed-b", True)]
    if condition_value is not None:
        facts.extend(
            (
                _direct_fact("attack-on", condition_value),
                _direct_fact("priority-on", condition_value),
            )
        )
    if reverse:
        clauses.reverse()
        facts.reverse()
    return _direct_problem(AAF_PROVIDER_ID, facts=facts, clauses=clauses)


def _constraint(
    kind: str,
    label: str,
    owner: str,
    expression: dict[str, object],
    *,
    target: str | None = None,
) -> dict[str, object]:
    return {
        "constraint_ref": _ref(kind, label),
        "owner_ivl_id": owner,
        "target_ivl_id": owner if target is None else target,
        "expression": expression,
    }


def _system(*rule_ids: str):
    harness = _ChainHarness()
    pack = harness.verify_pack()
    compiler = LegalIRCompilerV4(
        harness.pack_verifier,
        receipt_issuer="synthetic-service-issuer",
        receipt_signer=harness._sign_receipt,
    )
    refs = {
        rule.rule_id: reference
        for reference, rule in zip(pack.manifest.rule_refs, pack.rules, strict=True)
    }
    compilations = tuple(
        compiler.compile_rule(
            pack,
            rule_ref=refs[rule_id],
            run_identity_ref=harness.run_identity_ref,
            now=harness.now,
        )
        for rule_id in rule_ids
    )
    fact_receipt_ref, admitted_fact_ref = harness.admit_fact()
    router = BackendRouterV4(
        compiler,
        harness.fact_service,
        receipt_signer=harness._sign_receipt,
    )
    return harness, compilations, fact_receipt_ref, admitted_fact_ref, router


def _execute(*rule_ids: str):
    harness, compilations, fact_receipt_ref, admitted_fact_ref, router = _system(
        *rule_ids
    )
    executions = router.execute(
        compilations,
        run_identity_ref=harness.run_identity_ref,
        fact_admission_receipt_refs=(fact_receipt_ref,),
        limits=ResourceLimitsV4(),
        now=harness.now,
    )
    return (
        harness,
        compilations,
        fact_receipt_ref,
        admitted_fact_ref,
        router,
        executions,
    )


def _document(
    harness: _ChainHarness,
    reference: ContentRefV4,
    *,
    kind: str,
) -> dict[str, object]:
    raw = harness.resolver.resolve_content(
        reference,
        expected_artifact_kind=kind,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=BACKEND_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    )
    value = parse_json_document(raw)
    assert type(value) is dict
    return value


def _provider(executions, provider_id: str):
    return next(
        execution
        for execution in executions
        if execution.invocation.provider_id == provider_id
    )


def test_router_binds_compiler_issued_ivl_and_verified_fact_receipt() -> None:
    (
        harness,
        compilations,
        fact_receipt_ref,
        admitted_fact_ref,
        _,
        executions,
    ) = _execute("synthetic-positive")

    assert len(executions) == 1
    execution = executions[0]
    problem = _document(harness, execution.problem_ref, kind=execution.problem_ref.kind)
    assert execution.completed is True
    assert execution.receipt.run_identity_ref == harness.run_identity_ref
    assert problem["decision_time"] == harness.request.decision_time.wire
    assert problem["facts"] == [
        {
            "admission_receipt_ref": fact_receipt_ref.to_dict(),
            "fact_ref": admitted_fact_ref.to_dict(),
            "case_scope": "synthetic-case",
            "proposition": FACT_KEY,
            "value": True,
            "value_kind": "boolean",
        }
    ]
    assert problem["clauses"][0]["ivl_ref"] == compilations[0].ivl_ref.to_dict()
    assert problem["clauses"][0]["translation_receipt_refs"] == [
        compilations[0].rule_to_spec_receipt_ref.to_dict(),
        compilations[0].spec_to_ivl_receipt_ref.to_dict(),
    ]


def test_horn_separates_fact_closure_norms_and_actual_derivation_evidence() -> None:
    first_ref = _ref("rule-conclusion", "a-first-conclusion")
    clauses = [
        _direct_clause(
            "a-first", premise_keys=("seed",), conclusion_key="derived"
        ),
        _direct_clause(
            "b-same-head", premise_keys=("seed",), conclusion_key="derived"
        ),
        _direct_clause(
            "c-initial-head", premise_keys=("seed",), conclusion_key="already"
        ),
        *[
            _direct_clause(
                f"norm-{modality.lower()}",
                modality=modality,
                premise_keys=("derived",),
                conclusion_key=f"deontic-{modality.lower()}",
            )
            for modality in ("OBLIGATION", "PROHIBITION", "PERMISSION")
        ],
        _direct_clause(
            "z-no-modality-leak",
            premise_keys=("deontic-obligation",),
            conclusion_key="must-not-derive",
        ),
        _direct_clause(
            "z-missing", premise_keys=("absent",), conclusion_key="also-absent"
        ),
        _direct_clause(
            "z-false", premise_keys=("denied",), conclusion_key="also-denied"
        ),
    ]
    clauses[0]["conclusion_ref"] = first_ref
    problem = _direct_problem(
        HORN_PROVIDER_ID,
        facts=[
            _direct_fact("seed", True),
            _direct_fact("already", True),
            _direct_fact("denied", False),
        ],
        clauses=clauses,
    )

    run = execute_horn(canonical_bytes(problem))
    result = _run_document(run.result_bytes)
    proof = _run_document(run.proof_bytes)
    outputs = result["outputs"]
    witness = proof["witness"]

    assert outputs["derived_atoms"] == ["derived"]
    assert outputs["derived_refs"] == [first_ref]
    assert outputs["false_fact_keys"] == ["denied"]
    assert outputs["missing_fact_keys"] == ["absent", "deontic-obligation"]
    assert outputs["applicable_norms"] == [
        {
            "ivl_id": f"norm-{modality.lower()}",
            "rule_ref": _ref("rule-v4", f"norm-{modality.lower()}"),
            "conclusion_ref": _ref(
                "rule-conclusion", f"norm-{modality.lower()}-conclusion"
            ),
            "modality": modality,
        }
        for modality in ("OBLIGATION", "PERMISSION", "PROHIBITION")
    ]
    assert witness["least_fixpoint"] == ["already", "derived", "seed"]
    assert witness["fired_rule_ids"] == ["a-first"]
    assert set(witness["applicable_rule_ids"]) == {
        "a-first",
        "b-same-head",
        "c-initial-head",
        "norm-obligation",
        "norm-permission",
        "norm-prohibition",
    }


@pytest.mark.parametrize(
    ("decision_time", "active"),
    (
        ("2025-12-31T23:59:59.999999999Z", False),
        (DIRECT_START, True),
        ("2026-12-31T23:59:59.999999999Z", True),
        ("2027-01-01T00:00:00Z", False),
        ("2027-01-01T00:00:00.000000001Z", False),
    ),
)
def test_horn_rule_interval_is_half_open(
    decision_time: str,
    active: bool,
) -> None:
    clause = _direct_clause(
        "bounded",
        conclusion_key="bounded-derived",
        effective_to="2027-01-01T00:00:00Z",
    )
    problem = _direct_problem(
        HORN_PROVIDER_ID,
        facts=[_direct_fact("unrelated", True)],
        clauses=[clause],
        decision_time=decision_time,
    )

    run = execute_horn(canonical_bytes(problem))
    result = _run_document(run.result_bytes)
    proof = _run_document(run.proof_bytes)
    assert result["outputs"]["derived_atoms"] == (
        ["bounded-derived"] if active else []
    )
    assert result["outputs"]["inactive_rule_ids"] == ([] if active else ["bounded"])
    assert proof["witness"]["effective_intervals"] == [
        {
            "ivl_id": "bounded",
            "effective_from": DIRECT_START,
            "effective_to": "2027-01-01T00:00:00Z",
            "active": active,
        }
    ]


def test_router_horn_problem_includes_every_compiled_ivl() -> None:
    harness, _, _, _, _, executions = _execute(
        "synthetic-positive", "synthetic-missing-disputed"
    )
    execution = _provider(executions, HORN_PROVIDER_ID)
    problem = _document(harness, execution.problem_ref, kind=execution.problem_ref.kind)
    result = _document(
        harness,
        execution.receipt.backend_result_ref,
        kind=BACKEND_RESULT_KIND,
    )

    assert [row["ivl_id"] for row in problem["clauses"]] == [
        "synthetic-missing-disputed",
        "synthetic-positive",
    ]
    assert result["outputs"]["derived_atoms"] == []
    assert result["outputs"]["applicable_norms"] == [
        {
            "ivl_id": "synthetic-positive",
            "rule_ref": problem["clauses"][1]["rule_ref"],
            "conclusion_ref": problem["clauses"][1]["conclusion_ref"],
            "modality": "OBLIGATION",
        }
    ]
    assert result["outputs"]["missing_fact_keys"] == [
        "synthetic-missing-disputed.required-fact"
    ]


def test_router_aaf_excludes_rules_and_edges_with_absent_conditions() -> None:
    harness, _, _, _, _, executions = _execute(
        "synthetic-exception-priority", "synthetic-positive"
    )
    execution = _provider(executions, AAF_PROVIDER_ID)
    proof = _document(
        harness,
        execution.receipt.proof_ref,
        kind=BACKEND_PROOF_KIND,
    )
    graph = proof["witness"]["graph"]
    evaluation = proof["witness"]["evaluation"]

    assert [row["argument_id"] for row in graph["arguments"]] == [
        "synthetic-positive"
    ]
    assert graph["attacks"] == []
    assert graph["priority_edges"] == []
    assert evaluation["effective_attacks"] == []
    assert [row["label"] for row in evaluation["labels"]] == ["IN"]


@pytest.mark.parametrize(
    ("condition_value", "edge_count"),
    ((None, 0), (False, 0), (True, 1)),
)
def test_aaf_conditions_require_true_facts_and_bind_typed_evidence(
    condition_value: bool | None,
    edge_count: int,
) -> None:
    problem = _conditioned_aaf_problem(condition_value)
    run = execute_aaf(canonical_bytes(problem))
    proof = _run_document(run.proof_bytes)
    graph = proof["witness"]["graph"]

    assert len(graph["attacks"]) == edge_count
    assert len(graph["priority_edges"]) == edge_count
    assert len(proof["witness"]["relation_condition_evidence"]) == edge_count * 2
    if condition_value is True:
        assert graph["priority_edges"][0]["condition_ref"] == _ref(
            "admitted-fact-v4", "priority-on"
        )
        assert {
            row["condition_ref"]["digest"]
            for row in proof["witness"]["relation_condition_evidence"]
        } == {
            _ref("admitted-fact-v4", "attack-on")["digest"],
            _ref("admitted-fact-v4", "priority-on")["digest"],
        }


def test_aaf_output_is_stable_under_clause_fact_and_relation_order() -> None:
    first = execute_aaf(canonical_bytes(_conditioned_aaf_problem(True)))
    reversed_run = execute_aaf(
        canonical_bytes(_conditioned_aaf_problem(True, reverse=True))
    )
    first_result = _run_document(first.result_bytes)
    reversed_result = _run_document(reversed_run.result_bytes)
    first_proof = _run_document(first.proof_bytes)
    reversed_proof = _run_document(reversed_run.proof_bytes)

    assert first_result["outputs"] == reversed_result["outputs"]
    assert first_proof["witness"] == reversed_proof["witness"]


def test_aaf_empty_applicability_is_a_completed_empty_framework() -> None:
    problem = _direct_problem(
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

    run = execute_aaf(canonical_bytes(problem))
    result = _run_document(run.result_bytes)
    proof = _run_document(run.proof_bytes)
    empty_graph = {
        "schema_version": "jc/argument-graph-v4/1.0",
        "arguments": [],
        "attacks": [],
        "priority_edges": [],
        "permission_relations": [],
    }
    expected_graph_ref = ContentRefV4(
        "argument-graph-v4", DigestV4.from_bytes(canonical_bytes(empty_graph))
    ).to_dict()
    expected_outputs = {
        "schema_version": "jc/argumentation-evaluation-v4/1.0",
        "graph_ref": expected_graph_ref,
        "labels": [],
        "effective_attacks": [],
        "permission_resolutions": [],
        "exception_resolutions": [],
        "claim_projection": [],
        "priority_cycles": [],
        "state": "empty",
    }
    assert run.status == "COMPLETED"
    assert result["outputs"] == expected_outputs
    assert proof["witness"]["graph"] == empty_graph
    assert proof["witness"]["evaluation"] == expected_outputs
    assert proof["witness"]["relation_condition_evidence"] == []
    assert proof["witness"]["applicable_rule_ids"] == []


def test_aaf_permission_requires_a_prohibition_with_the_same_claim() -> None:
    permission = {
        "kind": "permission",
        "source_ref": _ref("rule-permission", "permission-source"),
        "permission_id": "permission-p",
        "permits": "p",
        "relation_kind": "exception",
        "source": "permission",
        "target": "target",
    }
    facts = [_direct_fact("permission-seed", True), _direct_fact("target-seed", True)]

    def problem(target_modality: str) -> dict[str, object]:
        return _direct_problem(
            AAF_PROVIDER_ID,
            facts=facts,
            clauses=[
                _direct_clause(
                    "permission",
                    modality="PERMISSION",
                    premise_keys=("permission-seed",),
                    conclusion_key="p",
                    relations=[permission],
                ),
                _direct_clause(
                    "target",
                    modality=target_modality,
                    premise_keys=("target-seed",),
                    conclusion_key="p",
                ),
            ],
        )

    assert _provider_error_code(
        lambda: execute_aaf(canonical_bytes(problem("OBLIGATION")))
    ) == "UNSUPPORTED_SEMANTICS"
    run = execute_aaf(canonical_bytes(problem("PROHIBITION")))
    proof = _run_document(run.proof_bytes)
    assert run.status == "COMPLETED"
    assert len(proof["witness"]["graph"]["permission_relations"]) == 1
    assert len(proof["witness"]["graph"]["attacks"]) == 1


def test_aaf_rejects_dormant_unknown_fields_and_duplicate_relation_sources() -> None:
    base = _conditioned_aaf_problem(None)
    unknown = deepcopy(base)
    unknown["clauses"][0]["premises"][0]["fact_key"] = "missing"
    unknown["clauses"][0]["relations"][0]["unknown"] = True
    assert _provider_error_code(
        lambda: execute_aaf(canonical_bytes(unknown))
    ) == "UNSUPPORTED_SEMANTICS"

    duplicate = deepcopy(base)
    duplicate["clauses"][0]["relations"] = [
        duplicate["clauses"][0]["relations"][0],
        deepcopy(duplicate["clauses"][0]["relations"][0]),
    ]
    assert _provider_error_code(
        lambda: execute_aaf(canonical_bytes(duplicate))
    ) == "PROVIDER_INPUT_SCHEMA"


def test_permission_temporal_fixture_fails_closed_for_obligation_target() -> None:
    harness, _, _, _, _, executions = _execute(
        "synthetic-permission-temporal", "synthetic-positive"
    )

    assert tuple(item.invocation.provider_id for item in executions) == (
        HORN_PROVIDER_ID,
        AAF_PROVIDER_ID,
        EXACT_PROVIDER_ID,
    )
    assert {
        item.invocation.provider_id: item.receipt.status for item in executions
    } == {
        HORN_PROVIDER_ID: "COMPLETED",
        AAF_PROVIDER_ID: "UNSUPPORTED_SEMANTICS",
        EXACT_PROVIDER_ID: "COMPLETED",
    }
    exact = _provider(executions, EXACT_PROVIDER_ID)
    exact_result = _document(
        harness,
        exact.receipt.backend_result_ref,
        kind=BACKEND_RESULT_KIND,
    )
    assert exact_result["outputs"]["temporal"] == []


def test_exact_provider_preserves_nanoseconds_and_reduced_rationals() -> None:
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
    numeric = [
        _constraint(
            "rule-numeric-constraint",
            label,
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
        for label in ("exact-ratio-a", "exact-ratio-b")
    ]
    inactive_numeric = _constraint(
        "rule-numeric-constraint",
        "inactive-add",
        "inactive",
        {
            "schema_version": "jc/rule-numeric-constraint/1.0",
            "rule_id": "inactive",
            "target_rule_id": "inactive",
            "operation": "integer_add",
            "operands": [1, 2],
        },
    )
    problem = _direct_problem(
        EXACT_PROVIDER_ID,
        facts=[_direct_fact("amount", 10)],
        clauses=[
            _direct_clause(
                "exact",
                modality="OBLIGATION",
                temporal_constraints=[temporal],
                numeric_constraints=numeric,
            ),
            _direct_clause(
                "inactive",
                modality="OBLIGATION",
                effective_from="2027-01-01T00:00:00Z",
                numeric_constraints=[inactive_numeric],
            ),
        ],
    )

    run = execute_exact(canonical_bytes(problem))
    result = _run_document(run.result_bytes)
    outputs = result["outputs"]
    assert outputs["temporal"] == [
        {
            "constraint_ref": temporal["constraint_ref"],
            "owner_ivl_id": "exact",
            "target_ivl_id": "exact",
            "operation": "interval",
            "active": True,
            "duration": {"seconds": 0, "nanoseconds": 999_999_999},
        }
    ]
    assert outputs["numeric"] == [
        {
            "constraint_ref": item["constraint_ref"],
            "owner_ivl_id": "exact",
            "target_ivl_id": "exact",
            "operation": "integer_multiply_ratio",
            "rational": {"numerator": 15, "denominator": 1},
        }
        for item in numeric
    ]
    assert outputs["rule_intervals"] == [
        {
            "ivl_id": "exact",
            "effective_from": DIRECT_START,
            "effective_to": None,
            "active": True,
        },
        {
            "ivl_id": "inactive",
            "effective_from": "2027-01-01T00:00:00Z",
            "effective_to": None,
            "active": False,
        },
    ]
    assert all(
        row["constraint_ref"] != inactive_numeric["constraint_ref"]
        for row in outputs["numeric"]
    )


def test_exact_rejects_duplicate_refs_and_constraint_owner_drift() -> None:
    constraint = _constraint(
        "rule-numeric-constraint",
        "duplicate",
        "exact",
        {
            "schema_version": "jc/rule-numeric-constraint/1.0",
            "rule_id": "exact",
            "target_rule_id": "exact",
            "operation": "integer_add",
            "operands": [1, 2],
        },
    )

    def run(rows: list[dict[str, object]]) -> object:
        problem = _direct_problem(
            EXACT_PROVIDER_ID,
            facts=[_direct_fact("seed", True)],
            clauses=[
                _direct_clause(
                    "exact", modality="OBLIGATION", numeric_constraints=rows
                )
            ],
        )
        return execute_exact(canonical_bytes(problem))

    assert _provider_error_code(
        lambda: run([constraint, deepcopy(constraint)])
    ) == "PROVIDER_INPUT_SCHEMA"
    drifted = deepcopy(constraint)
    drifted["owner_ivl_id"] = "other"
    drifted["expression"]["rule_id"] = "other"
    assert _provider_error_code(lambda: run([drifted])) == "PROVIDER_INPUT_SCHEMA"


def test_replay_reexecutes_identical_canonical_semantics() -> None:
    harness, _, _, _, router, executions = _execute("synthetic-positive")
    execution = executions[0]
    original = (
        execution.problem_ref,
        execution.receipt.backend_result_ref,
        execution.receipt.proof_ref,
    )

    assert router.replay(execution, now=harness.now) is True
    assert router.replay(execution, now=harness.now) is True
    assert (
        execution.problem_ref,
        execution.receipt.backend_result_ref,
        execution.receipt.proof_ref,
    ) == original


def test_invocation_binds_live_binary_package_and_build_inputs() -> None:
    harness, _, _, _, _, executions = _execute("synthetic-positive")
    execution = executions[0]
    binary_digest, package_digest, build_inputs = provider_runtime_identity()
    capability = _document(
        harness,
        execution.invocation.provider_capability_ref,
        kind=BACKEND_CAPABILITY_KIND,
    )
    build_body = dict(capability)
    recorded_build_digest = DigestV4.parse(build_body.pop("provider_build_digest"))

    assert execution.invocation.provider_id == HORN_PROVIDER_ID
    assert execution.invocation.provider_version == PROVIDER_VERSION
    assert execution.invocation.provider_binary_digest == binary_digest
    assert execution.invocation.provider_package_digest == package_digest
    assert capability["provider_build_inputs"] == build_inputs
    assert execution.invocation.provider_build_digest == recorded_build_digest
    assert recorded_build_digest == digest_value(build_body)
