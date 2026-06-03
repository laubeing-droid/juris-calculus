#!/usr/bin/env python3
"""
juris-calculus 核心基类 — 跨法域通用，法学中立
只认离散数学、图论、Horn 子句和 Fixpoint 迭代
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple


@dataclass
class DomainConfig:
    domain_id: str = ""
    name: str = ""
    jurisdiction: str = "cn"
    alpha: float = 1.0
    weights: Tuple[float, float, float, float] = (0.25, 0.15, 0.35, 0.25)
    taint_threshold: float = 0.45
    hard_audit_threshold: float = 0.25
    k_max: int = 4
    critical_score_threshold: float = 0.35
    critical_streak_max: int = 3
    concept_registry: Set[str] = field(default_factory=set)
    valid_transitions: Dict[str, List[str]] = field(default_factory=dict)


class BaseDomainProvider(ABC):
    """开源贡献者继承此类即可注入新法域规则与原子"""

    @property
    @abstractmethod
    def domain_id(self) -> str: ...

    @property
    @abstractmethod
    def jurisdiction(self) -> str: ...

    @property
    @abstractmethod
    def atom_registry(self) -> dict: ...

    @property
    @abstractmethod
    def rules(self) -> list: ...

    @property
    def concepts(self) -> List[str]:
        return list(self.atom_registry.keys())

    @property
    def config(self) -> DomainConfig:
        return DomainConfig(domain_id=self.domain_id, jurisdiction=self.jurisdiction,
                           concept_registry=set(self.concepts))

    def translate(self, chinese_text: str) -> Optional[str]:
        for cn, en in self.atom_registry.items():
            if cn in chinese_text:
                return en

    # ── 远程对齐资产插槽 ──
    # 开源社区添加新法域对齐框架时，覆盖此属性即可
    @property
    def remote_sync_url(self) -> Optional[str]:
        """远程对齐资产URL。返回None则不启用自动拉取"""
        return None

    @property
    def remote_sync_ttl(self) -> int:
        """对齐资产缓存有效期（秒），默认24小时"""
        return 86400


class InferenceEngine:
    """跨法域通用推理引擎 — Fixpoint 迭代 + 精算"""
    
    def __init__(self, provider: BaseDomainProvider):
        from compiler_core.types import LegalRule, LegalFact, IRState
        from compiler_core.evaluator import FixpointEvaluator
        self.provider = provider
        self.config = provider.config
        self.rules = provider.rules
        self.evaluator = FixpointEvaluator(self.rules, self.config, domain_id=provider.domain_id)
        self._init_pricing()

    def _init_pricing(self):
        from legalos_services.legalos_pricing import LegalOSPricingEngine
        self.pricing = LegalOSPricingEngine(alpha=self.config.alpha)

    def evaluate(self, facts: dict, case_id: str = ""):
        from compiler_core.types import LegalFact, IRState
        state = IRState(world_id=case_id)
        for fid, desc in facts.items():
            state.facts[fid] = LegalFact(fid, str(desc)[:200])
        try:
            return self.evaluator.evaluate(state)
        except Exception as e:
            return state

    def predict_hours(self, effective_nodes: float) -> dict:
        from legalos_services.legalos_pricing import PricingCase
        return self.pricing.predict_hours(PricingCase(effective_nodes=effective_nodes))
