"""Scenario analytics and the legal settlement grid for one solved input.

Production port of the retained LMM reference analytics
(``tools/business_relations/reference/business.py``: weight validation,
expectation, threshold event, common-belief interval, grid eligibility;
legal-math-modeling @ 88644bc, MIT License), extended as the plan requires:
production rows carry E[C], E[U], and E[R]=E[C]-E[U] separately, so a clipped
balance is never replaced by the raw residual.

Weights being nonnegative and summing to one is necessary but not sufficient:
world identity, coverage of the solved scenario set, and output consistency
are checked against the independently checked result. Probability rows are a
conditional model analysis, never a case win rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from compiler_core.business_root.checker import check
from compiler_core.business_root.codec import (
    BUSINESS_MODEL_BASIS_V1,
    BusinessRootError,
    require,
)
from compiler_core.business_root.solver import MODE_EXACT, Result
from compiler_core.business_root.spec import DecisionInputs, PrincipalSpec


@dataclass(frozen=True)
class Analytics:
    """Exact scenario analytics over the same Omega as the checked result."""

    context: object
    weights: tuple[tuple[tuple[tuple[str, bool], ...], Fraction], ...]
    threshold: Fraction
    expected_balance: Fraction
    expected_overpayment: Fraction
    expected_residual: Fraction
    event_probability: Fraction
    plaintiff_cost: Fraction
    defendant_cost: Fraction
    plaintiff_settle_cost: Fraction
    defendant_settle_cost: Fraction
    lower: Fraction
    upper: Fraction
    legal_options: tuple[Fraction, ...]
    mutually_acceptable: tuple[Fraction, ...]
    selected: Fraction | None


def _balances(result: Result) -> dict[object, tuple[Fraction, Fraction]]:
    return {
        outcome.world: (outcome.principal_balance, outcome.overpayment_residual)
        for outcome in result.outcomes
    }


def derive_analytics(
    spec: PrincipalSpec, result: Result, model: DecisionInputs
) -> Analytics:
    """Compute the analytics row from an already independently checked result."""

    if not check(spec, result):
        raise BusinessRootError(
            "UNCHECKED_RESULT", "analytics require an independently checked result",
            stage="analytics",
        )
    if result.mode != MODE_EXACT:
        raise BusinessRootError(
            "COMPLETE_SCENARIOS_REQUIRED",
            "exact analytics require every scenario to be solved",
            stage="analytics",
        )
    model.validate_against(spec, {world for world in _balances(result)})
    table = _balances(result)
    zero = Fraction(0)
    expected_balance = sum(
        (weight * table[world][0] for world, weight in model.weights), zero
    )
    expected_overpayment = sum(
        (weight * table[world][1] for world, weight in model.weights), zero
    )
    expected_residual = expected_balance - expected_overpayment
    event_probability = sum(
        (
            weight
            for world, weight in model.weights
            if table[world][0] >= model.threshold
        ),
        zero,
    )
    plaintiff_cost, defendant_cost, plaintiff_settle, defendant_settle = model.costs
    lower = expected_balance - plaintiff_cost + plaintiff_settle
    upper = expected_balance + defendant_cost - defendant_settle
    legal = tuple(sorted(model.legal_options))
    eligible = tuple(option for option in legal if lower <= option <= upper)
    return Analytics(
        spec.context,
        model.weights,
        model.threshold,
        expected_balance,
        expected_overpayment,
        expected_residual,
        event_probability,
        plaintiff_cost,
        defendant_cost,
        plaintiff_settle,
        defendant_settle,
        lower,
        upper,
        legal,
        eligible,
        eligible[0] if eligible else None,
    )


def check_analytics(
    spec: PrincipalSpec, result: Result, model: DecisionInputs, row: object
) -> bool:
    """Independent recomputation of every analytics field; no solver reuse."""

    try:
        if type(row) is not Analytics or row.context != spec.context:
            return False
        if not check(spec, result) or result.mode != MODE_EXACT:
            return False
        model.validate_against(spec, {world for world in _balances(result)})
        rationals = (
            row.threshold, row.expected_balance, row.expected_overpayment,
            row.expected_residual, row.event_probability, row.plaintiff_cost,
            row.defendant_cost, row.plaintiff_settle_cost, row.defendant_settle_cost,
            row.lower, row.upper,
        )
        if any(type(value) is not Fraction for value in rationals):
            return False
        if row.selected is not None and type(row.selected) is not Fraction:
            return False
        if any(type(option) is not Fraction for option in row.legal_options) or any(
            type(option) is not Fraction for option in row.mutually_acceptable
        ):
            return False
        if (
            row.weights,
            row.threshold,
            (
                row.plaintiff_cost,
                row.defendant_cost,
                row.plaintiff_settle_cost,
                row.defendant_settle_cost,
            ),
            set(row.legal_options),
        ) != (model.weights, model.threshold, model.costs, set(model.legal_options)):
            return False
        if len(row.legal_options) != len(model.legal_options):
            return False
        table = _balances(result)
        zero = Fraction(0)
        expectation = sum(
            (weight * table[world][0] for world, weight in model.weights), zero
        )
        overpayment = sum(
            (weight * table[world][1] for world, weight in model.weights), zero
        )
        event = sum(
            (
                weight
                for world, weight in model.weights
                if table[world][0] >= model.threshold
            ),
            zero,
        )
        if (row.expected_balance, row.expected_overpayment) != (expectation, overpayment):
            return False
        if row.expected_residual != expectation - overpayment:
            return False
        if row.event_probability != event:
            return False
        if row.lower + model.costs[0] - model.costs[2] != expectation:
            return False
        if row.upper - model.costs[1] + model.costs[3] != expectation:
            return False
        eligible = {
            option for option in model.legal_options
            if row.lower <= option <= row.upper
        }
        if set(row.mutually_acceptable) != eligible or len(
            row.mutually_acceptable
        ) != len(eligible):
            return False
        return (row.selected is None and not eligible) or row.selected in eligible
    except (TypeError, ValueError, KeyError, AttributeError):
        return False


def event_probabilities(
    result: Result, model: DecisionInputs, events: tuple[tuple[str, Fraction], ...]
) -> dict[str, Fraction]:
    """Probability of named threshold events over C or R (clipped, not raw)."""

    require(
        all(name in {"C", "R"} for name, _ in events),
        "UNKNOWN_EVENT_KIND",
        "named events must address C or R",
        stage="analytics",
    )
    table = _balances(result)
    answer: dict[str, Fraction] = {}
    zero = Fraction(0)
    for name, threshold in events:
        if name == "C":
            answer[name] = sum(
                (
                    weight for world, weight in model.weights
                    if table[world][0] >= threshold
                ),
                zero,
            )
        else:
            raw = {
                world: balance - overpay
                for world, (balance, overpay) in table.items()
            }
            answer[name] = sum(
                (
                    weight for world, weight in model.weights
                    if raw[world] >= threshold
                ),
                zero,
            )
    return answer


def require_model_basis(model: DecisionInputs) -> None:
    if model.basis != BUSINESS_MODEL_BASIS_V1:
        raise BusinessRootError(
            "UNSUPPORTED_MODEL_BASIS",
            "model basis is not the declared settlement grid",
            stage="analytics",
        )


__all__ = [
    "Analytics",
    "check_analytics",
    "derive_analytics",
    "event_probabilities",
    "require_model_basis",
]
