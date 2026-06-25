"""Phase C G9B litigation engineering tests."""

from compiler_core.argumentation import grounded_extension
from compiler_core.litigation_engineering import (
    LabelCertificate,
    InterventionPlan,
    StabilityAnalysis,
    analyze_stability,
    check_scc_correctness,
    find_minimal_intervention,
    generate_all_certificates,
    generate_certificate,
)


def _c(id_):
    return {"id": id_}


def test_scc_correctness_dag():
    """DAG: SCC decomposition preserves grounded semantics."""
    claims = [_c("A"), _c("B"), _c("C")]
    attacks = [("A", "B"), ("B", "C")]
    result = check_scc_correctness(claims, attacks)
    assert result.correct is True
    assert result.mismatches == []


def test_scc_correctness_pure_cycle():
    """Pure cycle stays inside one SCC and matches full computation."""
    claims = [_c("A"), _c("B")]
    attacks = [("A", "B"), ("B", "A")]
    result = check_scc_correctness(claims, attacks)
    assert result.correct is True
    assert result.scc_order == [["A", "B"]]


def test_scc_correctness_cross_scc_regression():
    """Known mixed case currently remains equivalent to full grounded evaluation."""
    claims = [_c("A"), _c("B"), _c("C")]
    attacks = [("C", "A"), ("A", "B"), ("B", "A")]
    result = check_scc_correctness(claims, attacks)
    assert result.correct is True
    assert result.full_accepted == ["B", "C"]
    assert result.scc_accepted == ["B", "C"]


def test_certificate_verifiable():
    claims = [_c("A"), _c("B")]
    attacks = [("A", "B")]
    result = grounded_extension(claims, attacks)
    cert = generate_certificate("A", claims, attacks, result)
    assert cert.label == "IN"
    assert cert.verifiable is True
    assert cert.attackers == []


def test_all_certificates():
    claims = [_c("A"), _c("B")]
    attacks = [("A", "B")]
    result = grounded_extension(claims, attacks)
    certs = generate_all_certificates(claims, attacks, result)
    assert len(certs) == 2
    assert all(isinstance(cert, LabelCertificate) for cert in certs)
    assert all(cert.verifiable for cert in certs)


def test_certificate_minimizes_shared_defender():
    claims = [_c("A"), _c("B"), _c("C"), _c("D")]
    attacks = [("B", "A"), ("C", "A"), ("D", "B"), ("D", "C")]
    result = grounded_extension(claims, attacks)
    cert = generate_certificate("A", claims, attacks, result)
    assert cert.label == "IN"
    assert cert.attackers == ["B", "C"]
    assert cert.minimal_witnesses == ["D"]
    assert cert.witnesses == ["D"]
    assert cert.proof_depth == 1
    assert cert.defense_paths == [
        {"target": "A", "attacker": "B", "defenders": ["D"]},
        {"target": "A", "attacker": "C", "defenders": ["D"]},
    ]


def test_certificate_tracks_undecided_dependency_witness():
    claims = [_c("A"), _c("B"), _c("C")]
    attacks = [("A", "B"), ("B", "A"), ("B", "C")]
    result = grounded_extension(claims, attacks)
    cert = generate_certificate("C", claims, attacks, result)
    assert cert.label == "UNDEC"
    assert cert.attackers == ["B"]
    assert cert.witnesses == ["B"]


def test_intervention_undec_to_in():
    """A<-B (A attacked by B, B undefended): add defender for A."""
    claims = [_c("A"), _c("B")]
    attacks = [("B", "A")]
    result = grounded_extension(claims, attacks)
    plan = find_minimal_intervention("A", claims, attacks, result)
    assert isinstance(plan, InterventionPlan)
    assert plan.current_label == "OUT"
    assert len(plan.interventions) >= 1


def test_intervention_already_in():
    claims = [_c("A")]
    attacks = []
    result = grounded_extension(claims, attacks)
    plan = find_minimal_intervention("A", claims, attacks, result)
    assert plan.current_label == "IN"
    assert plan.cost == 0


def test_stability_analysis():
    claims = [_c("A"), _c("B")]
    attacks = [("A", "B")]
    result = grounded_extension(claims, attacks)
    stability = analyze_stability("A", claims, attacks, result)
    assert isinstance(stability, StabilityAnalysis)
    assert stability.label == "IN"
    assert isinstance(stability.robustness_radius, int)
