"""Thin KG-style recall: search rules by concepts via concept_registry."""
from __future__ import annotations

from typing import Any, Dict, List


def recall_by_concept(rules: List[Dict[str, Any]], concepts: List[str], top_k: int = 10) -> List[Dict[str, Any]]:
    scored: List[tuple] = []
    for rule in rules:
        rule_concepts = set(rule.get("concepts", []) or [])
        namespace = rule.get("namespace", "") or ""
        hit_count = len(set(c.lower() for c in concepts) & set(c.lower() for c in rule_concepts))
        if hit_count:
            scored.append((hit_count, rule, namespace))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"rule_id": r["id"], "head_claim": r.get("head_claim", ""), "concepts": r.get("concepts", []),
             "namespace": ns, "hit_count": hit}
            for hit, r, ns in scored[:top_k]]
