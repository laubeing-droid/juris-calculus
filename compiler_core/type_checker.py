#!/usr/bin/env python3
"""Type and shape checks for minimal Legal IR v3."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Set

from compiler_core.legal_ir_v3 import LegalIRRule
from compiler_core.source_anchor import validate_source_anchor


@dataclass
class TypeCheckReport:
    status: str
    issues: List[str] = field(default_factory=list)


def check_legal_ir_rule(rule: LegalIRRule, known_rule_ids: Iterable[str] | None = None) -> TypeCheckReport:
    issues: List[str] = []
    known: Set[str] = set(known_rule_ids or [])
    if not rule.rule_id.strip():
        issues.append("RULE_ID_REQUIRED")
    if not rule.conclusion.predicate.strip():
        issues.append("CONCLUSION_REQUIRED")
    if not rule.validity.jurisdiction.strip():
        issues.append("JURISDICTION_REQUIRED")
    if rule.validity.valid_from and rule.validity.valid_to and rule.validity.valid_from > rule.validity.valid_to:
        issues.append("INVALID_VALIDITY_INTERVAL")
    if not validate_source_anchor(rule.source.authority_id):
        issues.append("SOURCE_ANCHOR_REQUIRED")

    variable_names = {variable.name for variable in rule.variables}
    for condition in list(rule.conditions.all) + list(rule.conditions.any) + list(rule.conditions.not_conditions):
        if not condition.predicate.strip():
            issues.append("EMPTY_CONDITION_PREDICATE")
        for arg in condition.args:
            if arg.startswith("$") and arg[1:] not in variable_names:
                issues.append(f"UNBOUND_VARIABLE:{arg}")
    for arg in rule.conclusion.args:
        if arg.startswith("$") and arg[1:] not in variable_names:
            issues.append(f"UNBOUND_VARIABLE:{arg}")
    for ref in rule.exceptions:
        if known and ref not in known:
            issues.append(f"UNKNOWN_EXCEPTION_REF:{ref}")
    for ref in rule.priority.get("priority_over", []) or []:
        if known and ref not in known:
            issues.append(f"UNKNOWN_PRIORITY_REF:{ref}")

    return TypeCheckReport(status="PASS" if not issues else "FAIL", issues=issues)
