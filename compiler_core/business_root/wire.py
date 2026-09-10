"""Total conversions between the jc-business-root/1 wire contracts and the
internal computation types of the solver/checker/analytics.

The wire contracts (``compiler_core.contracts``) are the public field
authority; the internal types (``spec``/``solver``) are the computation
forms ported from the LMM reference. Every conversion here is total and
validated in both directions by the contract test suite.
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

from compiler_core.business_root.analytics import Analytics
from compiler_core.business_root.codec import BusinessContextKey, rational_wire
from compiler_core.business_root.solver import Outcome, Result
from compiler_core.business_root.spec import (
    DecisionInputs,
    Formula,
    Payment,
    PrincipalSpec,
    SourceSpan,
    World,
)
from compiler_core.contracts import (
    BusinessAnalyticsV5,
    BusinessAtomPairV1,
    BusinessContextV1,
    BusinessFormulaV1,
    BusinessModelInputsV1,
    BusinessOutcomeRowV5,
    BusinessPaymentV1,
    BusinessSpecV1,
    BusinessSourceSpanV1,
    BusinessTaskInputV1,
    BusinessWorldV1,
    BusinessWorldWeightV1,
)


def context_key_of(context: BusinessContextV1) -> BusinessContextKey:
    """Project the wire context onto the internal 20-dimension key."""

    return BusinessContextKey(
        request=context.request,
        jurisdiction=context.jurisdiction,
        event_time=context.event_time,
        decision_time=context.decision_time,
        procedure=context.procedure,
        stage=context.stage,
        party=context.party,
        issue=context.issue,
        scenario=context.scenario,
        profile=context.profile,
        law_version=context.law_version,
        interpretation=context.interpretation,
        rulepack_version=context.rulepack_version,
        engine_version=context.engine_version,
        model_version=context.model_version,
        evidence_version=context.evidence_version,
        target=context.target,
        semantic_scope=context.semantic_scope,
        assumptions=tuple(context.assumptions),
        max_depth=context.max_depth,
    )


def formula_of(formula: BusinessFormulaV1) -> Formula:
    return Formula(
        formula.op,
        formula.atom,
        tuple(formula_of(child) for child in formula.children),
    )


def spec_of(task_input: BusinessTaskInputV1) -> PrincipalSpec:
    """Decode the wire input into the validated internal spec."""

    wire_spec = task_input.spec
    internal = PrincipalSpec(
        context=context_key_of(task_input.context),
        relation_id=wire_spec.relation_id,
        creditor=wire_spec.creditor,
        debtor=wire_spec.debtor,
        debt_id=wire_spec.debt_id,
        principal=Fraction(wire_spec.principal),
        due_day=_date(wire_spec.due_day),
        asof_day=_date(wire_spec.asof_day),
        sources=tuple(
            SourceSpan(
                source.source_id,
                source.version,
                source.body,
                source.start,
                source.end,
                source.quoted,
            )
            for source in wire_spec.sources
        ),
        payments=tuple(
            Payment(
                payment.payment_id,
                Fraction(payment.amount),
                _date(payment.event_day),
                payment.payer,
                payment.recipient,
                payment.debt_id,
                payment.recognition_atom,
                payment.source_id,
            )
            for payment in wire_spec.payments
        ),
        facts=tuple(
            (atom.atom, atom.observed) for atom in wire_spec.facts
        ),
        constraint=formula_of(wire_spec.constraint),
        approved_policy=wire_spec.approved_policy,
    )
    internal.validate()
    return internal


def model_of(task_input: BusinessTaskInputV1) -> DecisionInputs | None:
    """Decode the wire model; ``None`` keeps the run principal-only."""

    wire_model = task_input.model
    if wire_model is None:
        return None
    spec = spec_of(task_input)
    internal = DecisionInputs(
        context=spec.context,
        weights=tuple(
            (world_of(weight.world), Fraction(weight.probability))
            for weight in wire_model.weights
        ),
        threshold=Fraction(wire_model.threshold),
        costs=tuple(Fraction(cost) for cost in wire_model.costs),  # type: ignore[arg-type]
        legal_options=tuple(Fraction(option) for option in wire_model.legal_options),
        basis=wire_model.basis,
    )
    return internal


def world_of(world: BusinessWorldV1) -> World:
    return tuple((pair.atom, pair.value) for pair in world.atoms)


def wire_of_world(world: World) -> BusinessWorldV1:
    return BusinessWorldV1(tuple(
        BusinessAtomPairV1(key, value) for key, value in sorted(world)
    ))


def wire_of_context(context: BusinessContextKey) -> BusinessContextV1:
    return BusinessContextV1.from_dict(context.to_dict())


def wire_of_outcome_row(world: World, balance: Fraction, overpay: Fraction) -> BusinessOutcomeRowV5:
    return BusinessOutcomeRowV5(
        wire_of_world(world), rational_wire(balance), rational_wire(overpay)
    )


def wire_of_analytics(analytics, model_wire_weights: tuple[BusinessWorldWeightV1, ...]) -> BusinessAnalyticsV5:
    """Project internal analytics onto the wire row (weights stay as declared)."""

    return BusinessAnalyticsV5(
        weights=model_wire_weights,
        threshold=rational_wire(analytics.threshold),
        expected_balance=rational_wire(analytics.expected_balance),
        expected_overpayment=rational_wire(analytics.expected_overpayment),
        expected_residual=rational_wire(analytics.expected_residual),
        event_probability=rational_wire(analytics.event_probability),
        costs=(
            rational_wire(analytics.plaintiff_cost),
            rational_wire(analytics.defendant_cost),
            rational_wire(analytics.plaintiff_settle_cost),
            rational_wire(analytics.defendant_settle_cost),
        ),
        lower=rational_wire(analytics.lower),
        upper=rational_wire(analytics.upper),
        legal_options=tuple(rational_wire(option) for option in analytics.legal_options),
        mutually_acceptable=tuple(
            rational_wire(option) for option in analytics.mutually_acceptable
        ),
        selected=None if analytics.selected is None else rational_wire(analytics.selected),
        basis="SYNTHETIC-SETTLEMENT-GRID/1",
    )


def _date(value: str) -> date:
    return date.fromisoformat(value)


def analytics_of(row, context: BusinessContextKey) -> Analytics:
    """Rebuild the internal analytics row from its sealed wire projection."""

    return Analytics(
        context=context,
        weights=tuple(
            (world_of(weight.world), Fraction(weight.probability))
            for weight in row.weights
        ),
        threshold=Fraction(row.threshold),
        expected_balance=Fraction(row.expected_balance),
        expected_overpayment=Fraction(row.expected_overpayment),
        expected_residual=Fraction(row.expected_residual),
        event_probability=Fraction(row.event_probability),
        plaintiff_cost=Fraction(row.costs[0]),
        defendant_cost=Fraction(row.costs[1]),
        plaintiff_settle_cost=Fraction(row.costs[2]),
        defendant_settle_cost=Fraction(row.costs[3]),
        lower=Fraction(row.lower),
        upper=Fraction(row.upper),
        legal_options=tuple(Fraction(option) for option in row.legal_options),
        mutually_acceptable=tuple(
            Fraction(option) for option in row.mutually_acceptable
        ),
        selected=None if row.selected is None else Fraction(row.selected),
    )


def result_of(row, spec: PrincipalSpec) -> Result:
    """Rebuild the internal solver result from one sealed business row.

    Reconstruction reads only the run's own sealed row — it never re-solves.
    """

    from compiler_core.business_root.solver import (
        MODE_EXACT,
        MODE_INCONSISTENT,
        MODE_PARTIAL,
    )
    from compiler_core.contracts import BusinessCompletionV5

    mode_by_completion = {
        BusinessCompletionV5.EXACT_FINITE_SCENARIOS: MODE_EXACT,
        BusinessCompletionV5.PARTIAL_SCENARIOS: MODE_PARTIAL,
        BusinessCompletionV5.INCONSISTENT_ASSUMPTIONS: MODE_INCONSISTENT,
    }
    mode = mode_by_completion[row.completion]
    if mode == MODE_INCONSISTENT:
        return Result(spec.context, MODE_INCONSISTENT, (), ())
    outcomes = tuple(
        Outcome(
            spec.context,
            spec.relation_id,
            spec.creditor,
            spec.debtor,
            spec.debt_id,
            tuple(source.source_id for source in spec.sources),
            spec.asof_day,
            world_of(outcome.world),
            Fraction(outcome.principal_balance),
            Fraction(outcome.overpayment_residual),
        )
        for outcome in row.outcomes
    )
    pending = tuple(world_of(world) for world in row.pending_worlds)
    return Result(spec.context, mode, outcomes, pending)


__all__ = [
    "analytics_of",
    "context_key_of",
    "formula_of",
    "model_of",
    "result_of",
    "spec_of",
    "wire_of_analytics",
    "wire_of_context",
    "wire_of_outcome_row",
    "wire_of_world",
    "world_of",
]
