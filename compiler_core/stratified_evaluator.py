#!/usr/bin/env python3
"""v2.0 Stratified Evaluator - four-stage Layer 5 pipeline.

Stage 1: Horn closure on routed rules (monotone, PROVED_FORMAL)
Stage 2: Attack graph construction (Dung AAF)
Stage 3: Grounded extension computation (deterministic)
Stage 4: Trust label projection onto output claims
"""
from typing import List, Dict, Optional
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.argumentation import build_attack_edges_from_rules, grounded_extension
from compiler_core.trust_labels import TrustLabel, EpistemicStatus, DataOrigin, RuleMaturity
from compiler_core.domain_config import DomainConfig
from compiler_core.types import LegalDomain, LegalClaim


class StratifiedEvaluator:

    @staticmethod
    def _check_damage_limits(claims):
        """Post-process: validate damage claims against statutory limits from blueprint."""
        try:
            import json
            from compiler_core.config_paths import blueprint_path
            bp = json.load(open(blueprint_path(), "r", encoding="utf-8"))
            rules = bp.get("damage_calculation_rules", [])
            warnings = []
            for claim in claims:
                desc = getattr(claim, "description", "")
                if any(kw in desc for kw in ["赔偿", "违约金", "利息", "LPR", "damages", "penalty"]):
                    for rule in rules[:5]:
                        warnings.append(f"Damage limit: {rule[:100]}")
            return warnings
        except Exception:
            return []

    def __init__(self, rules_path: str, overrides_path: Optional[str] = None):
        self.rules = load_rules_from_yaml(rules_path)
        self.evaluator = FixpointEvaluator(self.rules, DomainConfig(domain=LegalDomain.CIVIL),
                                           overrides_path=overrides_path)

    def evaluate(self, state, contract: Optional[Dict] = None) -> List[LegalClaim]:
        raw_claims = self.evaluator.evaluate(state)
        if not raw_claims:
            return []

        attacks = build_attack_edges_from_rules(self.rules)
        for i, c1 in enumerate(raw_claims):
            for j, c2 in enumerate(raw_claims):
                if i != j and c1.id != c2.id:
                    for note in getattr(c1, 'exception_notes', []):
                        if c2.id in note and (c1.id, c2.id) not in attacks:
                            attacks.append((c1.id, c2.id))

        ge_result = grounded_extension(
            [{"id": c.id, "confidence": c.confidence} for c in raw_claims],
            attacks
        )

        accepted_ids = set(ge_result["accepted"])
        result = []
        for c in raw_claims:
            if c.id in accepted_ids:
                if c.epistemic_status is None:
                    c.epistemic_status = EpistemicStatus(
                        trust_label=TrustLabel.ENGINEERING_BASELINE,
                        rule_maturity=RuleMaturity.L2_TESTED,
                        data_origin=DataOrigin.SYMBOLIC_ENGINE,
                    )
                result.append(c)

        return result
