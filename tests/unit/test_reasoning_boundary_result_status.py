import pytest

from compiler_core.contracts import CertificateKind
from compiler_core.fact_trust_envelope import FactTrustEnvelope, FactTrustStatus
from compiler_core.reasoning_boundary import BoundaryResultStatus, classify_boundary_result


def _fact(key, status):
    return FactTrustEnvelope(
        fact_key=key,
        value=True,
        status=status,
        source_ids=("snapshot://1",),
        human_reviewed=True,
    )


def test_clean_verified_facts_classify_as_accepted_formal_result():
    result = classify_boundary_result(
        [_fact("f.clean", FactTrustStatus.VERIFIED_FACT)],
        used_rule_ids=["r.clean"],
        source_snapshot_ids=["snapshot://1"],
        checker_accepted=True,
        certificate_kind=CertificateKind.FORMAL,
        formal_kernel_used=True,
    )

    assert result.result_status == BoundaryResultStatus.ACCEPTED_FORMAL_RESULT
    assert result.formal_kernel_used
    assert not result.review_required


def test_user_assumed_required_fact_forces_hypothetical_result():
    result = classify_boundary_result([_fact("f.assumed", FactTrustStatus.USER_ASSUMED)])

    assert result.result_status == BoundaryResultStatus.HYPOTHETICAL_RESULT
    assert "assumption" in result.taint


def test_disputed_required_fact_forces_review_only_result():
    result = classify_boundary_result([_fact("f.disputed", FactTrustStatus.DISPUTED)])

    assert result.result_status == BoundaryResultStatus.REVIEW_ONLY_RESULT
    assert result.review_required


def test_unknown_required_fact_forces_missing_required_fact():
    result = classify_boundary_result([_fact("f.unknown", FactTrustStatus.UNKNOWN)])

    assert result.result_status == BoundaryResultStatus.MISSING_REQUIRED_FACT
    assert result.payload["missing_fact_keys"] == ["f.unknown"]


def test_conflict_generates_conflict_certificate_without_priority_resolution():
    result = classify_boundary_result(
        [_fact("f.clean", FactTrustStatus.VERIFIED_FACT)],
        conflict_nodes=["rule.A", "rule.B"],
    )

    assert result.result_status == BoundaryResultStatus.CONFLICT_CERTIFICATE
    assert result.payload["auto_resolved"] is False


def test_engine_error_does_not_emit_final_success():
    result = classify_boundary_result([], engine_error="boom")

    assert result.result_status == BoundaryResultStatus.ENGINE_ERROR
    assert not result.formal_kernel_used
    assert result.review_required


@pytest.mark.parametrize(
    "status",
    [
        FactTrustStatus.CANDIDATE_FACT,
        FactTrustStatus.NORMALIZED_FACT,
        FactTrustStatus.SOURCE_BOUND_FACT,
        FactTrustStatus.CHECKED_FACT,
        FactTrustStatus.REJECTED_FACT,
        FactTrustStatus.STALE_FACT,
    ],
)
def test_nonverified_facts_never_fall_through_to_formal_success(status):
    result = classify_boundary_result([_fact(f"fact::{status.value}", status)])

    assert result.result_status == BoundaryResultStatus.REVIEW_ONLY_RESULT
    assert not result.formal_kernel_used
    assert result.review_required

