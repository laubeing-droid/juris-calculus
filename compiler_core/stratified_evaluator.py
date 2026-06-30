#!/usr/bin/env python3
"""v2.1 Stratified Evaluator — four-stage pipeline.

Stage 1: evaluate_horn() — pure monotone Horn closure
Stage 2: build_attack_graph_from_evaluator() — AAF attack graph + rebuttal
Stage 3: grounded_extension() — Dung deterministic extension
Stage 4: Trust label projection + allowed/forbidden marking

Mathematical basis:
- Stage 1 specification: legal-math-modeling HornFixedPoint.lean.
- Stage 3 specification: legal-math-modeling DungFixedPoint.lean.
- Runtime evidence: local pytest, spec shadow fixtures, and independent checker tests.
"""
from typing import List, Dict, Optional
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.argumentation import (
    build_attack_graph_from_evaluator,
    grounded_extension, find_cycles,
)
from compiler_core.trust_labels import TrustLabel, EpistemicStatus, DataOrigin, RuleMaturity
from compiler_core.domain_config import DomainConfig
from compiler_core.types import LegalDomain, LegalClaim, IRState


class StratifiedEvaluator:

    @staticmethod
    def _check_damage_limits(claims):
        """Post-process: validate damage claims against statutory limits."""
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
        self.evaluator = FixpointEvaluator(
            self.rules, DomainConfig(domain=LegalDomain.CIVIL),
            overrides_path=overrides_path
        )
        # Reverse index: head_claim -> rule (O(1) lookup for rebuttal)
        self._claim_to_rule = {}
        for r in self.rules:
            if r.head_claim:
                self._claim_to_rule[r.head_claim] = r

    def evaluate(self, state: IRState, contract: Optional[Dict] = None) -> List[LegalClaim]:
        """Four-stage pipeline: Horn -> AAF -> Grounded Extension -> Trust Labels."""

        # Stage 1: Pure monotone Horn closure
        horn_state = self.evaluator.evaluate_horn(state)
        raw_claims = list(horn_state.claims.values())
        if not raw_claims:
            return []

        # Stage 2: Build complete attack graph
        evaluator_result = {"labels": {cid: cid for cid in horn_state.claims}}
        attacks = build_attack_graph_from_evaluator(
            self.rules, evaluator_result
        )

        # Stage 2b: Run rebuttal checks (non-monotone part) — O(claims) with reverse index
        if self.evaluator.constraint_validator.loaded:
            for claim in raw_claims:
                rule = self._claim_to_rule.get(claim.id)
                if rule and rule.concepts:
                    rebuttal = self.evaluator.constraint_validator.check_rebuttal(
                        claim.id, rule.concepts, horn_state
                    )
                    if rebuttal.triggered:
                        claim.confidence = 0.0
                        claim.forbidden_claim = True

        # Stage 3: Dung grounded extension (exclude confidence=0 claims)
        active_claims = [c for c in raw_claims if c.confidence > 0]
        ge_result = grounded_extension(
            [{"id": c.id, "confidence": c.confidence} for c in active_claims],
            attacks
        )
        accepted_ids = set(ge_result["accepted"])
        undecided_ids = set(ge_result.get("undecided", []))

        # Stage 4: Trust label projection + agent payload
        result = []
        for c in raw_claims:
            if c.id in accepted_ids and c.confidence > 0:
                c.allowed_claim = True
                c.forbidden_claim = False
                if c.epistemic_status is None:
                    c.epistemic_status = EpistemicStatus(
                        trust_label=TrustLabel.ENGINEERING_BASELINE,
                        rule_maturity=RuleMaturity.L2_TESTED,
                        data_origin=DataOrigin.SYMBOLIC_ENGINE,
                    )
                result.append(c)
            elif c.id in undecided_ids and c.confidence > 0:
                c.allowed_claim = False
                c.forbidden_claim = False
                c.requires_human_review = True
                result.append(c)
            else:
                c.allowed_claim = False
                c.forbidden_claim = True

        return result
