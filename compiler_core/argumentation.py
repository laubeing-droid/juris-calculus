"""v2.0 Dung AAF grounded extension for Layer 5."""
from typing import Dict, Iterable, List, Set, Tuple

def grounded_extension(claims, attacks, max_iter=100):
    cids = {c["id"] for c in claims}
    attackers_of: Dict[str, Set[str]] = {}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)

    accepted: Set[str] = set()
    for _ in range(max_iter):
        defended = set()
        for cid in cids:
            atts = attackers_of.get(cid, set())
            if not atts:
                defended.add(cid)
            else:
                all_defeated = True
                for a in atts:
                    a_atts = attackers_of.get(a, set())
                    if not (a_atts & accepted):
                        all_defeated = False
                        break
                if all_defeated:
                    defended.add(cid)
        if defended == accepted:
            break
        accepted = defended

    rejected = cids - accepted
    return {"accepted": sorted(accepted), "rejected": sorted(rejected), "iterations": _ + 1}


def build_attack_edges_from_rules(rules: Iterable) -> List[Tuple[str, str]]:
    """Build attack edges from explicit rule metadata."""
    edges: Set[Tuple[str, str]] = set()
    rules = list(rules)
    claim_by_rule_id = {
        getattr(rule, "id", ""): getattr(rule, "head_claim", "")
        for rule in rules
        if getattr(rule, "head_claim", "")
    }
    claim_ids = set(claim_by_rule_id.values())

    for rule in rules:
        source_claim = getattr(rule, "head_claim", "")
        if not source_claim:
            continue
        for target in getattr(rule, "attacks", []) or []:
            target_claim = claim_by_rule_id.get(target, target)
            if target_claim in claim_ids and target_claim != source_claim:
                edges.add((source_claim, target_claim))
        for target in getattr(rule, "priority_over", []) or []:
            target_claim = claim_by_rule_id.get(target, target)
            if target_claim in claim_ids and target_claim != source_claim:
                edges.add((source_claim, target_claim))

    return sorted(edges)
