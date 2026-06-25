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


# ---------------------------------------------------------------------------
# B6 Engineering capabilities: cycle/SCC witness, label reasons, proof trace
# ---------------------------------------------------------------------------

def scc_decomposition(
    claims: list[dict[str, Any]], attacks: list[tuple[str, str]]
) -> list[list[str]]:
    """Decompose attack graph into strongly connected components (Kosaraju).

    Returns list of SCCs, each a list of argument IDs. Topological order
    (source SCCs first, sink SCCs last).
    """
    cids = {c["id"] for c in claims}
    adj: dict[str, list[str]] = {cid: [] for cid in cids}
    radj: dict[str, list[str]] = {cid: [] for cid in cids}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            adj[src].append(tgt)
            radj[tgt].append(src)

    visited: set[str] = set()
    order: list[str] = []

    # Iterative DFS (first pass) — avoids recursion limit for large graphs
    def dfs1(start: str) -> None:
        stack: list[tuple[str, int]] = [(start, 0)]
        visited.add(start)
        while stack:
            v, idx = stack[-1]
            neighbors = adj.get(v, [])
            if idx < len(neighbors):
                w = neighbors[idx]
                stack[-1] = (v, idx + 1)
                if w not in visited:
                    visited.add(w)
                    stack.append((w, 0))
            else:
                stack.pop()
                order.append(v)

    for v in sorted(cids):
        if v not in visited:
            dfs1(v)

    visited.clear()
    sccs: list[list[str]] = []

    # Iterative DFS (second pass) — avoids recursion limit for large graphs
    def dfs2(start: str, comp: list[str]) -> None:
        stack: list[tuple[str, int]] = [(start, 0)]
        visited.add(start)
        comp.append(start)
        while stack:
            v, idx = stack[-1]
            neighbors = radj.get(v, [])
            if idx < len(neighbors):
                w = neighbors[idx]
                stack[-1] = (v, idx + 1)
                if w not in visited:
                    visited.add(w)
                    comp.append(w)
                    stack.append((w, 0))
            else:
                stack.pop()

    for v in reversed(order):
        if v not in visited:
            comp: list[str] = []
            dfs2(v, comp)
            sccs.append(sorted(comp))

    return sccs


def find_cycles(
    claims: list[dict[str, Any]], attacks: list[tuple[str, str]]
) -> list[list[str]]:
    """Find all SCCs that contain cycles (size > 1 or self-attack).
    Returns list of cycle witness SCCs.
    """
    sccs = scc_decomposition(claims, attacks)
    attack_set = {(s, t) for s, t in attacks}

    cycles = []
    for scc in sccs:
        if len(scc) > 1:
            cycles.append(scc)
        elif len(scc) == 1:
            # Check self-attack
            v = scc[0]
            if (v, v) in attack_set:
                cycles.append(scc)
    return cycles


def label_reasons(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    result: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Generate human-readable reasons for each argument's label.

    Returns dict mapping argument ID to:
      - label: "IN" | "OUT" | "UNDEC"
      - reason: short explanation
      - witnesses: list of relevant argument IDs
      - cycle_scc: SCC ID if undecided due to cycle
    """
    accepted = set(result["accepted"])
    rejected = set(result["rejected"])
    undecided = set(result["undecided"])
    cids = {c["id"] for c in claims}

    attackers_of: dict[str, set[str]] = {}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)

    sccs = scc_decomposition(claims, attacks)
    scc_map: dict[str, int] = {}
    for i, scc in enumerate(sccs):
        for v in scc:
            scc_map[v] = i

    reasons: dict[str, dict[str, Any]] = {}

    for cid in sorted(cids):
        if cid in accepted:
            atts = attackers_of.get(cid, set())
            if not atts:
                reasons[cid] = {"label": "IN", "reason": "no attackers", "witnesses": []}
            else:
                defenders = set()
                for a in atts:
                    a_atts = attackers_of.get(a, set())
                    defenders.update(a_atts & accepted)
                reasons[cid] = {
                    "label": "IN",
                    "reason": f"all attackers defeated by accepted arguments",
                    "witnesses": sorted(defenders),
                }
        elif cid in rejected:
            atts = attackers_of.get(cid, set())
            in_attackers = atts & accepted
            reasons[cid] = {
                "label": "OUT",
                "reason": f"attacked by IN argument(s)",
                "witnesses": sorted(in_attackers),
            }
        else:  # undecided
            scc_id = scc_map.get(cid)
            scc_nodes = sccs[scc_id] if scc_id is not None else [cid]
            if len(scc_nodes) > 1 or (
                len(scc_nodes) == 1 and (scc_nodes[0], scc_nodes[0]) in {(s, t) for s, t in attacks}
            ):
                reasons[cid] = {
                    "label": "UNDEC",
                    "reason": f"part of cycle/SCC that prevents grounded resolution",
                    "witnesses": scc_nodes,
                    "cycle_scc": scc_id,
                }
            else:
                # Depends on another undecided argument
                undecided_attackers = sorted(attackers_of.get(cid, set()) & undecided)
                reasons[cid] = {
                    "label": "UNDEC",
                    "reason": "depends on undecided argument(s)",
                    "witnesses": undecided_attackers,
                }

    return reasons


def proof_trace(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a complete proof trace for the grounded extension computation.

    Returns:
      - sccs: SCC decomposition
      - cycles: cycle witnesses
      - iteration_history: per-iteration accepted/defended sets
      - labels: per-argument label with reasons
      - convergent: whether convergence was achieved
    """
    if result is None:
        result = grounded_extension(claims, attacks)

    # Replay iterations to capture history
    cids = {c["id"] for c in claims}
    attackers_of: dict[str, set[str]] = {}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)

    iteration_history: list[dict[str, Any]] = []
    accepted: set[str] = set()
    iteration = 0
    max_iter = result["derived_bound"]

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

        iteration_history.append({
            "iteration": iteration,
            "accepted": sorted(accepted),
            "defended": sorted(defended),
        })

        if defended == accepted:
            break
        accepted = defended

    sccs = scc_decomposition(claims, attacks)
    cycles = find_cycles(claims, attacks)

    return {
        "sccs": sccs,
        "cycles": cycles,
        "iteration_history": iteration_history,
        "labels": label_reasons(claims, attacks, result),
        "convergent": result["convergent"],
        "accepted": result["accepted"],
        "rejected": result["rejected"],
        "undecided": result["undecided"],
    }
