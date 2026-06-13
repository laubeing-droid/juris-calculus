#!/usr/bin/env python3
"""Language Renderer — post-processing plugin for ProofTree → natural language.

编译器核心输出 ProofTree（纯 ID + 逻辑算子），
LanguageRenderer 负责将 ProofTree 翻译为目标语言的自然语言表述。

设计依据: Gemini 审计方案 — "法域与语言完全解耦，前端/AST 翻译层独立控制"
"""
from abc import ABC, abstractmethod
from typing import Dict, List
from compiler_core.proof_tree import ProofTree, ProofNode


class LanguageRenderer(ABC):
    """语言渲染插件基类。

    每个目标语言实现一个子类（如 ChineseRenderer、EnglishRenderer）。
    渲染器读取 ProofTree，查表将 claim_id / rule_id 翻译为自然语言。
    """

    @abstractmethod
    def render_claim(self, claim_id: str) -> str:
        """将单个法律主张 ID 渲染为目标语言表述。"""
        ...

    @abstractmethod
    def render_block_explanation(self, blocked_id: str) -> str:
        """渲染 CBL 阻断说明。"""
        ...

    @abstractmethod
    def render_source_anchor(self, anchor: str) -> str:
        """渲染法条引用。"""
        ...

    def render_proof_tree(self, tree: ProofTree) -> str:
        """将完整 ProofTree 渲染为目标语言文档。"""
        lines: List[str] = []
        lines.append(f"=== {self._jurisdiction_label(tree.jurisdiction)} ===\n")

        if tree.blocked_claims:
            lines.append(self._section_header("blocked"))
            for bid in tree.blocked_claims:
                lines.append(f"  [BLOCKED] {self.render_block_explanation(bid)}")
            lines.append("")

        if tree.spc_tendencies:
            lines.append(self._section_header("spc"))
            for sid in tree.spc_tendencies:
                node = tree.nodes.get(sid)
                if node:
                    lines.append(f"  [SPC] {self.render_claim(node.head_claim)}")
                    if node.source_anchor:
                        lines.append(f"        Ref: {self.render_source_anchor(node.source_anchor)}")
            lines.append("")

        statute_nodes = tree.get_statute_nodes()
        if statute_nodes:
            lines.append(self._section_header("statute"))
            for node in statute_nodes:
                lines.append(f"  [{node.modality or 'STATUTE'}] {self.render_claim(node.head_claim)} (conf={node.confidence:.2f})")
                if node.source_anchor:
                    lines.append(f"        Ref: {self.render_source_anchor(node.source_anchor)}")

        summary = tree.summary()
        lines.append(f"\n--- Summary: {summary['total_nodes']} nodes, "
                     f"{summary['blocked_count']} blocked, "
                     f"{summary['spc_count']} SPC, "
                     f"{summary['cn_count']} statute ---")

        return "\n".join(lines)

    @abstractmethod
    def _jurisdiction_label(self, jurisdiction: str) -> str:
        """返回法域的人类可读标签。"""
        ...

    @abstractmethod
    def _section_header(self, section: str) -> str:
        """返回章节标题。"""
        ...


class ChineseRenderer(LanguageRenderer):
    """中文渲染器 — 将 ProofTree 渲染为中文法律文书。"""

    # 法域标签映射
    _JURISDICTION_LABELS = {
        "CN": "中华人民共和国法律推理结论",
        "HK": "香港特别行政区法律推理结论",
        "US": "美国联邦/州法律推理结论",
    }

    # 章节标题
    _SECTION_HEADERS = {
        "blocked": "【成文法阻断】",
        "spc": "【最高法裁判倾向】",
        "statute": "【成文法规则推导】",
    }

    def __init__(self, claim_table: Dict[str, str] = None, anchor_table: Dict[str, str] = None):
        """初始化中文渲染器。

        Args:
            claim_table: claim_id → 中文表述映射表
            anchor_table: source_anchor → 中文法条引用映射表
        """
        self._claim_table = claim_table or {}
        self._anchor_table = anchor_table or {}

    def render_claim(self, claim_id: str) -> str:
        return self._claim_table.get(claim_id, claim_id)

    def render_block_explanation(self, blocked_id: str) -> str:
        return self._claim_table.get(blocked_id, f"概念 {blocked_id} 在中国法下无功能等价物")

    def render_source_anchor(self, anchor: str) -> str:
        return self._anchor_table.get(anchor, anchor)

    def _jurisdiction_label(self, jurisdiction: str) -> str:
        return self._JURISDICTION_LABELS.get(jurisdiction, f"{jurisdiction} 法律推理结论")

    def _section_header(self, section: str) -> str:
        return self._SECTION_HEADERS.get(section, f"【{section}】")


class EnglishRenderer(LanguageRenderer):
    """English renderer — renders ProofTree into English legal text."""

    _JURISDICTION_LABELS = {
        "CN": "PRC Legal Reasoning Conclusion",
        "HK": "Hong Kong SAR Legal Reasoning Conclusion",
        "US": "US Federal/State Legal Reasoning Conclusion",
    }

    _SECTION_HEADERS = {
        "blocked": "[STATUTORY BLOCKING]",
        "spc": "[SPC JUDICIAL TENDENCY]",
        "statute": "[STATUTORY RULE DERIVATION]",
    }

    def __init__(self, claim_table: Dict[str, str] = None, anchor_table: Dict[str, str] = None):
        self._claim_table = claim_table or {}
        self._anchor_table = anchor_table or {}

    def render_claim(self, claim_id: str) -> str:
        return self._claim_table.get(claim_id, claim_id)

    def render_block_explanation(self, blocked_id: str) -> str:
        return self._claim_table.get(blocked_id, f"Concept {blocked_id} has no functional equivalent in PRC law")

    def render_source_anchor(self, anchor: str) -> str:
        return self._anchor_table.get(anchor, anchor)

    def _jurisdiction_label(self, jurisdiction: str) -> str:
        return self._JURISDICTION_LABELS.get(jurisdiction, f"{jurisdiction} Legal Reasoning Conclusion")

    def _section_header(self, section: str) -> str:
        return self._SECTION_HEADERS.get(section, f"[{section.upper()}]")
