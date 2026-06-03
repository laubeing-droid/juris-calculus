#!/usr/bin/env python3
"""
juris-calculus 领域抽象基类 v2.0
开源贡献者继承此类即可注入新法域规则、原子、精算参数
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional


@dataclass
class DomainConfig:
    """领域配置（原 domain_config.py 的 DomainConfig 兼容超集）"""
    domain_id: str = ""
    name: str = ""
    jurisdiction: str = "cn"
    weights: tuple = (0.25, 0.15, 0.35, 0.25)
    taint_threshold: float = 0.45
    hard_audit_threshold: float = 0.25
    k_max: int = 4
    critical_score_threshold: float = 0.35
    critical_streak_max: int = 3
    alpha: float = 1.0  # 精算α（不再硬编码）
    concept_registry: Set[str] = field(default_factory=set)
    valid_transitions: Dict[str, List[str]] = field(default_factory=dict)


class BaseDomainProvider(ABC):
    """开源社区贡献新法律领域时，继承此类即可
    
    用法：
        class CriminalProvider(BaseDomainProvider):
            @property
            def domain_id(self) -> str: return "CRIMINAL"
            
            @property
            def atom_registry(self) -> dict:
                return {"自首": "Crim.Mitigation.SURRENDER", ...}
            
            @property
            def rules(self) -> list:
                return load_rules_from_yaml("criminal_rules.yaml")
        
        engine = InferenceEngine(provider=CriminalProvider())
    """

    @property
    @abstractmethod
    def domain_id(self) -> str:
        """领域唯一标识，如 'CIVIL_CONTRACT', 'CRIMINAL', 'ADMIN'"""
        pass

    @property
    @abstractmethod
    def jurisdiction(self) -> str:
        """法域，如 'cn', 'us'"""
        pass

    @property
    @abstractmethod
    def atom_registry(self) -> dict:
        """符号注册表: {中文概念: juris谓词ID}"""
        pass

    @property
    @abstractmethod
    def rules(self) -> list:
        """Horn 子句规则列表 [LegalRule, ...]"""
        pass

    @property
    def concepts(self) -> List[str]:
        """概念白名单（可被子类覆盖）"""
        return list(self.atom_registry.keys())

    @property
    def config(self) -> DomainConfig:
        """领域配置（含α精算参数）"""
        return DomainConfig(
            domain_id=self.domain_id,
            name=self.__class__.__name__,
            jurisdiction=self.jurisdiction,
            concept_registry=set(self.concepts),
            alpha=1.0
        )

    def translate(self, chinese_text: str) -> Optional[str]:
        """中文文本 → juris 谓词ID"""
        for cn, en in self.atom_registry.items():
            if cn in chinese_text:
                return en
        return None
