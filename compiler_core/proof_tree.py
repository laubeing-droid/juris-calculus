#!/usr/bin/env python3
"""Proof Tree — jurisdiction-neutral output format.

编译器核心只输出 ProofTree（实体ID + 规则ID + 逻辑算子 + 置信度），
不做任何自然语言渲染。语言映射由 LanguageRenderer 后置插件处理。

设计依据: Gemini 审计方案 — "编译器出 Proof Tree，语言映射是后置渲染插件"
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ProofNode:
    """证明树中的单个节点。"""
    node_id: str           # 如 "R:CBL_003" 或 "S:cn_rule_1234"
    kind: str              # "blocking" | "spc_tendency" | "statute" | "fact"
    head_claim: str        # 法律主张 ID（中立概念，非自然语言）
    confidence: float      # 0.0 ~ 1.0
    children: List[str]    # 子节点 ID 列表
    source_anchor: str     # 法条引用（如 "CivilCode_Art585"，非法域自然语言）
    modality: str = ""     # DDL 模态: OBLIGATION / PROHIBITION / PERMISSION / CONSTITUTIVE
    rule_id: str = ""      # 生成该节点的规则 ID；为空表示上游未提供可审计规则标识


@dataclass
class ProofTree:
    """完整证明树 — 编译器的最终输出格式。

    所有字段都是法域中立的 ID 和逻辑算子，不含自然语言。
    """
    jurisdiction: str                         # 目标法域: "CN" / "HK" / "US"
    nodes: Dict[str, ProofNode] = field(default_factory=dict)
    blocked_claims: List[str] = field(default_factory=list)    # 被 CBL 阻断的主张 ID
    spc_tendencies: List[str] = field(default_factory=list)    # SPC 裁判倾向主张 ID
    cn_claims: List[str] = field(default_factory=list)         # CN 成文法主张 ID
    bridge_health: Dict = field(default_factory=dict)          # 桥接健康状态

    def add_node(self, node: ProofNode) -> None:
        """添加一个证明节点。"""
        self.nodes[node.node_id] = node

    def get_blocking_nodes(self) -> List[ProofNode]:
        """返回所有 blocking 类型节点。"""
        return [n for n in self.nodes.values() if n.kind == "blocking"]

    def get_statute_nodes(self) -> List[ProofNode]:
        """返回所有 statute（成文法）类型节点。"""
        return [n for n in self.nodes.values() if n.kind == "statute"]

    def get_spc_nodes(self) -> List[ProofNode]:
        """返回所有 spc_tendency 类型节点。"""
        return [n for n in self.nodes.values() if n.kind == "spc_tendency"]

    def summary(self) -> Dict:
        """返回摘要统计（不含自然语言）。"""
        return {
            "jurisdiction": self.jurisdiction,
            "total_nodes": len(self.nodes),
            "blocked_count": len(self.blocked_claims),
            "spc_count": len(self.spc_tendencies),
            "cn_count": len(self.cn_claims),
            "bridge_health": self.bridge_health.get("status", "UNKNOWN"),
        }
