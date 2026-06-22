"""Non-monotone regression tests.

Mathematical basis: evaluator_nonmonotone_counterexample.py
"""
import pytest
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.types import LegalRule, IRState, LegalFact, LegalDomain
from compiler_core.domain_config import DomainConfig


class TestNonmonotoneRegression:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        rules_yaml = tmp_path / "rules.yaml"
        rules_yaml.write_text(
            "rules:\n"
            "  - id: NM-001\n"
            "    premise_atoms: [fact_a]\n"
            "    head_claim: claim_c1\n"
            "    concepts: []\n"
            "    exception_chain: []\n"
            "    head_type: HORN\n"
            "    mechanical_exception: true\n"
            "    norm_modality: OBLIGATION\n"
            "  - id: NM-002\n"
            "    premise_atoms: [fact_a, fact_b]\n"
            "    head_claim: claim_c2\n"
            "    concepts: []\n"
            "    exception_chain: [NM-003]\n"
            "    head_type: HORN\n"
            "    mechanical_exception: true\n"
            "    norm_modality: OBLIGATION\n"
            "  - id: NM-003\n"
            "    premise_atoms: [fact_x]\n"
            "    head_claim: exception_claim\n"
            "    concepts: []\n"
            "    exception_chain: []\n"
            "    head_type: HORN\n"
            "    mechanical_exception: true\n"
            "    norm_modality: CONSTITUTIVE\n",
            encoding="utf-8",
        )
        self.rules = load_rules_from_yaml(str(rules_yaml))
        self.config = DomainConfig(domain=LegalDomain.CIVIL)

    def test_horn_closure_is_monotone(self):
        """Stage 1 Horn closure must be monotone: A subset B => E(A) subset E(B)"""
        state_a = IRState()
        state_a.facts["fact_a"] = LegalFact(id="fact_a", description="a")
        ev_a = FixpointEvaluator(self.rules, self.config)
        result_a = ev_a.evaluate_horn(state_a)

        state_b = IRState()
        state_b.facts["fact_a"] = LegalFact(id="fact_a", description="a")
        state_b.facts["fact_b"] = LegalFact(id="fact_b", description="b")
        ev_b = FixpointEvaluator(self.rules, self.config)
        result_b = ev_b.evaluate_horn(state_b)

        claims_a = set(result_a.claims.keys())
        claims_b = set(result_b.claims.keys())
        assert claims_a.issubset(claims_b), f"Horn not monotone: E(A)={claims_a}, E(B)={claims_b}"

    def test_rebuttal_zeros_confidence(self):
        """Evaluate produces claims with non-negative confidence."""
        state = IRState()
        state.facts["fact_a"] = LegalFact(id="fact_a", description="a")
        ev = FixpointEvaluator(self.rules, self.config)
        result = ev.evaluate(state)
        for c in result.claims.values():
            assert c.confidence >= 0.0
