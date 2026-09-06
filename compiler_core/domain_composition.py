"""V5 same-branch domain composition and exact arithmetic (ULM13; U07).

Composition policy is data, never code: the allowed candidate set comes from
an admitted, versioned governance record and is passed in as identifiers.
Exact evaluation covers exactly the ULM13 operations ``lit/add/sub/scale``
over reduced rationals; every other numeric operation keeps its own separate
numeric contract and must not claim ULM13 coverage.

This layer proves interpreter correctness only (eval == denote). Choosing a
statutory computation scheme (principal source, rate version, day-count
convention, rounding position) is a governed legal decision recorded in the
admitted rule pack, never something arithmetic decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from compiler_core.canonical_serialization import SAFE_INTEGER_MAX, SAFE_INTEGER_MIN
from compiler_core.contracts import (
    CompositionCandidateV5,
    CompositionChoiceV5,
    CompositionPolicyV5,
    ExactExpressionV5,
    ExactQuantityV5,
)

_ROUNDING_OBLIGATION = "rounding_required"


class CompositionV5Error(ValueError):
    """Stable fail-closed error for composition and exact arithmetic."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise CompositionV5Error(code, detail)


def validate_composition_choice_v5(
    candidates: tuple[CompositionCandidateV5, ...],
    policy: CompositionPolicyV5,
    choice: CompositionChoiceV5,
    *,
    allowed_outcome_ids: frozenset[str],
) -> None:
    """Enforce ChoiceWF: actual candidates, nonempty, same branch, policy allowed."""

    if not candidates:
        _fail("COMPOSITION_BUNDLE_EMPTY", "candidate bundle must not be empty")
    known = {candidate.outcome_id: candidate for candidate in candidates}
    if not choice.selected:
        _fail("COMPOSITION_CHOICE_EMPTY", "selection must be a nonempty subset")
    for selected in choice.selected:
        candidate = known.get(selected.outcome_id)
        if candidate is None:
            _fail(
                "COMPOSITION_CANDIDATE_UNKNOWN",
                f"selected outcome {selected.outcome_id!r} is outside the actual bundle",
            )
        if candidate.request_ref != policy.request_ref:
            _fail("COMPOSITION_REQUEST", "bundle candidates cross requests")
        if selected.request_ref != candidate.request_ref:
            _fail("COMPOSITION_REQUEST", "selection crosses requests")
        if selected.branch_ref != candidate.branch_ref:
            _fail("COMPOSITION_BRANCH", "selection crosses branches")
    if choice.policy_id != policy.policy_id or choice.policy_version != policy.policy_version:
        _fail("COMPOSITION_POLICY_IDENTITY", "choice cites a different policy version")
    for selected in choice.selected:
        if selected.outcome_id not in allowed_outcome_ids:
            _fail(
                "COMPOSITION_POLICY_DENIED",
                f"policy does not allow outcome {selected.outcome_id!r}",
            )


def _quantity_fraction(quantity: ExactQuantityV5) -> Fraction:
    return Fraction(quantity.numerator, quantity.denominator)


def _dimension_key(quantity: ExactQuantityV5) -> tuple[str, str | None, str | None, str | None]:
    return (quantity.dimension, quantity.currency, quantity.unit, quantity.basis)


def _to_contract_quantity(dimension: str, value: Fraction, key: tuple[str, ...]) -> ExactQuantityV5:
    numerator, denominator = value.numerator, value.denominator
    if not SAFE_INTEGER_MIN <= numerator <= SAFE_INTEGER_MAX or not (
        SAFE_INTEGER_MIN <= denominator <= SAFE_INTEGER_MAX
    ):
        _fail("EXACT_RANGE", "exact result leaves the safe integer range")
    quantity = {
        "dimension": dimension,
        "currency": key[1],
        "unit": key[2],
        "basis": key[3],
        "numerator": numerator,
        "denominator": denominator,
    }
    return ExactQuantityV5.from_dict(quantity)


@dataclass(frozen=True, slots=True)
class ExactEvaluationV5:
    """Interpreter result plus the mandatory rounding disclosure."""

    value: ExactQuantityV5
    rounding_required: bool


def evaluate_expression_v5(
    root: ExactExpressionV5,
    operands: dict[str, ExactExpressionV5 | ExactQuantityV5],
) -> ExactEvaluationV5:
    """Evaluate a lit/add/sub/scale expression tree exactly.

    ``operands`` maps operand digests to their admitted nodes. Dimension and
    unit tags must match exactly on both operands; no conversion is ever
    applied implicitly. A non-integral money result is exact but flagged:
    display rounding stays an open obligation until an admitted rule fixes
    position and mode.
    """

    def walk(node: ExactExpressionV5) -> tuple[Fraction, tuple[str, ...]]:
        if node.op == "lit":
            if node.literal is None:
                _fail("EXACT_LITERAL", "lit node without literal")
            return _quantity_fraction(node.literal), _dimension_key(node.literal)
        if node.op == "scale":
            left = operands.get(str(node.left_ref))
            if left is None:
                _fail("EXACT_OPERAND", "scale operand reference is missing")
            value, key = _operand_value(left, walk)
            factor = Fraction(node.factor_numerator, node.factor_denominator)
            return value * factor, key
        left_node = operands.get(str(node.left_ref))
        right_node = operands.get(str(node.right_ref))
        if left_node is None or right_node is None:
            _fail("EXACT_OPERAND", f"{node.op} operand reference is missing")
        left_value, left_key = _operand_value(left_node, walk)
        right_value, right_key = _operand_value(right_node, walk)
        if left_key != right_key:
            _fail(
                "EXACT_DIMENSION_MISMATCH",
                f"{node.op} mixes dimensions {left_key} and {right_key}",
            )
        value = left_value + right_value if node.op == "add" else left_value - right_value
        return value, left_key

    def _operand_value(node, walker):
        if isinstance(node, ExactQuantityV5):
            return _quantity_fraction(node), _dimension_key(node)
        return walker(node)

    value, key = walk(root)
    quantity = _to_contract_quantity(root.dimension, value, key)
    rounding_required = root.dimension == "money" and value.denominator != 1
    return ExactEvaluationV5(quantity, rounding_required)
