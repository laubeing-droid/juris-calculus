#!/usr/bin/env python3
"""juris-calculus 类型定义"""
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple
from enum import Enum


class TaintStatus(str, Enum):
    """V6: 事实候选污染状态枚举"""
    CLEAR = "CLEAR"                   # 清洁：纯机械提取，无大模型介入
    TAINTED = "TAINTED"               # 污染：命中自由裁量概念或置信度不足
    ATTEMPTED_HIJACK = "ATTEMPTED_HIJACK"  # 标签劫持：大模型擅自分级carrier_level
    VERBATIM_MISMATCH = "VERBATIM_MISMATCH"  # 原文不匹配：编辑距离>3


class LegalDomain(Enum):
    CIVIL = "民事"; CRIMINAL = "刑事"; ADMINISTRATIVE = "行政"


@dataclass
class LegalFact:
    id: str; description: str = ""; source: str = ""; formalizable: float = 1.0
    # V6: 污染追踪扩展
    taint_status: str = "CLEAR"
    extraction_confidence: float = 1.0
    carrier_level: str = ""  # A/B/C 证据载体分级（由规则引擎判定，严禁大模型填写）
    raw_text: str = ""  # 原始文本（用于源锚定验证）
    source_anchor: str = ""  # 源锚定：上下文签名(context_prefix||raw_text||context_suffix)


@dataclass
class TaintNode:
    rule_id: str; claim_id: str; taint_source: str; formalizable_score: float; depth: int


@dataclass
class LegalClaim:
    id: str; description: str = ""; confidence: float = 1.0
    taint_chain: List[TaintNode] = field(default_factory=list)
    requires_human_review: bool = False
    # V6: 扩展
    claim_type: str = ""  # HORN_CLAIM / DISCRETIONARY / REQUIRES_REVIEW
    execution_trace_id: str = ""
    def taint_summary(self) -> str:
        return "CLEAR" if not self.taint_chain else " -> ".join(f"{n.rule_id}({n.taint_source})" for n in self.taint_chain)


@dataclass
class NegativeSpec:
    """V6: 反向要件缺口清单。大模型不仅输出提取到的事实，还必须输出未找到的要件。"""
    rule_id: str
    must_find: List[str] = field(default_factory=list)
    cannot_conclude_without: List[str] = field(default_factory=list)
    found_items: List[str] = field(default_factory=list)
    missing_items: List[str] = field(default_factory=list)
    human_review_required: bool = True
    def is_blocking(self) -> bool:
        return len(self.missing_items) > 0 and len(self.cannot_conclude_without) > 0


@dataclass
class LegalRule:
    id: str; premise_atoms: List[str] = field(default_factory=list)
    head_claim: str = ""; exception_chain: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)
    mechanical_exception: bool = True; head_type: str = "HORN"


@dataclass
class IRState:
    facts: Dict[str, LegalFact] = field(default_factory=dict)
    negative_facts: Dict[str, LegalFact] = field(default_factory=dict)
    claims: Dict[str, LegalClaim] = field(default_factory=dict)
    rules_applied: Set[str] = field(default_factory=set)
    temporal_scope: dict = field(default_factory=lambda: {"fact_date": "2021-03-15", "governing_law": "PRC_CivilCode_2021"})
    world_id: str = "W1"; iteration_count: int = 0; max_iterations: int = 100
    domain: LegalDomain = LegalDomain.CIVIL
