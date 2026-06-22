"""Unit tests for compiler_core FixpointEvaluator."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import unittest
from compiler_core.types import LegalRule, LegalFact, IRState, LegalDomain
from compiler_core.evaluator import FixpointEvaluator, CriticalClarityFailure
from compiler_core.domain_config import DomainConfig


class TestFixpointEvaluator(unittest.TestCase):

    def setUp(self):
        self.rules = [
            LegalRule("R1", ["A"], "C1", concepts=["Contract"]),
            LegalRule("R2", ["C1", "B"], "C2", concepts=["Contract", "Performance"]),
            LegalRule("R3", ["C2", "D"], "C3", 
                      exception_chain=["R_exc"], concepts=["Breach", "Damages"]),
            LegalRule("R_exc", ["force_majeure"], "C_exc", concepts=["ForceMajeure"],
                      mechanical_exception=False),
        ]
        self.config = DomainConfig(
            domain=LegalDomain.CIVIL,
            weights=(0.2, 0.2, 0.4, 0.2),
            taint_threshold=0.5,
            hard_audit_threshold=0.2,
            k_max=3,
            concept_registry={"Contract", "Performance", "Breach", "Damages", "ForceMajeure"},
        )
        self.ev = FixpointEvaluator(self.rules, self.config)

    def test_basic_fixpoint_convergence(self):
        state = IRState(world_id="test1")
        state.facts["A"] = LegalFact("A", "fact_a")
        state.facts["B"] = LegalFact("B", "fact_b")
        state.facts["D"] = LegalFact("D", "fact_d")
        result = self.ev.evaluate(state)
        self.assertIn("C1", result.claims)
        self.assertIn("C2", result.claims)
        self.assertIn("C3", result.claims)

    def test_exception_chain_blocks_claim(self):
        state = IRState(world_id="test2")
        state.facts["A"] = LegalFact("A", "fact_a")
        state.facts["B"] = LegalFact("B", "fact_b")
        state.facts["D"] = LegalFact("D", "fact_d")
        state.facts["force_majeure"] = LegalFact("force_majeure", "flood")
        result = self.ev.evaluate(state)
        self.assertIn("C_exc", result.claims)
        # C3 should NOT be found because exception chain triggered
        self.assertNotIn("C3", result.claims)

    def test_honest_refusal_on_missing_facts(self):
        state = IRState(world_id="test3")
        state.facts["A"] = LegalFact("A", "fact_a")
        result = self.ev.evaluate(state)
        self.assertIn("C1", result.claims)
        self.assertNotIn("C2", result.claims)

    def test_critical_clarity_failure_raised(self):
        fragile_rules = [
            LegalRule("R_low1", ["X"], "Y", concepts=[]),
            LegalRule("R_low2", ["Y"], "Z", concepts=[]),
            LegalRule("R_low3", ["Z"], "W", concepts=[]),
        ]
        fragile_config = DomainConfig(
            domain=LegalDomain.CIVIL,
            weights=(0.0, 0.0, 0.0, 0.0),
            taint_threshold=0.9,
            hard_audit_threshold=0.9,
            k_max=3,
            critical_score_threshold=0.5,
            critical_streak_max=3,
        )
        ev = FixpointEvaluator(fragile_rules, fragile_config)
        state = IRState(world_id="test4")
        state.facts["X"] = LegalFact("X", "trigger")
        with self.assertRaises(CriticalClarityFailure):
            ev.evaluate(state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
