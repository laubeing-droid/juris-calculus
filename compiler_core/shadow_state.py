#!/usr/bin/env python3
"""Shadow state for neural or LLM candidates."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ShadowCandidate:
    candidate_id: str
    candidate_type: str
    payload: Dict[str, Any]
    source: str = "shadow"
    confidence: float = 0.0
    accepted: bool = False
    rejection_reasons: List[str] = field(default_factory=list)


@dataclass
class ShadowState:
    world_id: str
    candidates: List[ShadowCandidate] = field(default_factory=list)

    def add_candidate(self, candidate: ShadowCandidate) -> None:
        candidate.accepted = False
        self.candidates.append(candidate)

    def accepted_candidates(self) -> List[ShadowCandidate]:
        return [candidate for candidate in self.candidates if candidate.accepted]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_id": self.world_id,
            "candidate_count": len(self.candidates),
            "candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "candidate_type": c.candidate_type,
                    "payload": dict(c.payload),
                    "source": c.source,
                    "confidence": c.confidence,
                    "accepted": c.accepted,
                    "rejection_reasons": list(c.rejection_reasons),
                }
                for c in self.candidates
            ],
        }


def compare_shadow_to_official(official_claims: List[str], shadow_claims: List[str]) -> Dict[str, Any]:
    official = set(official_claims)
    shadow = set(shadow_claims)
    return {
        "official_only": sorted(official - shadow),
        "shadow_only": sorted(shadow - official),
        "overlap": sorted(official & shadow),
        "divergence": bool((official - shadow) or (shadow - official)),
    }
