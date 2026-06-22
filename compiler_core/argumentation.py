"""v2.0 Dung AAF grounded extension for Layer 5."""
from typing import Dict, Iterable, List, Set, Tuple, Optional, Any


def grounded_extension(claims, attacks, max_iter=100):
    """Compute grounded extension and return accepted, rejected, undecided.

    Per Dung (1995):
    - IN  (accepted):  arguments in the grounded extension
    - OUT (rejected):  arguments attacked by an IN argument
    - UNDECIDED:       everything else (cycles where grounded semantics
                        gives empty; these are NOT rejected)
    """
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

    # Grounded labelling: OUT = attacked by IN
    rejected = set()
    for cid in cids:
        if cid in accepted:
            continue
        atts = attackers_of.get(cid, set())
        if atts & accepted:
            rejected.add(cid)

    undecided = cids - accepted - rejected
    return {
        "accepted": sorted(accepted),
        "rejected": sorted(rejected),
        "undecided": sorted(undecided),
        "iterations": _ + 1,
    }


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


def build_attack_graph_from_evaluator(
    claims: Dict[str, Any],
    rules: list,
    constraint_validator: Any,
    state: Any,
    blocked_claims: Set[str],
) -> List[Tuple[str, str]]:
    """Build complete attack graph from evaluator output.

    Attack sources:
    1. Explicit attacks/priority_over from rules (existing)
    2. Exception chain reverse attacks (new)
    3. Rebuttal-triggered confidence=0 claims attacked by all (new)
    4. PROHIBITION blocked_claims (new)
    """
    edges: Set[Tuple[str, str]] = set()

    # 1. Explicit attacks from rules
    explicit = build_attack_edges_from_rules(rules)
    edges.update(explicit)

    # 2. Exception chain reverse attacks
    rule_by_claim = {}
    for rule in rules:
        hc = getattr(rule, "head_claim", "")
        if hc:
            rule_by_claim[hc] = rule

    for claim_id, claim in claims.items():
        rule = rule_by_claim.get(claim_id)
        if rule is None:
            continue
        for exc_id in getattr(rule, "exception_chain", []) or []:
            exc_rule = None
            for r in rules:
                if getattr(r, "id", "") == exc_id:
                    exc_rule = r
                    break
            if exc_rule and exc_rule.head_claim in claims:
                edges.add((exc_rule.head_claim, claim_id))

    # 3. Rebutted claims (confidence=0) — marked for exclusion, not attacked
    #    Handled by caller filtering out confidence=0 claims before grounded_extension
    #    No edges added here to avoid O(n²) explosion

    # 4. PROHIBITION blocked claims
    for blocked_id in blocked_claims:
        if blocked_id in claims:
            for other_id in claims:
                if other_id != blocked_id:
                    edges.add((other_id, blocked_id))

    return sorted(edges)
