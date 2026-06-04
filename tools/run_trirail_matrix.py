#!/usr/bin/env python3
"""
run_trirail_matrix.py — 三轨对撞机 v1.2.0
══════════════════════════════════════════════════════════════
Tri-Rail Collider: HK × US × PRC 三法域并发对撞

                       ┌──> HK Engine (65 rules) ───────> State_HK
                       │
[Shared Fact Pool] ────┼──> US Engine (81 rules) ───────> State_US
                       │
                       └──> PRC-Alignment Engine ───────> State_PRC
                                (55 constraint rules)

分类维度:
  CHINA_US_COLLISION   — US VALID, PRC FORCE_VOID
  HK_CN_ASYMMETRY       — HK SUPPRESSED, PRC MAPPING_OVERRIDE
  TRI_RESONANCE         — 三轨无冲突
  COMPLEX_PARALLAX      — 其他复杂视差
══════════════════════════════════════════════════════════════
"""

import sys
import json
import copy
from pathlib import Path
from typing import Dict, List, Any
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compiler_core.types import LegalFact, IRState, LegalClaim
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml, CriticalClarityFailure
from compiler_core.domain_config import DomainConfig, LegalDomain
from adapter.prc_adapter import PRCAdapter


# ═══════════════════════════════════════════
# 对撞场景
# ═══════════════════════════════════════════

TRI_SCENARIOS = {
    "TRI_001_UltraVires_DataExport": {
        "description": "HK董事越权 + 美国Cloud Act数据请求 → PRC数据出境阻断",
        "facts": {
            "Director_Acted_UltraVires": 0.88,
            "US_Cloud_Act_Data_Request": 0.95,
            "Cross_Border_Data_Transfer_To_US": 0.92,
            "ContractOfSale_Exists": 0.9,
        }
    },
    "TRI_002_Litigation_Discovery": {
        "description": "美国诉前证据开示 + 关联公司资产混同 → 横向否认+数据阻断",
        "facts": {
            "US_Pre_Trial_Discovery": 0.91,
            "Affiliated_Companies_Asset_Confusion": 0.85,
            "Contract_Validity": 0.9,
        }
    },
    "TRI_003_OFAC_Sanction_Deadlock": {
        "description": "OFAC制裁 vs 反外国制裁法第12条强制对撞",
        "facts": {
            "OFAC_Sanctions_Imposed": 0.93,
            "US_Secondary_Sanction_Enforcement": 0.88,
            "ContractOfSale_Exists": 0.9,
            "Consideration_Provided": 0.85,
        }
    },
    "TRI_004_Plea_Bargaining_CrossBorder": {
        "description": "美国辩诉交易 → PRC认罪认罚从宽映射 + 数据出境",
        "facts": {
            "US_Plea_Bargaining_Act": 0.90,
            "Wrongful_Omission": 0.78,
            "Cross_Border_Data_Transfer_To_US": 0.85,
        }
    },
    "TRI_005_Chapter11_Director_Conflict": {
        "description": "US Ch11 + HK越权 → 破产重组 vs 权力抑制 三维对撞",
        "facts": {
            "Chapter11_Filed": 0.95,
            "Bankruptcy_Petition_Filed": 1.0,
            "Director_Acted_UltraVires": 0.88,
            "Consideration_Provided": 0.9,
            "ContractOfSale_Exists": 0.9,
        }
    },
    "TRI_006_Factoring_CrossBorder": {
        "description": "保理合同独立成章 vs US应收账款转让",
        "facts": {
            "Factoring_Account_Receivable_Transfer": 0.92,
            "Contract_Validity": 0.9,
            "Consideration_Provided": 0.85,
        }
    },
    "TRI_007_Crypto_Transaction_Conflict": {
        "description": "US加密货币交易 vs PRC强制禁止",
        "facts": {
            "Cryptocurrency_Transaction": 0.91,
            "Contract_Validity": 0.9,
            "Consideration_Provided": 0.85,
        }
    },
    "TRI_008_VIE_Structure_Review": {
        "description": "VIE架构 vs 外商投资负面清单穿透审查",
        "facts": {
            "US_Long_Arm_Jurisdiction_Asserted": 0.87,
            "Affiliated_Companies_Asset_Confusion": 0.82,
            "Cross_Border_Data_Transfer_To_US": 0.85,
        }
    },
    "TRI_009_Algorithm_Filing_Block": {
        "description": "算法未备案 + 数据出境 → PRC双阻断",
        "facts": {
            "CN_Deployment_Without_Filing": 0.88,
            "Cross_Border_Data_Transfer_To_US": 0.85,
        }
    },
    "TRI_010_AtWill_Employment_Conflict": {
        "description": "美国任意雇佣 vs PRC劳动合同法解雇保护",
        "facts": {
            "At_Will_Employment": 0.90,
            "Director_Acted_UltraVires": 0.75,
        }
    },
}


# ═══════════════════════════════════════════
# 分类器
# ═══════════════════════════════════════════

def classify_tri_state(
    hk_state: IRState,
    us_state: IRState,
    prc_state: Dict[str, Dict[str, Any]]
) -> str:
    """
    四分类判定 — 三轨并发结果。

    底层接口消费:
      - IRState.claims: Dict[str, LegalClaim]
      - IRState.state_tracker: Dict[str, str]
      - PRC State: Dict[rule_id, {type, status, ...}]
    """
    # 提取 HK/US 的终态签名
    hk_claims_set = set(hk_state.claims.keys())
    us_claims_set = set(us_state.claims.keys())

    # 有效性判定 — 基于 state_tracker
    hk_tracker_vals = set(hk_state.state_tracker.values())
    us_tracker_vals = set(us_state.state_tracker.values())

    hk_is_active = len(hk_claims_set) > 0
    us_is_active = len(us_claims_set) > 0
    hk_is_suppressed = "SUPPRESSED" in hk_tracker_vals

    # PRC 覆写提取
    has_prc_force_void = any(
        v.get("type") == "FORCE_VOID" for v in prc_state.values()
    )
    has_prc_force_suppress = any(
        v.get("type") == "FORCE_SUPPRESS" for v in prc_state.values()
    )
    has_prc_override = any(
        v.get("type") == "MAPPING_OVERRIDE" for v in prc_state.values()
    )
    has_prc_any = len(prc_state) > 0

    # 🎯 CHINA_US_COLLISION: PRC 强制否决 (不论US是否触发)
    # 关键修正: US引擎无匹配规则不代表"静默"，PRC的FORCE_VOID本身就是
    # 对"美国法域可能认可的行为"在中国法域下的强制性否决
    if has_prc_force_void or has_prc_force_suppress:
        if us_is_active or hk_is_active:
            # US/HK 有输出 → 直接冲突
            return "CHINA_US_COLLISION"
        else:
            # 双方均无规则触发，但PRC已表态 → 中国法域单边否决
            return "CHINA_US_COLLISION"

    # ⚠️ HK_CN_ASYMMETRY: HK 抑制 + PRC 有重构映射 (无FORCE_VOID)
    if hk_is_suppressed and has_prc_override:
        return "HK_CN_ASYMMETRY"

    # 🎯 TRI_RESONANCE: 三方均无冲突，无PRC覆写
    if not has_prc_any:
        return "TRI_RESONANCE"

    # 🌐 COMPLEX_PARALLAX: 仅有 MAPPING_OVERRIDE 但无状态冲突
    if has_prc_override:
        return "HK_CN_ASYMMETRY"

    return "COMPLEX_PARALLAX"


# ═══════════════════════════════════════════
# 三轨对撞引擎
# ═══════════════════════════════════════════

class TriRailCollider:
    """三轨并发对撞引擎"""

    def __init__(self):
        base = Path(__file__).resolve().parents[1]

        # ── HK 引擎 ──
        hk_rules_path = base / "configs" / "hk" / "rules.yaml"
        hk_overrides_path = base / "configs" / "L0_overrides_hk.yaml"
        hk_rules = load_rules_from_yaml(str(hk_rules_path))
        self.hk_engine = FixpointEvaluator(
            hk_rules, DomainConfig(domain=LegalDomain.CIVIL),
            overrides_path=str(hk_overrides_path)
        )

        # ── US 引擎 ──
        us_rules_path = base / "configs" / "en_US" / "US_Adapter.yaml"
        us_overrides_path = base / "configs" / "en_US" / "L0_overrides_us.yaml"
        us_rules = load_rules_from_yaml(str(us_rules_path))
        self.us_engine = FixpointEvaluator(
            us_rules, DomainConfig(domain=LegalDomain.CIVIL),
            overrides_path=str(us_overrides_path)
        )

        # ── PRC 约束引擎 ──
        self.prc_engine = PRCAdapter()

        print(f"[TriRail] HK={len(hk_rules)} rules | US={len(us_rules)} rules | PRC={len(self.prc_engine.constraint_rules)} constraints")

    def build_fact_state(self, facts_dict: Dict[str, float]) -> Dict[str, LegalFact]:
        """将 {fact_id: confidence} → {fact_id: LegalFact}"""
        return {
            k: LegalFact(id=k, description=k, extraction_confidence=v)
            for k, v in facts_dict.items()
        }

    def run_scenario(self, scenario_id: str, scenario: Dict) -> Dict:
        """运行单个三轨场景"""

        # 防御性深拷贝 — 三轨独立内存空间
        facts_hk = self.build_fact_state(scenario["facts"])
        facts_us = self.build_fact_state(scenario["facts"])
        facts_prc = self.build_fact_state(scenario["facts"])

        # ── 三轨并发 ──
        hk_state = IRState(facts=facts_hk)
        try:
            hk_state = self.hk_engine.evaluate(hk_state)
        except CriticalClarityFailure:
            pass

        us_state = IRState(facts=facts_us)
        try:
            us_state = self.us_engine.evaluate(us_state)
        except CriticalClarityFailure:
            pass

        prc_state = self.prc_engine.execute_prc_first_override(facts_prc)

        # ── 分类 ──
        classification = classify_tri_state(hk_state, us_state, prc_state)

        # ── 终端状态提取 ──
        hk_terminal = hk_state.state_tracker.get("Contract_Validity", "?")
        us_terminal = us_state.state_tracker.get("Contract_Validity", "?")
        if not hk_terminal:
            hk_terminal = "VALID" if hk_state.claims else "?"
        if not us_terminal:
            us_terminal = "VALID" if us_state.claims else "?"

        return {
            "scenario_id": scenario_id,
            "description": scenario["description"],
            "classification": classification,
            "hk": {
                "state": hk_terminal,
                "claims": list(hk_state.claims.keys()),
                "rebuttals": len(hk_state.rebuttal_log),
                "state_tracker": dict(hk_state.state_tracker),
            },
            "us": {
                "state": us_terminal,
                "claims": list(us_state.claims.keys()),
                "rebuttals": len(us_state.rebuttal_log),
                "state_tracker": dict(us_state.state_tracker),
            },
            "prc": {
                "overrides_count": len(prc_state),
                "force_void": [
                    rid for rid, v in prc_state.items()
                    if v.get("type") == "FORCE_VOID"
                ],
                "force_suppress": [
                    rid for rid, v in prc_state.items()
                    if v.get("type") == "FORCE_SUPPRESS"
                ],
                "mapping_override": [
                    rid for rid, v in prc_state.items()
                    if v.get("type") == "MAPPING_OVERRIDE"
                ],
            },
        }

    def run_all(self) -> Dict:
        """运行全部三轨场景"""
        print(f"\n[TriRail] Running {len(TRI_SCENARIOS)} cross-border scenarios...\n")

        results = {}
        for sid, scenario in TRI_SCENARIOS.items():
            result = self.run_scenario(sid, scenario)
            results[sid] = result

            # 实时输出
            cls = result["classification"]
            tag = {
                "CHINA_US_COLLISION": "[COLL!]",
                "HK_CN_ASYMMETRY": "[ASYMM]",
                "TRI_RESONANCE": "[RESON]",
                "COMPLEX_PARALLAX": "[PARLX]",
            }.get(cls, "[?????]")

            hk_c = len(result["hk"]["claims"])
            us_c = len(result["us"]["claims"])
            prc_c = result["prc"]["overrides_count"]
            print(f"  {tag} {sid}: HK={result['hk']['state']}({hk_c}c) US={result['us']['state']}({us_c}c) PRC={prc_c}ov")

        return results

    def generate_report(self, results: Dict) -> str:
        """生成三轨对撞报告"""
        lines = [
            "=" * 70,
            "  Tri-Rail Collider Report — v1.2.0",
            "  HK x US x PRC Cross-Jurisdictional Collision Matrix",
            "=" * 70,
            "",
        ]

        class_counts = Counter(r["classification"] for r in results.values())
        lines.append(f"Total scenarios: {len(results)}")
        for cls, count in class_counts.most_common():
            lines.append(f"  {cls}: {count}")
        lines.append("")

        # 逐场景
        for sid, r in results.items():
            cls = r["classification"]
            lines.append(f"--- {sid} [{cls}] ---")
            lines.append(f"  {r['description']}")
            lines.append(f"  HK: {r['hk']['state']} claims={r['hk']['claims'][:3]}")
            lines.append(f"  US: {r['us']['state']} claims={r['us']['claims'][:3]}")
            if r["prc"]["force_void"]:
                lines.append(f"  PRC FORCE_VOID: {r['prc']['force_void']}")
            if r["prc"]["force_suppress"]:
                lines.append(f"  PRC FORCE_SUPPRESS: {r['prc']['force_suppress']}")
            if r["prc"]["mapping_override"]:
                lines.append(f"  PRC MAPPING_OVERRIDE: {r['prc']['mapping_override']}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  Tri-Rail Collider v1.2.0")
    print("  HK x US x PRC Cross-Jurisdictional Concurrency")
    print("=" * 60)

    collider = TriRailCollider()

    # 运行全部场景
    results = collider.run_all()

    # 保存 JSON
    output_dir = Path(__file__).resolve().parents[1] / "configs" / "prc_us_alignment"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "trirail_matrix_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    import os
    print(f"\n[OK] Tri-Rail Matrix -> {json_path} ({os.path.getsize(json_path):,} bytes)")

    # 保存报告
    report = collider.generate_report(results)
    report_path = Path(__file__).resolve().parents[1] / "reports" / "trirail_report_v1.2.0.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[OK] Report -> {report_path}")
    print(report)
