"""U06/U07 acceptance samples JT28-JT34: procedure four-way table, same-branch
composition gates, and exact dimension arithmetic."""
from __future__ import annotations

import pytest

from compiler_core.canonical_serialization import DigestV4
from compiler_core.contracts import (
    CompositionCandidateV5,
    CompositionChoiceV5,
    CompositionPolicyV5,
    ExactExpressionV5,
    ProcedureAuthorityV5,
)
from compiler_core.domain_composition import (
    CompositionV5Error,
    evaluate_expression_v5,
    validate_composition_choice_v5,
)
from compiler_core.procedure import BurdenRuleOutcomeV5, adjudicate_v5

D = lambda n: DigestV4(f"sha256:{n:064x}")
AUTH = {
    "burden_rule_ref": "rule-burden-1",
    "standard_id": "standard-preponderance",
    "standard_version": "standard/1",
    "finding": "satisfied",
    "reviewer": "authorized-adjudicator",
    "authorization_ref": str(D(9)),
    "request_ref": str(D(1)),
}


def _authority(finding: str = "satisfied") -> ProcedureAuthorityV5:
    return ProcedureAuthorityV5.from_dict({**AUTH, "finding": finding})


def _rule() -> BurdenRuleOutcomeV5:
    return BurdenRuleOutcomeV5("claim_supported", "claim_not_supported")


# ---------------------------------------------------------------------------
# JT28-JT31: procedure decision table
# ---------------------------------------------------------------------------


def test_jt28_incomplete_solve_stays_solver_incomplete() -> None:
    result = adjudicate_v5(
        request_ref=D(1), evaluation_kind="incomplete",
        procedural_status="case-dismissed",
        authority=_authority(), authorization_verified=True, rule_outcomes=_rule(),
    )
    assert result.kind == "solver_incomplete"
    assert result.status is None and result.authority_ref is None
    assert result.open_obligations


def test_jt29_no_extension_without_authority_is_pending_not_loss() -> None:
    result = adjudicate_v5(request_ref=D(1), evaluation_kind="no_extension")
    assert result.kind == "pending_legal_judgment"
    assert result.status is None
    assert result.missing == ("burden-rule-or-finding",)


def test_jt30_procedural_input_precedes_entity_finding() -> None:
    result = adjudicate_v5(
        request_ref=D(1), evaluation_kind="extensions",
        procedural_status="procedure-moved",
        authority=_authority(), authorization_verified=True, rule_outcomes=_rule(),
    )
    assert result.kind == "procedural_disposition"
    result = adjudicate_v5(
        request_ref=D(1), evaluation_kind="extensions",
        authority=_authority("unmet"), authorization_verified=True, rule_outcomes=_rule(),
    )
    assert result.kind == "adjudicated_status"
    assert result.status == "claim_not_supported"


def test_jt31_unverified_reviewer_authority_is_pending() -> None:
    result = adjudicate_v5(
        request_ref=D(1), evaluation_kind="extensions",
        authority=_authority(), authorization_verified=False, rule_outcomes=_rule(),
    )
    assert result.kind == "pending_legal_judgment"
    assert result.missing == ("authorization-unverified",)
    assert result.status is None


# ---------------------------------------------------------------------------
# JT32-JT34: composition gates and exact arithmetic
# ---------------------------------------------------------------------------


def _bundle():
    candidate = CompositionCandidateV5.from_dict(
        {"outcome_id": "o1", "request_ref": str(D(1)), "branch_ref": str(D(2))}
    )
    policy = CompositionPolicyV5.from_dict({
        "policy_id": "policy-merge", "policy_version": "policy/1",
        "request_ref": str(D(1)), "governance_ref": str(D(3)),
    })
    return candidate, policy


def _choice(outcome_id: str, *, branch: DigestV4 = D(2), policy: str = "policy-merge") -> CompositionChoiceV5:
    return CompositionChoiceV5.from_dict({
        "policy_id": policy, "policy_version": "policy/1",
        "request_ref": str(D(1)), "branch_ref": str(branch),
        "selected": [{"outcome_id": outcome_id, "request_ref": str(D(1)), "branch_ref": str(branch)}],
        "child_branch_hint": None,
    })


def test_jt32_choice_gates_reject_bundle_and_policy_violations() -> None:
    candidate, policy = _bundle()
    validate_composition_choice_v5(
        (candidate,), policy, _choice("o1"), allowed_outcome_ids=frozenset({"o1"}),
    )
    with pytest.raises(CompositionV5Error) as caught:
        validate_composition_choice_v5(
            (candidate,), policy, _choice("ghost"), allowed_outcome_ids=frozenset({"o1"}),
        )
    assert caught.value.code == "COMPOSITION_CANDIDATE_UNKNOWN"
    with pytest.raises(CompositionV5Error) as caught:
        validate_composition_choice_v5(
            (candidate,), policy, _choice("o1"), allowed_outcome_ids=frozenset({"other"}),
        )
    assert caught.value.code == "COMPOSITION_POLICY_DENIED"
    other_branch = CompositionCandidateV5.from_dict(
        {"outcome_id": "o1", "request_ref": str(D(1)), "branch_ref": str(D(7))}
    )
    with pytest.raises(CompositionV5Error) as caught:
        validate_composition_choice_v5(
            (other_branch,), policy, _choice("o1"), allowed_outcome_ids=frozenset({"o1"}),
        )
    assert caught.value.code == "COMPOSITION_BRANCH"


def test_jt33_dimension_and_unit_mismatch_is_rejected() -> None:
    lit = lambda **kw: ExactExpressionV5.from_dict({
        "op": "lit", "dimension": kw["dimension"], "left_ref": None, "right_ref": None,
        "literal": kw["literal"], "factor_numerator": None, "factor_denominator": None,
    })
    cny = lit(dimension="money", literal={
        "dimension": "money", "currency": "CNY", "unit": None, "basis": None,
        "numerator": 100, "denominator": 1})
    usd = lit(dimension="money", literal={
        "dimension": "money", "currency": "USD", "unit": None, "basis": None,
        "numerator": 50, "denominator": 1})
    days = lit(dimension="duration", literal={
        "dimension": "duration", "currency": None, "unit": "day", "basis": None,
        "numerator": 30, "denominator": 1})
    months = lit(dimension="duration", literal={
        "dimension": "duration", "currency": None, "unit": "month", "basis": None,
        "numerator": 1, "denominator": 1})
    add = ExactExpressionV5.from_dict({
        "op": "add", "dimension": "money",
        "left_ref": str(D(11)), "right_ref": str(D(12)), "literal": None,
        "factor_numerator": None, "factor_denominator": None,
    })
    with pytest.raises(CompositionV5Error) as caught:
        evaluate_expression_v5(add, {str(D(11)): cny, str(D(12)): usd})
    assert caught.value.code == "EXACT_DIMENSION_MISMATCH"
    add_days = ExactExpressionV5.from_dict({
        "op": "add", "dimension": "duration",
        "left_ref": str(D(11)), "right_ref": str(D(12)), "literal": None,
        "factor_numerator": None, "factor_denominator": None,
    })
    with pytest.raises(CompositionV5Error) as caught:
        evaluate_expression_v5(add_days, {str(D(11)): days, str(D(12)): months})
    assert caught.value.code == "EXACT_DIMENSION_MISMATCH"


def test_jt34_exact_arithmetic_range_rounding_and_denominator() -> None:
    lit = lambda numerator: ExactExpressionV5.from_dict({
        "op": "lit", "dimension": "money", "left_ref": None, "right_ref": None,
        "literal": {"dimension": "money", "currency": "CNY", "unit": None, "basis": None,
                    "numerator": numerator, "denominator": 1},
        "factor_numerator": None, "factor_denominator": None,
    })
    scale = ExactExpressionV5.from_dict({
        "op": "scale", "dimension": "money", "left_ref": str(D(11)),
        "right_ref": None, "literal": None, "factor_numerator": 1, "factor_denominator": 3,
    })
    result = evaluate_expression_v5(scale, {str(D(11)): lit(100)})
    assert (result.value.numerator, result.value.denominator) == (100, 3)
    assert result.rounding_required is True
    # each operand is in safe range, but the product leaves it
    big_lit = lit(2**52)
    big_scale = ExactExpressionV5.from_dict({
        "op": "scale", "dimension": "money", "left_ref": str(D(11)),
        "right_ref": None, "literal": None, "factor_numerator": 2**40, "factor_denominator": 1,
    })
    with pytest.raises(CompositionV5Error) as caught:
        evaluate_expression_v5(big_scale, {str(D(11)): big_lit})
    assert caught.value.code == "EXACT_RANGE"
    with pytest.raises(Exception) as caught:
        ExactExpressionV5.from_dict({
            "op": "scale", "dimension": "money", "left_ref": str(D(11)),
            "right_ref": None, "literal": None, "factor_numerator": 1, "factor_denominator": 0,
        })
    assert "DENOMINATOR_NONPOSITIVE" in str(caught.value)
