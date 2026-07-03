"""Taint propagation helpers for LSC boundary absorption."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class TaintLabel(str, Enum):
    """Boundary taints that affect disclosure, not formal acceptability."""

    ASSUMPTION = "assumption"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"
    CONDITIONAL = "conditional"


@dataclass(frozen=True)
class TaintSet:
    """Small immutable taint container used by derived boundary facts."""

    labels: frozenset[TaintLabel] = field(default_factory=frozenset)

    def add(self, *labels: TaintLabel) -> "TaintSet":
        """Return a new taint set with extra labels."""

        return TaintSet(self.labels.union(labels))

    def union(self, *others: "TaintSet") -> "TaintSet":
        """Return a new taint set containing all labels from inputs."""

        merged = set(self.labels)
        for other in others:
            merged.update(other.labels)
        return TaintSet(frozenset(merged))

    def to_list(self) -> list[str]:
        """Return a deterministic string representation."""

        return sorted(label.value for label in self.labels)


def propagate_taint(*upstream: TaintSet) -> TaintSet:
    """Propagate derived-fact taint from all upstream facts."""

    return TaintSet().union(*upstream)


def taint_from_statuses(statuses: Iterable[str]) -> TaintSet:
    """Build taint from fact/result status strings."""

    labels: set[TaintLabel] = set()
    for status in statuses:
        normalized = status.lower()
        if normalized in {"user_assumed", "hypothetical_result", "hypothetical"}:
            labels.add(TaintLabel.ASSUMPTION)
        if normalized in {"disputed", "review_only_result", "degraded_to_auxiliary"}:
            labels.add(TaintLabel.DISPUTED)
        if normalized in {"unknown", "missing_required_fact"}:
            labels.add(TaintLabel.UNKNOWN)
        if normalized in {"deterministic_conditional", "conditional"}:
            labels.add(TaintLabel.CONDITIONAL)
    return TaintSet(frozenset(labels))

