"""Solver side of the finite conditional principal profile.

Production port of the retained LMM reference solver
(``tools/business_relations/reference/business.py``: formula compilation,
stack-machine evaluation, finite scenario enumeration, and the max/clip
outcome construction; legal-math-modeling @ 88644bc, MIT License).

The solver uses its own enumeration and its own max-based clips. Correctness
is never established here: :mod:`compiler_core.business_root.checker`
re-derives everything with independent semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product

from compiler_core.business_root.codec import BusinessRootError, require
from compiler_core.business_root.spec import (
    PrincipalSpec,
    World,
    all_boolean_assignments,
)

MODE_EXACT = "EXACT_FINITE_SCENARIOS"
MODE_PARTIAL = "PARTIAL_SCENARIOS"
MODE_INCONSISTENT = "INCONSISTENT_ASSUMPTIONS"


def compile_formula(formula) -> tuple[tuple[str, str], ...]:
    """Compile the guard into a flat stack program (solver TCB)."""

    code = tuple(
        item
        for child in formula.children
        for item in compile_formula(child)
    )
    return code + ((formula.op, formula.atom),)


def run_stack_program(code: tuple[tuple[str, str], ...], world: World) -> bool:
    """Stack interpreter; structurally different from the checker's denotation."""

    values, stack = dict(world), []
    for op, argument in code:
        if op == "true":
            stack.append(True)
        elif op == "false":
            stack.append(False)
        elif op == "atom":
            if argument not in values:
                raise BusinessRootError(
                    "UNDECLARED_CONSTRAINT_ATOM",
                    "program cites an atom missing from the declared keys",
                    stage="solver",
                )
            stack.append(values[argument])
        elif op == "not":
            stack.append(not stack.pop())
        else:
            right, left = stack.pop(), stack.pop()
            stack.append((left and right) if op == "and" else (left or right))
    require(len(stack) == 1, "STACK_SHAPE", "compiled program left a broken stack",
            stage="solver")
    return stack[0]


def solver_worlds(spec: PrincipalSpec) -> tuple[World, ...]:
    """Enumerate the scenario set Omega(I0) with the solver's own machinery."""

    spec.validate()
    keys = [key for key, _ in spec.facts]
    options = [(False, True) if value is None else (value,) for _, value in spec.facts]
    program = compile_formula(spec.constraint)
    worlds: list[World] = []
    for assignment in product(*options):
        world = tuple(zip(keys, assignment))
        if run_stack_program(program, world):
            worlds.append(world)
    return tuple(worlds)


@dataclass(frozen=True)
class Outcome:
    context: object
    relation_id: str
    creditor: str
    debtor: str
    debt_id: str
    basis_ids: tuple[str, ...]
    asof_day: object
    world: World
    principal_balance: Fraction
    overpayment_residual: Fraction
    conclusion_kind: str = "CONDITIONAL_PRINCIPAL_BALANCE_NOT_JUDGMENT"


@dataclass(frozen=True)
class Result:
    context: object
    mode: str
    outcomes: tuple[Outcome, ...]
    pending: tuple[World, ...]


def solve(spec: PrincipalSpec, budget: int | None = None) -> Result:
    """Solve every scenario in budget order; partial results keep pending worlds."""

    if budget is not None and (type(budget) is not int or budget < 0):
        raise BusinessRootError("BUDGET", "budget must be a nonnegative integer or null",
                                stage="solver")
    worlds = solver_worlds(spec)
    if not worlds:
        return Result(spec.context, MODE_INCONSISTENT, (), ())
    planned = len(worlds) if budget is None else min(budget, len(worlds))
    outcomes: list[Outcome] = []
    for world in worlds[:planned]:
        assignments = dict(world)
        paid = sum(
            (
                payment.amount
                for payment in spec.payments
                if assignments[payment.recognition_atom]
            ),
            Fraction(0),
        )
        residual = spec.principal - paid
        outcomes.append(Outcome(
            spec.context,
            spec.relation_id,
            spec.creditor,
            spec.debtor,
            spec.debt_id,
            tuple(source.source_id for source in spec.sources),
            spec.asof_day,
            world,
            max(residual, Fraction(0)),
            max(-residual, Fraction(0)),
        ))
    mode = MODE_EXACT if planned == len(worlds) else MODE_PARTIAL
    return Result(spec.context, mode, tuple(outcomes), tuple(worlds[planned:]))


__all__ = [
    "MODE_EXACT",
    "MODE_INCONSISTENT",
    "MODE_PARTIAL",
    "Outcome",
    "Result",
    "compile_formula",
    "run_stack_program",
    "solve",
    "solver_worlds",
]
