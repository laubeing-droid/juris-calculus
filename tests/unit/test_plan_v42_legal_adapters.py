"""Synthetic lexical and legal-routing cases; no substantive legal verdicts."""
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from compiler_core.applicable_law import select_applicable_law
from compiler_core.contracts import ContentRefV4, FactCandidateV4, digest_value
from compiler_core.fact_extraction import extract_fact_candidates
from compiler_core.deadlines import load_deadline_rules


def proposals(text):
    return extract_fact_candidates(
        text, document_ref=ContentRefV4("redacted-document", digest_value({"text": text})),
        evidence_ref=ContentRefV4("evidence", digest_value({"fixture": "synthetic"})),
        redaction_state="redacted",
    )


def test_FX01_explicit_values_bind_exact_spans_and_existing_contract():
    text = "合成甲称于2026年9月21日支付1.25万元，约定03个工作日处理。"
    output = proposals(text)
    assert [item["value"]["normalized"] for item in output] == [
        "2026-09-21", {"currency": "CNY", "amount": "12500.00"},
        {"count": 3, "unit": "business_days"},
    ]
    for item in output:
        candidate = FactCandidateV4.from_dict(item["candidate"])
        assert candidate.evidence_refs
        assert candidate.value_ref.digest == digest_value(item["value"])
        assert candidate.proposition_ref.digest == digest_value(item["proposition"])
        span = item["proposition"]
        assert text[span["spanStart"]:span["spanEnd"]] == item["value"]["raw"]
        assert item["value"]["status"] == "UNVERIFIED"
        assert item["reviewRequired"] is True
        assert span["legalRole"] is None


def test_FX02_invalid_and_relative_dates_are_not_invented():
    result = proposals("合成材料：2026-02-30，次日，2024-02-29。")
    assert [item["value"]["normalized"] for item in result] == [None, None, "2024-02-29"]
    assert result[0]["value"]["reason"] == "invalid_calendar_date"
    assert result[1]["value"]["reason"] == "relative_date_anchor_unverified"


def test_FX03_no_role_or_legal_conclusion_from_negated_text():
    result = proposals("合成乙否认曾收到100元。")
    assert result[0]["proposition"]["legalRole"] is None
    assert result[0]["value"]["status"] == "UNVERIFIED"
    assert proposals("合成材料没有可识别的数字。") == []


def test_FX04_reject_unredacted_input():
    reference = ContentRefV4("synthetic", digest_value({"fixture": "synthetic"}))
    with pytest.raises(ValueError, match="redacted_input_required"):
        extract_fact_candidates("合成100元", document_ref=reference,
                                evidence_ref=reference, redaction_state="raw")


def test_FX05_signed_decimal_amount_and_document_identity_preserved():
    output = proposals("合成数字：-1.25万元、负0.01元、+100元。")
    assert [item["value"]["normalized"]["amount"] for item in output] == ["-12500.00", "-0.01", "100"]
    assert proposals("10元")[0]["candidate"]["candidate_id"] != proposals("10元甲")[0]["candidate"]["candidate_id"]


def test_RC01_legal_preconditions_are_part_of_live_loaded_rules():
    root = Path(__file__).resolve().parents[2] / "configs"
    rule = load_deadline_rules(root)[("civil.third_party.revocation", "1")]
    assert {item["field"] for item in rule["decision"]["require"]} >= {
        "legalContext.absenceNotAttributable", "legalContext.effectiveInstrumentHarmsRights"}


@pytest.fixture
def legal_request():
    return {
        "sources": [
            {"versionId": "old", "sourceRef": "synthetic-source-old", "verified": True,
             "issuer": "synthetic-authority", "validFrom": "2020-01-01", "validTo": "2026-06-30"},
            {"versionId": "new", "sourceRef": "synthetic-source-new", "verified": True,
             "issuer": "synthetic-authority", "validFrom": "2026-06-30", "validTo": None},
        ],
        "basis": {"kind": "fact_time", "sourceRef": "synthetic-temporal-clause",
                  "ruleScope": "synthetic-claim-rule", "reviewRef": "synthetic-review",
                  "exceptionsReviewed": True},
        "factAt": "2026-06-29", "concept": "synthetic-retained-concept",
    }


@pytest.mark.parametrize("day,expected", [("2026-06-29", "old"), ("2026-06-30", "new")])
def test_AL01_reviewed_temporal_boundary_keeps_history(legal_request, day, expected):
    legal_request["factAt"] = day
    result = select_applicable_law(legal_request)
    assert result["status"] == "CANDIDATE"
    assert result["selectedVersionIds"] == [expected]
    assert result["consideredVersionIds"] == ["new", "old"]
    assert result["retrievalPolicy"] == "retain_history_and_opposing_views"
    assert result["legalConclusionVerified"] is False
    assert result["reviewRequired"] is True


@pytest.mark.parametrize("missing", ["sourceRef", "ruleScope", "reviewRef"])
def test_AL02_date_alone_cannot_supply_legal_basis(legal_request, missing):
    del legal_request["basis"][missing]
    assert select_applicable_law(legal_request)["selectedVersionIds"] == []
    assert select_applicable_law(legal_request)["status"] == "UNVERIFIED"


def test_AL03_source_gap_and_overlap_stay_unverified(legal_request):
    legal_request["sources"][0]["validTo"] = "2026-06-28"
    assert select_applicable_law(legal_request)["reasonCodes"] == ["version_gap_or_overlap"]
    legal_request["sources"][0]["validTo"] = "2026-07-01"
    legal_request["factAt"] = "2026-06-30"
    assert select_applicable_law(legal_request)["reasonCodes"] == ["version_gap_or_overlap"]


def test_AL04_unverified_source_not_promoted(legal_request):
    legal_request["sources"][0]["verified"] = False
    assert select_applicable_law(legal_request)["reasonCodes"] == ["verified_source_and_issuer_required"]


def test_AL05_specific_acceptance_clause_requires_instance_and_scope(legal_request):
    legal_request["basis"]["kind"] = "new_first_instance_acceptance"
    legal_request.update(acceptedAt="2026-06-30", newlyAccepted=True, instance="appeal")
    assert select_applicable_law(legal_request)["status"] == "UNVERIFIED"
    legal_request["instance"] = "first"
    assert select_applicable_law(legal_request)["selectedVersionIds"] == ["new"]
    assert legal_request["factAt"] == "2026-06-29"


@pytest.mark.parametrize("kind", ["criminal_leniency", "civil_favorable", "civil_gap", "continuing_fact"])
def test_AL06_comparison_cannot_be_replaced_by_date(legal_request, kind):
    legal_request["basis"]["kind"] = kind
    assert select_applicable_law(legal_request)["reasonCodes"] == ["substantive_comparison_review_required"]
    legal_request["comparison"] = {
        "selectedVersionId": "new", "oldOutcome": "synthetic-old-result",
        "newOutcome": "synthetic-new-result", "reason": "synthetic-reviewed-reason",
        "reviewRef": "synthetic-lawyer-review",
    }
    assert select_applicable_law(legal_request)["selectedVersionIds"] == ["new"]


def test_AL07_hierarchy_labels_do_not_resolve_competence_conflict(legal_request):
    legal_request.update(conflict=True, priority="new_special_higher")
    assert select_applicable_law(legal_request)["reasonCodes"] == ["competent_authority_resolution_required"]
    legal_request["conflictResolution"] = {"authority": "synthetic-competent-authority",
                                     "sourceRef": "synthetic-resolution",
                                     "reviewRef": "synthetic-review", "selectedVersionId": "old"}
    assert select_applicable_law(legal_request)["selectedVersionIds"] == ["old"]


def test_AL08_final_judgment_and_reasoning_only_do_not_change_existing_basis(legal_request):
    legal_request.update(finalBeforeTransition=True, finalJudgmentVersionId="old")
    assert select_applicable_law(legal_request)["reasonCodes"] == ["final_judgment_record_required"]
    legal_request["finalJudgmentRef"] = "synthetic-final-judgment"
    assert select_applicable_law(legal_request)["selectedVersionIds"] == ["old"]


def test_AL09_unknown_concepts_do_not_trigger_blanket_refusal(legal_request):
    other = deepcopy(legal_request)
    other["concept"] = "another-synthetic-concept"
    assert select_applicable_law(legal_request) == select_applicable_law(other)
