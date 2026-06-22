"""Universal SMT proofs for grounded extension via explicit fixpoint unrolling.

Instead of encoding the algebraic fixed-point condition (which allows non-minimal
solutions), we unroll the fixpoint iteration exactly as the Python engine does:
  in[0][i] = False
  in[k+1][i] = all attackers of i are attacked by some in[k][*]

After N steps (where N = number of nodes), the iteration stabilises, giving
the least fixed point = the grounded extension.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

try:
    import z3
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False


@dataclass
class ProofResult:
    n_nodes: int
    proved: bool
    status: str = ""
    time_seconds: float = 0.0


def _encode_fixpoint(solver, n_nodes, edge, iteration_vars, step):
    """Encode one iteration of the characteristic function.
    iteration_vars[step][i] = True iff all attackers of i are attacked
    by some node in iteration_vars[step-1].
    """
    prev = iteration_vars[step - 1]
    curr = iteration_vars[step]
    for i in range(n_nodes):
        # For each potential attacker j of i:
        # If edge[j][i] is True, then j must be attacked by some accepted node from prev
        att_cond = []
        for j in range(n_nodes):
            if i == j:
                continue
            # Is j attacked by any node in prev?
            defenders_of_j = []
            for d in range(n_nodes):
                if d == j:
                    continue
                # d attacks j AND d is in prev
                defenders_of_j.append(z3.And(edge[d][j], prev[d]))
            if defenders_of_j:
                # If j attacks i, then j must be defeated
                att_cond.append(z3.Implies(edge[j][i], z3.Or(defenders_of_j)))
            else:
                # j has no possible defenders, so j cannot attack i
                att_cond.append(z3.Not(edge[j][i]))
        if att_cond:
            solver.add(curr[i] == z3.And(att_cond))
        else:
            solver.add(curr[i] == True)


def _encode_dag_constraint(solver, n_nodes, edge):
    """No directed cycles: reachability encoding."""
    reachable = []
    step0 = [[edge[i][j] for j in range(n_nodes)] for i in range(n_nodes)]
    reachable.append(step0)
    for step in range(1, n_nodes):
        prev = reachable[step - 1]
        curr = [[z3.BoolVal(False) for _ in range(n_nodes)] for _ in range(n_nodes)]
        for i in range(n_nodes):
            for j in range(n_nodes):
                via = [z3.And(prev[i][m], edge[m][j]) for m in range(n_nodes)]
                curr[i][j] = z3.Or(prev[i][j], z3.Or(via) if via else z3.BoolVal(False))
        reachable.append(curr)
    for i in range(n_nodes):
        for j in range(n_nodes):
            if i != j:
                solver.add(z3.Implies(reachable[-1][i][j], z3.Not(edge[j][i])))
        solver.add(z3.Not(edge[i][i]))


def prove_dag_completeness(n_nodes: int, timeout_ms: int = 60000) -> ProofResult:
    """Prove: for all DAGs of size n_nodes, grounded extension has no undecided nodes."""
    if not HAS_Z3:
        return ProofResult(n_nodes, False, "Z3_UNAVAILABLE")

    start = time.time()
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)

    # Edge variables
    edge = [[z3.Bool(f"e_{i}_{j}") for j in range(n_nodes)] for i in range(n_nodes)]

    # DAG constraint
    _encode_dag_constraint(solver, n_nodes, edge)

    # Fixpoint unrolling: N+1 iterations (iter 0 = all False)
    iteration_vars = []
    for step in range(n_nodes + 1):
        iteration_vars.append([z3.Bool(f"in_{step}_{i}") for i in range(n_nodes)])

    # Iteration 0: all False
    for i in range(n_nodes):
        solver.add(z3.Not(iteration_vars[0][i]))

    # Iterations 1..N: characteristic function
    for step in range(1, n_nodes + 1):
        _encode_fixpoint(solver, n_nodes, edge, iteration_vars, step)

    # Final result: iteration_vars[N] is the grounded extension
    accepted = iteration_vars[n_nodes]

    # Claim negation: there exists an undecided node
    # undecided = NOT accepted AND NOT (attacked by any accepted)
    undecided = []
    for i in range(n_nodes):
        is_attacked_by_accepted = z3.Or([z3.And(edge[j][i], accepted[j])
                                         for j in range(n_nodes) if j != i]) if n_nodes > 1 else z3.BoolVal(False)
        undecided.append(z3.And(z3.Not(accepted[i]), z3.Not(is_attacked_by_accepted)))
    solver.add(z3.Or(undecided))

    result = solver.check()
    elapsed = time.time() - start

    if result == z3.unsat:
        return ProofResult(n_nodes, True, "UNSAT=PROVED", time_seconds=elapsed)
    elif result == z3.sat:
        model = solver.model()
        edges_list = [(i, j) for i in range(n_nodes) for j in range(n_nodes)
                      if i != j and z3.is_true(model[edge[i][j]])]
        acc_list = [i for i in range(n_nodes) if z3.is_true(model[accepted[i]])]
        return ProofResult(n_nodes, False,
                          f"SAT=CE edges={edges_list} acc={acc_list}", time_seconds=elapsed)
    return ProofResult(n_nodes, False, f"UNKNOWN={result}", time_seconds=elapsed)


def prove_cycle_all_undecided(n_nodes: int, timeout_ms: int = 60000) -> ProofResult:
    """Prove: for all simple cycle graphs of size n_nodes, accepted = {}."""
    if not HAS_Z3 or n_nodes < 2:
        return ProofResult(n_nodes, False, "Z3_UNAVAILABLE_OR_TRIVIAL")

    start = time.time()
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)

    edge = [[z3.Bool(f"e_{i}_{j}") for j in range(n_nodes)] for i in range(n_nodes)]

    # Cycle constraint: each node has exactly 1 out-edge, 1 in-edge, strongly connected
    for i in range(n_nodes):
        out_edges = [edge[i][j] for j in range(n_nodes) if i != j]
        solver.add(z3.PbEq([(e, 1) for e in out_edges], 1))
        solver.add(z3.Not(edge[i][i]))
    for j in range(n_nodes):
        in_edges = [edge[i][j] for i in range(n_nodes) if i != j]
        solver.add(z3.PbEq([(e, 1) for e in in_edges], 1))

    # Connectivity: every node reachable from every other
    reachable = []
    step0 = [[edge[i][j] for j in range(n_nodes)] for i in range(n_nodes)]
    reachable.append(step0)
    for step in range(1, n_nodes):
        prev = reachable[step - 1]
        curr = [[z3.BoolVal(False) for _ in range(n_nodes)] for _ in range(n_nodes)]
        for i in range(n_nodes):
            for j in range(n_nodes):
                via = [z3.And(prev[i][m], edge[m][j]) for m in range(n_nodes)]
                curr[i][j] = z3.Or(prev[i][j], z3.Or(via) if via else z3.BoolVal(False))
        reachable.append(curr)
    for i in range(n_nodes):
        for j in range(n_nodes):
            if i != j:
                solver.add(reachable[-1][i][j])

    # Fixpoint unrolling
    iteration_vars = []
    for step in range(n_nodes + 1):
        iteration_vars.append([z3.Bool(f"in_{step}_{i}") for i in range(n_nodes)])
    for i in range(n_nodes):
        solver.add(z3.Not(iteration_vars[0][i]))
    for step in range(1, n_nodes + 1):
        _encode_fixpoint(solver, n_nodes, edge, iteration_vars, step)

    accepted = iteration_vars[n_nodes]

    # Claim negation: there exists an accepted node
    solver.add(z3.Or(accepted))

    result = solver.check()
    elapsed = time.time() - start

    if result == z3.unsat:
        return ProofResult(n_nodes, True, "UNSAT=PROVED", time_seconds=elapsed)
    elif result == z3.sat:
        model = solver.model()
        edges_list = [(i, j) for i in range(n_nodes) for j in range(n_nodes)
                      if i != j and z3.is_true(model[edge[i][j]])]
        acc_list = [i for i in range(n_nodes) if z3.is_true(model[accepted[i]])]
        return ProofResult(n_nodes, False,
                          f"SAT=CE edges={edges_list} acc={acc_list}", time_seconds=elapsed)
    return ProofResult(n_nodes, False, f"UNKNOWN={result}", time_seconds=elapsed)
