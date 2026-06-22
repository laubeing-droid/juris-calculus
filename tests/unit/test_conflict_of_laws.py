"""Tests for conflict_of_laws and multi_jurisdiction_orchestrator (#10, #11)."""
import unittest
from compiler_core.types import LegalFact
from compiler_core.conflict_of_laws import select_jurisdiction


def _facts(*names):
    return {n: LegalFact(id=n, description=n, extraction_confidence=0.9) for n in names}


class TestConflictOfLaws(unittest.TestCase):

    def test_explicit_choice_cn(self):
        result = select_jurisdiction({}, explicit_choice="CN")
        self.assertEqual(result, "CN")

    def test_explicit_choice_hk(self):
        result = select_jurisdiction({}, explicit_choice="HK")
        self.assertEqual(result, "HK")

    def test_choice_of_law_fact_cn(self):
        result = select_jurisdiction(_facts("governing_law_cn", "contract_formed"))
        self.assertEqual(result, "CN")

    def test_choice_of_law_fact_hk(self):
        result = select_jurisdiction(_facts("governing_law_hk", "ContractOfSale_Exists"))
        self.assertEqual(result, "HK")

    def test_closest_connection_cn(self):
        """CN signals dominate → CN selected."""
        facts = _facts("contract_formed", "breach_alleged", "damages_claimed")
        result = select_jurisdiction(facts)
        self.assertEqual(result, "CN")

    def test_closest_connection_us(self):
        """US signals dominate → US selected."""
        facts = _facts("Consideration_Provided", "Arbitration_Agreement_Valid_Enforceable")
        result = select_jurisdiction(facts)
        self.assertEqual(result, "US")

    def test_default_when_no_signals(self):
        """No signals → default CN."""
        result = select_jurisdiction({})
        self.assertEqual(result, "CN")

    def test_default_override(self):
        """Default can be overridden."""
        result = select_jurisdiction({}, default_jurisdiction="HK")
        self.assertEqual(result, "HK")


class TestMultiJurisdictionOrchestrator(unittest.TestCase):

    def test_orchestrator_imports(self):
        """Module imports without error."""
        from compiler_core.multi_jurisdiction_orchestrator import MultiJurisdictionOrchestrator
        mjo = MultiJurisdictionOrchestrator()
        self.assertIsNotNone(mjo)


if __name__ == "__main__":
    unittest.main()
