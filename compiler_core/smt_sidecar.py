#!/usr/bin/env python3
"""Optional SMT sidecar for numeric, date, and state constraints."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List


@dataclass
class SMTResult:
    status: str
    constraints: List[str] = field(default_factory=list)
    unsat_core: List[str] = field(default_factory=list)
    reason: str = ""


class SMTSidecar:
    def __init__(self) -> None:
        try:
            import z3  # type: ignore
            self.z3 = z3
            self.available = True
        except Exception:
            self.z3 = None
            self.available = False

    def check(self, constraints: List[Dict[str, Any]]) -> SMTResult:
        if not self.available:
            return self._python_fallback(constraints)
        return self._z3_check(constraints)

    def check_limitation_period(self, start_date: str, filing_date: str, max_days: int, name: str = "limitation_period") -> SMTResult:
        return self.check([limitation_constraint(start_date, filing_date, max_days, name)])

    def check_money_cap(self, amount: int, cap: int, name: str = "money_cap") -> SMTResult:
        return self.check([money_cap_constraint(amount, cap, name)])

    def _python_fallback(self, constraints: List[Dict[str, Any]]) -> SMTResult:
        failed: List[str] = []
        names: List[str] = []
        for index, constraint in enumerate(constraints):
            name = str(constraint.get("name", f"c{index}"))
            names.append(name)
            if not _eval_constraint(constraint):
                failed.append(name)
        if failed:
            return SMTResult(status="UNSAT", constraints=names, unsat_core=failed, reason="python_fallback")
        return SMTResult(status="SAT", constraints=names, reason="python_fallback")

    def _z3_check(self, constraints: List[Dict[str, Any]]) -> SMTResult:
        solver = self.z3.Solver()
        names: List[str] = []
        tracked: Dict[str, Any] = {}
        for index, constraint in enumerate(constraints):
            name = str(constraint.get("name", f"c{index}"))
            expr = _z3_expr(self.z3, constraint)
            if expr is None:
                return self._python_fallback(constraints)
            tag = self.z3.Bool(name)
            names.append(name)
            tracked[name] = tag
            solver.assert_and_track(expr, tag)
        result = solver.check()
        if result == self.z3.sat:
            return SMTResult(status="SAT", constraints=names, reason="z3")
        if result == self.z3.unsat:
            core = [str(item) for item in solver.unsat_core()]
            return SMTResult(status="UNSAT", constraints=names, unsat_core=core, reason="z3")
        return SMTResult(status="UNKNOWN", constraints=names, reason="z3")


def _eval_constraint(constraint: Dict[str, Any]) -> bool:
    op = constraint.get("op")
    left = constraint.get("left")
    right = constraint.get("right")
    if constraint.get("type") == "date":
        left = date.fromisoformat(str(left))
        right = date.fromisoformat(str(right))
    if op == "<=":
        return left <= right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == ">":
        return left > right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "mutually_exclusive":
        active = [state for state, enabled in (constraint.get("states") or {}).items() if enabled]
        return len(active) <= 1
    raise ValueError(f"Unsupported SMT sidecar constraint: {op}")


def _z3_expr(z3, constraint: Dict[str, Any]):
    op = constraint.get("op")
    if op == "mutually_exclusive":
        states = constraint.get("states") or {}
        active = [z3.Bool(str(name)) for name, enabled in states.items() if enabled]
        return z3.AtMost(*active, 1) if active else z3.BoolVal(True)

    left = _z3_value(z3, constraint.get("left"), constraint.get("type"))
    right = _z3_value(z3, constraint.get("right"), constraint.get("type"))
    if op == "<=":
        return left <= right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == ">":
        return left > right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    return None


def _z3_value(z3, value: Any, value_type: str | None):
    if value_type == "date":
        return z3.IntVal(date.fromisoformat(str(value)).toordinal())
    if isinstance(value, bool):
        return z3.BoolVal(value)
    if isinstance(value, int):
        return z3.IntVal(value)
    if isinstance(value, float):
        return z3.RealVal(str(value))
    return z3.IntVal(int(value))


def limitation_constraint(start_date: str, filing_date: str, max_days: int, name: str = "limitation_period") -> Dict[str, Any]:
    start = date.fromisoformat(start_date).toordinal()
    filing = date.fromisoformat(filing_date).toordinal()
    return {"name": name, "left": filing - start, "op": "<=", "right": max_days}


def money_cap_constraint(amount_minor_units: int, cap_minor_units: int, name: str = "money_cap") -> Dict[str, Any]:
    return {"name": name, "left": amount_minor_units, "op": "<=", "right": cap_minor_units}
