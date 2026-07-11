#!/usr/bin/env python3
"""juris-calculus 类型定义"""
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple, Any, Iterable, Mapping
from typing import TYPE_CHECKING
from compiler_core.trust_labels import TrustLabel, EpistemicStatus, DataOrigin, RuleMaturity
from enum import Enum


class TaintStatus(str, Enum):
    """V6: 事实候选污染状态枚举"""
    CLEAR = "CLEAR"                   # 清洁：纯机械提取，无大模型介入
    TAINTED = "TAINTED"               # 污染：命中自由裁量概念或置信度不足
    ATTEMPTED_HIJACK = "ATTEMPTED_HIJACK"  # 标签劫持：大模型擅自分级carrier_level
    VERBATIM_MISMATCH = "VERBATIM_MISMATCH"  # 原文不匹配：编辑距离>3


class DataQuality(str, Enum):
    """数据质量标签 — 来源: legal-math-modeling/model_status.py"""
    CLEAN = "CLEAN"                    # 干净: 蒸馏 + 人工双审
    UNCERTAIN = "UNCERTAIN"            # 不确定: 仅 LLM 蒸馏, 无人工审核
    DEGRADED = "DEGRADED"              # 降级: 概念映射缺失或过时
    CONFLICTING = "CONFLICTING"        # 冲突: 与其他规则存在攻击关系
    SPARSE = "SPARSE"                  # 稀疏: 补偿字段缺失 (赔偿/免责 未提取)
    PROVISIONAL = "PROVISIONAL"        # 临时: L2/L3 轻量级条目
    CANDIDATE_ONLY = "CANDIDATE_ONLY"  # 候选: 可训练导出，但不得进入正式推理


class LegalDomain(Enum):
    CIVIL = "民事"; CRIMINAL = "刑事"; ADMINISTRATIVE = "行政"


class ValidityState(str, Enum):
    """合同效力状态机 v1.1"""
    VALID = "VALID"              # 生效
    PENDING = "PENDING"          # 效力待定（如未成年人签约待追认）
    CONDITIONAL = "CONDITIONAL"  # 附条件未成就
    VOIDABLE = "VOIDABLE"        # 可撤销（未行使撤销权前）
    VOID = "VOID"                # 自始无效
    TERMINATED = "TERMINATED"    # 有效→解除，向前失效


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
    id: str; description: str = ""; confidence: float = 1.0; epistemic_status: Optional[EpistemicStatus] = None
    taint_chain: List[TaintNode] = field(default_factory=list)
    requires_human_review: bool = False
    # V6: 扩展
    claim_type: str = ""  # HORN_CLAIM / DISCRETIONARY / REQUIRES_REVIEW
    execution_trace_id: str = ""
    proof_trace: List[Dict[str, Any]] = field(default_factory=list)
    source_anchor: str = ""
    domain_origin: str = ""  # v1.1: 来自哪个 L2 领域 (contract/corporate/tort...)
    L0_primitive_source: str = ""  # v1.1: 映射到哪个 L0 原语
    allowed_claim: bool = True
    forbidden_claim: bool = False
    agent_instruction: str = ""
    def get_trust_label(self) -> str:
        if self.epistemic_status is None: return "UNVERIFIED"
        return self.epistemic_status.trust_label.value

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
    attacks: List[str] = field(default_factory=list)
    priority_over: List[str] = field(default_factory=list)
    norm_modality: str = "UNKNOWN"
    modality_confidence: float = 0.0
    modality_source: str = ""
    reparation_chain_pool: list = field(default_factory=list)
    source_anchor: str = ""
    valid_from: str = ""
    valid_to: str = ""
    jurisdiction: str = ""
    authority_rank: str = ""
    trust_label: str = "UNVERIFIED"
    data_quality: str = "CLEAN"


SOURCE_ANCHOR_FIELDS = ("source_anchor", "legal_basis", "citation", "source_ref", "authority_id")


def resolve_rule_source_anchor(rule: Mapping[str, Any]) -> Any:
    """按固定优先级复用规则自身已有来源字段，不加工内容、不推测缺失来源。"""
    for field_name in SOURCE_ANCHOR_FIELDS:
        value = rule.get(field_name)
        if value is not None and str(value).strip():
            return value
    return ""


def normalize_rule_admission(rule: Mapping[str, Any]) -> Dict[str, Any]:
    """归一化 YAML 规则准入状态；无来源锚时强制降为不可推理的训练候选。"""
    normalized = dict(rule)
    normalized["source_anchor"] = resolve_rule_source_anchor(rule)
    if not normalized["source_anchor"]:
        normalized["trust_label"] = TrustLabel.UNVERIFIED.value
        normalized["data_quality"] = DataQuality.CANDIDATE_ONLY.value
    return normalized


def is_rule_reasoning_eligible(rule: Any) -> bool:
    """判断规则能否进入正式索引；这里只执行准入隔离，不改变任何推理语义。"""
    if isinstance(rule, Mapping):
        rule = normalize_rule_admission(rule)
        quality = rule.get("data_quality", DataQuality.CLEAN.value)
    else:
        quality = getattr(rule, "data_quality", DataQuality.CLEAN.value)
    return getattr(quality, "value", quality) != DataQuality.CANDIDATE_ONLY.value


def build_rule_inventory(rules: Iterable[Any]) -> Dict[str, int]:
    """以输入顺序无关的计数生成共享 inventory，且不丢弃候选 corpus。"""
    corpus = list(rules)
    reasoning_eligible_total = sum(is_rule_reasoning_eligible(rule) for rule in corpus)
    return {
        "corpus_total": len(corpus),
        "reasoning_eligible_total": reasoning_eligible_total,
        "candidate_only_total": len(corpus) - reasoning_eligible_total,
    }


@dataclass
class IRState:
    facts: Dict[str, LegalFact] = field(default_factory=dict)
    negative_facts: Dict[str, LegalFact] = field(default_factory=dict)
    claims: Dict[str, LegalClaim] = field(default_factory=dict)
    rules_applied: Set[str] = field(default_factory=set)
    temporal_scope: dict = field(default_factory=lambda: {"fact_date": "2021-03-15", "governing_law": "PRC_CivilCode_2021"})
    world_id: str = "W1"; iteration_count: int = 0; max_iterations: int = 100; horn_saturated: bool = False; horn_truncated: bool = False; horn_truncation_reason: str = ""; horn_derived_bound: int = 0; horn_iterations: int = 0
    domain: LegalDomain = LegalDomain.CIVIL
    rebuttal_log: list = field(default_factory=list)
    jurisdiction: str = ""
    state_tracker: dict = field(default_factory=lambda: {"Contract_Validity": "VALID"})
    negative_specs: list = field(default_factory=list)
    blocked_claims: set = field(default_factory=set)

class NormModality(str, Enum):
    """DDL norm modality: obligation, prohibition, permission, constitutive."""
    UNKNOWN = "UNKNOWN"
    OBLIGATION = "OBLIGATION"
    PROHIBITION = "PROHIBITION"
    PERMISSION = "PERMISSION"
    CONSTITUTIVE = "CONSTITUTIVE"

