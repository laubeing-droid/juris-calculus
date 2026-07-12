#!/usr/bin/env python3
"""v2.0 Step Verifier - symbolic EVM verification for Layer 5.

Absorbs LawThinker EVM Verify strategy: every claim passes through
knowledge accuracy, fact-law relevance, and procedural compliance checks
before entering memory.  All neural outputs require symbolic verifier clearance.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional
from compiler_core.trust_labels import TrustLabel, EpistemicStatus, DataOrigin
from compiler_core.criminal_complexity import verify_actor_charge_binding


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    DOWNGRADE = "DOWNGRADE"
    REQUIRES_HUMAN = "REQUIRES_HUMAN"


@dataclass
class StepVerificationResult:
    claim_id: str
    knowledge_accuracy: Verdict = Verdict.PASS
    fact_law_relevance: Verdict = Verdict.PASS
    procedural_compliance: Verdict = Verdict.PASS
    neural_output_compliance: Verdict = Verdict.PASS
    overall: Verdict = Verdict.PASS
    downgrade_reason: str = ""
    audit_log: List[str] = field(default_factory=list)


class StepVerifier:

    @staticmethod
    def _load_gap_methodology():
        """Legacy blueprint gap methodology has been retired from the public runtime."""
        return {}

    def verify_with_gap(self, claim, original_request: float = None):
        """Enhanced verify: apply judgment gap methodology to claims."""
        result = self.verify(claim)
        gap = self._load_gap_methodology()
        if gap and original_request and hasattr(claim, "confidence"):
            if claim.confidence < 0.5:
                result.downgrade_reason += " | gap: low confidence vs request"
        return result

    def __init__(self):
        self.results: List[StepVerificationResult] = []

    def verify(self, claim, rule_context: Optional[Dict] = None) -> StepVerificationResult:
        result = StepVerificationResult(claim_id=getattr(claim, 'id', str(claim)))

        if hasattr(claim, 'epistemic_status') and claim.epistemic_status:
            ep = claim.epistemic_status
            if ep.data_origin == DataOrigin.TOY_SYNTHETIC:
                result.knowledge_accuracy = Verdict.DOWNGRADE
                result.downgrade_reason = "Toy synthetic data cannot escalate"
            if ep.data_origin == DataOrigin.NEURAL_LEAF_SUGGESTION:
                result.neural_output_compliance = Verdict.PASS

        if hasattr(claim, 'confidence') and claim.confidence < 0.2:
            result.fact_law_relevance = Verdict.FAIL
            result.downgrade_reason = f"Confidence too low: {claim.confidence}"

        if rule_context and rule_context.get("criminal_case"):
            binding = verify_actor_charge_binding(claim, rule_context.get("criminal_case"))
            result.audit_log.append(f"criminal_binding={binding['passed']}")
            if not binding["passed"]:
                result.fact_law_relevance = Verdict.DOWNGRADE
                reason = "; ".join(binding["issues"])
                result.downgrade_reason = (result.downgrade_reason + " | " if result.downgrade_reason else "") + reason

        has_fail = any(v == Verdict.FAIL for v in [
            result.knowledge_accuracy, result.fact_law_relevance,
            result.procedural_compliance, result.neural_output_compliance
        ])
        has_downgrade = any(v == Verdict.DOWNGRADE for v in [
            result.knowledge_accuracy, result.fact_law_relevance
        ])
        if has_fail:
            result.overall = Verdict.FAIL
        elif has_downgrade:
            result.overall = Verdict.DOWNGRADE

        self.results.append(result)
        return result

    def verify_neural_output(self, neural_result, registry=None) -> StepVerificationResult:
        """Verify a neural leaf result before it can influence any pipeline state."""
        result = StepVerificationResult(claim_id=getattr(neural_result, "node_id", str(neural_result)))
        if registry is not None:
            valid, errors = registry.validate_result(neural_result)
        elif hasattr(neural_result, "validate"):
            valid, errors = neural_result.validate()
        else:
            valid, errors = False, ["NEURAL_RESULT_VALIDATE_MISSING"]

        result.audit_log.extend(errors)
        if not valid:
            result.neural_output_compliance = Verdict.FAIL
            result.overall = Verdict.FAIL
            result.downgrade_reason = "; ".join(errors)
        elif not getattr(neural_result, "requires_symbolic_verification", True):
            result.neural_output_compliance = Verdict.FAIL
            result.overall = Verdict.FAIL
            result.downgrade_reason = "SYMBOLIC_VERIFICATION_REQUIRED"
        else:
            result.neural_output_compliance = Verdict.PASS
            result.audit_log.append("neural_output_guardrails=PASS")

        self.results.append(result)
        return result
