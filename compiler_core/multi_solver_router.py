"""Route legal reasoning tasks to appropriate solver: Horn, AAF, SMT, or State Machine."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from compiler_core.types import IRState, LegalRule, LegalDomain
from compiler_core.evaluator import FixpointEvaluator
from compiler_core.smt_sidecar import SMTSidecar, limitation_constraint, money_cap_constraint


class SolverKind(str, Enum):
    HORN = "horn"
    AAF = "aaf"
    SMT = "smt"
    STATE_MACHINE = "state_machine"
    UNKNOWN = "unknown"


@dataclass
class SolverTask:
    task_id: str
    kind: SolverKind
    rules: List[LegalRule] = field(default_factory=list)
    state: Optional[IRState] = None
    constraints: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SolverResult:
    task_id: str
    kind: SolverKind
    claims: Dict[str, float] = field(default_factory=dict)
    smt_status: str = ""
    smt_unsat_core: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    solver_available: bool = True


def detect_task_kind(rules: List[LegalRule], state: IRState | None = None) -> SolverKind:
    has_defeasible = any(rule.head_type != "HORN" or (rule.exception_chain or rule.attacks) for rule in rules)
    has_smt_applicable = any(rule.valid_from and rule.valid_to and rule.valid_from > rule.valid_to for rule in rules)
    has_state_machine = state and state.state_tracker and any(v in {"PENDING", "CONDITIONAL", "VOIDABLE"} for v in state.state_tracker.values())

    if has_smt_applicable:
        return SolverKind.SMT
    if has_state_machine:
        return SolverKind.STATE_MACHINE
    if has_defeasible:
        return SolverKind.AAF
    return SolverKind.HORN


def route_and_solve(
    rules: List[LegalRule],
    state: IRState | None = None,
    jurisdiction: str = "zh_CN",
    smt_constraints: List[Dict[str, Any]] | None = None,
) -> SolverResult:
    kind = detect_task_kind(rules, state)
    result = SolverResult(task_id=f"route_{jurisdiction}", kind=kind)

    if kind == SolverKind.HORN or kind == SolverKind.AAF:
        evaluator = FixpointEvaluator(rules=rules)
        try:
            if state is None:
                state = IRState(domain=LegalDomain.CIVIL, jurisdiction=jurisdiction)
            eval_result = evaluator.evaluate(state)
            result.claims = {claim.id: claim.confidence for claim in eval_result.claims.values() if claim.confidence > 0}
        except Exception as exc:
            result.issues.append(f"HORN_EVALUATOR_ERROR:{exc}")
            result.solver_available = False

    if kind == SolverKind.SMT:
        sidecar = SMTSidecar()
        constraints = smt_constraints or []
        for rule in rules:
            if rule.authority_rank and rule.valid_from:
                constraints.append(limitation_constraint(rule.valid_from, "2026-06-13", 3 * 365, f"temporal_{rule.id}"))
        smt_result = sidecar.check(constraints)
        result.smt_status = smt_result.status
        result.smt_unsat_core = smt_result.unsat_core
        if smt_result.status == "UNSAT":
            result.issues.append("SMT_CONTRADICTION_DETECTED")

    return result
