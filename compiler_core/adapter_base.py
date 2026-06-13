#!/usr/bin/env python3
"""v2.1 Abstract adapter base — jurisdiction-agnostic interface.

Every jurisdiction addon implements these methods.
Extracted from adapter/__init__.py to remove HK/US hardcoding from core.

v2.1 additions (Gemini + Doubao audit):
  - load_evaluator: convenience factory for FixpointEvaluator
  - get_legal_family: civil_law / common_law / mixed
  - get_modal_mapping: DDL modal word → NormModality enum
  - get_priority_evaluator: defeasibility precedence function
"""
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional
from compiler_core.types import IRState, LegalDomain
from compiler_core.domain_config import DomainConfig


class JurisdictionAdapter(ABC):
    """法域适配器: map_to_L0() + validate_against_guardrails()

    Subclasses MUST set:
        jurisdiction: str   — e.g. "CN", "HK", "US"
        rules_path: str     — path to rules YAML
        overrides_path: str — path to L0 overrides YAML
    """
    jurisdiction: str = ""
    rules_path: str = ""
    overrides_path: str = ""

    # ── 抽象方法（子类必须实现） ──────────────────────

    @abstractmethod
    def map_to_L0(self, domain_concept: str) -> str:
        """将法域特有概念映射到 L0 原语 (Status/Act/Defect/Power/Agent/?)"""
        ...

    @abstractmethod
    def validate_against_guardrails(self, state: IRState) -> Dict:
        """护栏检查: 返回 {valid: bool, issues: [...]}"""
        ...

    # ── 可覆盖方法（有默认实现） ──────────────────────

    def get_legal_family(self) -> str:
        """返回法系类型: civil_law / common_law / mixed"""
        return "civil_law"

    def get_modal_mapping(self) -> Dict[str, str]:
        """返回该法域的 DDL 模态词汇映射。

        格式: {"应当": "OBLIGATION", "不得": "PROHIBITION", ...}
        子类应覆盖此方法提供法域特定映射。
        """
        return {}

    def get_priority_evaluator(
        self,
    ) -> Callable[[Dict, Dict], int]:
        """返回偏序比较函数: (rule_a, rule_b) -> int

        大陆法: 依赖效力位阶 (authority_rank, 上位法优于下位法)
        普通法: 依赖先例判准 (stare decisis + court hierarchy)

        默认实现: 按 authority_rank 降序（大陆法模式）。
        """
        def civil_law_priority(rule_a: Dict, rule_b: Dict) -> int:
            rank_a = rule_a.get("authority_rank", 0)
            rank_b = rule_b.get("authority_rank", 0)
            if rank_a != rank_b:
                return rank_b - rank_a  # higher rank wins
            return 0
        return civil_law_priority

    # ── 便利方法 ─────────────────────────────────────

    def load_evaluator(self, route_request: Optional[List[str]] = None):
        """加载规则并创建 FixpointEvaluator 实例。

        Args:
            route_request: 可选的域过滤请求列表

        Returns:
            FixpointEvaluator 实例
        """
        from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
        from compiler_core.legal_compiler import LegalCompiler

        compiler = LegalCompiler(self.rules_path, overrides_path=self.overrides_path)
        rules = compiler.compile_rules(route_request)
        l0 = getattr(self, "_L0_MAP", {})
        return FixpointEvaluator(
            rules,
            DomainConfig(domain=LegalDomain.CIVIL),
            overrides_path=self.overrides_path,
            l0_map=l0,
        )
