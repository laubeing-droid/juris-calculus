"""Adversarial test — verify engine rejects misleading inputs."""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.types import IRState, LegalFact, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.config_paths import rules_path


class TestAdversarial:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.rules = load_rules_from_yaml(rules_path("zh_CN"))
        self.config = DomainConfig(domain=LegalDomain.CIVIL)

    def test_empty_facts_returns_no_claims(self):
        """Empty facts should produce no claims."""
        state = IRState()
        ev = FixpointEvaluator(self.rules, self.config)
        result = ev.evaluate(state)
        assert len(result.claims) == 0

    def test_unrelated_facts_low_confidence(self):
        """Completely unrelated facts should produce few/no high-confidence claims."""
        state = IRState()
        state.facts["random_xyz"] = LegalFact(id="random_xyz", description="今日天气晴朗适合郊游")
        ev = FixpointEvaluator(self.rules, self.config)
        result = ev.evaluate(state)
        high_conf = sum(1 for c in result.claims.values() if c.confidence > 0.7)
        assert high_conf <= 2  # very few or none

    def test_contradictory_facts_handled(self):
        """Contradictory facts should not crash the engine."""
        state = IRState()
        state.facts["fact_contract_valid"] = LegalFact(id="fact_contract_valid", description="合同有效成立")
        state.facts["fact_contract_void"] = LegalFact(id="fact_contract_void", description="合同无效自始无效")
        ev = FixpointEvaluator(self.rules, self.config)
        result = ev.evaluate(state)
        # Should not crash
        assert isinstance(result.claims, dict)

    def test_single_generic_fact(self):
        """A single very generic fact should not trigger thousands of rules."""
        state = IRState()
        state.facts["generic"] = LegalFact(id="generic", description="当事人之间存在纠纷")
        ev = FixpointEvaluator(self.rules, self.config)
        result = ev.evaluate(state)
        # Should trigger some rules but not all 21,145
        assert len(result.claims) < 100
