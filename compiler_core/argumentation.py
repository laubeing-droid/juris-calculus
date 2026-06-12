"""v2.0 Dung AAF grounded extension for Layer 5."""
from typing import List, Dict, Set, Tuple

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
