"""Promotion candidate: typed artifact for neural->symbolic automated promotion."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PromotionState(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    SHADOW_ONLY = "SHADOW_ONLY"
    PROMOTABLE = "PROMOTABLE"
    FINAL_AUTOMATED = "FINAL_AUTOMATED"
    BLOCKED = "BLOCKED"
    REPAIRABLE = "REPAIRABLE"
    REVOKED = "REVOKED"


@dataclass
class PromotionCandidate:
    candidate_id: str
    source_spans: List[str] = field(default_factory=list)
    confidence: float = 0.5
    model_id: str = ""
    model_card_id: str = ""
    dataset_version: str = ""
    uncertainty: str = ""
    state: PromotionState = PromotionState.DRAFT
    gate_results: Dict[str, str] = field(default_factory=dict)
    audit_trace: List[Dict[str, Any]] = field(default_factory=list)
    rollback_trigger: str = ""


def required_gates() -> List[str]:
    return [
        "source_anchor",
        "type_check",
        "relevance_benchmark",
        "smt_sidecar",
        "shadow_divergence",
        "neural_contract_auditor",
        "promotion_policy",
    ]
