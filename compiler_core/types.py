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


# 正式准入原语的唯一实现位于 rule_admission（生产 wheel 模块）；types.py
# 仅向仓库内既有消费者转发既有导入路径，types.py 本身不进入正式 wheel。
from compiler_core.rule_admission import (  # noqa: E402
    SOURCE_ANCHOR_FIELDS as SOURCE_ANCHOR_FIELDS,
    DataQuality as DataQuality,
    build_rule_inventory as build_rule_inventory,
    is_rule_reasoning_eligible as is_rule_reasoning_eligible,
    normalize_rule_admission as normalize_rule_admission,
    resolve_rule_source_anchor as resolve_rule_source_anchor,
)


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


class FactTrustStatus(str, Enum):
    """事实从候选到可进入正式内核的机器状态。"""

    CANDIDATE_FACT = "candidate_fact"
    NORMALIZED_FACT = "normalized_fact"
    SOURCE_BOUND_FACT = "source_bound_fact"
    CHECKED_FACT = "checked_fact"
    VERIFIED_FACT = "verified_fact"
    REJECTED_FACT = "rejected_fact"
    STALE_FACT = "stale_fact"
    USER_ASSUMED = "user_assumed"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


class FactCreator(str, Enum):
    """事实创建者类型；该字段只参与准入审计，不代表事实为真。"""

    LLM = "llm"
    HUMAN = "human"
    SYSTEM = "system"
    COURT = "court"
    IMPORT = "import"


@dataclass
class LegalFact:
    """JC唯一事实对象，同时承载来源、状态、污染和人工复核元数据。"""

    id: str
    description: str = ""
    source: str = ""
    formalizable: float = 1.0
    # V6: 污染追踪扩展
    taint_status: str = "CLEAR"
    extraction_confidence: float = 1.0
    carrier_level: str = ""  # A/B/C 证据载体分级（由规则引擎判定，严禁大模型填写）
    raw_text: str = ""  # 原始文本（用于源锚定验证）
    source_anchor: str = ""  # 源锚定：上下文签名(context_prefix||raw_text||context_suffix)
    value: Any = None
    status: FactTrustStatus = FactTrustStatus.CANDIDATE_FACT
    source_ids: Tuple[str, ...] = field(default_factory=tuple)
    alternatives: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    provenance: Dict[str, Any] = field(default_factory=dict)
    human_reviewed: bool = False
    created_by: FactCreator = FactCreator.SYSTEM
    reasoning_tier: str = "P0"

    def __post_init__(self) -> None:
        """规范化边界字段，拒绝未知状态和会混淆准入含义的路由层级。"""

        if not isinstance(self.status, FactTrustStatus):
            self.status = FactTrustStatus(str(self.status))
        if not isinstance(self.created_by, FactCreator):
            self.created_by = FactCreator(str(self.created_by))
        if self.reasoning_tier not in {"P0", "P1", "P2"}:
            raise ValueError(f"unknown reasoning_tier: {self.reasoning_tier}")
        self.source_ids = tuple(sorted({str(item) for item in self.source_ids if str(item)}))
        self.alternatives = tuple(dict(item) for item in self.alternatives)
        self.provenance = dict(self.provenance)

    @property
    def fact_key(self) -> str:
        """提供旧边界payload使用的只读事实键名称。"""

        return self.id

    @property
    def reasoning_eligible_by_default(self) -> bool:
        """状态层只承认verified；正式准入仍须调用完整门禁。"""

        return self.status == FactTrustStatus.VERIFIED_FACT

    @property
    def requires_review_packet(self) -> bool:
        """标记必须进入缺失事实或争议复核数据的状态。"""

        return self.status in {FactTrustStatus.DISPUTED, FactTrustStatus.UNKNOWN}

    @property
    def assumption_tainted(self) -> bool:
        """标记只能支持假设结果的用户假定事实。"""

        return self.status == FactTrustStatus.USER_ASSUMED

    def can_enter_formal_kernel(self) -> bool:
        """执行唯一事实准入门禁；reasoning_tier不得改变结果。"""

        if self.status != FactTrustStatus.VERIFIED_FACT:
            return False
        if not (self.human_reviewed and self.source_ids):
            return False
        if self.created_by == FactCreator.COURT:
            return bool(self.provenance.get("court_trusted"))
        return self._has_verified_admission_marker()

    def _has_verified_admission_marker(self) -> bool:
        """外部输入中 verified fact 必须带入可核验准入标志。"""

        marker = self.provenance.get("admission_channel")
        if marker:
            marker = str(marker).strip().lower()
            if marker in {"trusted_service", "court", "admission_service", "trusted_admission", "trusted"}:
                return True
        for key in ("admission_attestation_id", "admission_asserted", "trusted", "verified", "court_trusted", "attested"):
            value = self.provenance.get(key)
            if isinstance(value, bool):
                if value:
                    return True
            elif isinstance(value, str):
                if value.strip().lower() in {"true", "1", "yes", "pass", "ok"}:
                    return True
            elif value is not None:
                return True
        return False

    def trust_dict(self) -> Dict[str, Any]:
        """返回新的稳定字典，供边界转换和审计摘要使用。"""

        return {
            "fact_key": self.id,
            "value": self.value,
            "status": self.status.value,
            "source_ids": list(self.source_ids),
            "alternatives": [dict(item) for item in self.alternatives],
            "provenance": dict(self.provenance),
            "human_reviewed": self.human_reviewed,
            "created_by": self.created_by.value,
            "reasoning_tier": self.reasoning_tier,
        }


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


@dataclass
class IRState:
    facts: Dict[str, LegalFact] = field(default_factory=dict)
    negative_facts: Dict[str, LegalFact] = field(default_factory=dict)
    claims: Dict[str, LegalClaim] = field(default_factory=dict)
    rules_applied: Set[str] = field(default_factory=set)
    temporal_scope: dict = field(default_factory=dict)
    world_id: str = ""; iteration_count: int = 0; max_iterations: int = 100; horn_saturated: bool = False; horn_truncated: bool = False; horn_truncation_reason: str = ""; horn_derived_bound: int = 0; horn_iterations: int = 0
    domain: LegalDomain = LegalDomain.CIVIL
    rebuttal_log: list = field(default_factory=list)
    jurisdiction: str = ""
    state_tracker: dict = field(default_factory=dict)
    negative_specs: list = field(default_factory=list)
    blocked_claims: set = field(default_factory=set)

class NormModality(str, Enum):
    """DDL norm modality: obligation, prohibition, permission, constitutive."""
    UNKNOWN = "UNKNOWN"
    OBLIGATION = "OBLIGATION"
    PROHIBITION = "PROHIBITION"
    PERMISSION = "PERMISSION"
    CONSTITUTIVE = "CONSTITUTIVE"

