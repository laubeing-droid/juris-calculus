"""
parallax_inference.py — 视差推理：CN ↔ HK 双法域并行推理 + 盲点检测
三层架构之约束层扩展：将中国法的演绎逻辑置于普通法的批判性审查之下
"""
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from compiler_core.types import IRState, LegalFact, LegalClaim, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.config_paths import rules_path as _cp_rules
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml

@dataclass
class RiskWarning:
    cn_claim: str
    hk_claim: str
    cn_confidence: float
    hk_confidence: float
    hk_rebuttal_trigger: str = ""
    message: str = ""
    severity: str = "INFO"  # INFO | WARNING | CRITICAL

@dataclass
class ParallaxResult:
    cn_claims: Dict[str, LegalClaim] = field(default_factory=dict)
    hk_claims: Dict[str, LegalClaim] = field(default_factory=dict)
    risk_warnings: List[RiskWarning] = field(default_factory=list)
    cn_rebuttals: List[dict] = field(default_factory=list)
    hk_rebuttals: List[dict] = field(default_factory=list)

# CN→HK claim mapping: when CN produces X and HK produces Y, what's the relationship?
CLAIM_CONFLICTS = {
    # CN claim → [(conflicting HK claim, risk message)]
    "ContractExists": [
        ("Contract_Void", "中国法视角下合同成立，但普通法下因货品灭失/无对价/卖方无权售卖等隐含抗辩逻辑，该合同存在被认定无效的法律风险"),
    ],
    "BreachEstablished": [
        ("No_PropertyPasses", "中国法认定违约成立，但普通法下因货品未特定化，产权尚未转移——违约责任的范围可能需要重新评估"),
    ],
}

class ParallaxInference:
    """
    视差推理引擎：同一事实集，双法域独立推理，对比盲点。
    
    使用方式:
        pi = ParallaxInference()
        result = pi.run(state, cn_rules_path, hk_rules_path)
        for w in result.risk_warnings:
            print(f"[{w.severity}] {w.message}")
    """

    def __init__(self, cn_rules_path: str = None, 
                 hk_rules_path: str = None):
        self.cn_rules = load_rules_from_yaml(cn_rules_path) if cn_rules_path else []
        self.hk_rules = load_rules_from_yaml(hk_rules_path) if hk_rules_path else []
        self.cn_evaluator = None
        self.hk_evaluator = None

    def run(self, facts: List[LegalFact], domain: LegalDomain = None) -> ParallaxResult:
        """主入口：并行推理 + 对比分析"""
        result = ParallaxResult()
        cfg = DomainConfig(domain=domain or LegalDomain.CIVIL)

        # ─── 链路 A: 中国法 ───
        if self.cn_rules:
            self.cn_evaluator = FixpointEvaluator(self.cn_rules, cfg)
            cn_state = IRState(domain=domain or LegalDomain.CIVIL, jurisdiction="CN")
            for f in facts:
                cn_state.facts[f.id] = f
            cn_state = self.cn_evaluator.evaluate(cn_state)
            result.cn_claims = cn_state.claims
            result.cn_rebuttals = cn_state.rebuttal_log

        # ─── 链路 B: 香港法 ───
        if self.hk_rules:
            self.hk_evaluator = FixpointEvaluator(self.hk_rules, cfg)
            hk_state = IRState(domain=domain or LegalDomain.CIVIL, jurisdiction="HK")
            for f in facts:
                hk_state.facts[f.id] = f
            hk_state = self.hk_evaluator.evaluate(hk_state)
            result.hk_claims = hk_state.claims
            result.hk_rebuttals = hk_state.rebuttal_log

        # ─── 盲点分析 ───
        self._detect_blindspots(result)

        return result

    def _detect_blindspots(self, result: ParallaxResult):
        """对比 CN 和 HK 结果，检测冲突和盲点"""

        # 1. 直接冲突：CN 有主张，HK 有否定
        for cn_claim_id, cn_claim in result.cn_claims.items():
            conflicts = CLAIM_CONFLICTS.get(cn_claim_id, [])
            for hk_conflict_id, msg in conflicts:
                if hk_conflict_id in result.hk_claims:
                    result.risk_warnings.append(RiskWarning(
                        cn_claim=cn_claim_id,
                        hk_claim=hk_conflict_id,
                        cn_confidence=cn_claim.confidence,
                        hk_confidence=result.hk_claims[hk_conflict_id].confidence,
                        message=msg,
                        severity="WARNING"
                    ))

        # 2. HK 反驳了中国法概念：CN claim exists, HK rebutted related concept
        cn_claim_set = set(result.cn_claims.keys())
        hk_rebutted_set = {log.get("claim_id", "") for log in result.hk_rebuttals}
        
        # Map CN claims to HK rebuttal triggers
        for cn_id in cn_claim_set:
            for rb_log in result.hk_rebuttals:
                trigger = rb_log.get("trigger_fact", "")
                claim = rb_log.get("claim_id", "")
                if cn_id and claim:
                    result.risk_warnings.append(RiskWarning(
                        cn_claim=cn_id,
                        hk_claim=claim,
                        cn_confidence=result.cn_claims[cn_id].confidence if cn_id in result.cn_claims else 0,
                        hk_confidence=0.0,
                        hk_rebuttal_trigger=trigger,
                        message=f"中国法下「{cn_id}」成立，但普通法隐含抗辩逻辑因「{trigger}」触发而否定类似主张——建议审查是否存在未被中国法规则捕获的潜在抗辩",
                        severity="INFO"
                    ))

        # 3. HK 有主张但 CN 没有 → 中国法盲区
        hk_only = set(result.hk_claims.keys()) - cn_claim_set
        for hk_id in hk_only:
            hk_claim = result.hk_claims[hk_id]
            if hk_claim.confidence > 0.4:  # 仅报告有信心的
                result.risk_warnings.append(RiskWarning(
                    cn_claim="(无对应结论)",
                    hk_claim=hk_id,
                    cn_confidence=0,
                    hk_confidence=hk_claim.confidence,
                    message=f"普通法下「{hk_id}」成立（置信度 {hk_claim.confidence:.2f}），但中国法规则集未产生对应结论——该概念可能为中国法规则集的覆盖盲区",
                    severity="INFO"
                ))

    def report(self, result: ParallaxResult) -> str:
        """生成人类可读的报告"""
        lines = []
        lines.append("═══ 视差推理报告 ═══")
        lines.append(f"CN 主张: {len(result.cn_claims)} | HK 主张: {len(result.hk_claims)}")
        lines.append(f"CN 反驳: {len(result.cn_rebuttals)} | HK 反驳: {len(result.hk_rebuttals)}")
        lines.append(f"盲点检测: {len(result.risk_warnings)} 项")

        if result.risk_warnings:
            lines.append("")
            lines.append("── 风险警告 ──")
            for w in result.risk_warnings:
                lines.append(f"  [{w.severity}] {w.message}")

        if result.cn_claims:
            lines.append("")
            lines.append("── 中国法结论 ──")
            for c in result.cn_claims.values():
                lines.append(f"  {c.id:40s} conf={c.confidence:.2f}")

        if result.hk_claims:
            lines.append("")
            lines.append("── 香港法结论 ──")
            for c in result.hk_claims.values():
                status = "REBUTTED" if c.confidence == 0 else "OK"
                lines.append(f"  [{status}] {c.id:40s} conf={c.confidence:.2f}")

        return "\n".join(lines)
