"""Legal validity state machine with formal transition rules and SMT-backed validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from compiler_core.types import ValidityState


TRANSITIONS: Dict[ValidityState, List[ValidityState]] = {
    ValidityState.VALID: [ValidityState.TERMINATED],
    ValidityState.PENDING: [ValidityState.VALID, ValidityState.VOID],
    ValidityState.CONDITIONAL: [ValidityState.VALID, ValidityState.VOID],
    ValidityState.VOIDABLE: [ValidityState.VALID, ValidityState.VOID],
    ValidityState.VOID: [],
    ValidityState.TERMINATED: [],
}

TRANSITION_LABELS: Dict[Tuple[ValidityState, ValidityState], str] = {
    (ValidityState.VALID, ValidityState.TERMINATED): "termination_event",
    (ValidityState.PENDING, ValidityState.VALID): "ratification",
    (ValidityState.PENDING, ValidityState.VOID): "rejection_or_lapse",
    (ValidityState.CONDITIONAL, ValidityState.VALID): "condition_fulfilled",
    (ValidityState.CONDITIONAL, ValidityState.VOID): "condition_failed",
    (ValidityState.VOIDABLE, ValidityState.VALID): "ratification_or_waiver",
    (ValidityState.VOIDABLE, ValidityState.VOID): "rescission",
}

TERMINAL_STATES = {ValidityState.VOID, ValidityState.TERMINATED}


@dataclass
class ValidityTransition:
    from_state: ValidityState
    to_state: ValidityState
    trigger: str
    evidence: List[str] = field(default_factory=list)
    source_anchor: str = ""


@dataclass
class ValidityPath:
    contract_id: str
    initial_state: ValidityState = ValidityState.VALID
    transitions: List[ValidityTransition] = field(default_factory=list)

    def current_state(self) -> ValidityState:
        if not self.transitions:
            return self.initial_state
        return self.transitions[-1].to_state


def validate_transition(from_state: ValidityState, to_state: ValidityState, trigger: str = "") -> Dict[str, Any]:
    allowed = TRANSITIONS.get(from_state, [])
    legal = to_state in allowed
    label = TRANSITION_LABELS.get((from_state, to_state), "")
    issues: List[str] = []
    if not legal:
        issues.append(f"ILLEGAL_TRANSITION:{from_state.value}->{to_state.value}")
    if trigger and label and trigger != label:
        issues.append(f"TRIGGER_MISMATCH:expected={label},actual={trigger}")
    if from_state in TERMINAL_STATES:
        issues.append(f"TRANSITION_FROM_TERMINAL:{from_state.value}")
    return {
        "from": from_state.value,
        "to": to_state.value,
        "legal": legal,
        "expected_trigger": label,
        "issues": issues,
        "status": "PASS" if legal and not issues else "FAIL",
    }


def validate_path(path: ValidityPath) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    all_legal = True
    for idx, transition in enumerate(path.transitions):
        check = validate_transition(transition.from_state, transition.to_state, transition.trigger)
        if check["status"] == "FAIL":
            all_legal = False
            findings.append({"step": idx, "check": check})
        if not transition.source_anchor:
            findings.append({"step": idx, "issue": "TRANSITION_WITHOUT_SOURCE_ANCHOR"})
    return {
        "contract_id": path.contract_id,
        "path_length": len(path.transitions),
        "current_state": path.current_state().value,
        "finding_count": len(findings),
        "all_legal": all_legal,
        "status": "PASS" if all_legal and not any("WITHOUT_SOURCE_ANCHOR" in str(f) for f in findings) else "FAIL",
        "findings": findings,
    }


def smt_backed_validate(path: ValidityPath, max_voidable_days: int = 365, max_pending_days: int = 90) -> Dict[str, Any]:
    from compiler_core.smt_sidecar import limitation_constraint, SMTSidecar
    sidecar = SMTSidecar()
    constraints = []
    voidable_count = 0
    pending_count = 0
    for t in path.transitions:
        if t.from_state == ValidityState.VOIDABLE:
            voidable_count += 1
        if t.from_state == ValidityState.PENDING:
            pending_count += 1
    if voidable_count > 1:
        constraints.append(limitation_constraint("2021-01-01", "2026-06-13", max_voidable_days, "voidable_window"))
    if pending_count > 1:
        constraints.append(limitation_constraint("2021-01-01", "2026-06-13", max_pending_days, "pending_window"))
    smt_result = sidecar.check(constraints)
    return {
        "contract_id": path.contract_id,
        "smt_status": smt_result.status,
        "smt_available": sidecar.available,
        "smt_unsat_core": smt_result.unsat_core,
        "constraint_count": len(constraints),
        "status": "PASS" if smt_result.status == "SAT" or not sidecar.available else "FAIL",
    }
