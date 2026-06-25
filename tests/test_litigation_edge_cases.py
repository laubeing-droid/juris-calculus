"""Edge case tests for litigation engineering pipeline.

Covers boundary conditions detected during API alignment testing:
empty AAF, single argument, all-UNDEC, duplicate updates, unreachable targets.
"""

import sys
sys.path.insert(0, "..")

import pytest
from compiler_core.argumentation import grounded_extension
from compiler_core.litigation_engineering import (
    generate_certificate,
    generate_all_certificates,
    find_minimal_intervention,
    analyze_stability,
)
from compiler_core.horn_completeness import (
    compute_minimal_support,
    compute_minimal_rebuttal,
    compute_missing_evidence,
    analyze_rule_impact,
)

_c = lambda x: {"id": x, "horns": [x], "label": "?"}


class TestEmptyAaf:
    """Edge cases: empty or minimal AAF input."""

    def test_single_claim_no_attacks_is_in(self):
        claims = [_c("a")]
        attacks = []
        result = grounded_extension(claims, attacks)
        cert = generate_certificate("a", claims, attacks, result)
        assert cert is not None
        assert cert.label == "IN"

    def test_self_attack_produces_undec(self):
        claims = [_c("a")]
        attacks = [("a", "a")]
        result = grounded_extension(claims, attacks)
        cert = generate_certificate("a", claims, attacks, result)
        assert cert is not None
        assert cert.label == "UNDEC"

    def test_even_cycle_produces_all_undec(self):
        claims = [_c("a"), _c("b")]
        attacks = [("a", "b"), ("b", "a")]
        result = grounded_extension(claims, attacks)
        certs = generate_all_certificates(claims, attacks, result)
        assert isinstance(certs, list)
        assert len(certs) == 2
        for c in certs:
            assert c.label == "UNDEC"


class TestCertificateEdgeCases:
    """Edge cases around certificate payload correctness."""

    def test_no_crash_on_self_attack_cert(self):
        claims = [_c("a")]
        attacks = [("a", "a")]
        result = grounded_extension(claims, attacks)
        cert = generate_certificate("a", claims, attacks, result)
        assert cert is not None

    def test_shared_defender_cert_structure(self):
        claims = [_c("a"), _c("b"), _c("c")]
        attacks = [("b", "a"), ("c", "a")]
        result = grounded_extension(claims, attacks)
        cert = generate_certificate("a", claims, attacks, result)
        assert cert is not None
        assert cert.label in ("IN", "OUT", "UNDEC")
        assert isinstance(cert.attackers, list)


class TestInterventionEdgeCases:
    """Edge cases for minimal intervention discovery."""

    def test_unreachable_target_returns_empty_plan(self):
        claims = [_c("a")]
        attacks = []
        result = grounded_extension(claims, attacks)
        plan = find_minimal_intervention("nonexistent", claims, attacks, result)
        assert plan is not None
        assert len(plan.interventions) == 0

    def test_target_already_at_desired_label(self):
        claims = [_c("a"), _c("b")]
        attacks = []
        result = grounded_extension(claims, attacks)
        plan = find_minimal_intervention("a", claims, attacks, result)
        assert plan is not None
        assert plan.cost >= 0

    def test_intervention_no_claims(self):
        result = grounded_extension([], [])
        plan = find_minimal_intervention("x", [], [], result)
        assert plan is not None
        assert len(plan.interventions) == 0


class TestStabilityEdgeCases:
    """Edge cases for stability/impact analysis."""

    def test_stability_single_claim_no_attacks(self):
        claims = [_c("a")]
        result = grounded_extension(claims, [])
        stability = analyze_stability("a", claims, [], result)
        assert stability is not None
        assert stability.label in ("IN", "OUT", "UNDEC")
        assert isinstance(stability.robustness_radius, int)

    def test_stability_in_cycle(self):
        claims = [_c("a"), _c("b")]
        attacks = [("a", "b"), ("b", "a")]
        result = grounded_extension(claims, attacks)
        stability = analyze_stability("a", claims, attacks, result)
        assert stability is not None
        assert stability.label == "UNDEC"


class TestHornEdgeCases:
    """Edge cases for Horn completeness operations."""

    def test_rule_supports_from_fact(self):
        rules = [{"head": "b", "body": ["a"]}]
        facts = {"a"}
        support = compute_minimal_support("b", facts, rules)
        assert support is not None
        assert isinstance(support, set)

    def test_rule_impact_empty_rules(self):
        impact = analyze_rule_impact([], {}, "t")
        assert impact is not None

    def test_rule_impact_nonexistent_id(self):
        rules = [{"head": "b", "body": ["a"]}]
        facts = {"a"}
        impact = analyze_rule_impact("b", rules, facts)
        assert impact is not None
        assert isinstance(impact, dict)


class TestKnownBoundaries:
    """Tests that document known edge case behavior (actual or expected).

    These verify that the system does not crash under unusual inputs.
    Some may trigger internal assertions; these are valuable bug detectors.
    """

    def test_generate_all_certs_empty_returns_empty_list(self):
        result = grounded_extension([], [])
        certs = generate_all_certificates([], [], result)
        assert isinstance(certs, list)
        assert len(certs) == 0