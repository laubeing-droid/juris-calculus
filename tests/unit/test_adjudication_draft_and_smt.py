#!/usr/bin/env python3
from __future__ import annotations

from compiler_core.adjudication_draft import (
    DraftAdjudication, DraftHolding, DraftIssue, HoldingCategory,
    audit_adjudication_draft,
)


def test_audit_blocks_final_conclusions():
    draft = DraftAdjudication(
        case_id="C1", jurisdiction="test",
        issues=[DraftIssue(issue_id="I1", description="test", source_spans=["s1"])],
        holdings=[DraftHolding(
            holding_id="H1", category=HoldingCategory.CLAIM_ESTABLISHED,
            claims=["c1"], source_spans=["s1"], authority=["a1"],
        )],
    )
    report = audit_adjudication_draft(draft)
    assert report["status"] == "FAIL"
    assert any("FINAL_CONCLUSION" in finding["issue"] for finding in report["findings"])


def test_audit_accepts_cannot_decide():
    draft = DraftAdjudication(
        case_id="C1", jurisdiction="test",
        issues=[DraftIssue(issue_id="I1", description="test", source_spans=["s1"])],
        holdings=[DraftHolding(
            holding_id="H1", category=HoldingCategory.CANNOT_DECIDE,
            source_spans=["s1"], authority=["a1"],
        )],
    )
    report = audit_adjudication_draft(draft)
    assert report["status"] == "PASS"


def test_audit_blocks_no_issues():
    draft = DraftAdjudication(case_id="C1", jurisdiction="test")
    report = audit_adjudication_draft(draft)
    assert any("NO_ISSUES" in finding["issue"] for finding in report["findings"])
