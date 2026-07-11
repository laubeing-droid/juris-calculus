import pytest

from compiler_core.fact_trust_envelope import (
    FactTrustEnvelope,
    can_enter_formal_kernel,
    from_fact_coordinate,
)
from compiler_core.types import FactCreator, FactTrustStatus, LegalFact


@pytest.mark.parametrize("status", list(FactTrustStatus))
def test_only_complete_verified_fact_can_enter_formal_kernel(status):
    """全部事实状态共用一个fail-closed准入门禁。"""

    fact = LegalFact(
        id=f"fact::{status.value}",
        status=status,
        source_ids=("source::1",),
        human_reviewed=True,
        created_by=FactCreator.HUMAN,
    )

    assert fact.can_enter_formal_kernel() is (status == FactTrustStatus.VERIFIED_FACT)


def test_verified_fact_still_needs_source_and_review_material():
    fact = LegalFact(id="fact::verified", status=FactTrustStatus.VERIFIED_FACT)

    assert not fact.can_enter_formal_kernel()
    assert not can_enter_formal_kernel(fact)


def test_court_fixed_preserves_existing_court_gate():
    fact = from_fact_coordinate({
        "fact_key": "fact::court",
        "determination_state": "COURT_FIXED",
        "provenance": {"created_by": "court", "source_document_id": "judgment::1"},
    })

    assert isinstance(fact, LegalFact)
    assert fact.created_by == FactCreator.COURT
    assert fact.can_enter_formal_kernel()


@pytest.mark.parametrize("legacy_status", ["ADMITTED", "HUMAN_REVIEWED", "ENGINE_DERIVED"])
def test_legacy_review_states_never_upgrade_to_verified(legacy_status):
    fact = from_fact_coordinate({
        "fact_key": f"fact::{legacy_status}",
        "determination_state": legacy_status,
        "provenance": {"source_ref": "source::review"},
    })

    assert fact.status == FactTrustStatus.CHECKED_FACT
    assert not fact.can_enter_formal_kernel()


def test_unknown_legacy_state_degrades_to_candidate():
    fact = from_fact_coordinate({"fact_key": "fact::unknown-state", "determination_state": "MADE_UP"})

    assert fact.status == FactTrustStatus.CANDIDATE_FACT
    assert not fact.can_enter_formal_kernel()


def test_assumed_disputed_and_unknown_keep_boundary_metadata():
    assumed = from_fact_coordinate({"fact_key": "fact::assumed", "determination_state": "USER_ASSUMED"})
    disputed = from_fact_coordinate({
        "fact_key": "fact::disputed",
        "determination_state": "DISPUTED",
        "alternatives": [{"value": "A"}, {"value": "B"}],
    })
    unknown = from_fact_coordinate({"fact_key": "fact::unknown", "determination_state": "UNKNOWN"})

    assert assumed.assumption_tainted
    assert disputed.requires_review_packet
    assert [item["value"] for item in disputed.alternatives] == ["A", "B"]
    assert unknown.requires_review_packet
    assert unknown.value is None


def test_reasoning_tier_never_controls_formal_admission():
    results = {
        tier: LegalFact(
            id=f"fact::{tier}",
            status=FactTrustStatus.VERIFIED_FACT,
            source_ids=("source::1",),
            human_reviewed=True,
            reasoning_tier=tier,
        ).can_enter_formal_kernel()
        for tier in ("P0", "P1", "P2")
    }

    assert results == {"P0": True, "P1": True, "P2": True}


def test_migration_factory_returns_legal_fact_not_parallel_object():
    fact = FactTrustEnvelope(
        "fact::legacy",
        True,
        FactTrustStatus.VERIFIED_FACT,
        source_ids=("source::1",),
        human_reviewed=True,
    )

    assert type(fact) is LegalFact
    assert fact.fact_key == "fact::legacy"


def test_legal_fact_copies_mutable_boundary_inputs():
    provenance = {"source": "original"}
    alternatives = [{"value": "A"}]
    fact = LegalFact(id="fact::copy", provenance=provenance, alternatives=tuple(alternatives))

    provenance["source"] = "changed"
    alternatives[0]["value"] = "B"

    assert fact.provenance == {"source": "original"}
    assert fact.alternatives == ({"value": "A"},)
