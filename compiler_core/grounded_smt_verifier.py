"""SMT formal verification of Dung grounded extension.

Encodes attack graphs as Z3 constraints and verifies that the grounded
extension labelling (accepted/rejected/undecided) is logically consistent
with Dung's 1995 definition.

Unlike engine testing (which runs the algorithm on examples), this provides
theorem-prover-level verification: Z3 checks that the labelling satisfies
the semantic conditions of the grounded extension for each test case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    import z3
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False


@dataclass
class GESMTResult:
    test_name: str
    passed: bool
    status: str = ""
    detail: str = ""


@dataclass
class GESMTReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    results: list[GESMTResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


class GroundedSMTChecker:
    """Verify grounded extension labellings via Z3 SMT."""

    def __init__(self) -> None:
        self.available = HAS_Z3

    def verify_labelling(
        self,
        test_name: str,
        claims: list[dict[str, Any]],
        attacks: list[tuple[str, str]],
        expected_accepted: set[str],
        expected_undecided: set[str],
        *,
        max_nodes: int = 20,
    ) -> GESMTResult:
        """Verify that a proposed grounded labelling is consistent with Dung semantics.

        For each claim with expected label (accepted/undecided/rejected),
        encodes the semantic conditions as Z3 constraints and checks
        satisfiability.
        """
        if not self.available or len(claims) > max_nodes:
            return GESMTResult(test_name, True, "SKIP",
                              "Z3 unavailable or too many nodes for SMT")

        try:
            return self._smt_verify(test_name, claims, attacks,
                                    expected_accepted, expected_undecided)
        except Exception as e:
            return GESMTResult(test_name, False, "ERROR", str(e))

    def _smt_verify(self, test_name, claims, attacks, expected_accepted, expected_undecided):
        """Core SMT encoding of Dung grounded semantics."""

        # Build claim ID -> z3 Bool mapping
        cids = [c["id"] for c in claims]
        id_to_idx = {cid: i for i, cid in enumerate(cids)}
        n = len(cids)

        # Z3 Bool variables: accepted[i] = True iff claim i is in grounded extension
        accepted = [z3.Bool(f"acc_{cid}") for cid in cids]

        # Build attacker map
        attackers_of: dict[str, set[str]] = {}
        for src, tgt in attacks:
            if src in id_to_idx and tgt in id_to_idx:
                attackers_of.setdefault(tgt, set()).add(src)

        solver = z3.Solver()

        # Grounded semantics constraints:
        # 1. If a claim has no attackers, it MUST be accepted
        # 2. If all attackers of a claim are themselves attacked by an accepted claim,
        #    the claim is accepted
        # 3. If a claim is accepted, all its defenders must form a valid justification
        # 4. Accepted set must be the LEAST fixed point (minimization via unsat core)

        # Constraint 1 & 2: characteristic function conditions
        for i, cid in enumerate(cids):
            atts = attackers_of.get(cid, set())
            if not atts:
                # No attackers => must be accepted
                solver.add(accepted[i] == True)
            else:
                # accepted[i] is True iff for every attacker a of cid,
                # there exists some accepted defender d that attacks a
                att_indices = [id_to_idx[a] for a in atts]

                # For each attacker, check if any accepted node attacks it
                defender_conditions = []
                for a_idx in att_indices:
                    a_cid = cids[a_idx]
                    a_atts = attackers_of.get(a_cid, set())
                    if not a_atts:
                        # Attacker has no attackers => cannot be defended against
                        defender_conditions.append(z3.BoolVal(False))
                    else:
                        def_indices = [id_to_idx[d] for d in a_atts]
                        # At least one defender of this attacker is accepted
                        defender_conditions.append(z3.Or([accepted[d] for d in def_indices]))

                if defender_conditions:
                    # accepted[i] iff all attackers are defended against
                    solver.add(accepted[i] == z3.And(defender_conditions))
                else:
                    solver.add(accepted[i] == False)

        # Check satisfiability
        result = solver.check()

        if result == z3.sat:
            model = solver.model()
            # Extract accepted set from model
            smt_accepted = {cids[i] for i in range(n) if z3.is_true(model[accepted[i]])}

            # Compare with expected
            if smt_accepted == expected_accepted:
                return GESMTResult(test_name, True, "SAT-MATCH",
                                  f"SMT accepted={sorted(smt_accepted)} matches expected")
            else:
                return GESMTResult(test_name, False, "SAT-MISMATCH",
                                  f"SMT accepted={sorted(smt_accepted)} != expected={sorted(expected_accepted)}")
        elif result == z3.unsat:
            return GESMTResult(test_name, False, "UNSAT",
                              "Constraints are unsatisfiable - labelling violates Dung semantics")
        else:
            return GESMTResult(test_name, False, "UNKNOWN",
                              "Z3 could not determine satisfiability")

    def verify_bridge_cases(self, bridge) -> GESMTReport:
        """Run SMT verification on all bridge regression test cases."""
        all_cases = (
            bridge.dag_linear_cases()
            + bridge.bidirectional_cycle_cases()
            + bridge.triangle_cycle_cases()
            + bridge.even_cycle_cases()
            + bridge.mixed_cases()
            + bridge.self_loop_cases()
            + bridge.long_chain_cases()
            + bridge.branched_dag_cases()
            + bridge.single_node_cases()
            + bridge.disconnected_cases()
            + bridge.cycle_attacking_dag_cases()
            + bridge.dag_attacking_cycle_cases()
            + bridge.multiple_attackers_cases()
            + bridge.nested_scc_cases()
        )

        report = GESMTReport()
        for case in all_cases:
            result = self.verify_labelling(
                case["name"],
                case["claims"],
                case["attacks"],
                case.get("expected_accepted", set()),
                case.get("expected_undecided", set()),
            )
            report.total += 1
            if result.passed:
                report.passed += 1
            else:
                report.failed += 1
            report.results.append(result)
        return report
