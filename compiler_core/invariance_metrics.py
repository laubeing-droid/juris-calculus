"""Inv(f) / Align(f) metrics from LexGuard: symbolic-only, no LLM dependency."""
from __future__ import annotations

from typing import Any, Dict, List


def compute_metrics(base_claims: List[str], perturbed_claims: List[str], expected_relation: str = "same_claims_as_base") -> Dict[str, Any]:
    base_set = set(base_claims)
    pert_set = set(perturbed_claims)
    unchanged = base_set == pert_set

    if expected_relation == "same_claims_as_base":
        pass_score = 1.0 if unchanged else 0.0
        return {
            "invariance": pass_score,
            "change_alignment": None,
            "added_claims": sorted(pert_set - base_set),
            "removed_claims": sorted(base_set - pert_set),
            "expected_relation": expected_relation,
            "status": "PASS" if pass_score > 0.5 else "FAIL",
        }
    elif expected_relation == "must_remove":
        removed = base_set - pert_set
        added_bad = pert_set - base_set
        pass_score = 1.0 if removed and not added_bad else 0.0
        return {
            "invariance": None,
            "change_alignment": pass_score,
            "added_claims": sorted(added_bad),
            "removed_claims": sorted(removed),
            "expected_relation": expected_relation,
            "status": "PASS" if pass_score > 0.5 else "FAIL",
        }
    elif expected_relation == "must_include":
        included = pert_set - base_set
        pass_score = 1.0 if included else 0.0
        return {
            "invariance": None,
            "change_alignment": pass_score,
            "added_claims": sorted(included),
            "removed_claims": sorted(base_set - pert_set),
            "expected_relation": expected_relation,
            "status": "PASS" if pass_score > 0.5 else "FAIL",
        }
    return {
        "invariance": 1.0 if unchanged else 0.0,
        "change_alignment": 0.0 if unchanged else 1.0,
        "added_claims": sorted(pert_set - base_set),
        "removed_claims": sorted(base_set - pert_set),
        "expected_relation": expected_relation,
        "status": "PASS" if unchanged else "FAIL",
    }


def aggregate_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    invariance_scores = [r["invariance"] for r in results if r.get("invariance") is not None]
    align_scores = [r["change_alignment"] for r in results if r.get("change_alignment") is not None]
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    return {
        "case_count": total,
        "passed": passed,
        "overall_pass_rate": passed / total if total else 0.0,
        "mean_invariance": sum(invariance_scores) / len(invariance_scores) if invariance_scores else None,
        "mean_change_alignment": sum(align_scores) / len(align_scores) if align_scores else None,
        "invariance_cases": len(invariance_scores),
        "change_alignment_cases": len(align_scores),
        "status": "PASS" if passed == total else "FAIL",
    }
