#!/usr/bin/env python3
"""v2.0 Adversarial Pipeline - Layer 4 MAX mode triangular counter-check.

Three roles: Reasoner (Horn), Auditor (blueprint rules), Verifier (gate scripts).
Only activated in ThinkMode.MAX; failed checks produce UNVERIFIED trust downgrade.
"""
from enum import Enum
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from compiler_core.criminal_complexity import audit_criminal_claims

class ThinkMode(str, Enum):
    QUICK_SCAN = "QUICK_SCAN"
    STANDARD = "STANDARD"
    MAX = "MAX"

class RoleVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"

@dataclass
class AdversarialResult:
    role: str
    verdict: RoleVerdict
    issues: List[str] = field(default_factory=list)
    audit_trail: List[str] = field(default_factory=list)
    requires_human_review: bool = False

class AdversarialPipeline:

    def run_contract_audit(self, claims, contract_type="general"):
        """Enhanced audit: verify contract claims against review elements from blueprint."""
        issues = []
        try:
            import json
            from compiler_core.config_paths import blueprint_path
            bp = json.load(open(blueprint_path(), "r", encoding="utf-8"))
            elements = bp.get("contract_review_elements", [])
            if elements:
                for claim in claims:
                    desc = claim.get("description", "")
                    if "合同" in desc or "contract" in desc.lower():
                        for elem in elements[:8]:
                            if elem.get("element", "") not in desc:
                                issues.append(f"Contract element missing: {elem.get('element','?')}")
        except Exception:
            pass
        return issues

    def __init__(self, mode: ThinkMode = ThinkMode.STANDARD):
        self.mode = mode
        self.failures: List[AdversarialResult] = []

    @property
    def is_active(self) -> bool:
        return self.mode == ThinkMode.MAX

    def run_reasoner(self, claims: List[Dict], rules_applied: List[str]) -> AdversarialResult:
        issues = []
        if not claims:
            issues.append("No claims produced after Horn closure")
        if not rules_applied:
            issues.append("No rules triggered")
        audit = [f"Horn closure: {len(claims)} claims, {len(rules_applied)} rules"]
        return AdversarialResult(role="reasoner",
                                 verdict=RoleVerdict.FAIL if issues else RoleVerdict.PASS,
                                 issues=issues, audit_trail=audit)

    def run_auditor(self, claims: List[Dict], blueprint_contracts: List[Dict]) -> AdversarialResult:
        issues = []
        for claim in claims:
            if claim.get("confidence", 0) < 0.2:
                issues.append(f"Low-confidence claim: {claim.get('id', '?')}")
        audit = [f"Blueprint audit: checked {len(claims)} claims against {len(blueprint_contracts)} contracts"]
        ver = RoleVerdict.FAIL if len(issues) > len(claims) * 0.5 else (RoleVerdict.INCONCLUSIVE if issues else RoleVerdict.PASS)
        return AdversarialResult(role="auditor", verdict=ver, issues=issues, audit_trail=audit)

    def run_criminal_complexity_audit(self, case_facts, claims: Optional[List[Dict]] = None) -> AdversarialResult:
        """Audit MultiJustice-style criminal cases for actor/charge/law mixing."""
        report = audit_criminal_claims(case_facts, claims or [])
        complexity = report["complexity"]
        audit = [
            "Criminal complexity: "
            f"{complexity['scenario_id']} {complexity['scenario_label']}, "
            f"defendants={complexity['defendant_count']}, charges={complexity['charge_count']}"
        ]
        issues = report["issues"]
        if not complexity.get("route_tag"):
            return AdversarialResult(role="criminal_auditor", verdict=RoleVerdict.INCONCLUSIVE,
                                     issues=issues, audit_trail=audit)
        return AdversarialResult(role="criminal_auditor",
                                 verdict=RoleVerdict.FAIL if issues else RoleVerdict.PASS,
                                 issues=issues, audit_trail=audit,
                                 requires_human_review=bool(issues))

    def run_verifier(self, claims: List[Dict], gate_results: List[Dict]) -> AdversarialResult:
        issues = []
        for g in gate_results:
            if g.get("level") == "ERROR":
                issues.append(f"Gate {g.get('gate_id', '?')} ERROR: {g.get('reason', '?')}")
        audit = [f"Gate verification: {len(gate_results)} gates, {len(issues)} violations"]
        return AdversarialResult(role="verifier",
                                 verdict=RoleVerdict.FAIL if issues else RoleVerdict.PASS,
                                 issues=issues, audit_trail=audit)

# Methodology references from unified-legal-ai-cn agents
AGENT_METHODOLOGY = {
    "DocAnalyzer": {"capabilities": ["文书解析（原 DocAnalyzer）", "证据分析（原 EvidenceAnalyzer 合并）", "知识增强（内联：evidence-evaluation + legal-document-summarization）"], "steps": ["1. **文档接入**：检查完整性，判定是否需要 OCR", "2. **信息抽取**：逐页解析，提取结构化字段", "3. **证据评估**：三性递进审查 + 证明力评估", "4. **文书分类**：匹配文档类型标签", "5. **标识生成**：确定案号或生成替代案件标识"]},
    "IssueIdentifier": {"capabilities": ["争议焦点系统提取", "法律关系定性分析", "对抗视角盲点补充", "知识增强（内联：conflict-resolution + argument-chain-construction）", "优先级分层排序"], "steps": ["1. **材料审阅**：读入 DocAnalyzer 产出", "2. **焦点提取**：逐段标注争议陈述", "3. **关系定性**：确定法律关系类型", "4. **对抗检验**：三方视角模拟对抗，挖掘隐藏争点", "5. **论证构建**：为每个焦点搭建论证链"]},
    "Researcher": {"capabilities": ["精准法条检索", "构成要件逐项拆解", "类案检索与裁判口径归纳", "知识增强（内联：case-retrieval + legal-interpretation-argument）", "适用路径择优"], "steps": ["1. **推理内核检测**：调用 `tools/list` 检查 `get_citation` 是否可用", "2. 查询词生成：将争议焦点转换为精准法律检索词", "3. 多源并发检索：JC 调 get_citation；Prompt 调 multi-search/yuandian/zhihe", "4. 规范解构：逐条拆解法条的假定条件、行为模式和法律后果", "5. 效力校验：JC 自动校验规则版本；Prompt 手动核查法条现行状态"]},
    "Strategist": {"capabilities": ["SWOT 四维态势分析", "多套策略方案", "概率化预判", "知识增强（内联：legal-risk-assessment）", "资源投入建议"], "steps": ["1. **推理内核检测**：调用 `tools/list` 检查 `trirail_collide`", "2. 态势汇总：汇聚 DocAnalyzer/IssueIdentifier/Researcher 产出", "3. 对抗推演：三轮递进式模拟对抗（原告/被告/法官）", "4. 方案构建：进攻/防守/折中三套路径", "5. 风险标注：每套方案附带风险评估矩阵"]},
    "Writer": {"capabilities": ["多类型文书覆盖（原 Writer）", "论证体系构建", "报告生成（原 Reporter 合并）", "知识增强（内联：legal-document-formatting + multi-document-summarization）", "双格式输出"], "steps": ["1. **推理内核检测**：调用 `tools/list` 检查 `generate_memo`", "2. 需求确认：文书类型、受众、提交时限", "3. 材料汇聚：案件事实 + 争议焦点 + 法律依据 + 策略方案", "4. 模板匹配：对应文书类型的结构框架", "5. 对抗推演：对抗性文书执行多方视角推演"]},
}
