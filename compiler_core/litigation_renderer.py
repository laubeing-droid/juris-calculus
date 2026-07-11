"""旧诉讼报告数据契约与纯Markdown渲染；不得重新运行求值器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HornStep:
    """审计事件已记录的一步Horn派生。"""

    iteration: int
    rule_id: str
    premises: list[str]
    derived: list[str]


@dataclass
class ArgumentRecord:
    """审计图中的论证节点。"""

    argument_id: str
    conclusion: str
    support_facts: list[str]
    rule_id: str


@dataclass
class AttackRecord:
    """审计图中的攻击边。"""

    source: str
    target: str
    kind: str
    reason: str


@dataclass
class ClaimAnalysis:
    """既有规范结果派生的单项展示数据。"""

    claim_id: str
    status: str
    label: str
    horn_derivation: List[HornStep] = field(default_factory=list)
    attacks_against: List[str] = field(default_factory=list)
    attacks_from: List[str] = field(default_factory=list)
    minimal_support: List[str] = field(default_factory=list)
    minimal_rebuttal: List[Dict[str, Any]] = field(default_factory=list)
    missing_evidence: List[Dict[str, Any]] = field(default_factory=list)
    certificate: Optional[Dict[str, Any]] = None
    fail_closed_note: Optional[str] = None


@dataclass
class LitigationReport:
    """旧报告展示契约；正式v3 renderer将在CanonicalResult上构建。"""

    case_id: str
    schema_version: str = "litigation-v1"
    facts: List[str] = field(default_factory=list)
    rules_applied: List[str] = field(default_factory=list)
    horn_closure: List[str] = field(default_factory=list)
    arguments: List[ArgumentRecord] = field(default_factory=list)
    attacks: List[AttackRecord] = field(default_factory=list)
    grounded_summary: Dict[str, Any] = field(default_factory=dict)
    claim_analyses: List[ClaimAnalysis] = field(default_factory=list)
    impact_analysis: Optional[Dict[str, Any]] = None
    truncation_warning: Optional[str] = None
    fail_closed_boundary: Dict[str, bool] = field(default_factory=dict)


class LitigationChainRenderer:
    """只渲染调用方已提供的报告数据；本类不存在evaluate入口。"""

    def render_markdown(self, report: LitigationReport) -> str:
        """确定性渲染旧报告结构，不读取规则、事实源或求值器。"""

        summary = report.grounded_summary
        lines = [
            f"# Litigation Reasoning Report: {report.case_id}",
            "",
            "## Case Facts",
            "",
            *[f"- {fact}" for fact in report.facts],
            "",
            "## Rules Applied",
            "",
            *[f"- {rule_id}" for rule_id in report.rules_applied],
            "",
            "## Grounded Summary",
            "",
            f"- Accepted (IN): {summary.get('accepted_count', 0)}",
            f"- Rejected (OUT): {summary.get('rejected_count', 0)}",
            f"- Undecided: {summary.get('undecided_count', 0)}",
            "",
        ]
        if report.truncation_warning:
            lines.append(f"> **Warning**: {report.truncation_warning}")
        for analysis in report.claim_analyses:
            lines.extend([
                f"## Claim: {analysis.claim_id}",
                "",
                f"**Status**: {analysis.status}  ",
                f"**Label**: {analysis.label}  ",
            ])
            if analysis.minimal_support:
                lines.append(f"**Minimal Support**: {', '.join(analysis.minimal_support)}")
            if analysis.attacks_against:
                lines.append(f"**Attacked By**: {', '.join(analysis.attacks_against)}")
            if analysis.certificate:
                lines.append(
                    f"**Certificate**: {analysis.certificate.get('label', 'NONE')} "
                    f"(verifiable: {analysis.certificate.get('verifiable', False)})"
                )
            lines.append("")
        if report.fail_closed_boundary:
            lines.extend([
                "## Safety Boundary",
                f"- Horn truncated: {report.fail_closed_boundary.get('horn_truncated', False)}",
                f"- Grounded truncated: {report.fail_closed_boundary.get('grounded_truncated', False)}",
                f"- No uncertainty upgrade: {report.fail_closed_boundary.get('no_uncertainty_upgrade', False)}",
            ])
        return "\n".join(lines)
