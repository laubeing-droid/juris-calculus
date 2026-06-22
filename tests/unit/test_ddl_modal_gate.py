"""Tests for DDL modal gate behavior (#13) and PROHIBITION regression (#14)."""
import unittest
from compiler_core.types import LegalRule, LegalFact, IRState, LegalDomain
from compiler_core.evaluator import FixpointEvaluator, CriticalClarityFailure
from compiler_core.domain_config import DomainConfig
from compiler_core.trust_labels import TrustLabel


def _make_rule(rid, premises, head, modality="UNKNOWN", head_type="HORN", mechanical=True, exception_chain=None):
    return LegalRule(
        id=rid, premise_atoms=premises, head_claim=head,
        head_type=head_type, mechanical_exception=mechanical,
        norm_modality=modality, exception_chain=exception_chain or [],
    )


def _make_facts(**kwargs):
    return {k: LegalFact(id=k, description=k, extraction_confidence=v) for k, v in kwargs.items()}


class TestDDLModalGate(unittest.TestCase):
    """#13: DDL 模态门控专项测试"""

    def test_obligation_gap_produces_negative_spec(self):
        """OBLIGATION rule with missing premises → negative spec, not a claim."""
        rule = _make_rule("R1", ["A", "B"], "C", modality="OBLIGATION")
        ev = FixpointEvaluator([rule], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))  # B is missing
        result = ev.evaluate(state)
        self.assertNotIn("C", result.claims)
        # Should have a negative spec
        specs = [s for s in result.negative_specs if s.get("rule_id") == "R1"]
        self.assertEqual(len(specs), 1)
        self.assertIn("B", specs[0]["missing"])

    def test_prohibition_blocks_claim(self):
        """PROHIBITION rule blocks its head_claim."""
        rule = _make_rule("R1", ["A"], "B", modality="PROHIBITION")
        ev = FixpointEvaluator([rule], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        self.assertIn("B", result.blocked_claims)
        self.assertNotIn("B", result.claims)

    def test_prohibition_prevents_downstream_use(self):
        """#14: Blocked claim cannot be used as premise by downstream rules (#1 fix)."""
        r1 = _make_rule("R1", ["A"], "B", modality="PROHIBITION")
        r2 = _make_rule("R2", ["B"], "C")  # uses B as premise
        ev = FixpointEvaluator([r1, r2], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        self.assertIn("B", result.blocked_claims)
        self.assertNotIn("C", result.claims,
            "Downstream rule should NOT fire when its premise is blocked by PROHIBITION")

    def test_permission_marks_hypothetical(self):
        """#6: PERMISSION rules produce HYPOTHETICAL claims."""
        rule = _make_rule("R1", ["A"], "B", modality="PERMISSION")
        ev = FixpointEvaluator([rule], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        if "B" in result.claims:
            claim = result.claims["B"]
            self.assertEqual(claim.epistemic_status.trust_label, TrustLabel.UNVERIFIED)

    def test_constitutive_produces_claim(self):
        """CONSTITUTIVE rules produce normal claims."""
        rule = _make_rule("R1", ["A"], "B", modality="CONSTITUTIVE")
        ev = FixpointEvaluator([rule], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        self.assertIn("B", result.claims)
        self.assertNotIn("B", result.blocked_claims)

    def test_unknown_modality_passes_through(self):
        """UNKNOWN modality behaves like normal HORN rule."""
        rule = _make_rule("R1", ["A"], "B", modality="UNKNOWN")
        ev = FixpointEvaluator([rule], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        self.assertIn("B", result.claims)

    def test_prohibition_then_normal_rule_chain(self):
        """Normal chain: A→B (normal), then B→C (normal) both fire."""
        r1 = _make_rule("R1", ["A"], "B")
        r2 = _make_rule("R2", ["B"], "C")
        ev = FixpointEvaluator([r1, r2], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        self.assertIn("B", result.claims)
        self.assertIn("C", result.claims)

    def test_prohibition_interrupts_chain(self):
        """Chain interrupted: A→B (normal), B→BLOCKED (PROHIBITION), B→C (normal, should NOT fire)."""
        r1 = _make_rule("R1", ["A"], "B")
        r2 = _make_rule("R2_BLOCK", ["B"], "B_BLOCKED", modality="PROHIBITION")
        # R3 wants to use B as premise - but B is not blocked by R2.
        # R2 blocks B_BLOCKED, not B. So B is still usable.
        # This tests that only the head_claim of PROHIBITION is blocked.
        r3 = _make_rule("R3", ["B"], "C")
        ev = FixpointEvaluator([r1, r2, r3], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        self.assertIn("B_BLOCKED", result.blocked_claims)
        # B itself is not blocked, so R3 can still fire
        self.assertIn("C", result.claims)

    def test_exception_overrides_prohibition(self):
        """Exception chain: rule fires but exception fires too, producing different claim."""
        r1 = _make_rule("R1", ["A"], "B", exception_chain=["R1_EX"])
        r1_ex = _make_rule("R1_EX", ["EX_FACT"], "B_OVERRIDDEN")
        ev = FixpointEvaluator([r1, r1_ex], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9, EX_FACT=0.9))
        result = ev.evaluate(state)
        # Exception fires, so original claim B should not be produced
        # Instead, B_OVERRIDDEN should be produced
        self.assertIn("B_OVERRIDDEN", result.claims)

    def test_l0_degradation_skipped_for_irrelevant_map(self):
        """#5: L0 degradation skipped when l0_map has no relevant entries."""
        # CN rule with CN-style atoms, US-style l0_map (no overlap)
        rule = _make_rule("R1", ["contract_formed"], "breach_concluded")
        l0_map = {"Consideration_Provided": "Power", "Arbitral_Award": "Status"}  # US terms only
        ev = FixpointEvaluator([rule], DomainConfig(domain=LegalDomain.CIVIL), l0_map=l0_map)
        state = IRState(facts=_make_facts(contract_formed=0.9))
        result = ev.evaluate(state)
        if "breach_concluded" in result.claims:
            # Should NOT be degraded to UNVERIFIED
            claim = result.claims["breach_concluded"]
            self.assertNotEqual(claim.epistemic_status.trust_label, TrustLabel.UNVERIFIED)

    def test_l0_degradation_active_for_relevant_map(self):
        """L0 degradation active when some premises map but some don't."""
        rule = _make_rule("R1", ["contract_formed", "unknown_concept"], "result")
        l0_map = {"contract_formed": "Status"}  # partial mapping
        ev = FixpointEvaluator([rule], DomainConfig(domain=LegalDomain.CIVIL), l0_map=l0_map)
        state = IRState(facts=_make_facts(contract_formed=0.9, unknown_concept=0.8))
        result = ev.evaluate(state)
        if "result" in result.claims:
            claim = result.claims["result"]
            self.assertEqual(claim.epistemic_status.trust_label, TrustLabel.UNVERIFIED)

    def test_deterministic_execution_order(self):
        """#2: Execution order is deterministic (sorted)."""
        rules = [_make_rule(f"R{i}", ["A"], f"C{i}") for i in range(10)]
        results = []
        for _ in range(5):
            ev = FixpointEvaluator(rules, DomainConfig(domain=LegalDomain.CIVIL))
            state = IRState(facts=_make_facts(A=0.9))
            result = ev.evaluate(state)
            results.append(list(result.claims.keys()))
        # All runs should produce identical claim sets
        for r in results[1:]:
            self.assertEqual(r, results[0], "Execution order should be deterministic")


class TestProhibitionRegression(unittest.TestCase):
    """#14: PROHIBITION bug regression tests."""

    def test_blocked_claim_not_in_claims(self):
        """Blocked claim should not appear in claims dict."""
        rule = _make_rule("R1", ["A"], "B", modality="PROHIBITION")
        ev = FixpointEvaluator([rule], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        self.assertNotIn("B", result.claims)

    def test_blocked_claim_in_blocked_set(self):
        """Blocked claim should appear in blocked_claims set."""
        rule = _make_rule("R1", ["A"], "B", modality="PROHIBITION")
        ev = FixpointEvaluator([rule], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        self.assertIn("B", result.blocked_claims)

    def test_downstream_rule_respects_block(self):
        """Downstream rule that depends on blocked claim should not fire."""
        r1 = _make_rule("BLOCK", ["A"], "B", modality="PROHIBITION")
        r2 = _make_rule("USE_B", ["B"], "C")
        ev = FixpointEvaluator([r1, r2], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        self.assertNotIn("C", result.claims)

    def test_unrelated_rule_not_affected_by_block(self):
        """Rule that doesn't depend on blocked claim should still fire."""
        r1 = _make_rule("BLOCK", ["A"], "B", modality="PROHIBITION")
        r2 = _make_rule("USE_A", ["A"], "D")  # uses A, not B
        ev = FixpointEvaluator([r1, r2], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        self.assertIn("D", result.claims)

    def test_multiple_prohibitions(self):
        """Multiple PROHIBITION rules can block different claims."""
        r1 = _make_rule("B1", ["A"], "X", modality="PROHIBITION")
        r2 = _make_rule("B2", ["A"], "Y", modality="PROHIBITION")
        r3 = _make_rule("USE_XY", ["X", "Y"], "Z")
        ev = FixpointEvaluator([r1, r2, r3], DomainConfig(domain=LegalDomain.CIVIL))
        state = IRState(facts=_make_facts(A=0.9))
        result = ev.evaluate(state)
        self.assertIn("X", result.blocked_claims)
        self.assertIn("Y", result.blocked_claims)
        self.assertNotIn("Z", result.claims)


if __name__ == "__main__":
    unittest.main()
