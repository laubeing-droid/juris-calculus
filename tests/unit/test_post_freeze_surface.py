import json
from pathlib import Path

from compiler_core.post_freeze_surface import (
    SURFACE_TOOLS,
    attack_graph_explanation,
    batch_case_audit,
    case_deviation_detection,
    certified_litigation_report,
    damages_baseline,
    governance_report,
    impact_report,
    ingest_candidate,
    jurisdiction_route_guard,
    minimum_evidence_checklist,
    private_layer_contract,
    stress_fixtures,
)


def test_f1_report_rejects_malformed_certificate():
    result = certified_litigation_report({"malformed_certificate": True})

    assert result["status"] == "blocked"
    assert result["decision_status"] == "TAINTED"
    assert "MALFORMED_CERTIFICATE" in result["risk_labels"]
    assert result["payload"]["checker_verdict"]["accepted"] is False


def test_f2_minimum_evidence_is_suggestion_not_fact():
    result = minimum_evidence_checklist({"facts": ["contract_exists"], "target": "delivery_breach"})

    assert result["decision_status"] == "UNDECIDED"
    assert result["payload"]["suggestions_only"] is True
    assert result["payload"]["evidence_type_suggestions"]


def test_f3_attack_graph_preserves_cycle_as_undecided():
    result = attack_graph_explanation({"graph_kind": "cycle"})

    assert result["payload"]["grounded_result"]["undecided"]
    assert result["decision_status"] == "UNDECIDED"


def test_f5_batch_case_audit_isolates_cases():
    result = batch_case_audit({"count": 10})

    assert result["payload"]["case_count"] == 10
    assert {item["status"] for item in result["payload"]["results"]} <= {"ok", "blocked", "error"}


def test_f6_candidate_never_enters_kernel():
    result = ingest_candidate({"raw_text": "LLM extracted alleged fact", "source_span": ["s1"]})

    assert result["status"] == "blocked"
    assert result["decision_status"] == "TAINTED"
    assert result["payload"]["enters_kernel"] is False
    assert result["payload"]["verification_state"] == "CANDIDATE_ONLY"


def test_f7_governance_flags_missing_source_anchor():
    result = governance_report({"rules": [{"id": "R1", "head": "C", "body": []}]})

    assert "MISSING_PROVENANCE" in result["risk_labels"]
    assert result["payload"]["risk_queue"] == ["R1"]


def test_f8_impact_does_not_change_decision():
    result = impact_report({"rule_id": "rule::delivery_obligation"})

    assert result["payload"]["decision_changed"] is False
    assert "required_recheck_fixtures" in result["payload"]


def test_f9_route_guard_blocks_unmapped():
    result = jurisdiction_route_guard({"concept": "definitely_unmapped", "source": "CN", "target": "HK"})

    assert result["status"] == "blocked"
    assert result["decision_status"] == "UNDECIDED"


def test_f10_required_surface_tools_are_registered():
    required = {"evaluate", "route", "trace", "check", "batch", "render", "diff", "governance", "impact", "ingest_candidate"}

    assert required <= set(SURFACE_TOOLS)


def test_f11_damages_baseline_does_not_set_decision_status():
    result = damages_baseline({"principal": 100000})

    assert result["decision_status"] is None
    assert "ENGINEERING_BASELINE" in result["risk_labels"]


def test_f12_deviation_blocks_insufficient_samples():
    result = case_deviation_detection({"samples": []})

    assert result["status"] == "blocked"
    assert "LOW_EVIDENCE" in result["risk_labels"]


def test_f13_stress_fixtures_cover_required_types():
    result = stress_fixtures({})
    fixture_types = {item["type"] for item in result["payload"]["fixtures"]}

    assert {
        "cycle attack",
        "self-attack",
        "exception chain",
        "priority conflict",
        "missing evidence",
        "tainted fact",
        "malformed certificate",
        "jurisdiction collision",
    } <= fixture_types
    assert result["payload"]["differential_ready"] is True


def test_f14_private_layer_contract_keeps_kernel_semantics():
    result = private_layer_contract({})

    assert result["payload"]["kernel_semantics_changed"] is False
    assert "litigation strategy draft" in result["payload"]["private_layer_only"]


def test_surface_outputs_are_json_serializable():
    outputs = [
        certified_litigation_report({}),
        attack_graph_explanation({"graph_kind": "priority"}),
        stress_fixtures({}),
    ]

    json.dumps(outputs, ensure_ascii=False)
