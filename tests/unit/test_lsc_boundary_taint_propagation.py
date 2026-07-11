from compiler_core.contracts import CertificateKind
from compiler_core.fact_trust_envelope import FactTrustEnvelope, FactTrustStatus
from compiler_core.lsc_boundary_status import classify_boundary_result
from compiler_core.taint import TaintLabel, TaintSet, propagate_taint, taint_from_statuses


def test_user_assumed_required_fact_pollutes_result():
    result = classify_boundary_result([
        FactTrustEnvelope("fact.required", True, FactTrustStatus.USER_ASSUMED)
    ])

    assert result.result_status.value == "hypothetical_result"
    assert "assumption" in result.taint


def test_user_assumed_optional_fact_pollutes_when_used():
    result = classify_boundary_result([
        FactTrustEnvelope("fact.optional.used", True, FactTrustStatus.USER_ASSUMED)
    ])

    assert result.result_status.value == "hypothetical_result"


def test_unused_optional_fact_does_not_pollute():
    result = classify_boundary_result([
        FactTrustEnvelope(
            "fact.required",
            True,
            FactTrustStatus.VERIFIED_FACT,
            source_ids=("source::1",),
            human_reviewed=True,
        )
    ], checker_accepted=True, certificate_kind=CertificateKind.FORMAL, formal_kernel_used=True)

    assert result.result_status.value == "accepted_formal_result"
    assert result.taint == ()


def test_derived_fact_inherits_upstream_assumption_taint():
    result = classify_boundary_result([
        FactTrustEnvelope(
            "fact.derived",
            True,
            FactTrustStatus.CHECKED_FACT,
            provenance={"derived_from": {"provenance_taint": "HYPOTHETICAL_RESULT"}},
        )
    ])

    assert result.result_status.value == "hypothetical_result"
    assert "assumption" in result.taint


def test_taint_union_is_disclosure_only_container():
    upstream = TaintSet(frozenset({TaintLabel.ASSUMPTION}))
    downstream = taint_from_statuses(["DISPUTED"])

    assert propagate_taint(upstream, downstream).to_list() == ["assumption", "disputed"]

