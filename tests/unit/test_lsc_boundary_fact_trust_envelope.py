from compiler_core.fact_trust_envelope import (
    FactTrustStatus,
    can_enter_formal_kernel,
    from_lsc_fact_coordinate,
)


def test_admitted_maps_to_checked_not_verified_kernel_entry():
    fact = from_lsc_fact_coordinate({
        "fact_key": "f.admitted",
        "determination_state": "ADMITTED",
        "value": True,
        "provenance": {"source_ref": "src://admission"},
    })

    assert fact.status == FactTrustStatus.CHECKED_FACT
    assert not can_enter_formal_kernel(fact)


def test_verified_still_needs_jc_gate_material():
    fact = from_lsc_fact_coordinate({
        "fact_key": "f.verified",
        "determination_state": "VERIFIED",
        "value": True,
        "provenance": {},
    })

    assert fact.status == FactTrustStatus.VERIFIED_FACT
    assert not can_enter_formal_kernel(fact)


def test_court_fixed_with_court_provenance_can_enter_boundary_gate():
    fact = from_lsc_fact_coordinate({
        "fact_key": "f.court",
        "determination_state": "COURT_FIXED",
        "value": True,
        "provenance": {"created_by": "court", "source_document_id": "judgment://1"},
    })

    assert fact.status == FactTrustStatus.VERIFIED_FACT
    assert fact.created_by.value == "court"
    assert can_enter_formal_kernel(fact)


def test_court_fixed_without_court_provenance_does_not_silently_upgrade_creator():
    fact = from_lsc_fact_coordinate({
        "fact_key": "f.court.raw",
        "determination_state": "VERIFIED",
        "value": True,
        "provenance": {"source_ref": "src://not-court"},
    })

    assert fact.created_by.value != "court"
    assert not can_enter_formal_kernel(fact)


def test_user_assumed_enters_assumption_taint():
    fact = from_lsc_fact_coordinate({
        "fact_key": "f.assumed",
        "determination_state": "USER_ASSUMED",
        "value": "assumed",
        "provenance": {"source_agent": "human"},
    })

    assert fact.status == FactTrustStatus.USER_ASSUMED
    assert fact.assumption_tainted
    assert not fact.reasoning_eligible_by_default


def test_disputed_preserves_alternatives_for_review_packet():
    fact = from_lsc_fact_coordinate({
        "fact_key": "f.disputed",
        "determination_state": "DISPUTED",
        "alternatives": [{"value": "A"}, {"value": "B"}],
        "provenance": {"source_ref": "src://dispute"},
    })

    assert fact.status == FactTrustStatus.DISPUTED
    assert fact.requires_review_packet
    assert [item["value"] for item in fact.alternatives] == ["A", "B"]


def test_unknown_becomes_missing_review_material_without_exception():
    fact = from_lsc_fact_coordinate({
        "fact_key": "f.unknown",
        "determination_state": "UNKNOWN",
        "provenance": {"source_ref": "src://missing"},
    })

    assert fact.status == FactTrustStatus.UNKNOWN
    assert fact.value is None
    assert fact.requires_review_packet

