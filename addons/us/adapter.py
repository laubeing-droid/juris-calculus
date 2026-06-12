#!/usr/bin/env python3
"""US addon ? UCC/common law adapter with blueprint-backed L0 + court lookup."""
import sys, yaml
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from compiler_core.adapter_base import JurisdictionAdapter
from compiler_core.types import LegalFact, IRState, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.legal_compiler import LegalCompiler
from compiler_core.constraint_validator import ConstraintValidator
from compiler_core.config_paths import us_adapter_path as _cp_adapter, overrides_path as _cp_overrides

class USAdapter(JurisdictionAdapter):
    jurisdiction = "US"
    rules_path = _cp_adapter()
    overrides_path = _cp_overrides("us")

    # Dynamically loaded from US_Adapter.yaml via _load_L0_map()
    _L0_MAP: Dict[str, str] = {}
    _constraint_rules: List[Dict] = []
    _loaded = False

    @classmethod
    def _ensure_loaded(cls):
        """懒加载 US_Adapter.yaml → 自动构建 _L0_MAP + 约束规则"""
        if cls._loaded:
            return
        try:
            adapter_path = Path(__file__).resolve().parents[1] / cls.rules_path
            with open(adapter_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)

            for r in raw.get("rules", []):
                head = r.get("head_claim", "")
                l0 = r.get("l0_primitive", "?")
                if head:
                    cls._L0_MAP[head] = l0
                for p in r.get("premise_atoms", []):
                    if p and p not in cls._L0_MAP:
                        cls._L0_MAP[p] = l0

            # 加载 L0_overrides constraint rules
            override_path = Path(__file__).resolve().parents[1] / cls.overrides_path
            with open(override_path, "r", encoding="utf-8") as f:
                ov = yaml.safe_load(f)
            cls._constraint_rules = ov.get("constraint_rules", [])

            cls._loaded = True
        except Exception as e:
            # 降级: 使用硬编码的最小 _L0_MAP
            cls._L0_MAP = {
                "ContractFormed": "Status",
                "PerformanceDue": "Act",
                "BreachEstablished": "Status",
                "RemedyMonetaryDamages": "Act",
                "Consideration_Provided": "Status",
                "Promissory_Estoppel_Bar": "Defect",
                "Foreseeable_Damages": "Status",
                "Mitigation_Duty": "Act",
                "Fiduciary_Duty": "Power",
                "Ultra_Vires": "Defect",
                "Reasonable_Reliance": "Status",
            }
            cls._loaded = True

    def map_to_L0(self, concept: str) -> str:
        self._ensure_loaded()
        result = self._L0_MAP.get(concept, None)
        if result is not None:
            return result
        try:
            from .us_lookup import l0_primitive_from_term
            bp_result = l0_primitive_from_term(concept)
            if bp_result != "?":
                return bp_result
        except Exception:
            pass
        return "?"

    def validate_against_guardrails(self, state: IRState) -> Dict:
        self._ensure_loaded()
        issues = []
        unmapped = []
        for fid, fact in state.facts.items():
            l0 = self.map_to_L0(fid)
            if l0 == "?":
                unmapped.append(fid)
        if unmapped:
            issues.append(f"无L0映射: {', '.join(unmapped)}")

        # v1.1: 检查 constraint_rules 触发
        triggered_constraints = []
        for cr in self._constraint_rules:
            trigger = cr.get("trigger_fact", "")
            if trigger in state.facts and state.facts[trigger].extraction_confidence > 0:
                # 附加条件检查
                conds = cr.get("additional_conditions", [])
                all_met = True
                for c in conds:
                    if c.startswith("NOT "):
                        neg = c[4:]
                        if neg in state.facts and state.facts[neg].extraction_confidence > 0:
                            all_met = False
                    elif c not in state.facts or state.facts[c].extraction_confidence <= 0:
                        all_met = False
                if all_met:
                    triggered_constraints.append({
                        "id": cr.get("id", ""),
                        "action": cr.get("action", ""),
                        "target": cr.get("target", ""),
                        "new_state": cr.get("new_state", ""),
                        "irreversible": cr.get("irreversible", False),
                    })

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "unmapped_count": len(unmapped),
            "constraints_triggered": triggered_constraints,
        }


# ═══════════════════════════════════════════
# 联邦推理器: HK+US 双域并行
# ═══════════════════════════════════════════

class FederatedReasoner:
    """多法域联邦推理: 输入概念 → 双域并行评估 → 差异报告"""

    def __init__(self):
        self.adapters = {
            "HK": HKAdapter(),
            "US": USAdapter(),
        }

    def run(self, facts: Dict[str, float], jurisdictions: List[str] = None) -> Dict:
        """并行跑指定法域，返回差异报告"""
        if jurisdictions is None:
            jurisdictions = list(self.adapters.keys())

        results = {}
        for jdx in jurisdictions:
            adapter = self.adapters[jdx]
            ev = adapter.load_evaluator()
            s = IRState(domain=LegalDomain.CIVIL, jurisdiction=jdx)

            for fid, conf in facts.items():
                s.facts[fid] = LegalFact(fid, extraction_confidence=conf)

            try:
                res = ev.evaluate(s)
                results[jdx] = {
                    "claims": {c.id: c.confidence for c in res.claims.values() if c.confidence > 0},
                    "state": s.state_tracker.get("Contract_Validity", "?"),
                    "rebuttals": len(s.rebuttal_log),
                    "L0_map": {fid: adapter.map_to_L0(fid) for fid in facts},
                    "guardrail": adapter.validate_against_guardrails(s),
                }
            except Exception as e:
                results[jdx] = {"error": str(e)}

        # 差异检测
        diff = self._compute_diff(results, jurisdictions)
        return {"results": results, "diff": diff}

    def _compute_diff(self, results: Dict, jdxs: List[str]) -> Dict:
        if len(jdxs) < 2:
            return {"message": "至少两个法域才能检测差异"}

        r1, r2 = results.get(jdxs[0], {}), results.get(jdxs[1], {})
        c1 = set(r1.get("claims", {}).keys())
        c2 = set(r2.get("claims", {}).keys())

        return {
            "shared_claims": sorted(c1 & c2),
            f"{jdxs[0]}_only": sorted(c1 - c2),
            f"{jdxs[1]}_only": sorted(c2 - c1),
            "state_divergence": f"{r1.get('state','?')} vs {r2.get('state','?')}" if r1.get("state") != r2.get("state") else "",
        }


# ═══════════════════════════════════════════
# Hadley v Baxendale 视差实验室
# ═══════════════════════════════════════════

def hadley_v_baxendale_test():
    """经典判例: 可预见性损害赔偿原则 — 跨法系视差检测"""
    federated = FederatedReasoner()

    print("═══ Hadley v Baxendale 跨法系视差实验室 ═══")
    print()
    print("案情: 磨坊主Hadley委托承运人Baxendale运送断裂的机轴去Greenwich")
    print("      Baxendale延迟交付 → Hadley的磨坊停工5天 → 索赔利润损失")
    print("      法院裁定: 利润损失不可预见 → 仅赔一般损害赔偿")
    print()

    # 映射到通用事实
    facts = {
        "ContractOfSale_Exists": 1.0,    # 运输合同成立
        "Breach_By_Delay": 1.0,           # 延迟违约
        "Special_Damages_Claimed": 1.0,   # 特殊损害赔偿(利润损失)
        "Damages_Were_Foreseeable": 0.3,  # 可预见性存在争议
        "General_Damages_Sufficient": 1.0, # 一般损害赔偿足够
    }

    result = federated.run(facts, ["HK", "US"])

    print("法域结果:")
    for jdx, data in result["results"].items():
        if "error" in data:
            print(f"  {jdx}: ERROR - {data['error']}")
        else:
            claims = data.get("claims", {})
            l0_map = data.get("L0_map", {})
            print(f"  {jdx}: state={data['state']} | claims={len(claims)} | rebuttals={data['rebuttals']}")
            for cid, conf in claims.items():
                print(f"    {cid}: conf={conf:.2f}")
            print(f"    L0映射: {l0_map}")

    print()
    print("视差报告:")
    diff = result["diff"]
    if diff.get("hk_only"):
        print(f"  HK特有主张: {diff['hk_only']}")
    if diff.get("us_only"):
        print(f"  US特有主张: {diff['us_only']}")
    if diff.get("state_divergence"):
        print(f"  ⚠️ 状态分歧: {diff['state_divergence']}")
    if not diff.get("hk_only") and not diff.get("us_only") and not diff.get("state_divergence"):
        print(f"  ✅ 双法域结论一致 — L0原语层无分歧")