"""Strict exact-number, context, and closed-decode codec for jc-business-root/1.

Production port of the retained LMM reference codecs
(``tools/business_relations/reference/context.py`` and the exact-rational
discipline of ``delivery_bundle.py``, legal-math-modeling @ 88644bc, MIT
License). LMM keeps the mathematical/reference authority; this module is the
JC production codec authority for the business capability.

Every rational is a canonical string (``"n"`` or ``"n/d"``); floats, booleans
used as integers, and non-canonical rational strings are rejected. Digests are
locators, never equality proofs.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from fractions import Fraction
import re

from compiler_core.contracts import ContractV4Error

BUSINESS_ROOT_CAPABILITY = "jc-business-root/1"
BUSINESS_PROFILE_V1 = "SYNTHETIC-CONDITIONAL-PRINCIPAL/1"
BUSINESS_MODEL_BASIS_V1 = "SYNTHETIC-SETTLEMENT-GRID/1"
BUSINESS_REQUIREMENT_V1 = "SYNTHETIC_EXACT_PRINCIPAL_ANALYTICS_TWO_FILES/1"
BUSINESS_CHECKER_VERSION = "jc-business-checker/1"
BUSINESS_FORMAL_EVIDENCE_V1 = "CROSS_VALIDATED_GENERAL_ALGORITHM_PENDING_KERNEL"
BUSINESS_LEGAL_BASIS_STATUS_V1 = "DECLARED_SYNTHETIC_BASIS_NOT_LEGAL_REVIEW"
BUSINESS_EMPIRICAL_STATUS_V1 = "NO_REAL_DATA"

_RATIONAL_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z")
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_FORBIDDEN_IDENTITY_CHARS = frozenset(
    "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)


class BusinessRootError(ValueError):
    """Typed fail-closed business error: stage, stable code, affected ids."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        stage: str,
        task_id: str | None = None,
    ) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.stage = stage
        self.task_id = task_id


def exact_rational(value: object, *, label: str) -> Fraction:
    """Parse one canonical rational string; reject every lossy carrier."""

    if type(value) is not str:
        raise BusinessRootError(
            "RATIONAL_MUST_BE_STRING",
            f"{label} must be a canonical rational string",
            stage="codec",
        )
    if _RATIONAL_PATTERN.fullmatch(value) is None:
        raise BusinessRootError(
            "NONCANONICAL_RATIONAL",
            f"{label} is not a canonical rational string",
            stage="codec",
        )
    try:
        parsed = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise BusinessRootError(
            "NONCANONICAL_RATIONAL",
            f"{label} is not a canonical rational string",
            stage="codec",
        ) from exc
    if rational_wire(parsed) != value:
        raise BusinessRootError(
            "NONCANONICAL_RATIONAL",
            f"{label} is not a canonical rational string",
            stage="codec",
        )
    return parsed


def rational_wire(value: Fraction) -> str:
    """Canonical exact wire form: ``n`` or ``n/d`` with a positive denominator."""

    if type(value) is not Fraction:
        raise BusinessRootError(
            "MONEY_TYPE", "exact wire form requires a Fraction", stage="codec"
        )
    return str(value.numerator) if value.denominator == 1 else (
        f"{value.numerator}/{value.denominator}"
    )


def iso_date(value: object, *, label: str) -> date:
    """Parse one strict ISO-8601 calendar date; no timezones, no datetimes."""

    if type(value) is not str or _DATE_PATTERN.fullmatch(value) is None:
        raise BusinessRootError(
            "DATE_FORMAT", f"{label} must be an ISO calendar date", stage="codec"
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise BusinessRootError(
            "DATE_FORMAT", f"{label} is not a real calendar date", stage="codec"
        ) from exc


def date_wire(value: date) -> str:
    if type(value) is not date:
        raise BusinessRootError("DATE_FORMAT", "wire form requires a date", stage="codec")
    return value.isoformat()


def identity_string(value: object, *, label: str) -> str:
    """One nonempty identity string without control or bidi-override characters."""

    if type(value) is not str or not value:
        raise BusinessRootError(
            "IDENTITY", f"{label} must be a nonempty string", stage="codec"
        )
    if any(ord(ch) < 32 or ch in _FORBIDDEN_IDENTITY_CHARS for ch in value):
        raise BusinessRootError(
            "IDENTITY", f"{label} carries control or bidi-override characters",
            stage="codec",
        )
    return value


def require(condition: bool, code: str, detail: str, *, stage: str) -> None:
    if not condition:
        raise BusinessRootError(code, detail, stage=stage)


def closed_keys(payload: object, expected: frozenset[str] | set[str], *, label: str) -> dict:
    """Reject missing, unknown, and non-object payloads in one check."""

    if type(payload) is not dict:
        raise BusinessRootError(
            "CLOSED_SCHEMA_MISMATCH", f"{label} must be an object", stage="codec"
        )
    present = set(payload)
    if present != set(expected):
        missing = sorted(set(expected) - present)
        unknown = sorted(present - set(expected))
        raise BusinessRootError(
            "CLOSED_SCHEMA_MISMATCH",
            f"{label} field set differs: missing={missing} unknown={unknown}",
            stage="codec",
        )
    return payload


@dataclass(frozen=True)
class BusinessContextKey:
    """The 20 semantic dimensions shared by every business object in a task.

    Structural equality is input equality; ``canonical_json`` exists for
    rendering and locators, never as a hash-injection proof.
    """

    request: str
    jurisdiction: str
    event_time: str
    decision_time: str
    procedure: str
    stage: str
    party: str
    issue: str
    scenario: str
    profile: str
    law_version: str
    interpretation: str
    rulepack_version: str
    engine_version: str
    model_version: str
    evidence_version: str
    target: str
    semantic_scope: str
    assumptions: tuple[str, ...]
    max_depth: int

    def __post_init__(self) -> None:
        for item in fields(self):
            if item.name in {"assumptions", "max_depth"}:
                continue
            value = getattr(self, item.name)
            if type(value) is not str or not value:
                raise BusinessRootError(
                    "CONTEXT_FIELD",
                    f"context.{item.name} must be a nonempty string",
                    stage="codec",
                )
        if type(self.max_depth) is not int or self.max_depth < 0:
            raise BusinessRootError(
                "CONTEXT_DEPTH",
                "context.max_depth must be an explicit nonnegative integer",
                stage="codec",
            )
        if type(self.assumptions) is not tuple or any(
            type(a) is not str or not a for a in self.assumptions
        ) or len(set(self.assumptions)) != len(self.assumptions):
            raise BusinessRootError(
                "CONTEXT_ASSUMPTIONS",
                "context.assumptions must be unique nonempty strings",
                stage="codec",
            )
        object.__setattr__(self, "assumptions", tuple(sorted(self.assumptions)))

    def canonical_json(self) -> str:
        from compiler_core.canonical_serialization import canonical_text

        return canonical_text(self.to_dict())

    def to_dict(self) -> dict:
        values = {item.name: getattr(self, item.name) for item in fields(self)}
        values["assumptions"] = list(values["assumptions"])
        return values

    @classmethod
    def from_dict(cls, payload: object) -> "BusinessContextKey":
        closed_keys(payload, {item.name for item in fields(cls)}, label="context")
        assumptions = payload["assumptions"]  # type: ignore[index]
        if type(assumptions) is not list:
            raise BusinessRootError(
                "CONTEXT_ASSUMPTIONS", "context.assumptions must be an array",
                stage="codec",
            )
        values = dict(payload)  # type: ignore[arg-type]
        values["assumptions"] = tuple(assumptions)
        return cls(**values)

    @classmethod
    def from_json(cls, text: str) -> "BusinessContextKey":
        from compiler_core.canonical_serialization import parse_json_document

        return cls.from_dict(parse_json_document(text))


def require_same_context(*contexts: BusinessContextKey) -> BusinessContextKey:
    """Cross-subject/issue/version/model/scope composition is rejected."""

    if not contexts or any(type(c) is not BusinessContextKey for c in contexts):
        raise BusinessRootError(
            "CONTEXT_TYPE", "typed context required", stage="codec"
        )
    if any(c != contexts[0] for c in contexts[1:]):
        raise BusinessRootError(
            "CONTEXT_COMPOSITION",
            "one business task binds exactly one context across spec and model",
            stage="codec",
        )
    return contexts[0]


def contract_error(code: str, detail: str) -> ContractV4Error:
    return ContractV4Error(code, detail)


__all__ = [
    "BUSINESS_CHECKER_VERSION",
    "BUSINESS_EMPIRICAL_STATUS_V1",
    "BUSINESS_FORMAL_EVIDENCE_V1",
    "BUSINESS_LEGAL_BASIS_STATUS_V1",
    "BUSINESS_MODEL_BASIS_V1",
    "BUSINESS_PROFILE_V1",
    "BUSINESS_REQUIREMENT_V1",
    "BUSINESS_ROOT_CAPABILITY",
    "BusinessContextKey",
    "BusinessRootError",
    "closed_keys",
    "contract_error",
    "date_wire",
    "exact_rational",
    "identity_string",
    "iso_date",
    "rational_wire",
    "require",
    "require_same_context",
]
