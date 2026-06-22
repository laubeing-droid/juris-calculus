"""Universal SMT proof: for all DAGs of size N, grounded extension is complete.

Encodes the negation of the universal claim as Z3 constraints:
  "There exists a DAG attack graph of size N where grounded_extension
   produces at least one UNDECIDED node."

If Z3 returns UNSAT, the universal claim is PROVED for all graphs of size N.
If Z3 returns SAT, it produces a counterexample DAG.

This is genuine theorem proving via bounded model checking.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

try:
    import z3
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False


@dataclass
class UniversalProofResult:
    n_nodes: int
    proved: bool
    status: str = ""
    counterexample: dict[str, Any] | None = None
    time_seconds: float = 0.0


def prove_dag_completeness(n_nodes: int, timeout_ms: int = 30000) -> UniversalProofResult:
    """Prove that for all DAGs of size n_nodes, grounded extension is complete (no undecided).

    Returns UniversalProofResult with proved=True if UNSAT (theorem holds),
    or proved=False with a counterexample if SAT (theorem is false for this size).
    """
    if not HAS_Z3:
        return UniversalProofResult(n_nodes, False, "Z3_UNAVAILABLE")

    start = time.time()
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)

    # --- Variables ---
    # edge[i][j]: True if node i attacks node j
    edge = [[z3.Bool(f"edge_{i}_{j}") for j in range(n_nodes)] for i in range(n_nodes)]
    # accepted[i]: True if node i is in the grounded extension
    accepted = [z3.Bool(f"acc_{i}") for i in range(n_nodes)]

    # --- DAG constraint: no directed cycles ---
    # For any sequence of k distinct nodes i1->i2->...->ik->i1, at least one edge is absent.
    # We encode "no cycles" using an explicit enumeration for small N.
    # For N<=5, we can enumerate all possible cycles.

    # Method: encode reachability. If there's a path from i to j (i != j),
    # then there can't be an edge from j to i.
    # We compute reachability iteratively.

    # reachable[k][i][j]: is j reachable from i in <= k steps
    reachable = []
    # Step 0: reachable[0][i][j] = edge[i][j]
    step0 = [[edge[i][j] for j in range(n_nodes)] for i in range(n_nodes)]
    reachable.append(step0)

    # Step k: reachable[k][i][j] = reachable[k-1][i][j] OR
    #   exists m: reachable[k-1][i][m] AND edge[m][j]
    for step in range(1, n_nodes):
        prev = reachable[step - 1]
        curr = [[z3.BoolVal(False) for _ in range(n_nodes)] for _ in range(n_nodes)]
        for i in range(n_nodes):
            for j in range(n_nodes):
                # Via intermediate node m
                via = [z3.And(prev[i][m], edge[m][j]) for m in range(n_nodes)]
                curr[i][j] = z3.Or(prev[i][j], z3.Or(via) if via else z3.BoolVal(False))
        reachable.append(curr)

    # DAG: for any i != j, if j is reachable from i, then edge[j][i] must be False
    for i in range(n_nodes):
        for j in range(n_nodes):
            if i != j:
                solver.add(z3.Implies(reachable[-1][i][j], z3.Not(edge[j][i])))

    # Also: no self-attacks (simplifies encoding)
    for i in range(n_nodes):
        solver.add(z3.Not(edge[i][i]))

    # --- Grounded extension semantics ---
    # accepted[i] is True iff all attackers of i are attacked by some accepted node
    for i in range(n_nodes):
        # Attackers of i: nodes j where edge[j][i] is True
        att_conditions = []
        for j in range(n_nodes):
            if i != j:
                # For each potential attacker j
                defenders_of_j = []
                for d in range(n_nodes):
                    if d != j:
                        # d attacks j AND d is accepted => j is defended against
                        defenders_of_j.append(z3.And(edge[d][j], accepted[d]))
                # j attacks i (edge[j][i]) => j must be defended against (some accepted d attacks j)
                if defenders_of_j:
                    att_conditions.append(
                        z3.Implies(edge[j][i], z3.Or(defenders_of_j))
                    )
                else:
                    # If j has no potential defenders, then j cannot attack i
                    # (otherwise i would have an undefeated attacker)
                    att_conditions.append(z3.Not(edge[j][i]))
            # else: self-attack already excluded

        # accepted[i] iff ALL attacker conditions hold
        if att_conditions:
            solver.add(accepted[i] == z3.And(att_conditions))
        else:
            solver.add(accepted[i] == True)

    # --- Claim negation: exists undecided node ---
    # A node is undecided if it's NOT accepted AND
    # it's NOT attacked by any accepted node (i.e., not rejected)
    undecided_conditions = []
    for i in range(n_nodes):
        is_rejected = z3.Or([z3.And(edge[j][i], accepted[j]) for j in range(n_nodes)]) if n_nodes > 1 else z3.BoolVal(False)
        is_undecided = z3.And(z3.Not(accepted[i]), z3.Not(is_rejected))
        undecided_conditions.append(is_undecided)

    # Negation of universal claim: there exists at least one undecided node
    solver.add(z3.Or(undecided_conditions))

    # Run solver
    result = solver.check()
    elapsed = time.time() - start

    if result == z3.unsat:
        return UniversalProofResult(n_nodes, True, "UNSAT=PROVED", time_seconds=elapsed)
    elif result == z3.sat:
        model = solver.model()
        # Extract counterexample
        edges_list = []
        for i in range(n_nodes):
            for j in range(n_nodes):
                if i != j and z3.is_true(model[edge[i][j]]):
                    edges_list.append([i, j])
        accepted_list = [i for i in range(n_nodes) if z3.is_true(model[accepted[i]])]
        ce = {"edges": edges_list, "accepted": accepted_list, "n": n_nodes}
        return UniversalProofResult(n_nodes, False, "SAT=COUNTEREXAMPLE",
                                    counterexample=ce, time_seconds=elapsed)
    else:
        return UniversalProofResult(n_nodes, False, f"UNKNOWN={result}", time_seconds=elapsed)


def run_universal_proof_benchmark(max_n: int = 5) -> list[UniversalProofResult]:
    """Run the universal DAG completeness proof for sizes 2 through max_n."""
    results = []
    for n in range(2, max_n + 1):
        r = prove_dag_completeness(n, timeout_ms=60000)
        symbol = "PROVED" if r.proved else "FAIL"
        ce_info = ""
        if r.counterexample:
            ce_info = f" | counterexample edges={r.counterexample['edges']}"
        print(f"N={n}: {symbol} ({r.time_seconds:.1f}s) {r.status}{ce_info}")
        results.append(r)
    return results
