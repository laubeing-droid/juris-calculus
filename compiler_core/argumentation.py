"""v3.0 Dung AAF grounded extension — formal correctness (G9A).

Per Dung (1995):
  - Characteristic function F(S) = {a | all attackers of a are attacked by S}
  - F is monotone on the complete lattice of argument sets
  - For finite argument sets, iteration from empty set reaches the
    least fixed point (grounded extension) in at most |AR| steps
  - Grounded extension is unique

B3 fixes:
  - Iteration upper bound derived from argument count (not hardcoded 100)
  - Returns convergent/truncated status explicitly
  - Correctly handles self-attack, cycles, and arbitrary attack graphs
  - Deterministic output ordering
"""

from typing import Any, Dict, List, Optional, Set, Tuple


def grounded_extension(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    max_iter: Optional[int] = None,
) -> dict[str, Any]:
    """Compute the grounded extension of a Dung abstract argumentation framework.

    Args:
        claims: List of dicts with at least 'id' key per argument.
        attacks: List of (source_id, target_id) pairs.
        max_iter: Optional explicit bound. If None, derived from |claims|.
                  If provided and insufficient, returns TRUNCATED.

    Returns:
        dict with:
          accepted: list of IN arguments (grounded extension members)
          rejected: list of OUT arguments (attacked by accepted)
          undecided: list of UNDEC arguments (cycles and their consequences)
          iterations: number of characteristic function evaluations
          derived_bound: upper bound derived from argument count
          convergent: True if least fixed point reached within bound
          truncated: True if max_iter was insufficient to reach fixed point
    """
    cids: Set[str] = {c["id"] for c in claims}
    n = len(cids)
    derived_bound = n + 1  # at most |AR| steps to reach fixed point, +1 for convergence check  # at least 1 iteration for empty check

    if max_iter is None:
        max_iter = derived_bound
    elif max_iter < 1:
        max_iter = 1

    # Build attack relation: attackers_of[tgt] = {src | src attacks tgt}
    attackers_of: Dict[str, Set[str]] = {}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)

    # Fixed-point iteration: F(S) = {a | all attackers of a are attacked by S}
    # Start from bottom (empty set), iterate F until stable or max_iter exhausted
    accepted: Set[str] = set()
    convergent = False
    iteration = 0

    while iteration < max_iter:
        iteration += 1
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
            convergent = True
            break

        accepted = defended

    # Grounded labelling
    # IN  = accepted (grounded extension members)
    # OUT = attacked by IN (and not IN)
    # UNDECIDED = everything else (cycles where grounded semantics gives empty)
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
        "iterations": iteration,
        "derived_bound": derived_bound,
        "convergent": convergent,
        "truncated": not convergent and iteration >= max_iter,
    }

