"""Defeasible priority resolver: priority_over + authority_rank -> total order."""
from __future__ import annotations

from typing import List

from compiler_core.types import LegalRule


AUTHORITY_RANK_ORDER: dict = {"constitution": 1, "statute": 2, "regulation": 3, "guideline": 4, "unknown": 99}


def resolve_priority(rules: List[LegalRule]) -> List[LegalRule]:
    scores: dict = {}
    explicit_edges: set = set()

    for rule in rules:
        rank_score = AUTHORITY_RANK_ORDER.get((rule.authority_rank or "unknown").lower(), 99)
        specificity = len(rule.premise_atoms or [])
        scores[rule.id] = (rank_score, specificity)
        for prio in rule.priority_over or []:
            explicit_edges.add((rule.id, prio))

    def _key(rule: LegalRule):
        rank, spec = scores.get(rule.id, (99, 0))
        return (rank, -spec)

    sorted_rules = sorted(rules, key=_key)

    for src, tgt in explicit_edges:
        try:
            src_idx = next(i for i, r in enumerate(sorted_rules) if r.id == src)
            tgt_idx = next(i for i, r in enumerate(sorted_rules) if r.id == tgt)
            if src_idx > tgt_idx:
                sorted_rules[src_idx], sorted_rules[tgt_idx] = sorted_rules[tgt_idx], sorted_rules[src_idx]
        except StopIteration:
            pass

    return sorted_rules
