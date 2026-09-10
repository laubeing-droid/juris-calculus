"""Typed I0 authority for the finite conditional principal profile.

Production port of the retained LMM reference spec types
(``tools/business_relations/reference/business.py``, legal-math-modeling
@ 88644bc, MIT License). Guards stay finite propositional formulas; the spec
computes a matured, admitted principal balance only — other claims, defenses,
taxes, interest and judgments are NOT modelled.

The input is one complete typed payload (context, spec, model) decoded
elsewhere through :mod:`compiler_core.business_root.codec`; this module holds
the typed objects, validation, and lossless wire conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from fractions import Fraction
from itertools import product

from compiler_core.business_root.codec import (
    BUSINESS_MODEL_BASIS_V1,
    BUSINESS_PROFILE_V1,
    BusinessContextKey,
    BusinessRootError,
    closed_keys,
    date_wire,
    exact_rational,
    identity_string,
    iso_date,
    rational_wire,
    require,
)

World = tuple[tuple[str, bool], ...]

_FORMULA_OPS = frozenset({"true", "false", "atom", "not", "and", "or"})


@dataclass(frozen=True)
class Formula:
    """One finite propositional guard over declared fact atoms."""

    op: str
    atom: str = ""
    children: tuple["Formula", ...] = ()

    def __post_init__(self) -> None:
        if self.op not in _FORMULA_OPS:
            raise BusinessRootError(
                "UNREGISTERED_FORMULA", f"unknown formula op {self.op!r}", stage="spec"
            )
        if (self.op == "atom") != bool(self.atom):
            raise BusinessRootError("ATOM_FIELDS", "atom op requires exactly its atom",
                                    stage="spec")
        arity = len(self.children)
        if (self.op in {"true", "false", "atom"} and arity) or (
            self.op == "not" and arity != 1
        ):
            raise BusinessRootError("FORMULA_ARITY", f"{self.op} has wrong arity",
                                    stage="spec")
        if self.op in {"and", "or"} and arity != 2:
            raise BusinessRootError("FORMULA_ARITY", f"{self.op} has wrong arity",
                                    stage="spec")

    def to_dict(self) -> dict:
        return {
            "op": self.op,
            "atom": self.atom,
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, payload: object) -> "Formula":
        if type(payload) is not dict:
            raise BusinessRootError("FORMULA_SCHEMA", "formula must be an object",
                                    stage="spec")
        closed_keys(payload, {"op", "atom", "children"}, label="formula")
        children = payload["children"]
        if type(children) is not list:
            raise BusinessRootError("FORMULA_SCHEMA", "children must be an array",
                                    stage="spec")
        return cls(
            payload["op"],  # type: ignore[arg-type]
            payload["atom"],  # type: ignore[arg-type]
            tuple(cls.from_dict(child) for child in children),  # type: ignore[arg-type]
        )


FORMULA_TRUE = Formula("true")


def atom_names(formula: Formula) -> frozenset[str]:
    return (
        {formula.atom} if formula.op == "atom" else frozenset().union(
            *(atom_names(child) for child in formula.children)
        )
    )


@dataclass(frozen=True)
class SourceSpan:
    """One declared in-input source span; binding is by content, not by id."""

    source_id: str
    version: str
    body: str
    start: int
    end: int
    quoted: str

    def valid(self) -> bool:
        return (
            bool(self.source_id) and bool(self.version)
            and 0 <= self.start < self.end <= len(self.body)
            and self.body[self.start:self.end] == self.quoted
        )


@dataclass(frozen=True)
class Payment:
    payment_id: str
    amount: Fraction
    event_day: date
    payer: str
    recipient: str
    debt_id: str
    recognition_atom: str
    source_id: str


@dataclass(frozen=True)
class PrincipalSpec:
    """The complete conditional principal input (one I0 spec fragment)."""

    context: BusinessContextKey
    relation_id: str
    creditor: str
    debtor: str
    debt_id: str
    principal: Fraction
    due_day: date
    asof_day: date
    sources: tuple[SourceSpan, ...]
    payments: tuple[Payment, ...]
    facts: tuple[tuple[str, bool | None], ...]
    constraint: Formula = FORMULA_TRUE
    approved_policy: str = BUSINESS_PROFILE_V1

    def validate(self) -> None:
        if type(self.context) is not BusinessContextKey or any(
            type(x) is not tuple for x in (self.sources, self.payments, self.facts)
        ):
            raise BusinessRootError(
                "IMMUTABLE_TYPED_SPEC_REQUIRED",
                "spec requires typed immutable fragments",
                stage="spec",
            )
        if self.approved_policy != BUSINESS_PROFILE_V1:
            raise BusinessRootError(
                "UNSUPPORTED_PROFILE",
                f"profile {self.approved_policy!r} is not supported",
                stage="spec",
            )
        for value in (self.relation_id, self.creditor, self.debtor, self.debt_id):
            identity_string(value, label="spec identity")
        if self.creditor == self.debtor:
            raise BusinessRootError(
                "FRAGMENT_REQUIRES_DISTINCT_PARTIES",
                "creditor and debtor must be distinct",
                stage="spec",
            )
        if type(self.principal) is not Fraction or self.principal < 0:
            raise BusinessRootError("MONEY_TYPE", "principal must be a nonnegative exact rational",
                                    stage="spec")
        if self.asof_day < self.due_day:
            raise BusinessRootError(
                "NOT_DUE_IN_THIS_FRAGMENT", "as-of day precedes the due day", stage="spec"
            )
        if (
            self.context.event_time != self.due_day.isoformat()
            or self.context.decision_time != self.asof_day.isoformat()
        ):
            raise BusinessRootError(
                "TEMPORAL_BINDING", "context anchors and spec dates disagree", stage="spec"
            )
        if self.context.scenario != "finite-conditional-completions" or (
            not self.context.assumptions
        ):
            raise BusinessRootError(
                "CONDITIONAL_SCOPE_REQUIRED",
                "the conditional profile requires declared scenario assumptions",
                stage="spec",
            )
        source_ids = [source.source_id for source in self.sources]
        if not source_ids or len(source_ids) != len(set(source_ids)) or not all(
            source.valid() for source in self.sources
        ):
            raise BusinessRootError(
                "SOURCE_BINDING", "source spans are missing, duplicated, or inconsistent",
                stage="spec",
            )
        keys = [key for key, _ in self.facts]
        if len(keys) != len(set(keys)) or any(
            not key or (value is not None and type(value) is not bool)
            for key, value in self.facts
        ):
            raise BusinessRootError(
                "FACT_SCHEMA", "fact atoms must be unique keys with bool-or-open values",
                stage="spec",
            )
        if not atom_names(self.constraint) <= set(keys):
            raise BusinessRootError(
                "UNDECLARED_CONSTRAINT_ATOM", "constraint cites an undeclared atom",
                stage="spec",
            )
        payment_ids = [payment.payment_id for payment in self.payments]
        if len(payment_ids) != len(set(payment_ids)):
            raise BusinessRootError(
                "DUPLICATE_PAYMENT", "payment ids must be unique", stage="spec"
            )
        for payment in self.payments:
            if type(payment.amount) is not Fraction or payment.amount < 0:
                raise BusinessRootError(
                    "PAYMENT_AMOUNT", "payment amounts must be nonnegative exact rationals",
                    stage="spec",
                )
            if payment.event_day > self.asof_day:
                raise BusinessRootError(
                    "FUTURE_PAYMENT", "payment event day is after the as-of day",
                    stage="spec",
                )
            if (payment.payer, payment.recipient, payment.debt_id) != (
                self.debtor, self.creditor, self.debt_id
            ):
                raise BusinessRootError(
                    "PAYMENT_PARTY_OR_DEBT", "payment parties and debt do not bind the spec",
                    stage="spec",
                )
            if (
                payment.recognition_atom not in keys
                or payment.source_id not in set(source_ids)
            ):
                raise BusinessRootError(
                    "PAYMENT_BASIS", "payment cites an unknown atom or source",
                    stage="spec",
                )


@dataclass(frozen=True)
class DecisionInputs:
    """The model half of I0: weights, threshold, costs, and the legal grid."""

    context: BusinessContextKey
    weights: tuple[tuple[World, Fraction], ...]
    threshold: Fraction
    costs: tuple[Fraction, Fraction, Fraction, Fraction]
    legal_options: tuple[Fraction, ...]
    basis: str = BUSINESS_MODEL_BASIS_V1

    def validate_against(self, spec: PrincipalSpec, balances: dict[World, Fraction]) -> None:
        if type(self.context) is not BusinessContextKey or type(self.basis) is not str:
            raise BusinessRootError("MODEL_BINDING", "model requires a typed context",
                                    stage="analytics")
        if self.context != spec.context:
            raise BusinessRootError(
                "INPUT_SUBJECT_MISMATCH", "model context differs from the spec context",
                stage="analytics",
            )
        if self.basis != BUSINESS_MODEL_BASIS_V1:
            raise BusinessRootError(
                "UNSUPPORTED_MODEL_BASIS",
                f"model basis {self.basis!r} is not supported",
                stage="analytics",
            )
        worlds = {world for world, _ in self.weights}
        if type(self.weights) is not tuple or len(worlds) != len(self.weights) or (
            worlds != set(balances)
        ):
            raise BusinessRootError(
                "MODEL_WORLD_COVERAGE",
                "weights must bind every solved world exactly once",
                stage="analytics",
            )
        for world, weight in self.weights:
            if not valid_world_shape(world, spec) or type(weight) is not Fraction or weight < 0:
                raise BusinessRootError(
                    "PROBABILITY_SPACE", "weights must be nonnegative exact rationals",
                    stage="analytics",
                )
        if sum((weight for _, weight in self.weights), Fraction(0)) != 1:
            raise BusinessRootError(
                "PROBABILITY_SPACE", "weights must sum to exactly one", stage="analytics"
            )
        if type(self.threshold) is not Fraction or type(self.costs) is not tuple or len(
            self.costs
        ) != 4 or any(type(cost) is not Fraction or cost < 0 for cost in self.costs):
            raise BusinessRootError(
                "MODEL_QUANTITIES", "threshold and costs must be nonnegative rationals",
                stage="analytics",
            )
        if type(self.legal_options) is not tuple or len(set(self.legal_options)) != len(
            self.legal_options
        ) or any(
            type(option) is not Fraction or option < 0 for option in self.legal_options
        ):
            raise BusinessRootError(
                "DECLARED_ACTION_SET", "legal options must be unique nonnegative rationals",
                stage="analytics",
            )


def valid_world_shape(world: object, spec: PrincipalSpec) -> bool:
    return (
        type(world) is tuple
        and len(world) == len(spec.facts)
        and all(
            type(pair) is tuple and len(pair) == 2 and pair[0] == key
            and type(pair[1]) is bool
            for pair, (key, _) in zip(world, spec.facts)
        )
    )


# ---------------------------------------------------------------------------
# Wire conversion (lossless encode/decode between typed objects and dicts).
# ---------------------------------------------------------------------------


def encode_world(world: World) -> list[list[object]]:
    return [[key, value] for key, value in sorted(world)]


def decode_world(payload: object) -> World:
    if type(payload) is not list:
        raise BusinessRootError("WORLD_SCHEMA", "world must be an array of pairs",
                                stage="codec")
    pairs: list[tuple[str, bool]] = []
    for pair in payload:
        if type(pair) is not list or len(pair) != 2 or type(pair[0]) is not str or type(
            pair[1]
        ) is not bool:
            raise BusinessRootError(
                "WORLD_SCHEMA", "world pairs must be [string, boolean]", stage="codec"
            )
        pairs.append((pair[0], pair[1]))
    if len(pairs) != len({key for key, _ in pairs}):
        raise BusinessRootError("DUPLICATE_WORLD_ATOM", "world repeats an atom",
                                stage="codec")
    return tuple(sorted(pairs))


def encode_spec(spec: PrincipalSpec) -> dict:
    spec.validate()
    return {
        "context": spec.context.to_dict(),
        "relation_id": spec.relation_id,
        "creditor": spec.creditor,
        "debtor": spec.debtor,
        "debt_id": spec.debt_id,
        "principal": rational_wire(spec.principal),
        "due_day": date_wire(spec.due_day),
        "asof_day": date_wire(spec.asof_day),
        "sources": [
            {
                "source_id": source.source_id,
                "version": source.version,
                "body": source.body,
                "start": source.start,
                "end": source.end,
                "quoted": source.quoted,
            }
            for source in spec.sources
        ],
        "payments": [
            {
                "payment_id": payment.payment_id,
                "amount": rational_wire(payment.amount),
                "event_day": date_wire(payment.event_day),
                "payer": payment.payer,
                "recipient": payment.recipient,
                "debt_id": payment.debt_id,
                "recognition_atom": payment.recognition_atom,
                "source_id": payment.source_id,
            }
            for payment in spec.payments
        ],
        "facts": [[key, value] for key, value in spec.facts],
        "constraint": spec.constraint.to_dict(),
        "approved_policy": spec.approved_policy,
    }


def decode_spec(payload: object) -> PrincipalSpec:
    closed_keys(
        payload,
        {
            "context", "relation_id", "creditor", "debtor", "debt_id", "principal",
            "due_day", "asof_day", "sources", "payments", "facts", "constraint",
            "approved_policy",
        },
        label="spec",
    )
    assert isinstance(payload, dict)
    context = BusinessContextKey.from_dict(payload["context"])
    if type(payload["sources"]) is not list or type(payload["payments"]) is not list or (
        type(payload["facts"]) is not list
    ):
        raise BusinessRootError("SPEC_SCHEMA", "sources/payments/facts must be arrays",
                                stage="codec")
    sources = []
    for row in payload["sources"]:
        closed_keys(
            row, {"source_id", "version", "body", "start", "end", "quoted"},
            label="source span",
        )
        assert isinstance(row, dict)
        if type(row["start"]) is not int or type(row["end"]) is not int or type(
            row["body"]
        ) is not str or type(row["quoted"]) is not str:
            raise BusinessRootError("SOURCE_BINDING", "source span fields are mistyped",
                                    stage="codec")
        sources.append(SourceSpan(
            identity_string(row["source_id"], label="source_id"),
            identity_string(row["version"], label="source version"),
            row["body"], row["start"], row["end"], row["quoted"],
        ))
    payments = []
    for row in payload["payments"]:
        closed_keys(
            row,
            {
                "payment_id", "amount", "event_day", "payer", "recipient", "debt_id",
                "recognition_atom", "source_id",
            },
            label="payment",
        )
        assert isinstance(row, dict)
        payments.append(Payment(
            identity_string(row["payment_id"], label="payment_id"),
            exact_rational(row["amount"], label="payment amount"),
            iso_date(row["event_day"], label="payment event_day"),
            identity_string(row["payer"], label="payer"),
            identity_string(row["recipient"], label="recipient"),
            identity_string(row["debt_id"], label="payment debt_id"),
            identity_string(row["recognition_atom"], label="recognition_atom"),
            identity_string(row["source_id"], label="payment source_id"),
        ))
    facts: list[tuple[str, bool | None]] = []
    for row in payload["facts"]:
        if type(row) is not list or len(row) != 2 or type(row[0]) is not str or type(
            row[1]
        ) not in (bool, type(None)):
            raise BusinessRootError(
                "FACT_SCHEMA", "fact rows must be [string, boolean-or-null]", stage="codec"
            )
        facts.append((row[0], row[1]))
    principal = exact_rational(payload["principal"], label="principal")
    spec = PrincipalSpec(
        context=context,
        relation_id=identity_string(payload["relation_id"], label="relation_id"),
        creditor=identity_string(payload["creditor"], label="creditor"),
        debtor=identity_string(payload["debtor"], label="debtor"),
        debt_id=identity_string(payload["debt_id"], label="debt_id"),
        principal=principal,
        due_day=iso_date(payload["due_day"], label="due_day"),
        asof_day=iso_date(payload["asof_day"], label="asof_day"),
        sources=tuple(sources),
        payments=tuple(payments),
        facts=tuple(facts),
        constraint=Formula.from_dict(payload["constraint"]),
        approved_policy=payload["approved_policy"],  # type: ignore[arg-type]
    )
    spec.validate()
    return spec


def encode_model(model: DecisionInputs) -> dict:
    return {
        "weights": [
            {"world": encode_world(world), "probability": rational_wire(weight)}
            for world, weight in model.weights
        ],
        "threshold": rational_wire(model.threshold),
        "costs": [rational_wire(cost) for cost in model.costs],
        "legal_options": [rational_wire(option) for option in model.legal_options],
        "basis": model.basis,
    }


def decode_model(payload: object, context: BusinessContextKey) -> DecisionInputs:
    closed_keys(payload, {"weights", "threshold", "costs", "legal_options", "basis"},
                label="model")
    assert isinstance(payload, dict)
    if type(payload["weights"]) is not list or type(payload["costs"]) is not list or (
        type(payload["legal_options"]) is not list
    ):
        raise BusinessRootError("MODEL_SCHEMA", "weights/costs/legal_options must be arrays",
                                stage="codec")
    weights = []
    for row in payload["weights"]:
        closed_keys(row, {"world", "probability"}, label="weight")
        assert isinstance(row, dict)
        weights.append((
            decode_world(row["world"]),
            exact_rational(row["probability"], label="weight"),
        ))
    costs = tuple(
        exact_rational(cost, label=f"costs[{index}]")
        for index, cost in enumerate(payload["costs"])
    )
    if len(costs) != 4:
        raise BusinessRootError("MODEL_QUANTITIES", "costs must have exactly four entries",
                                stage="codec")
    legal = tuple(
        exact_rational(option, label=f"legal_options[{index}]")
        for index, option in enumerate(payload["legal_options"])
    )
    model = DecisionInputs(
        context=context,
        weights=tuple(weights),
        threshold=exact_rational(payload["threshold"], label="threshold"),
        costs=costs,  # type: ignore[arg-type]
        legal_options=legal,
        basis=payload["basis"],  # type: ignore[arg-type]
    )
    return model


def replace_model(model: DecisionInputs, **changes) -> DecisionInputs:
    return replace(model, **changes)


def all_boolean_assignments(keys: tuple[str, ...]):
    """Every Boolean assignment over the declared keys, in a fixed order."""

    return product((False, True), repeat=len(keys))


__all__ = [
    "DecisionInputs",
    "FORMULA_TRUE",
    "Formula",
    "Payment",
    "PrincipalSpec",
    "SourceSpan",
    "World",
    "all_boolean_assignments",
    "atom_names",
    "decode_model",
    "decode_spec",
    "decode_world",
    "encode_model",
    "encode_spec",
    "encode_world",
    "replace_model",
    "valid_world_shape",
]
