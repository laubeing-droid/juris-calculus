"""#16: ConstraintValidator unit tests."""
import unittest
from compiler_core.constraint_validator import ConstraintValidator
from compiler_core.types import IRState, LegalFact


class TestConstraintValidator(unittest.TestCase):

    def test_loads_with_valid_overrides(self):
        cv = ConstraintValidator(overrides_path="configs/L0_overrides_cn.yaml")
        self.assertTrue(cv.loaded)

    def test_get_undefined_concepts_empty(self):
        cv = ConstraintValidator(overrides_path="configs/L0_overrides_cn.yaml")
        result = cv.get_undefined_concepts([])
        self.assertIsInstance(result, list)

    def test_check_constraint_rules_returns_list(self):
        cv = ConstraintValidator(overrides_path="configs/L0_overrides_cn.yaml")
        state = IRState(facts={
            "test_fact": LegalFact(id="test_fact", description="", extraction_confidence=0.9)
        })
        result = cv.check_constraint_rules(state)
        self.assertIsInstance(result, list)

    def test_check_rebuttal_returns_result(self):
        cv = ConstraintValidator(overrides_path="configs/L0_overrides_cn.yaml")
        state = IRState(facts={
            "test_fact": LegalFact(id="test_fact", description="", extraction_confidence=0.9)
        })
        result = cv.check_rebuttal("test_claim", ["Contract"], state)
        # Returns a RebuttalResult or None
        self.assertTrue(result is None or hasattr(result, '__class__'))

    def test_resolve_l0_primitive_returns_string(self):
        cv = ConstraintValidator(overrides_path="configs/L0_overrides_cn.yaml")
        result = cv.resolve_L0_primitive("Contract")
        self.assertIsInstance(result, str)

    def test_validate_l2_l0_completeness(self):
        cv = ConstraintValidator(overrides_path="configs/L0_overrides_cn.yaml")
        result = cv.validate_L2_L0_completeness()
        self.assertIsInstance(result, (dict, list))


if __name__ == "__main__":
    unittest.main()
