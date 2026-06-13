"""Adjudication draft model: candidate-only legal analysis, never final conclusion."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DraftConclusionStatus(str, Enum):
    DRAFT = "DRAFT"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    NEEDS_AUTHORITY = "NEEDS_AUTHORITY"
    BLOCKED = "BLOCKED"


class HoldingCategory(str, Enum):
    CLAIM_ESTABLISHED = "claim_established"
    CLAIM_REJECTED = "claim_rejected"
    CLAIM_WITHDRAWN = "claim_withdrawn"
    DEFENSE_SUSTAINED = "defense_sustained"
    DEFENSE_OVERRULED = "defense_overruled"
    REMANDED = "remanded"
    CANNOT_DECIDE = "cannot_decide"


@dataclass
class DraftIssue:
    issue_id: str
    description: str
    relevant_rules: List[str] = field(default_factory=list)
    source_spans: List[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class DraftHolding:
    holding_id: str
    category: HoldingCategory = HoldingCategory.CANNOT_DECIDE
    claims: List[str] = field(default_factory=list)
    rationale: str = ""
    authority: List[str] = field(default_factory=list)
    source_spans: List[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class DraftAdjudication:
    case_id: str
    jurisdiction: str
    facts: Dict[str, Any] = field(default_factory=dict)
    issues: List[DraftIssue] = field(default_factory=list)
    holdings: List[DraftHolding] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    missing_authority: List[str] = field(default_factory=list)
    uncertainty: str = ""
    status: DraftConclusionStatus = DraftConclusionStatus.DRAFT
    model: Dict[str, str] = field(default_factory=dict)


def audit_adjudication_draft(draft: DraftAdjudication) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    if draft.status == DraftConclusionStatus.BLOCKED:
        return {
            "case_id": draft.case_id,
            "status": "BLOCKED",
            "finding_count": 1,
            "blocking_count": 1,
            "findings": [{"issue": "ADJUDICATION_BLOCKED", "detail": draft.uncertainty}],
        }
    for holding in draft.holdings:
        if not holding.source_spans:
            findings.append({"holding_id": holding.holding_id, "issue": "HOLDING_WITHOUT_SOURCE_SPAN"})
        if not holding.authority:
            findings.append({"holding_id": holding.holding_id, "issue": "HOLDING_WITHOUT_AUTHORITY"})
        if holding.category == HoldingCategory.CANNOT_DECIDE:
            findings.append({"holding_id": holding.holding_id, "issue": "HOLDING_CANNOT_DECIDE", "detail": holding.rationale})
        if holding.category in {HoldingCategory.CLAIM_ESTABLISHED, HoldingCategory.CLAIM_REJECTED, HoldingCategory.DEFENSE_SUSTAINED, HoldingCategory.DEFENSE_OVERRULED}:
            findings.append({"holding_id": holding.holding_id, "issue": "FINAL_CONCLUSION_IN_DRAFT", "detail": "draft model must not output final conclusions"})
    if not draft.issues:
        findings.append({"case_id": draft.case_id, "issue": "NO_ISSUES_IDENTIFIED"})
    blocking = [f for f in findings if "FINAL_CONCLUSION" in f.get("issue", "") or f.get("issue") == "ADJUDICATION_BLOCKED"]
    return {
        "case_id": draft.case_id,
        "issue_count": len(draft.issues),
        "holding_count": len(draft.holdings),
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "status": "PASS" if not blocking and findings else ("FAIL" if blocking else "PASS_WITH_FINDINGS"),
        "findings": findings,
    }
