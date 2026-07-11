"""Enhanced evidence checklist with recommended actions and priority."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from compiler_core.canonical_serialization import content_id


@dataclass
class EvidenceGap:
    """A single evidence gap with recommended actions."""
    claim_id: str
    gap_type: str  # direct_evidence | chain_link | premises_unsatisfied | orphan_fact
    missing_items: list[str]
    status: str  # critical | high | medium | low
    recommended_action: str
    estimated_impact: str  # what would change if this evidence were provided


@dataclass
class EnhancedEvidenceChecklist:
    """Prioritized evidence checklist for a case."""
    case_id: str
    gaps: list[EvidenceGap] = field(default_factory=list)
    total_critical: int = 0
    total_high: int = 0
    summary: str = ""


def build_enhanced_checklist(
    claim_analyses: list[Any],
    facts: list[str],
    rules_applied: list[str],
) -> EnhancedEvidenceChecklist:
    """Build a prioritized evidence checklist from claim analyses.

    Priority logic:
      - critical: UNDECIDED claims with 1-2 missing premises
      - high: UNDECIDED claims with 3+ missing premises
      - medium: OUT claims where missing evidence could flip to IN
      - low: IN claims where evidence is sufficient
    """
    gaps: list[EvidenceGap] = []
    fact_set = set(facts)

    for analysis in claim_analyses:
        cid = getattr(analysis, "claim_id", "")
        status = getattr(analysis, "status", "UNKNOWN")
        missing = getattr(analysis, "missing_evidence", []) or []

        for item in missing:
            gap_type = item.get("type", "unknown")
            evidence = item.get("evidence", [])
            item_status = item.get("status", "unspecified")

            # Determine priority
            if status == "UNDECIDED" and len(evidence) <= 2:
                priority = "critical"
                action = f"Collect evidence for: {', '.join(evidence)}"
                impact = f"Would enable claim '{cid}' to be resolved"
            elif status == "UNDECIDED":
                priority = "high"
                action = f"Prioritize collecting: {', '.join(evidence[:3])}..."
                impact = f"Would begin resolving claim '{cid}'"
            elif status == "REFUTED" and len(evidence) <= 2:
                priority = "medium"
                action = f"If evidence '{', '.join(evidence)}' could be established, claim '{cid}' may flip to PROVED"
                impact = f"Could overturn REFUTED status for '{cid}'"
            else:
                priority = "low"
                action = f"Supplementary evidence: {', '.join(evidence)}"
                impact = f"Would strengthen claim '{cid}'"

            gaps.append(EvidenceGap(
                claim_id=cid,
                gap_type=gap_type,
                missing_items=list(evidence),
                status=priority,
                recommended_action=action,
                estimated_impact=impact,
            ))

    # Sort by priority: critical > high > medium > low
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    gaps.sort(key=lambda g: priority_order.get(g.status, 99))

    total_critical = sum(1 for g in gaps if g.status == "critical")
    total_high = sum(1 for g in gaps if g.status == "high")

    summary = (
        f"Total evidence gaps: {len(gaps)} "
        f"(critical: {total_critical}, high: {total_high}). "
        f"Facts available: {len(facts)}. "
        f"Rules applied: {len(rules_applied)}."
    )

    return EnhancedEvidenceChecklist(
        case_id=content_id("checklist", {"facts": sorted(facts)}),
        gaps=gaps,
        total_critical=total_critical,
        total_high=total_high,
        summary=summary,
    )
