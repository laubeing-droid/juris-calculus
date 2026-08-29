"""Official YAML rule admission primitives for the formal wheel.

This module carries exactly what official YAML pack verification needs:
the data-quality vocabulary, source-anchor resolution, rule admission
normalization, and the reasoning-eligibility predicate with its inventory
helper. It must stay importable from the production wheel, so it may not
depend on repository-only modules such as compiler_core.types.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Iterable, Mapping

from compiler_core.trust_labels import TrustLabel


class DataQuality(str, Enum):
    """数据质量标签 — 来源: legal-math-modeling/model_status.py"""

    CLEAN = "CLEAN"                    # 干净: 蒸馏 + 人工双审
    UNCERTAIN = "UNCERTAIN"            # 不确定: 仅 LLM 蒸馏, 无人工审核
    DEGRADED = "DEGRADED"              # 降级: 概念映射缺失或过时
    CONFLICTING = "CONFLICTING"        # 冲突: 与其他规则存在攻击关系
    SPARSE = "SPARSE"                  # 稀疏: 补偿字段缺失 (赔偿/免责 未提取)
    PROVISIONAL = "PROVISIONAL"        # 临时: L2/L3 轻量级条目
    CANDIDATE_ONLY = "CANDIDATE_ONLY"  # 候选: 可训练导出，但不得进入正式推理


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


__all__ = (
    "DataQuality",
    "SOURCE_ANCHOR_FIELDS",
    "resolve_rule_source_anchor",
    "normalize_rule_admission",
    "is_rule_reasoning_eligible",
    "build_rule_inventory",
)
