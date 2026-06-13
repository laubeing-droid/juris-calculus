"""Minimal PROLEG format translator: LegalRule -> PROLEG fact/rule text, no runtime."""
from __future__ import annotations

from typing import List

from compiler_core.types import LegalRule


def legal_rule_to_proleg(rule: LegalRule) -> str:
    lines: List[str] = []
    for premise in rule.premise_atoms or []:
        lines.append(f"fact({rule.id}, {premise}).")
    head = rule.head_claim or "unknown_claim"
    lines.append(f"rule({rule.id}, [{', '.join(rule.premise_atoms or [])}], {head}).")
    for exc in rule.exception_chain or []:
        lines.append(f"exception({rule.id}, {exc}).")
    for atk in rule.attacks or []:
        lines.append(f"attack({rule.id}, {atk}).")
    return "\n".join(lines)


def proleg_to_prolog_like(proleg_text: str) -> str:
    lines: List[str] = []
    for line in proleg_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith("."):
            lines.append(stripped)
        else:
            lines.append(stripped + ".")
    return "\n".join(lines)
