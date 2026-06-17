"""Tests for StratifiedEvaluator (Phase 2C: bug fix verification)."""
import pytest
from compiler_core.stratified_evaluator import StratifiedEvaluator
from compiler_core.types import LegalClaim


class TestStratifiedEvaluator:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        rules_yaml = tmp_path / "rules.yaml"
        rules_yaml.write_text(
            "rules:\n"
            "  - id: SE-001\n"
            "    premise_atoms: [fact_a]\n"
            "    head_claim: claim_a\n"
            "    concepts: [contract]\n"
            "    exception_chain: []\n"
            "    head_type: HORN\n"
            "    mechanical_exception: true\n"
            "    norm_modality: OBLIGATION\n"
            "  - id: SE-002\n"
            "    premise_atoms: [fact_b]\n"
            "    head_claim: claim_b\n"
            "    concepts: [tort]\n"
            "    exception_chain: []\n"
            "    head_type: HORN\n"
            "    mechanical_exception: true\n"
            "    norm_modality: OBLIGATION\n",
            encoding="utf-8",
        )
        self.evaluator = StratifiedEvaluator(str(rules_yaml))

    def test_returns_list_not_irdstate(self):
        """evaluate() must return List[LegalClaim], not IRState."""
        from compiler_core.types import IRState, LegalFact
        state = IRState()
        state.facts["fact_a"] = LegalFact(id="fact_a", description="fact a")
        result = self.evaluator.evaluate(state)
        assert isinstance(result, list)
        for c in result:
            assert isinstance(c, LegalClaim)

    def test_returns_claims_when_facts_match(self):
        """Matching facts should produce at least one accepted claim."""
        from compiler_core.types import IRState, LegalFact
        state = IRState()
        state.facts["fact_a"] = LegalFact(id="fact_a", description="fact a")
        state.facts["fact_b"] = LegalFact(id="fact_b", description="fact b")
        result = self.evaluator.evaluate(state)
        assert len(result) >= 1
        claim_ids = {c.id for c in result}
        assert "claim_a" in claim_ids or "claim_b" in claim_ids

    def test_returns_empty_when_no_facts(self):
        """No facts -> no claims."""
        from compiler_core.types import IRState
        state = IRState()
        result = self.evaluator.evaluate(state)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_accepted_claims_have_epistemic_status(self):
        """Accepted claims must have epistemic_status set."""
        from compiler_core.types import IRState, LegalFact
        state = IRState()
        state.facts["fact_a"] = LegalFact(id="fact_a", description="fact a")
        result = self.evaluator.evaluate(state)
        for c in result:
            assert c.epistemic_status is not None
