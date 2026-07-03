"""LSC boundary result statuses for JC engineering outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from compiler_core.fact_trust_envelope import FactTrustEnvelope, FactTrustStatus


class BoundaryResultStatus(str, Enum):
    """Result states that disclose boundary conditions without changing JC semantics."""

    ACCEPTED_FORMAL_RESULT = "accepted_formal_result"
    HYPOTHETICAL_RESULT = "hypothetical_result"
    REVIEW_ONLY_RESULT = "review_only_result"
    MISSING_REQUIRED_FACT = "missing_required_fact"
    CONFLICT_CERTIFICATE = "conflict_certificate"
    ENGINE_ERROR = "engine_error"


@dataclass(frozen=True)
class BoundaryResult:
    """Uniform output packet carrying status, provenance, taint, and review data."""

    result_status: BoundaryResultStatus
    used_fact_keys: tuple[str, ...] = field(default_factory=tuple)
    used_rule_ids: tuple[str, ...] = field(default_factory=tuple)
    source_snapshot_ids: tuple[str, ...] = field(default_factory=tuple)
    provenance: dict[str, Any] = field(default_factory=dict)
    taint: tuple[str, ...] = field(default_factory=tuple)
    review_required: bool = False
    formal_kernel_used: bool = False
    renderer_output_kind: str = "machine_packet"
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready result packet with required audit fields."""

        return {
            "result_status": self.result_status.value,
            "used_fact_keys": list(self.used_fact_keys),
            "used_rule_ids": list(self.used_rule_ids),
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "provenance": dict(self.provenance),
            "taint": list(self.taint),
            "review_required": self.review_required,
            "formal_kernel_used": self.formal_kernel_used,
            "renderer_output_kind": self.renderer_output_kind,
            "payload": dict(self.payload),
        }


def classify_boundary_result(
    used_facts: Iterable[FactTrustEnvelope],
    *,
    used_rule_ids: Iterable[str] = (),
    source_snapshot_ids: Iterable[str] = (),
    conflict_nodes: Iterable[str] = (),
    engine_error: str | None = None,
) -> BoundaryResult:
    """Classify a boundary result from used facts and non-semantic conditions."""

    facts = tuple(used_facts)
    used_fact_keys = tuple(fact.fact_key for fact in facts)
    taint = _taint_from_facts(facts)
    provenance = {
        "summary_only": True,
        "fact_count": len(facts),
        "source_ids": sorted({source_id for fact in facts for source_id in fact.source_ids}),
    }
    common = {
        "used_fact_keys": used_fact_keys,
        "used_rule_ids": tuple(used_rule_ids),
        "source_snapshot_ids": tuple(source_snapshot_ids),
        "provenance": provenance,
        "taint": taint,
    }
    if engine_error:
        return BoundaryResult(
            BoundaryResultStatus.ENGINE_ERROR,
            review_required=True,
            payload={"error": engine_error},
            **common,
        )
    conflict_tuple = tuple(conflict_nodes)
    if conflict_tuple:
        return BoundaryResult(
            BoundaryResultStatus.CONFLICT_CERTIFICATE,
            review_required=True,
            payload={"conflict_nodes": list(conflict_tuple), "auto_resolved": False},
            **common,
        )
    if any(fact.status == FactTrustStatus.UNKNOWN for fact in facts):
        missing = [fact.fact_key for fact in facts if fact.status == FactTrustStatus.UNKNOWN]
        return BoundaryResult(
            BoundaryResultStatus.MISSING_REQUIRED_FACT,
            review_required=True,
            payload={"missing_fact_keys": missing},
            **common,
        )
    if any(fact.status == FactTrustStatus.DISPUTED for fact in facts):
        return BoundaryResult(
            BoundaryResultStatus.REVIEW_ONLY_RESULT,
            review_required=True,
            payload={"alternative_paths": _alternatives(facts)},
            **common,
        )
    if "assumption" in taint:
        return BoundaryResult(
            BoundaryResultStatus.HYPOTHETICAL_RESULT,
            review_required=True,
            payload={"hypothetical": True},
            **common,
        )
    return BoundaryResult(
        BoundaryResultStatus.ACCEPTED_FORMAL_RESULT,
        formal_kernel_used=True,
        **common,
    )


def ensure_required_audit_fields(result: Mapping[str, Any]) -> bool:
    """Return True when a result exposes all LSC-derived audit fields."""

    required = {
        "result_status",
        "used_fact_keys",
        "used_rule_ids",
        "source_snapshot_ids",
        "provenance",
        "taint",
        "review_required",
        "formal_kernel_used",
        "renderer_output_kind",
    }
    return required <= set(result)


def _taint_from_facts(facts: Iterable[FactTrustEnvelope]) -> tuple[str, ...]:
    labels: set[str] = set()
    for fact in facts:
        if fact.status == FactTrustStatus.USER_ASSUMED:
            labels.add("assumption")
        if fact.status == FactTrustStatus.DISPUTED:
            labels.add("disputed")
        if fact.status == FactTrustStatus.UNKNOWN:
            labels.add("unknown")
        derived = (fact.provenance.get("derived_from") or {}) if isinstance(fact.provenance, Mapping) else {}
        upstream_taint = str(derived.get("provenance_taint") or "")
        if upstream_taint == "HYPOTHETICAL_RESULT":
            labels.add("assumption")
        if upstream_taint == "DETERMINISTIC_CONDITIONAL":
            labels.add("conditional")
    return tuple(sorted(labels))


def _alternatives(facts: Iterable[FactTrustEnvelope]) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    for fact in facts:
        if fact.status == FactTrustStatus.DISPUTED:
            paths.append({"fact_key": fact.fact_key, "alternatives": [dict(item) for item in fact.alternatives]})
    return paths

