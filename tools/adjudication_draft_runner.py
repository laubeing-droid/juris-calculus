#!/usr/bin/env python3
"""Adjudication draft runner: candidate-only legal analysis."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.adjudication_draft import (
    DraftAdjudication, DraftHolding, DraftIssue, DraftConclusionStatus, HoldingCategory, audit_adjudication_draft,
)


def mock_draft(case_id: str, jurisdiction: str, facts: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not facts:
        return {
            "case_id": case_id,
            "status": "BLOCKED",
            "issue": "NO_FACTS_PROVIDED",
        }
    draft = DraftAdjudication(
        case_id=case_id,
        jurisdiction=jurisdiction,
        facts=facts,
        issues=[
            DraftIssue(issue_id="IS-1", description="Was a valid contract formed?", relevant_rules=["contract_formation"], source_spans=["statute:42"], confidence=0.7),
            DraftIssue(issue_id="IS-2", description="Was there a breach?", relevant_rules=["breach_detection"], source_spans=["statute:43"], confidence=0.65),
        ],
        holdings=[
            DraftHolding(holding_id="H-1", category=HoldingCategory.CANNOT_DECIDE, claims=["breach_established"], rationale="insufficient evidence for damages", authority=["statute:42"], source_spans=["statute:42"], confidence=0.5),
        ],
        missing_evidence=["damages_quantum", "witness_statement"],
        missing_authority=[],
        uncertainty="draft model 鈥?not a legal conclusion",
        status=DraftConclusionStatus.DRAFT,
        model={"provider": "mock", "model_id": "draft/v0", "version": "0.1"},
    )
    audit = audit_adjudication_draft(draft)
    return {
        "case_id": case_id,
        "jurisdiction": jurisdiction,
        "issues": [{"issue_id": i.issue_id, "description": i.description, "relevant_rules": i.relevant_rules} for i in draft.issues],
        "holdings": [{"holding_id": h.holding_id, "category": h.category.value, "claims": h.claims} for h in draft.holdings],
        "missing_evidence": draft.missing_evidence,
        "status": audit["status"],
        "audit_findings": audit["findings"],
        "model": draft.model,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Adjudication draft model runner.")
    parser.add_argument("--case-id", default="CASE-001")
    parser.add_argument("--jurisdiction", default="zh_CN")
    parser.add_argument("--facts-json")
    args = parser.parse_args()
    facts = json.loads(args.facts_json) if args.facts_json else (json.loads(Path(args.facts_file).read_text(encoding='utf-8')) if getattr(args, 'facts_file', None) and Path(args.facts_file).exists() else None)
    report = mock_draft(args.case_id, args.jurisdiction, facts)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "PASS_WITH_FINDINGS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
