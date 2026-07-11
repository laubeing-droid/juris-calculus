from compiler_core.review_packet import ConflictCertificate
from compiler_core.reasoning_boundary import classify_boundary_result
from compiler_core.fact_trust_envelope import FactTrustEnvelope, FactTrustStatus


def test_conflicting_rules_generate_conflict_certificate():
    certificate = ConflictCertificate(
        conflict_nodes=("claim.allow", "claim.forbid"),
        rules=("rule.allow", "rule.forbid"),
        facts=("fact.a",),
    ).to_dict()

    assert certificate["result_status"] == "conflict_certificate"
    assert certificate["rules"] == ["rule.allow", "rule.forbid"]


def test_conflict_certificate_does_not_auto_resolve_priority():
    result = classify_boundary_result(
        [FactTrustEnvelope("fact.a", True, FactTrustStatus.VERIFIED_FACT)],
        conflict_nodes=["rule.allow", "rule.forbid"],
    )

    assert result.payload["auto_resolved"] is False
    assert result.review_required

