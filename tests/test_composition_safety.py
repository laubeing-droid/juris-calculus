"""Phase E compositional safety tests."""
from compiler_core.composition_safety import (
    Stage1Interface, Stage2Interface, Stage3Interface, Stage4Interface,
    check_attack_graph_completeness, check_compositional_safety,
    GoldenCase, GOLDEN_CORPUS, CompositionSafetyReport,
)

def test_stage1_saturated():
    s1 = Stage1Interface(claims=["A"], source_rules=["R1"], saturation_status="saturated", provenance=[], truncation_warning="")
    assert s1.validate() == []

def test_stage1_truncated_no_warning():
    s1 = Stage1Interface(claims=[], source_rules=[], saturation_status="truncated", provenance=[], truncation_warning="")
    assert len(s1.validate()) >= 1

def test_stage2_orphan_attacker():
    s2 = Stage2Interface(arguments=[{"id":"A"}], attack_edges=[("X","A")], edge_sources={}, source_anchors=[], completeness="complete")
    assert len(s2.validate()) >= 1

def test_stage3_truncated_convergent():
    s3 = Stage3Interface(accepted=[], rejected=[], undecided=[], convergent=True, truncated=True, certificate=None, witness_data={})
    assert len(s3.validate()) >= 1

def test_stage4_undec_to_forbidden():
    s4 = Stage4Interface(label_map={"A":"forbidden"}, forbidden=["A"], human_review=[], undec_degraded=False)
    assert len(s4.validate()) == 0

def test_composition_undec_to_forbidden():
    s3 = Stage3Interface(accepted=[], rejected=[], undecided=["A"], convergent=True, truncated=False, certificate=None, witness_data={})
    s4 = Stage4Interface(label_map={"A":"forbidden"}, forbidden=["A"], human_review=[], undec_degraded=False)
    report = check_compositional_safety(None, None, s3, s4)
    assert not report.safe

def test_attack_graph_completeness():
    report = check_attack_graph_completeness([{"id":"A"}], [], [("A","B")], {"rebuttal": ["A->B"]})
    assert not report.complete

def test_golden_corpus_size():
    assert len(GOLDEN_CORPUS) >= 9

def test_golden_case_validation():
    case = GoldenCase(case_id="test", description="test", facts=[{"id":"F1"}], rules=[{"id":"R1","head":"H","body":["F1"]}], generated_aaf={}, expected_labels={"A":"IN"}, proof_certificates=[], trust_projection={}, source_anchors=[])
    assert case.validate() == []
