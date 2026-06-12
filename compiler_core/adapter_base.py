#!/usr/bin/env python3
"""v2.0 Abstract adapter base — jurisdiction-agnostic interface.

Every jurisdiction addon implements these two methods.
Extracted from adapter/__init__.py to remove HK/US hardcoding from core.
"""
from abc import ABC, abstractmethod
from typing import Dict
from compiler_core.types import IRState


class JurisdictionAdapter(ABC):
    """法域适配器: map_to_L0() + validate_against_guardrails()"""
    jurisdiction: str = ""
    rules_path: str = ""
    overrides_path: str = ""

    @abstractmethod
    def map_to_L0(self, domain_concept: str) -> str:
        """将法域特有概念映射到 L0 原语 (Status/Act/Defect/Power/Agent/?)"""
        ...

    @abstractmethod
    def validate_against_guardrails(self, state: IRState) -> Dict:
        """护栏检查: 返回 {valid: bool, issues: [...]}"""
        ...
