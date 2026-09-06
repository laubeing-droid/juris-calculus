"""U02 acceptance samples JT04-JT07 for the closed V5 contract objects.

JT04 strict contract rejection, JT05 identity rebinding, JT06 empty
obligation/support escape, JT07 wrong-subject admission. These tests exercise
only the public contract authority; deeper gates are covered in their own
work packages.
"""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from compiler_core.canonical_serialization import digest_value
from compiler_core.contracts import (
    ContractV4Error,
    DefeatPolicyV5,
    EvalOutcomeV5,
    ExactQuantityV5,
    PremiseTokenV5,
    QueryResultV5,
    QueryRequestV5,
    ScenarioKeyV5,
    SemanticBranchV5,
    SupportHyperedgeV5,
    V4_OBJECT_REGISTRY,
)

REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
D1 = "sha256:" + "11" * 32
D2 = "sha256:" + "22" * 32
D3 = "sha256:" + "33" * 32


def _error_code(exc: BaseException) -> str | None:
    return getattr(exc, "code", None)


def _scenario(assumptions: tuple[str, ...] = ("disputed-a",)) -> dict:
    return {
        "request_ref": D1,
        "scenario_id": "scenario-1",
        "assumptions": list(assumptions),
        "assumptions_digest": str(digest_value({"assumptions": list(assumptions)})),
    }


# ---------------------------------------------------------------------------
# JT04: strict contract rejection on malformed V5 input
# ---------------------------------------------------------------------------


def test_jt04_v5_objects_reject_unknown_and_missing_fields() -> None:
    payload = _scenario()
    payload["undeclared_extension"] = "forbidden"
    with pytest.raises(ContractV4Error) as caught:
        ScenarioKeyV5.from_dict(payload)
    assert _error_code(caught.value) == "UNKNOWN_FIELD"

    incomplete = {
        "request_ref": D1,
        "scenario_id": "scenario-1",
        "assumptions": [],
    }
    with pytest.raises(ContractV4Error) as caught:
        ScenarioKeyV5.from_dict(incomplete)
    assert _error_code(caught.value) == "MISSING_FIELD"


def test_jt04_bool_is_not_an_integer_and_rationals_stay_canonical() -> None:
    with pytest.raises(ContractV4Error) as caught:
        ExactQuantityV5.from_dict({
            "dimension": "money", "currency": "CNY", "unit": None, "basis": None,
            "numerator": True, "denominator": 1,
        })
    assert _error_code(caught.value) == "TYPE_MISMATCH"

    with pytest.raises(ContractV4Error) as caught:
        ExactQuantityV5.from_dict({
            "dimension": "money", "currency": "CNY", "unit": None, "basis": None,
            "numerator": 2, "denominator": 4,
        })
    assert _error_code(caught.value) == "NON_CANONICAL_RATIONAL"


def test_jt04_profile_and_gate_enums_are_closed() -> None:
    with pytest.raises(ContractV4Error) as caught:
        QueryRequestV5.from_dict({
            "query_id": "q", "claim": "c", "profile": "dung superset",
            "mapping_version": "m", "scenario_ref": D1,
        })
    assert _error_code(caught.value) == "ENUM_VALUE"

    with pytest.raises(ContractV4Error) as caught:
        QueryResultV5.from_dict({
            "query_id": "q", "profile": "grounded", "branch_ref": D1,
            "gate": "wishful", "common": False, "possible": False,
            "common_refuted": False, "possibly_refuted": False,
            "undecided_some": False, "inconsistent_some": False,
            "excluded": False, "witnesses": [],
        })
    assert _error_code(caught.value) == "ENUM_VALUE"


# ---------------------------------------------------------------------------
# JT05: identity rebinding across case/run/scenario/profile/mapping
# ---------------------------------------------------------------------------


def test_jt05_scenario_digest_binds_assumption_set() -> None:
    payload = _scenario(("disputed-a",))
    payload["assumptions_digest"] = str(digest_value({"assumptions": ["disputed-b"]}))
    with pytest.raises(ContractV4Error) as caught:
        ScenarioKeyV5.from_dict(payload)
    assert _error_code(caught.value) == "SELF_DIGEST_MISMATCH"


def test_jt05_branch_digest_changes_with_profile_and_extension() -> None:
    branch_payload = {
        "scenario": _scenario(("disputed-a",)),
        "profile": "grounded",
        "extension_ref": D2,
        "branch_digest": D3,
    }
    body = {k: v for k, v in branch_payload.items() if k != "branch_digest"}
    branch_payload["branch_digest"] = str(digest_value(body))
    branch = SemanticBranchV5.from_dict(json.loads(json.dumps(branch_payload)))

    changed = json.loads(json.dumps(branch_payload))
    changed["profile"] = "preferred"
    body = {k: v for k, v in changed.items() if k != "branch_digest"}
    changed["branch_digest"] = str(digest_value(body))
    rebinding = SemanticBranchV5.from_dict(changed)

    assert branch.branch_digest != rebinding.branch_digest
    tampered = json.loads(json.dumps(branch_payload))
    tampered["profile"] = "preferred"
    with pytest.raises(ContractV4Error) as caught:
        SemanticBranchV5.from_dict(tampered)
    assert _error_code(caught.value) == "SELF_DIGEST_MISMATCH"


def test_jt05_query_identity_separates_mapping_versions() -> None:
    first = QueryRequestV5.from_dict({
        "query_id": "q1", "claim": "claim-a", "profile": "grounded",
        "mapping_version": "mapping/1", "scenario_ref": D1,
    })
    second = QueryRequestV5.from_dict({
        "query_id": "q1", "claim": "claim-a", "profile": "grounded",
        "mapping_version": "mapping/2", "scenario_ref": D1,
    })
    assert first.mapping_version != second.mapping_version
    assert first.canonical_digest() != second.canonical_digest()


# ---------------------------------------------------------------------------
# JT06: empty support/obligation sets cannot pass
# ---------------------------------------------------------------------------


def test_jt06_empty_support_edge_is_rejected() -> None:
    with pytest.raises(ContractV4Error) as caught:
        SupportHyperedgeV5.from_dict({
            "rule_ref": "rule-1", "premises": [], "conclusion": "atom",
            "request_ref": D1,
        })
    assert _error_code(caught.value) == "EMPTY_STRING"


def test_jt06_incomplete_without_open_obligation_is_rejected() -> None:
    family = {"profile": "preferred", "extension_refs": [D2], "coverage": "discovered_only"}
    with pytest.raises(ContractV4Error) as caught:
        EvalOutcomeV5.from_dict({
            "profile": "preferred", "kind": "incomplete", "family": family,
            "empty_family_evidence_ref": None, "open_obligations": [],
        })
    assert _error_code(caught.value) == "EMPTY_STRING"


def test_jt06_partial_alone_cannot_claim_exact_coverage() -> None:
    family = {"profile": "preferred", "extension_refs": [], "coverage": "discovered_only"}
    with pytest.raises(ContractV4Error) as caught:
        EvalOutcomeV5.from_dict({
            "profile": "preferred", "kind": "extensions", "family": family,
            "empty_family_evidence_ref": None, "open_obligations": [],
        })
    assert _error_code(caught.value) == "TYPE_AUTHORITY"


# ---------------------------------------------------------------------------
# JT07: wrong subject/kind admission is rejected at the contract boundary
# ---------------------------------------------------------------------------


def test_jt07_admitted_premise_cannot_smuggle_assumptions() -> None:
    with pytest.raises(ContractV4Error) as caught:
        PremiseTokenV5.from_dict({
            "fact_key": "fact-a", "request_ref": D1, "origin": "admitted",
            "attestation_ref": D2, "assumption_witness": "assumption-1",
            "dependencies": [],
        })
    assert _error_code(caught.value) == "TYPE_AUTHORITY"

    with pytest.raises(ContractV4Error) as caught:
        PremiseTokenV5.from_dict({
            "fact_key": "fact-a", "request_ref": D1, "origin": "assumed",
            "attestation_ref": D2, "assumption_witness": "assumption-1",
            "dependencies": [],
        })
    assert _error_code(caught.value) == "TYPE_AUTHORITY"


def test_jt07_defeat_policy_rejects_unknown_kinds() -> None:
    with pytest.raises(ContractV4Error) as caught:
        DefeatPolicyV5.from_dict({
            "policy_id": "policy-x", "policy_version": "1", "request_ref": D1,
            "allowed_kinds": ["priority_defeat"], "legal_evidence_ref": D3,
        })
    assert _error_code(caught.value) == "ENUM_VALUE"


def test_jt07_attack_kind_migration_table_is_frozen() -> None:
    from compiler_core.contracts import ATTACK_KIND_MIGRATION_V5

    assert ATTACK_KIND_MIGRATION_V5["premise_challenge"] == "undermine"
    assert ATTACK_KIND_MIGRATION_V5["exception"] == "exception_attack"
    assert ATTACK_KIND_MIGRATION_V5["priority_defeat"] is None


def test_jt07_registry_covers_all_v5_objects() -> None:
    for type_id in (
        "ScenarioKeyV5", "QueryRequestV5", "PremiseTokenV5", "StructuredArgumentV5",
        "TypedAttackV5", "DefeatPolicyV5", "EvalOutcomeV5", "SemanticBranchV5",
        "QueryResultV5", "ProcedureResultV5", "ExactExpressionV5",
        "CompositionChoiceV5", "AssuranceEnvelopeV5", "HornDeltaV5",
        "EmpiricalResultV5",
    ):
        assert type_id in V4_OBJECT_REGISTRY
