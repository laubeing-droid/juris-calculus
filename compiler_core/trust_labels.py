#!/usr/bin/env python3
"""v2.0 Trust label system - epistemic status + provenance + maturity."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

class TrustLabel(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    ENGINEERING_BASELINE = "ENGINEERING_BASELINE"
    DATA_INSUFFICIENT_FOR_PROOF = "DATA_INSUFFICIENT_FOR_PROOF"
    TOY_SYNTHETIC_PROOF_ONLY = "TOY_SYNTHETIC_PROOF_ONLY"
    TESTED_PROPERTY = "TESTED_PROPERTY"
    SMT_PROVED_FINITE = "SMT_PROVED_FINITE"
    PROVED_FORMAL = "PROVED_FORMAL"
    PROVED_BY_EXHAUSTIVE_ENUMERATION = "PROVED_BY_EXHAUSTIVE_ENUMERATION"

class RuleMaturity(str, Enum):
    DRAFT = "DRAFT"
    L1_REVIEWED = "L1_REVIEWED"
    L2_TESTED = "L2_TESTED"
    L3_VERIFIED = "L3_VERIFIED"

class DataOrigin(str, Enum):
    SYMBOLIC_ENGINE = "SYMBOLIC_ENGINE"
    NEURAL_LEAF_SUGGESTION = "NEURAL_LEAF_SUGGESTION"
    HUMAN_ANNOTATED = "HUMAN_ANNOTATED"
    REAL_CASE_EXTRACTED = "REAL_CASE_EXTRACTED"
    TOY_SYNTHETIC = "TOY_SYNTHETIC"
    UNKNOWN = "UNKNOWN"

@dataclass
class EpistemicStatus:
    trust_label: TrustLabel = TrustLabel.UNVERIFIED
    rule_maturity: RuleMaturity = RuleMaturity.DRAFT
    data_origin: DataOrigin = DataOrigin.UNKNOWN
    mathematical_basis: str = ""
    verification_artifacts: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    jurisdiction_coverage: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trust_label": self.trust_label.value,
            "rule_maturity": self.rule_maturity.value,
            "data_origin": self.data_origin.value,
            "mathematical_basis": self.mathematical_basis,
            "verification_artifacts": list(self.verification_artifacts),
            "limitations": list(self.limitations),
            "jurisdiction_coverage": dict(self.jurisdiction_coverage),
        }

RED_LINE_PHRASES = [
    "FINAL_ALL_THEOREMS_PROVED",
    "REAL_PRICING_VALIDATED",
    "DP_EPSILON_LEGALLY_DETERMINED",
    "GraphSimilarityMetric",
    "OriginalEvaluatorMonotone",
]
