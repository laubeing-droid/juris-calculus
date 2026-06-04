#!/usr/bin/env python3
"""
tools/action_agent/compiler.py — MemoCompiler v1.0
══════════════════════════════════════════════════════════════
Action Agent: 将 TriRailCollider 输出 → 合伙人可签字的
              涉外商事争议跨境处置备忘录 (Markdown)

设计原则:
  1. 确定性渲染: 同一输入永远产出同一法律意见
  2. 法条追溯: 每条意见附带具体法条全文引用
  3. 风险分级: 红(紧急)/黄(预警)/绿(安全)
  4. 脱敏: 不输出内部计算参数 (Logic Hash/迭代次数等)

用法:
  from tools.action_agent.compiler import MemoCompiler
  compiler = MemoCompiler()
  memo_md = compiler.compile(trirail_result)
══════════════════════════════════════════════════════════════
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from tools.action_agent.state_to_text import (
    get_classification_text,
    get_state_opinion,
    get_citation,
    get_prc_citation_full,
    render_risk_matrix,
)


def get_source_version() -> str:
    """获取当前规则集的版本哈希 — 注入备忘录作为法律意见版本标签"""
    try:
        from tools.operator_registry import OperatorRegistry
        return OperatorRegistry.get_source_hash()
    except Exception:
        return "UNVERSIONED"

# ── Jinja2 模板加载 ──
try:
    from jinja2 import Environment, FileSystemLoader
    _JINJA2_AVAILABLE = True
except ImportError:
    _JINJA2_AVAILABLE = False


class MemoCompiler:
    """
    法律备忘录编译器。

    输入: TriRailCollider 输出的单场景结果 (Dict)
    输出: Markdown 格式的法律备忘录
    """

    def __init__(self, template_dir: str = None):
        if template_dir is None:
            template_dir = str(Path(__file__).resolve().parent)
        self.template_dir = template_dir
        self._env = None

        if _JINJA2_AVAILABLE:
            self._env = Environment(
                loader=FileSystemLoader(template_dir),
                trim_blocks=True,
                lstrip_blocks=True,
            )
            self._template = self._env.get_template("partners_memo.j2")
        else:
            self._template = None

    def compile(self, trirail_result: Dict, case_id: str = None) -> str:
        """
        将三轨对撞结果编译为法律备忘录。

        Args:
            trirail_result: TriRailCollider.run_scenario() 的单场景输出
            case_id: 案件编号 (默认使用 scenario_id)

        Returns:
            Markdown 格式的法律备忘录文本
        """
        if case_id is None:
            case_id = trirail_result.get("scenario_id", "UNKNOWN")

        classification = trirail_result.get("classification", "COMPLEX_PARALLAX")
        cls_text = get_classification_text(classification)

        # ── 提取各轨数据 ──
        hk_data = trirail_result.get("hk", {})
        us_data = trirail_result.get("us", {})
        prc_data = trirail_result.get("prc", {})

        hk_claims = hk_data.get("claims", [])
        us_claims = us_data.get("claims", [])

        force_void = prc_data.get("force_void", [])
        force_suppress = prc_data.get("force_suppress", [])
        mapping_override = prc_data.get("mapping_override", [])
        cn_claims_count = prc_data.get("cn_claims_count", 0)

        # ── 风险矩阵 ──
        risk = render_risk_matrix(
            classification, force_void, force_suppress,
            mapping_override, cn_claims_count
        )

        # ── 法条引用 ──
        all_rule_ids = force_void + force_suppress + mapping_override
        citations = []
        seen = set()
        for rid in all_rule_ids:
            short_cite = get_citation(rid)
            if short_cite not in seen:
                full_text = get_prc_citation_full(short_cite)
                if full_text:
                    citations.append({
                        "name": short_cite,
                        "full_text": full_text,
                    })
                seen.add(short_cite)

        # ── 构建渲染上下文 ──
        context = {
            "case_id": case_id,
            "date": datetime.now().strftime("%Y年%m月%d日"),
            "risk_level": cls_text["risk_level"],
            "signature_phrase": cls_text["signature_phrase"],
            "hk_rules_count": 93,
            "us_rules_count": 81,
            "cn_rules_count": 2117,
            "cbl_rules_count": 42,
            "hk_state": hk_data.get("state", "?"),
            "us_state": us_data.get("state", "?"),
            "hk_claims": hk_claims,
            "us_claims": us_claims,
            "cn_claims_count": cn_claims_count,
            "red_zone": risk["red_zone"],
            "grey_zone": risk["grey_zone"],
            "force_suppress_rules": force_suppress,
            "citations": citations,
            "threat_detected": trirail_result.get("fast_path", False),
            "threat_signature": trirail_result.get("threat_signature", ""),
            "threat_level": trirail_result.get("threat_level", ""),
            "description": trirail_result.get("description", ""),
            # ── 版本水印 ──
            "source_hash": get_source_version(),
        }

        # ── 渲染 ──
        if self._template:
            return self._template.render(**context)
        else:
            return self._fallback_render(context)

    def _fallback_render(self, ctx: Dict) -> str:
        """无 Jinja2 时的降级渲染 (纯字符串拼接)"""
        lines = [
            f"# 涉外商事争议跨境处置备忘录",
            f"## 关于「{ctx['case_id']}」跨境法律风险的合规审计备忘录",
            f"",
            f"**日期**: {ctx['date']}",
            f"**风险评级**: {ctx['risk_level']}",
            f"",
            f"## 一、 事实摘要",
            f"本案经三轨对撞，综合风险评级: {ctx['risk_level']}。",
            f"> {ctx['signature_phrase']}",
            f"",
            f"## 二、 法律责任审计",
            f"",
        ]

        if ctx["red_zone"]:
            lines.append("### 紧急纠正事项（红色区域）")
            for item in ctx["red_zone"]:
                lines.append(f"- 【{item['opinion']['action_tone']}】{item['rule_id']}: {item['citation']}")
            lines.append("")

        if ctx["grey_zone"]:
            lines.append("### 预警观察事项（灰色区域）")
            for item in ctx["grey_zone"]:
                lines.append(f"- {item['rule_id']}: {item['citation']}")
            lines.append("")

        if ctx["cn_claims_count"] > 0:
            lines.append(f"**中国成文法主张**: {ctx['cn_claims_count']} 条相关规则触发。")
            lines.append("")

        lines.append("## 三、 执行行动方案")
        lines.append("（请参见完整模板版本 — 建议安装 jinja2 以获得完整输出）")
        lines.append("")
        lines.append("---")
        lines.append(f"*本备忘录由 Juris-Calculus v1.2.0 Action Agent 自动生成*")

        return "\n".join(lines)

    def compile_all(self, trirail_results: Dict[str, Dict],
                    output_dir: str = None) -> Dict[str, str]:
        """
        批量编译所有三轨场景为备忘录。

        Returns:
            {scenario_id: memo_markdown}
        """
        memos = {}
        for sid, result in trirail_results.items():
            memo = self.compile(result, case_id=sid)
            memos[sid] = memo

            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                path = Path(output_dir) / f"{sid}_memo.md"
                with open(path, "w", encoding="utf-8") as f:
                    f.write(memo)

        return memos


# ── 快捷入口 ──
def compile_to_memo(trirail_result: Dict, case_id: str = None) -> str:
    """单次调用快捷函数"""
    compiler = MemoCompiler()
    return compiler.compile(trirail_result, case_id)
