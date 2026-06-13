#!/usr/bin/env python3
"""v2.0 Neural Leaf Node Layer - 6 allowed nodes + kill switch + cold start.

Design constraint: neural outputs NEVER decide legal outcomes.
Allowed: SCORE / RANK / CALIBRATION / ANOMALY_FLAG only.
All neural outputs MUST pass Step Verifier with trust_label <= ENGINEERING_BASELINE.
"""
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
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

FORBIDDEN_OUTPUT_FIELDS = {
    "contract_is_valid",
    "applicable_law",
    "legal_conclusion",
    "judgment",
    "liability",
    "epsilon_legal_value",
    "final_decision",
    "disposition",
    "sentence",
}

ALLOWED_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


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
        if not self.node_id or not str(self.node_id).strip():
            errors.append("NODE_ID_REQUIRED")
        if not isinstance(self.node_type, NeuralLeafType):
            errors.append(f"UNKNOWN_NODE_TYPE: {self.node_type}")
        if not _is_probability(self.score):
            errors.append(f"SCORE_OUT_OF_RANGE: {self.score}")
        if not _is_probability(self.model_confidence):
            errors.append(f"MODEL_CONFIDENCE_OUT_OF_RANGE: {self.model_confidence}")
        if self.rank is not None and (not isinstance(self.rank, int) or self.rank < 0):
            errors.append(f"INVALID_RANK: {self.rank}")
        if self.calibration_delta is not None:
            if not isinstance(self.calibration_delta, (int, float)) or not isfinite(float(self.calibration_delta)):
                errors.append(f"INVALID_CALIBRATION_DELTA: {self.calibration_delta}")
            elif abs(float(self.calibration_delta)) > 1.0:
                errors.append(f"CALIBRATION_DELTA_OUT_OF_RANGE: {self.calibration_delta}")
        if self.anomaly_flag is not None and not isinstance(self.anomaly_flag, bool):
            errors.append(f"INVALID_ANOMALY_FLAG: {self.anomaly_flag}")
        if self.risk_level is not None and self.risk_level not in ALLOWED_RISK_LEVELS:
            errors.append(f"INVALID_RISK_LEVEL: {self.risk_level}")
        if not isinstance(self.raw_output, dict):
            errors.append("RAW_OUTPUT_MUST_BE_DICT")
        else:
            for key in _walk_keys(self.raw_output):
                if key in FORBIDDEN_OUTPUT_FIELDS:
                    errors.append(f"FORBIDDEN_OUTPUT_FIELD: {key}")
        trust_value = getattr(self.trust_label, "value", str(self.trust_label))
        if trust_value not in ("UNVERIFIED", "ENGINEERING_BASELINE"):
            errors.append(f"TRUST_LABEL_CEILING_VIOLATION: {trust_value}")
        if not self.requires_symbolic_verification:
            errors.append("SYMBOLIC_VERIFICATION_REQUIRED")
        for feature in self.features_used:
            if not isinstance(feature, str) or not feature.strip():
                errors.append("INVALID_FEATURE_NAME")
        for feature, importance in self.feature_importance.items():
            if feature not in self.features_used:
                errors.append(f"FEATURE_IMPORTANCE_WITHOUT_FEATURE: {feature}")
            if not _is_probability(importance):
                errors.append(f"FEATURE_IMPORTANCE_OUT_OF_RANGE: {feature}={importance}")
        return len(errors) == 0, errors


class NeuralLeafRegistry:
    def __init__(self):
        self._nodes: Dict[str, NeuralLeafType] = {}
        self._kill_switch = False
        self._audit_log: List[Dict] = []

    def register(self, node_id: str, node_type: NeuralLeafType) -> bool:
        if not node_id or not str(node_id).strip():
            return False
        if not isinstance(node_type, NeuralLeafType):
            return False
        if node_type.value in FORBIDDEN_NEURAL_LEAF_TYPES:
            return False
        self._nodes[node_id] = node_type
        self._audit_log.append({"action": "REGISTER", "node_id": node_id, "node_type": node_type.value})
        return True

    def is_available(self, node_id: str) -> bool:
        if self._kill_switch:
            return False
        return node_id in self._nodes

    def list_nodes(self) -> Dict[str, str]:
        return {node_id: node_type.value for node_id, node_type in self._nodes.items()}

    def audit_log(self) -> List[Dict]:
        return list(self._audit_log)

    def validate_result(self, result: NeuralLeafResult) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        if self._kill_switch:
            errors.append("KILL_SWITCH_ACTIVE")
        registered_type = self._nodes.get(result.node_id)
        if registered_type is None:
            errors.append(f"UNREGISTERED_NODE: {result.node_id}")
        elif registered_type != result.node_type:
            actual_type = getattr(result.node_type, "value", str(result.node_type))
            errors.append(f"NODE_TYPE_MISMATCH: expected={registered_type.value} actual={actual_type}")

        valid, result_errors = result.validate()
        errors.extend(result_errors)
        self._audit_log.append({
            "action": "VALIDATE_RESULT",
            "node_id": result.node_id,
            "status": "PASS" if valid and not errors else "FAIL",
            "errors": list(errors),
        })
        return len(errors) == 0, errors

    def kill(self) -> None:
        self._kill_switch = True
        self._audit_log.append({"action": "KILL_SWITCH_ACTIVE", "timestamp": __import__('time').time()})

    def revive(self) -> None:
        self._kill_switch = False
        self._audit_log.append({"action": "KILL_SWITCH_RELEASED", "timestamp": __import__('time').time()})

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


def _is_probability(value: Any) -> bool:
    return isinstance(value, (int, float)) and isfinite(float(value)) and 0.0 <= float(value) <= 1.0


def _walk_keys(value: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys
