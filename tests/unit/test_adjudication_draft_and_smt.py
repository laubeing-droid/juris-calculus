#!/usr/bin/env python3
from __future__ import annotations

from compiler_core.adjudication_draft import (
    DraftAdjudication, DraftHolding, DraftIssue, DraftConclusionStatus,
    HoldingCategory, audit_adjudication_draft,
)
from tools.adjudication_draft_runner import mock_draft
from tools.smt_evaluator_compare import compare, extract_constraints
from compiler_core.types import LegalRule


def test_audit_blocks_final_conclusions():
    draft = DraftAdjudication(
        case_id="C1", jurisdiction="test",
        issues=[DraftIssue(issue_id="I1", description="test", source_spans=["s1"])],
        holdings=[DraftHolding(holding_id="H1", category=HoldingCategory.CLAIM_ESTABLISHED, claims=["c1"], source_spans=["s1"], authority=["a1"])],
    )
    report = audit_adjudication_draft(draft)
    assert report["status"] == "FAIL"
    assert any("FINAL_CONCLUSION" in f["issue"] for f in report["findings"])


def test_audit_accepts_cannot_decide():
    draft = DraftAdjudication(
        case_id="C1", jurisdiction="test",
        issues=[DraftIssue(issue_id="I1", description="test", source_spans=["s1"])],
        holdings=[DraftHolding(holding_id="H1", category=HoldingCategory.CANNOT_DECIDE, source_spans=["s1"], authority=["a1"])],
    )
    report = audit_adjudication_draft(draft)
    assert report["status"] == "PASS"


def test_audit_blocks_no_issues():
    draft = DraftAdjudication(case_id="C1", jurisdiction="test")
    report = audit_adjudication_draft(draft)
    assert any("NO_ISSUES" in f["issue"] for f in report["findings"])


def test_mock_draft_with_facts():
    report = mock_draft("C1", "test", {"contract_exists": 1.0})
    assert report["case_id"] == "C1"
    assert len(report["issues"]) == 2
    assert report["status"] == "PASS"


def test_mock_draft_no_facts():
    report = mock_draft("C1", "test")
    assert report["status"] == "BLOCKED"


def test_extract_constraints_from_rules():
    rules = [
        LegalRule(id="R1", premise_atoms=["p1"], head_claim="c1", valid_from="2025-01-01", valid_to="2024-01-01", authority_rank="statute", priority_over=["R2"]),
        LegalRule(id="R2", premise_atoms=["p2"], head_claim="c2"),
    ]
    constraints = extract_constraints(rules)
    assert any("temporal_R1" in c["name"] for c in constraints)
    assert any("priority_R1" in c["name"] for c in constraints)


def test_smt_compare_on_sample_fixture():
    report = compare("tests/fixtures/rule_migration_sample.yaml", jurisdiction="test")
    assert report["smt_available"] in {True, False}
    assert "horn_claim_count" in report
    assert report["status"] in {"PASS", "DIVERGENCE_DETECTED"}
