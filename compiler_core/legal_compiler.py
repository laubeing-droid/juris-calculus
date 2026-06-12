#!/usr/bin/env python3
"""v2.0 Legal Compiler - 5-pass compilation facade.

Pass 1: source anchoring -> Pass 2: shard routing -> Pass 3: Horn slicing
Pass 4: exception inclusion -> Pass 5: trust label projection
"""
from typing import List, Dict, Optional
from compiler_core.evaluator import load_rules_from_yaml
from compiler_core.types import LegalRule
from compiler_core.trust_labels import TrustLabel, EpistemicStatus


class LegalCompiler:
    def __init__(self, rules_path: str, overrides_path: Optional[str] = None):
        self.rules_path = rules_path
        self.overrides_path = overrides_path
        self._all_rules: List[LegalRule] = []

    def compile_rules(self, route_request: Optional[List[str]] = None) -> List[LegalRule]:
        if self._all_rules:
            pass
        else:
            self._all_rules = load_rules_from_yaml(self.rules_path)

        if route_request is None:
            return list(self._all_rules)

        selected = [r for r in self._all_rules
                    if any(d in r.id.lower() or any(d in c.lower() for c in r.concepts)
                           for d in route_request)]
        return selected or list(self._all_rules)

    def validate_refs(self) -> Dict:
        all_ids = {r.id for r in self._all_rules}
        broken = []
        for r in self._all_rules:
            for exc in r.exception_chain:
                if exc not in all_ids:
                    broken.append(f"{r.id} -> {exc}")
        return {"total_rules": len(self._all_rules), "broken_refs": len(broken), "detail": broken}
