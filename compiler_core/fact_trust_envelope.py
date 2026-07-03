"""LSC-inspired fact trust envelope for JC engineering boundaries.

This module is intentionally outside the formal kernel. It maps LSC fact-state
language into JC fact trust metadata without changing verified_fact eligibility,
Horn closure, certificate acceptance, or DecisionStatus semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class FactTrustStatus(str, Enum):
    """Machine-readable fact states used by the engineering boundary layer."""

    CANDIDATE_FACT = "candidate_fact"
    NORMALIZED_FACT = "normalized_fact"
    SOURCE_BOUND_FACT = "source_bound_fact"
    CHECKED_FACT = "checked_fact"
    VERIFIED_FACT = "verified_fact"
    REJECTED_FACT = "rejected_fact"
    STALE_FACT = "stale_fact"
    USER_ASSUMED = "user_assumed"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


class FactCreator(str, Enum):
    """Origin class for a fact-trust envelope."""

    LLM = "llm"
    HUMAN = "human"
    SYSTEM = "system"
    COURT = "court"
    IMPORT = "import"


LSC_STATUS_MAP = {
    "ADMITTED": FactTrustStatus.CHECKED_FACT,
    "HUMAN_REVIEWED": FactTrustStatus.CHECKED_FACT,
    "VERIFIED": FactTrustStatus.VERIFIED_FACT,
    "COURT_FIXED": FactTrustStatus.VERIFIED_FACT,
    "USER_ASSUMED": FactTrustStatus.USER_ASSUMED,
    "DISPUTED": FactTrustStatus.DISPUTED,
    "UNKNOWN": FactTrustStatus.UNKNOWN,
    "ENGINE_DERIVED": FactTrustStatus.CHECKED_FACT,
}


@dataclass(frozen=True)
class FactTrustEnvelope:
    """Status-wrapped fact value that preserves trust and audit metadata."""

    fact_key: str
    value: Any = None
    status: FactTrustStatus = FactTrustStatus.CANDIDATE_FACT
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    alternatives: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    provenance: dict[str, Any] = field(default_factory=dict)
    human_reviewed: bool = False
    created_by: FactCreator = FactCreator.SYSTEM

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready representation of the envelope."""

        return {
            "fact_key": self.fact_key,
            "value": self.value,
            "status": self.status.value,
            "source_ids": list(self.source_ids),
            "alternatives": [dict(item) for item in self.alternatives],
            "provenance": dict(self.provenance),
            "human_reviewed": self.human_reviewed,
            "created_by": self.created_by.value,
        }

    @property
    def reasoning_eligible_by_default(self) -> bool:
        """Return True only for already verified facts."""

        return self.status == FactTrustStatus.VERIFIED_FACT

    @property
    def requires_review_packet(self) -> bool:
        """Return True when the fact must be surfaced for human review."""

        return self.status in {FactTrustStatus.DISPUTED, FactTrustStatus.UNKNOWN}

    @property
    def assumption_tainted(self) -> bool:
        """Return True when use of this fact can only support hypothetical output."""

        return self.status == FactTrustStatus.USER_ASSUMED


def from_lsc_fact_coordinate(payload: Mapping[str, Any]) -> FactTrustEnvelope:
    """Map an LSC FactCoordinate-shaped payload into a JC envelope.

    The mapping is conservative: LSC VERIFIED is represented as verified-state
    metadata, but callers still need the existing JC verified_fact gate before
    letting the fact affect formal reasoning.
    """

    raw_state = str(payload.get("determination_state") or payload.get("truth_status") or "")
    status = LSC_STATUS_MAP.get(raw_state, FactTrustStatus.CANDIDATE_FACT)
    provenance = dict(payload.get("provenance") or {})
    creator = _creator_from_payload(raw_state, provenance)
    source_ids = tuple(_source_ids(provenance))
    alternatives = tuple(dict(item) for item in payload.get("alternatives") or ())
    return FactTrustEnvelope(
        fact_key=str(payload.get("fact_key") or ""),
        value=payload.get("value"),
        status=status,
        source_ids=source_ids,
        alternatives=alternatives,
        provenance=provenance,
        human_reviewed=bool(payload.get("human_reviewed") or raw_state == "HUMAN_REVIEWED"),
        created_by=creator,
    )


def can_enter_formal_kernel(envelope: FactTrustEnvelope) -> bool:
    """Check the boundary-layer precondition for formal-kernel entry."""

    if envelope.status != FactTrustStatus.VERIFIED_FACT:
        return False
    if envelope.created_by == FactCreator.COURT:
        return True
    return bool(envelope.human_reviewed and envelope.source_ids)


def _creator_from_payload(raw_state: str, provenance: Mapping[str, Any]) -> FactCreator:
    created_by = str(provenance.get("created_by") or provenance.get("source_agent") or "").lower()
    if raw_state == "COURT_FIXED" or created_by == "court":
        return FactCreator.COURT
    if created_by in {item.value for item in FactCreator}:
        return FactCreator(created_by)
    if raw_state in {"ADMITTED", "HUMAN_REVIEWED"}:
        return FactCreator.HUMAN
    return FactCreator.SYSTEM


def _source_ids(provenance: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("source_id", "source_ref", "source_document_id"):
        value = provenance.get(key)
        if value:
            values.append(str(value))
    return values

