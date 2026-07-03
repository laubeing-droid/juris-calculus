"""Conflict certificates and review packets for boundary-only outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class ConflictCertificate:
    """Machine-readable conflict packet that never resolves priority by itself."""

    conflict_nodes: tuple[str, ...]
    rules: tuple[str, ...] = field(default_factory=tuple)
    facts: tuple[str, ...] = field(default_factory=tuple)
    auto_resolved: bool = False
    review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return the certificate as JSON-ready data."""

        return {
            "result_status": "conflict_certificate",
            "conflict_nodes": list(self.conflict_nodes),
            "rules": list(self.rules),
            "facts": list(self.facts),
            "auto_resolved": self.auto_resolved,
            "review_required": self.review_required,
        }


@dataclass(frozen=True)
class ReviewPacket:
    """Review-only packet for disputed, unknown, P1, or P2 material."""

    reason: str
    fact_keys: tuple[str, ...] = field(default_factory=tuple)
    alternative_paths: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    review_questions: tuple[str, ...] = field(default_factory=tuple)
    enters_certificate_accepted_result: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return the review packet as JSON-ready data."""

        return {
            "result_status": "review_only_result",
            "reason": self.reason,
            "fact_keys": list(self.fact_keys),
            "alternative_paths": [dict(path) for path in self.alternative_paths],
            "review_questions": list(self.review_questions),
            "enters_certificate_accepted_result": self.enters_certificate_accepted_result,
        }


def build_review_packet(
    reason: str,
    fact_keys: Iterable[str] = (),
    alternative_paths: Iterable[dict[str, Any]] = (),
) -> ReviewPacket:
    """Build a conservative review packet with default review questions."""

    facts = tuple(fact_keys)
    questions = tuple(f"Verify boundary status for {fact_key}" for fact_key in facts)
    return ReviewPacket(
        reason=reason,
        fact_keys=facts,
        alternative_paths=tuple(dict(path) for path in alternative_paths),
        review_questions=questions,
    )

