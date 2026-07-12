from compiler_core.neural_leaf import (
    NeuralLeafRegistry,
    NeuralLeafResult,
    NeuralLeafTrustLabel,
    NeuralLeafType,
)
from compiler_core.step_verifier import StepVerifier, Verdict


def test_neural_leaf_result_rejects_legal_decision_fields():
    result = NeuralLeafResult(
        node_id="rerank-1",
        node_type=NeuralLeafType.CASE_SIMILARITY_RERANKER,
        score=0.8,
        model_confidence=0.7,
        raw_output={"nested": {"legal_conclusion": "contract valid"}},
    )

    valid, errors = result.validate()

    assert not valid
    assert "FORBIDDEN_OUTPUT_FIELD: legal_conclusion" in errors


def test_registry_validates_registered_node_and_kill_switch():
    registry = NeuralLeafRegistry()
    assert registry.register("risk-1", NeuralLeafType.REBUTTAL_RISK_SCORER)
    result = NeuralLeafResult(
        node_id="risk-1",
        node_type=NeuralLeafType.REBUTTAL_RISK_SCORER,
        score=0.4,
        risk_level="MEDIUM",
        model_confidence=0.6,
        features_used=["rule_count"],
        feature_importance={"rule_count": 0.9},
    )

    valid, errors = registry.validate_result(result)
    assert valid, errors

    registry.kill()
    valid, errors = registry.validate_result(result)
    assert not valid
    assert "KILL_SWITCH_ACTIVE" in errors


def test_neural_leaf_requires_symbolic_verification_and_safe_ranges():
    result = NeuralLeafResult(
        node_id="calibrator-1",
        node_type=NeuralLeafType.SEMANTIC_THRESHOLD_CALIBRATOR,
        score=1.2,
        calibration_delta=2.0,
        trust_label=NeuralLeafTrustLabel.ENGINEERING_BASELINE,
        requires_symbolic_verification=False,
    )

    valid, errors = result.validate()

    assert not valid
    assert "SCORE_OUT_OF_RANGE: 1.2" in errors
    assert "CALIBRATION_DELTA_OUT_OF_RANGE: 2.0" in errors
    assert "SYMBOLIC_VERIFICATION_REQUIRED" in errors


def test_step_verifier_rejects_invalid_neural_output():
    result = NeuralLeafResult(
        node_id="risk-2",
        node_type=NeuralLeafType.REBUTTAL_RISK_SCORER,
        score=0.9,
        model_confidence=0.9,
        raw_output={"final_decision": "liable"},
    )

    checked = StepVerifier().verify_neural_output(result)

    assert checked.neural_output_compliance == Verdict.FAIL
    assert checked.overall == Verdict.FAIL
    assert "FORBIDDEN_OUTPUT_FIELD: final_decision" in checked.downgrade_reason
