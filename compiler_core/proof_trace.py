#!/usr/bin/env python3
"""Structured proof trace events for symbolic evaluation."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class ProofEvent:
    event_type: str
    rule_id: str = ""
    claim_id: str = ""
    premises: List[str] = field(default_factory=list)
    missing_premises: List[str] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    triggered_exception: str = ""
    confidence: float = 0.0
    source_anchor: str = ""
    notes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def trace_id(self, world_id: str = "") -> str:
        payload = "|".join([
            world_id,
            self.event_type,
            self.rule_id,
            self.claim_id,
            ",".join(self.premises),
            ",".join(self.exceptions),
            self.triggered_exception,
        ])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "rule_id": self.rule_id,
            "claim_id": self.claim_id,
            "premises": list(self.premises),
            "missing_premises": list(self.missing_premises),
            "exceptions": list(self.exceptions),
            "triggered_exception": self.triggered_exception,
            "confidence": self.confidence,
            "source_anchor": self.source_anchor,
            "notes": list(self.notes),
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
        }


def make_trace_id(world_id: str, rule_id: str, claim_id: str) -> str:
    payload = f"{world_id}|{rule_id}|{claim_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
