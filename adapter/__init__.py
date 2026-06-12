#!/usr/bin/env python3
"""法域适配器基类 + 跨法系联邦推理"""
import sys
from pathlib import Path
from compiler_core.adapter_base import JurisdictionAdapter  # v2.0: moved to core
from typing import Dict, List, Optional
import yaml

from compiler_core.types import LegalFact, IRState, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.legal_compiler import LegalCompiler
from compiler_core.constraint_validator import ConstraintValidator


# ═══════════════════════════════════════════
# 适配器基类
# ═══════════════════════════════════════════

class JurisdictionAdapter(ABC):
    """法域适配器: map_to_L0() + validate_against_guardrails()"""
    jurisdiction: str = ""
    rules_path: str = ""
    overrides_path: str = ""

    @abstractmethod
    def map_to_L0(self, domain_concept: str) -> str:
        """将法域特有概念映射到 L0 原语"""
        ...

    @abstractmethod
    def validate_against_guardrails(self, state: IRState) -> Dict:
        """护栏检查: 返回 {valid: bool, issues: [...]}"""
        ...

    def load_evaluator(self, route_request=None) -> FixpointEvaluator:
        compiler = LegalCompiler(self.rules_path, overrides_path=self.overrides_path)
        rules = compiler.compile_rules(route_request)
        l0 = getattr(self, '_L0_MAP', {})
        return FixpointEvaluator(rules, DomainConfig(domain=LegalDomain.CIVIL), overrides_path=self.overrides_path, l0_map=l0)


# ═══════════════════════════════════════════
# 香港适配器
# ═══════════════════════════════════════════



if __name__ == "__main__":
    hadley_v_baxendale_test()
