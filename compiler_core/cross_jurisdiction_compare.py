"""Cross-jurisdiction formal comparison: source anchor diff + priority conflict detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from compiler_core.types import LegalRule


@dataclass
class JurisdictionPairDiff:
    pair: str
    shared_claims: List[str] = field(default_factory=list)
    only_left: List[str] = field(default_factory=list)
    only_right: List[str] = field(default_factory=list)
    source_anchor_mismatches: List[Dict[str, Any]] = field(default_factory=list)
    priority_reversals: List[Dict[str, Any]] = field(default_factory=list)
    state_divergence: str = ""


def compare_rule_sets(left_rules: List[LegalRule], right_rules: List[LegalRule], left_label: str = "A", right_label: str = "B") -> JurisdictionPairDiff:
    diff = JurisdictionPairDiff(pair=f"{left_label} vs {right_label}")
    left_ids = {rule.id for rule in left_rules}
    right_ids = {rule.id for rule in right_rules}
    diff.shared_claims = sorted(left_ids & right_ids)
    diff.only_left = sorted(left_ids - right_ids)
    diff.only_right = sorted(right_ids - left_ids)

    left_map = {rule.id: rule for rule in left_rules}
    right_map = {rule.id: rule for rule in right_rules}

    for rid in diff.shared_claims:
        lr = left_map.get(rid)
        rr = right_map.get(rid)
        if lr and rr:
            left_anchor = (lr.source_anchor or "").strip()
            right_anchor = (rr.source_anchor or "").strip()
            if left_anchor and right_anchor and left_anchor != right_anchor:
                diff.source_anchor_mismatches.append({"rule_id": rid, "left": left_anchor, "right": right_anchor})
            left_prios = set(lr.priority_over or [])
            right_prios = set(rr.priority_over or [])
            for pid in left_prios & right_prios:
                diff.priority_reversals.append({"rule_id": rid, "shared_priority_target": pid, "note": "same priority declared in both jurisdictions"})

    return diff


def diff_report(diff: JurisdictionPairDiff) -> Dict[str, Any]:
    return {
        "pair": diff.pair,
        "shared_claim_count": len(diff.shared_claims),
        "left_only_count": len(diff.only_left),
        "right_only_count": len(diff.only_right),
        "source_anchor_mismatch_count": len(diff.source_anchor_mismatches),
        "priority_reversal_count": len(diff.priority_reversals),
        "divergence_indicators": [],
        "status": "PASS" if not diff.source_anchor_mismatches else "DIVERGENCE_FOUND",
    }
