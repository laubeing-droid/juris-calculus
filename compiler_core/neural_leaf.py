#!/usr/bin/env python3
"""v2.0 Neural Leaf Node Layer - 6 allowed nodes + kill switch + cold start.

Design constraint: neural outputs NEVER decide legal outcomes.
Allowed: SCORE / RANK / CALIBRATION / ANOMALY_FLAG only.
All neural outputs MUST pass Step Verifier with trust_label <= ENGINEERING_BASELINE.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple


class NeuralLeafType(str, Enum):
    SHARD_ROUTER_RERANK = "rule_shard_router_rerank"
    SEMANTIC_THRESHOLD_CALIBRATOR = "semantic_fact_threshold_calibrator"
    CASE_SIMILARITY_RERANKER = "case_similarity_reranker"
    PRICING_ALPHA_CALIBRATOR = "pricing_alpha_calibrator"
    ANOMALY_DETECTOR = "anomaly_detector"
    REBUTTAL_RISK_SCORER = "rebuttal_risk_scorer"

FORBIDDEN_NEURAL_LEAF_TYPES = [
    "contract_validity_decider",
    "law_applicability_decider",
    "epsilon_legal_determiner",
    "final_judgment_generator_without_symbolic_verifier",
]


class NeuralLeafTrustLabel(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    ENGINEERING_BASELINE = "ENGINEERING_BASELINE"


@dataclass
class NeuralLeafResult:
    node_id: str
    node_type: NeuralLeafType
    score: float = 0.0
    rank: Optional[int] = None
    calibration_delta: Optional[float] = None
    anomaly_flag: Optional[bool] = None
    risk_level: Optional[str] = None
    features_used: List[str] = field(default_factory=list)
    feature_importance: Dict[str, float] = field(default_factory=dict)
    model_version: str = "unknown"
    training_data_version: str = "unknown"
    training_date: str = "unknown"
    trust_label: NeuralLeafTrustLabel = NeuralLeafTrustLabel.ENGINEERING_BASELINE
    requires_symbolic_verification: bool = True
    model_confidence: float = 0.0
    raw_output: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> Tuple[bool, List[str]]:
        errors = []
        forbidden = ["contract_is_valid", "applicable_law", "legal_conclusion",
                     "judgment", "liability", "epsilon_legal_value"]
        for key in forbidden:
            if key in self.raw_output:
                errors.append(f"FORBIDDEN_OUTPUT_FIELD: {key}")
        if self.trust_label.value not in ("UNVERIFIED", "ENGINEERING_BASELINE"):
            errors.append(f"TRUST_LABEL_CEILING_VIOLATION: {self.trust_label.value}")
        return len(errors) == 0, errors


class NeuralLeafRegistry:
    def __init__(self):
        self._nodes: Dict[str, NeuralLeafType] = {}
        self._kill_switch = False
        self._audit_log: List[Dict] = []

    def register(self, node_id: str, node_type: NeuralLeafType) -> bool:
        if node_type.value in FORBIDDEN_NEURAL_LEAF_TYPES:
            return False
        self._nodes[node_id] = node_type
        return True

    def is_available(self, node_id: str) -> bool:
        if self._kill_switch:
            return False
        return node_id in self._nodes

    def kill(self) -> None:
        self._kill_switch = True
        self._audit_log.append({"action": "KILL_SWITCH_ACTIVE", "timestamp": __import__('time').time()})

    def revive(self) -> None:
        self._kill_switch = False

    def cold_start_status(self):
        """Explicit cold-start state, queryable by MCP/dashboard.

        When cold_start=True, all legal decisions come from the symbolic
        engine only. Neural nodes remain dormant until training data arrives.
        """
        n = len(self._nodes)
        return {
            "cold_start": n == 0,
            "registered_nodes": n,
            "kill_switch_active": self._kill_switch,
            "message": (
                "COLD_START: 0 neural nodes registered. "
                "All legal reasoning via symbolic engine only."
                if n == 0
                else f"NEURAL_ACTIVE: {n} node(s) registered."
            ),
        }
