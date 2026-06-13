"""De Jure 19-dimension rule quality scoring: extends rule_quality_auditor with per-dimension 0-1 scores."""
from __future__ import annotations

from typing import Any, Dict, List


DE_JURE_CRITERIA = {
    "S1_Metadata": [
        "completeness", "fidelity_to_source", "non_hallucination",
        "title_quality", "citation_date_precision", "optional_field_population",
    ],
    "S2_Definitions": [
        "definition_completeness", "source_fidelity", "non_hallucination_def",
        "precision_formatting", "term_quality",
    ],
    "S3_RuleSemantics": [
        "accuracy", "fidelity_to_source_rule", "non_hallucination_rule",
        "structural_completeness", "exception_completeness",
        "condition_completeness", "actionability", "penalty_correctness",
    ],
}


def score_rule_de_jure(rule: Dict[str, Any], known_rule_ids: set, known_claim_labels: set) -> Dict[str, Any]:
    scores: Dict[str, float] = {}
    evidence: Dict[str, str] = {}

    # S1: Metadata (fields present => deterministic score)
    scores["completeness"] = 1.0 if all(k in rule for k in ("id", "head_claim", "premise_atoms")) else 0.0
    scores["fidelity_to_source"] = 1.0 if rule.get("source_anchor", "").strip() else 0.0
    scores["non_hallucination"] = 0.5 if rule.get("head_claim", "") else 0.0
    scores["title_quality"] = 0.5
    scores["citation_date_precision"] = 1.0 if rule.get("valid_from", "") else 0.5
    scores["optional_field_population"] = 1.0 if rule.get("jurisdiction", "") or rule.get("authority_rank", "") else 0.5

    # S2: Definitions (cross-reference completeness)
    scores["definition_completeness"] = 0.5
    scores["source_fidelity"] = scores["fidelity_to_source"]
    scores["non_hallucination_def"] = 1.0 if rule.get("id", "") else 0.0
    scores["precision_formatting"] = 0.5
    scores["term_quality"] = 0.5

    # S3: Rule Semantics
    scores["accuracy"] = 1.0 if rule.get("head_claim", "") and rule.get("premise_atoms") else 0.0
    scores["fidelity_to_source_rule"] = scores["fidelity_to_source"]
    scores["non_hallucination_rule"] = 1.0 if rule.get("id", "") and rule.get("head_claim", "") else 0.0
    scores["structural_completeness"] = 1.0 if rule.get("premise_atoms") and rule.get("head_claim") else 0.0
    exceptions = rule.get("exception_chain", []) or []
    scores["exception_completeness"] = 1.0 if all(e in known_rule_ids for e in exceptions) else 0.5
    scores["condition_completeness"] = 1.0 if len(rule.get("premise_atoms", []) or []) >= 1 else 0.0
    scores["actionability"] = 1.0 if rule.get("head_claim", "") and rule.get("head_type", "") else 0.5
    scores["penalty_correctness"] = 0.5

    avg = {stage: sum(scores.get(c, 0.0) for c in criteria) / len(criteria) if criteria else 0.0
           for stage, criteria in DE_JURE_CRITERIA.items()}
    overall = sum(scores.values()) / len(scores) if scores else 0.0

    return {
        "rule_id": rule.get("id", ""),
        "scores": scores,
        "stage_averages": avg,
        "overall_score": overall,
        "needs_repair": overall < 0.9,
        "status": "PASS" if overall >= 0.9 else "NEEDS_REPAIR",
    }


def audit_rules_de_jure(rules: List[Dict[str, Any]], strict_source: bool = False) -> Dict[str, Any]:
    known_ids = {str(r.get("id", "")) for r in rules if isinstance(r, dict)}
    known_claims = {str(r.get("head_claim", "")) for r in rules if isinstance(r, dict)}
    results = []
    for rule in rules:
        if isinstance(rule, dict):
            results.append(score_rule_de_jure(rule, known_ids, known_claims))
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    return {
        "rule_count": total,
        "passed_count": passed,
        "pass_rate": passed / total if total else 0.0,
        "stage_averages": {
            stage: sum(r["stage_averages"].get(stage, 0.0) for r in results) / max(total, 1)
            for stage in DE_JURE_CRITERIA
        },
        "overall_average": sum(r["overall_score"] for r in results) / max(total, 1),
        "status": "PASS" if passed == total else "REPAIRABLE",
        "results": results,
    }
