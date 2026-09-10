"""Independent checker for the finite conditional principal profile.

Production port of the retained LMM reference checker
(``tools/business_relations/reference/business.py``: structural denotation,
bitmask enumeration over every Boolean assignment, conservation-based
row checking; legal-math-modeling @ 88644bc, MIT License).

The checker never reuses the solver's max clips, its compiled program, or its
enumeration. Every outcome row must satisfy C>=0, U>=0, C*U=0, and
C-U+recognized==principal; coverage must equal the independently formed
scenario set; duplicate, missing, and foreign worlds are rejected.
"""

from __future__ import annotations

from fractions import Fraction

from compiler_core.business_root.codec import BusinessRootError
from compiler_core.business_root.solver import (
    MODE_EXACT,
    MODE_INCONSISTENT,
    MODE_PARTIAL,
    Outcome,
    Result,
)
from compiler_core.business_root.spec import (
    PrincipalSpec,
    World,
    all_boolean_assignments,
    valid_world_shape,
)


def denote(formula, world: World) -> bool:
    """Structural denotation; the checker's own evaluation path."""

    values = dict(world)
    if formula.op == "true":
        return True
    if formula.op == "false":
        return False
    if formula.op == "atom":
        return values[formula.atom]
    if formula.op == "not":
        return not denote(formula.children[0], world)
    if formula.op == "and":
        return all(denote(child, world) for child in formula.children)
    return any(denote(child, world) for child in formula.children)


def checker_worlds(spec: PrincipalSpec) -> frozenset[World]:
    """Enumerate every Boolean assignment independently, then restrict it."""

    spec.validate()
    keys = [key for key, _ in spec.facts]
    fixed = dict(spec.facts)
    domain: list[World] = []
    for assignment in all_boolean_assignments(tuple(keys)):
        world = tuple(zip(keys, assignment))
        if all(
            fixed[key] is None or fixed[key] is value for key, value in world
        ) and denote(spec.constraint, world):
            domain.append(world)
    return frozenset(domain)


def recognized_total(spec: PrincipalSpec, world: World) -> Fraction:
    """Sum of payments recognized under one world (independent recomputation)."""

    assignments = dict(world)
    return sum(
        (
            payment.amount
            for payment in spec.payments
            if assignments[payment.recognition_atom]
        ),
        Fraction(0),
    )


def check(spec: PrincipalSpec, report: object) -> bool:
    """Fixed checker: no callback, no execution of certificate-supplied code."""

    try:
        if type(report) is not Result or report.context != spec.context:
            return False
        if report.mode not in {MODE_EXACT, MODE_PARTIAL, MODE_INCONSISTENT}:
            return False
        domain = checker_worlds(spec)
        if not domain:
            return (
                report.mode == MODE_INCONSISTENT
                and not report.outcomes
                and not report.pending
            )
        if report.mode == MODE_INCONSISTENT:
            return False
        seen: list[World] = []
        for outcome in report.outcomes:
            if type(outcome) is not Outcome:
                return False
            if (
                outcome.context,
                outcome.relation_id,
                outcome.creditor,
                outcome.debtor,
                outcome.debt_id,
                outcome.basis_ids,
                outcome.asof_day,
                outcome.conclusion_kind,
            ) != (
                spec.context,
                spec.relation_id,
                spec.creditor,
                spec.debtor,
                spec.debt_id,
                tuple(source.source_id for source in spec.sources),
                spec.asof_day,
                "CONDITIONAL_PRINCIPAL_BALANCE_NOT_JUDGMENT",
            ):
                return False
            if not valid_world_shape(outcome.world, spec):
                return False
            if outcome.world not in domain or outcome.world in seen:
                return False
            seen.append(outcome.world)
            balance, overpay = outcome.principal_balance, outcome.overpayment_residual
            if type(balance) is not Fraction or type(overpay) is not Fraction:
                return False
            if min(balance, overpay) < 0 or balance * overpay != 0:
                return False
            if balance - overpay + recognized_total(spec, outcome.world) != spec.principal:
                return False
        for world in report.pending:
            if not valid_world_shape(world, spec):
                return False
        if len(set(report.pending)) != len(report.pending):
            return False
        if set(seen) & set(report.pending):
            return False
        if frozenset(seen) | frozenset(report.pending) != domain:
            return False
        if report.mode == MODE_EXACT:
            return not report.pending
        return bool(report.pending)
    except (TypeError, ValueError, KeyError, AttributeError):
        return False


def require_checked(spec: PrincipalSpec, report: object) -> Result:
    """Return the report when it passes; raise a typed error otherwise."""

    if not check(spec, report):
        raise BusinessRootError(
            "BUSINESS_CHECKER_REJECT",
            "the solver report failed independent conservation or coverage checks",
            stage="checker",
        )
    return report


__all__ = [
    "check",
    "checker_worlds",
    "denote",
    "recognized_total",
    "require_checked",
]
