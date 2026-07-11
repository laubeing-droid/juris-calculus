#!/usr/bin/env python3
"""
run_trirail_matrix.py — 三轨对撞机 v1.2.0
══════════════════════════════════════════════════════════════
Tri-Rail Collider: HK × US × PRC 三法域并发对撞

                       ┌──> HK engineering track ───────> State_HK
                       │
[Shared Fact Pool] ────┼──> US engineering track ───────> State_US
                       │
                       └──> PRC-Alignment Engine ───────> State_PRC
                                (runtime inventory)

分类维度:
  CHINA_US_COLLISION   — US VALID, PRC FORCE_VOID
  HK_CN_ASYMMETRY       — HK SUPPRESSED, PRC MAPPING_OVERRIDE
  TRI_RESONANCE         — 三轨无冲突
  COMPLEX_PARALLAX      — 其他复杂视差
══════════════════════════════════════════════════════════════
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Any
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compiler_core.types import LegalFact, IRState, LegalClaim
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml, CriticalClarityFailure
from compiler_core.domain_config import DomainConfig, LegalDomain
from compiler_core.prc_collision_engine import PRCCollisionEngine
from compiler_core.proof_tree import ProofTree
from compiler_core.rule_packs import RulePackRegistry, sha256_file

# ── 威胁拦截器 (Gemini审计: 下沉至TriRailCollider主路径最前端) ──
from tools.distill_jurisdiction import FastPathInterceptor


# ═══════════════════════════════════════════
# 对撞场景
# ═══════════════════════════════════════════

TRI_SCENARIOS = {
    "TRI_001_UltraVires_DataExport": {
        "description": "HK董事越权 + 美国Cloud Act数据请求 → PRC数据出境阻断",
        "context": "cross_border",  # 标记为跨境场景
        "facts": {
            "Director_Acted_UltraVires": 0.88,
            "US_Cloud_Act_Data_Request": 0.95,
            "Cross_Border_Data_Transfer_To_US": 0.92,
            "ContractOfSale_Exists": 0.9,
            "Cross_Border_Context": 1.0,
        }
    },
    "TRI_002_Litigation_Discovery": {
        "description": "美国诉前证据开示 + 关联公司资产混同 → 横向否认+数据阻断",
        "context": "cross_border",
        "facts": {
            "US_Pre_Trial_Discovery": 0.91,
            "Affiliated_Companies_Asset_Confusion": 0.85,
            "Contract_Validity": 0.9,
            "Cross_Border_Context": 1.0,
        }
    },
    "TRI_003_OFAC_Sanction_Deadlock": {
        "description": "OFAC制裁 vs 反外国制裁法第12条强制对撞",
        "context": "cross_border",
        "facts": {
            "OFAC_Sanctions_Imposed": 0.93,
            "US_Secondary_Sanction_Enforcement": 0.88,
            "ContractOfSale_Exists": 0.9,
            "Consideration_Provided": 0.85,
            "Cross_Border_Context": 1.0,
        }
    },
    "TRI_004_Plea_Bargaining_CrossBorder": {
        "description": "美国辩诉交易 → PRC认罪认罚从宽映射 + 数据出境",
        "context": "cross_border",
        "facts": {
            "US_Plea_Bargaining_Act": 0.90,
            "Wrongful_Omission": 0.78,
            "Cross_Border_Data_Transfer_To_US": 0.85,
            "Cross_Border_Context": 1.0,
        }
    },
    "TRI_005_Chapter11_Director_Conflict": {
        "description": "US Ch11 + HK越权 → 破产重组 vs 权力抑制 三维对撞",
        "context": "cross_border",
        "facts": {
            "Chapter11_Filed": 0.95,
            "Bankruptcy_Petition_Filed": 1.0,
            "Director_Acted_UltraVires": 0.88,
            "Consideration_Provided": 0.9,
            "ContractOfSale_Exists": 0.9,
            "Cross_Border_Context": 1.0,
        }
    },
    "TRI_006_Factoring_CrossBorder": {
        "description": "保理合同独立成章 vs US应收账款转让",
        "context": "cross_border",
        "facts": {
            "Factoring_Account_Receivable_Transfer": 0.92,
            "Contract_Validity": 0.9,
            "Consideration_Provided": 0.85,
            "Cross_Border_Context": 1.0,
        }
    },
    "TRI_007_Crypto_Transaction_Conflict": {
        "description": "US加密货币交易 vs PRC强制禁止",
        "context": "cross_border",
        "facts": {
            "Cryptocurrency_Transaction": 0.91,
            "Contract_Validity": 0.9,
            "Consideration_Provided": 0.85,
            "Cross_Border_Context": 1.0,
        }
    },
    "TRI_008_VIE_Structure_Review": {
        "description": "VIE架构 vs 外商投资负面清单穿透审查",
        "context": "cross_border",
        "facts": {
            "US_Long_Arm_Jurisdiction_Asserted": 0.87,
            "Affiliated_Companies_Asset_Confusion": 0.82,
            "Cross_Border_Data_Transfer_To_US": 0.85,
            "Cross_Border_Context": 1.0,
        }
    },
    "TRI_009_Algorithm_Filing_Block": {
        "description": "算法未备案 + 数据出境 → PRC双阻断",
        "context": "cross_border",
        "facts": {
            "CN_Deployment_Without_Filing": 0.88,
            "Cross_Border_Data_Transfer_To_US": 0.85,
            "Cross_Border_Context": 1.0,
        }
    },
    "TRI_010_AtWill_Employment_Conflict": {
        "description": "美国任意雇佣 vs PRC劳动合同法解雇保护",
        "context": "cross_border",
        "facts": {
            "At_Will_Employment": 0.90,
            "Director_Acted_UltraVires": 0.75,
            "Cross_Border_Context": 1.0,
        }
    },
    # ── 负对照: 纯境内场景，不应触发 FORCE_VOID ──
    "TRI_011_Pure_Domestic_CN": {
        "description": "纯中国大陆境内保理合同——不应触发任何跨境阻断",
        "context": "domestic",
        "facts": {
            "Factoring_Account_Receivable_Transfer": 0.92,
            "Contract_Validity": 0.9,
            "Consideration_Provided": 0.85,
            # 注意: 不注入 Cross_Border_Context
        }
    },
    # ── CN 桥接验收: 港美事实 → 中国法规则触发 ──
    "TRI_012_CN_Bridge_Verification": {
        "description": "跨境合同违约 + 损害赔偿 → CN 正式准入规则触发验证",
        "context": "cross_border",
        "facts": {
            "ContractOfSale_Exists": 0.95,
            "Breach_Established": 0.92,
            "Buyer_FailsToPay": 0.90,
            "Damages_Awarded": 0.88,
            "Loss_Occurred": 0.85,
            "Goods_Defective": 0.80,
            "Cross_Border_Context": 1.0,
        }
    },
}


# ═══════════════════════════════════════════
# 分类器
# ═══════════════════════════════════════════

def classify_tri_state(
    hk_state: IRState,
    us_state: IRState,
    prc_tree: ProofTree,
    blocking_action_types: Dict[str, str],
) -> str:
    """
    四分类判定 — 三轨并发结果。

    底层接口消费:
      - IRState.claims: Dict[str, LegalClaim]
      - IRState.state_tracker: Dict[str, str]
      - PRC ProofTree: 已触发阻断规则与中国法/SPC 推理节点
      - blocking_action_types: PRC 引擎公开的规则 ID → 动作类型只读映射
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

    # 仅按 PRCCollisionEngine 实际触发的规则分类，禁止从输出文案反推动作。
    triggered_actions = {
        blocking_action_types.get(rule_id, "")
        for rule_id in prc_tree.blocked_claims
    }
    has_prc_force_void = "FORCE_VOID" in triggered_actions
    has_prc_force_suppress = "FORCE_SUPPRESS" in triggered_actions
    has_prc_override = "MAPPING_OVERRIDE" in triggered_actions
    has_prc_any = bool(prc_tree.blocked_claims)

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

        # ── HK 引擎 (Cap 26 + Extended Cap 32/622/571/4A) ──
        hk_rules_path = base / "configs" / "hk" / "rules.yaml"
        hk_extended_path = base / "configs" / "hk" / "extended_rules.yaml"
        hk_overrides_path = base / "configs" / "L0_overrides_hk.yaml"

        # 加载 Cap 26 基础规则
        hk_rules = load_rules_from_yaml(str(hk_rules_path))
        # 追加扩展规则 (Cap 32/622/571/4A)
        hk_extended = load_rules_from_yaml(str(hk_extended_path))
        hk_rules += hk_extended
        self.hk_rules = hk_rules
        self.hk_engine = FixpointEvaluator(
            hk_rules, DomainConfig(domain=LegalDomain.CIVIL),
            overrides_path=str(hk_overrides_path)
        )

        # ── US 引擎 ──
        us_rules_path = base / "configs" / "en_US" / "US_Adapter.yaml"
        us_overrides_path = base / "configs" / "en_US" / "L0_overrides_us.yaml"
        us_rules = load_rules_from_yaml(str(us_rules_path))
        self.us_rules = us_rules
        self.us_engine = FixpointEvaluator(
            us_rules, DomainConfig(domain=LegalDomain.CIVIL),
            overrides_path=str(us_overrides_path)
        )

        # ── PRC 约束引擎：当前唯一正式实现为 PRCCollisionEngine ──
        self.prc_engine = PRCCollisionEngine()

        # ── 威胁拦截器 (Gemini审计: First Gatekeeper) ──
        self.threat_interceptor = FastPathInterceptor()

        self.rule_inventory = {
            "HK": self._summarize_rules(hk_rules),
            "US": self._summarize_rules(us_rules),
            "PRC": self.prc_engine.rule_inventory,
        }
        registry = RulePackRegistry(base / "configs")
        self.pack_digests = {
            "HK": registry.verify("hk-legacy-corpus").content_digest,
            "US": registry.verify("us-l0-adapter-legacy-corpus").content_digest,
            "PRC_CN": registry.verify("cn-legacy-corpus").content_digest,
            "PRC_CBL": sha256_file(base / "configs" / "prc_us_alignment" / "blocking_rules.yaml"),
            "PRC_SPC": sha256_file(base / "configs" / "prc_us_alignment" / "spc_rules.yaml"),
        }

    @staticmethod
    def _summarize_rules(rules: List) -> Dict[str, int]:
        """按加载器写入的候选标记统计语料与正式准入规则。"""
        candidate = sum(
            1 for rule in rules
            if getattr(rule, "data_quality", "") == "CANDIDATE_ONLY"
        )
        return {
            "corpus_total": len(rules),
            "reasoning_eligible_total": len(rules) - candidate,
            "candidate_only_total": candidate,
        }

    def build_fact_state(self, facts_dict: Dict[str, float]) -> Dict[str, LegalFact]:
        """将 {fact_id: confidence} → {fact_id: LegalFact}"""
        return {
            k: LegalFact(id=k, description=k, extraction_confidence=v)
            for k, v in facts_dict.items()
        }

    @staticmethod
    def _evaluate_track(evaluator: FixpointEvaluator, facts: Dict[str, LegalFact]) -> IRState:
        """执行单法域轨道；清晰度熔断时只保留高置信部分状态。"""
        state = IRState(facts=facts)
        try:
            return evaluator.evaluate(state)
        except CriticalClarityFailure as exc:
            partial = getattr(exc, "partial_state", None)
            if partial is None:
                return state
            partial.claims = {
                key: claim for key, claim in partial.claims.items()
                if claim.confidence > 0.8
            }
            return partial

    @staticmethod
    def _terminal_state(state: IRState) -> str:
        """提取合同终态；无显式状态时只按是否产生主张给出兼容值。"""
        terminal = state.state_tracker.get("Contract_Validity", "?")
        return terminal or ("VALID" if state.claims else "?")

    def _split_blocking_actions(self, tree: ProofTree) -> Dict[str, List[str]]:
        """把已触发阻断规则按引擎声明的动作类型确定性分组。"""
        groups = {"FORCE_VOID": [], "FORCE_SUPPRESS": [], "MAPPING_OVERRIDE": []}
        actions = self.prc_engine.blocking_action_types
        for rule_id in sorted(tree.blocked_claims):
            action = actions.get(rule_id, "")
            if action in groups:
                groups[action].append(rule_id)
        return groups

    @staticmethod
    def _used_rules(*states_or_tree: Any) -> List[str]:
        """汇总真实规则 ID；缺失规则标识的节点不参与审计清单。"""
        used = set()
        for item in states_or_tree:
            if isinstance(item, IRState):
                used.update(str(rule_id) for rule_id in item.rules_applied)
            elif isinstance(item, ProofTree):
                used.update(
                    node.rule_id for node in item.nodes.values()
                    if node.rule_id
                )
        return sorted(used)

    @staticmethod
    def _source_snapshots(*states_or_tree: Any) -> List[str]:
        """汇总实际产出节点携带的来源锚，不使用描述文本补齐。"""
        anchors = set()
        for item in states_or_tree:
            if isinstance(item, IRState):
                anchors.update(
                    claim.source_anchor for claim in item.claims.values()
                    if claim.source_anchor
                )
            elif isinstance(item, ProofTree):
                anchors.update(
                    node.source_anchor for node in item.nodes.values()
                    if node.source_anchor
                )
        return sorted(anchors)

    def run_scenario(self, scenario_id: str, scenario: Dict) -> Dict:
        """运行单个三轨场景"""

        facts_raw = scenario.get("facts", {})
        if not isinstance(facts_raw, dict) or any(
            not isinstance(key, str)
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0.0 <= float(value) <= 1.0
            for key, value in facts_raw.items()
        ):
            raise ValueError("facts must be a {string: confidence} mapping with confidence in [0, 1]")

        # ═══ 哨兵: 威胁签名预检 (Gemini审计: First Gatekeeper) ═══
        fact_names = sorted(facts_raw)
        threat_hit = self.threat_interceptor.intercept(fact_names)
        if threat_hit:
            target_rule = str(threat_hit.get("target_rule", ""))
            return {
                "scenario_id": scenario_id,
                "description": scenario.get("description", ""),
                "classification": "CHINA_US_COLLISION",
                "hk": {"state": "?", "claims": [], "claims_count": 0},
                "us": {"state": "?", "claims": [], "claims_count": 0},
                "prc": {
                    "overrides_count": 1,
                    "force_void": [target_rule] if target_rule else [],
                    "force_suppress": [],
                    "mapping_override": [],
                    "spc_claims_count": 0,
                    "cn_claims_count": 0,
                    "cn_rules_total": self.rule_inventory["PRC"]["tracks"]["cn"]["corpus_total"],
                    "blocked_claims": [target_rule] if target_rule else [],
                    "bridge_health": {"status": "NOT_RUN"},
                },
                "fast_path": True,
                "threat_signature": threat_hit.get("signature_id", ""),
                "threat_level": threat_hit.get("threat_level", ""),
                "rule_inventory": self.rule_inventory,
                "pack_digests": self.pack_digests,
                "lsc_boundary": {
                    "result_status": "review_only_result",
                    "used_fact_keys": fact_names,
                    "used_rule_ids": [target_rule] if target_rule else [],
                    "source_snapshot_ids": [],
                    "provenance": {"summary_only": True, "source": "deterministic threat interceptor"},
                    "taint": ["FAST_PATH_INTERCEPT", "UNVERIFIED_INPUT_FACTS"],
                    "review_required": True,
                    "formal_kernel_used": False,
                    "renderer_output_kind": "machine_packet",
                    "execution_mode": "ENGINEERING_HARNESS",
                    "pack_digests": self.pack_digests,
                },
            }

        # 三轨分别构建事实对象，防止任一 evaluator 修改其他轨输入。
        hk_state = self._evaluate_track(self.hk_engine, self.build_fact_state(facts_raw))
        us_state = self._evaluate_track(self.us_engine, self.build_fact_state(facts_raw))
        prc_tree = self.prc_engine.run(self.build_fact_state(facts_raw))

        # ── 分类 ──
        classification = classify_tri_state(
            hk_state,
            us_state,
            prc_tree,
            self.prc_engine.blocking_action_types,
        )
        blocking = self._split_blocking_actions(prc_tree)
        used_rules = self._used_rules(hk_state, us_state, prc_tree)
        source_snapshots = self._source_snapshots(hk_state, us_state, prc_tree)

        return {
            "scenario_id": scenario_id,
            "description": scenario["description"],
            "classification": classification,
            "hk": {
                "state": self._terminal_state(hk_state),
                "claims": sorted(hk_state.claims),
                "rebuttals": len(hk_state.rebuttal_log),
                "state_tracker": dict(sorted(hk_state.state_tracker.items())),
            },
            "us": {
                "state": self._terminal_state(us_state),
                "claims": sorted(us_state.claims),
                "rebuttals": len(us_state.rebuttal_log),
                "state_tracker": dict(sorted(us_state.state_tracker.items())),
            },
            "prc": {
                "overrides_count": len(prc_tree.blocked_claims),
                "force_void": blocking["FORCE_VOID"],
                "force_suppress": blocking["FORCE_SUPPRESS"],
                "mapping_override": blocking["MAPPING_OVERRIDE"],
                "spc_claims_count": len(prc_tree.spc_tendencies),
                "cn_claims_count": len(prc_tree.cn_claims),
                "cn_rules_total": self.rule_inventory["PRC"]["tracks"]["cn"]["corpus_total"],
                "blocked_claims": sorted(prc_tree.blocked_claims),
                "bridge_health": dict(sorted(prc_tree.bridge_health.items())),
            },
            "fast_path": False,
            "rule_inventory": self.rule_inventory,
            "pack_digests": self.pack_digests,
            "lsc_boundary": {
                "result_status": "review_only_result",
                "used_fact_keys": fact_names,
                "used_rule_ids": used_rules,
                "source_snapshot_ids": source_snapshots,
                "provenance": {"summary_only": True, "source": "TriRailCollider"},
                "taint": ["ENGINEERING_HARNESS", "NO_REASONING_READY_TRIRAIL_PACKS", "UNVERIFIED_INPUT_FACTS"],
                "review_required": True,
                "formal_kernel_used": False,
                "renderer_output_kind": "machine_packet",
                "execution_mode": "ENGINEERING_HARNESS",
                "pack_digests": self.pack_digests,
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
            cn_c = result["prc"].get("cn_claims_count", 0)
            spc_c = result["prc"].get("spc_claims_count", 0)
            print(f"  {tag} {sid}: HK={result['hk']['state']}({hk_c}c) US={result['us']['state']}({us_c}c) PRC={prc_c}ov CN={cn_c}c SPC={spc_c}c")

        return results

    def generate_report(self, results: Dict) -> str:
        """生成三轨对撞报告"""
        hk_count = self.rule_inventory["HK"]["reasoning_eligible_total"]
        us_count = self.rule_inventory["US"]["reasoning_eligible_total"]
        prc_tracks = self.rule_inventory["PRC"]["tracks"]
        lines = [
            "=" * 70,
            "  Tri-Rail Collider Report — v1.2.0",
            (
                f"  HK ({hk_count}) x US ({us_count}) x PRC "
                f"(CBL={prc_tracks['blocking']['reasoning_eligible_total']} + "
                f"SPC={prc_tracks['spc']['reasoning_eligible_total']} + "
                f"CN={prc_tracks['cn']['reasoning_eligible_total']})"
            ),
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
            cn_c = r["prc"].get("cn_claims_count", 0)
            spc_c = r["prc"].get("spc_claims_count", 0)
            if cn_c or spc_c:
                lines.append(f"  PRC CN={cn_c}c SPC={spc_c}c (total={r['prc'].get('cn_rules_total', 0)} rules)")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)


# ═══════════════════════════════════════════
# 热力图生成
# ═══════════════════════════════════════════

def generate_heatmap_html(results: Dict, output_path: Path):
    """生成三轨交互式热力图 HTML"""
    color_map = {
        "CHINA_US_COLLISION": "#ef4444",
        "HK_CN_ASYMMETRY":   "#f59e0b",
        "TRI_RESONANCE":     "#22c55e",
        "COMPLEX_PARALLAX":  "#3b82f6",
    }
    tag_map = {
        "CHINA_US_COLLISION": "COLLISION",
        "HK_CN_ASYMMETRY":   "ASYMMETRY",
        "TRI_RESONANCE":     "RESONANCE",
        "COMPLEX_PARALLAX":  "PARALLAX",
    }

    cards = []
    for sid, r in results.items():
        cls = r["classification"]
        color = color_map.get(cls, "#6b7280")
        tag = tag_map.get(cls, "?")

        cards.append(f"""
        <div class="card" style="border-left:5px solid {color}">
            <span class="tag tag-{tag}">{cls}</span>
            <div class="case-id">{sid}</div>
            <div class="desc">{r['description']}</div>
            <div class="grid-3">
                <div class="rail-box hk">
                    <div class="rail-label">HK</div>
                    <div class="rail-state">{r['hk']['state']}</div>
                    <div class="rail-claims">{', '.join(r['hk']['claims'][:2]) or 'silent'}</div>
                </div>
                <div class="rail-box us">
                    <div class="rail-label">US</div>
                    <div class="rail-state">{r['us']['state']}</div>
                    <div class="rail-claims">{', '.join(r['us']['claims'][:2]) or 'silent'}</div>
                </div>
                <div class="rail-box prc">
                    <div class="rail-label">PRC</div>
                    <div class="rail-state">{r['prc']['overrides_count']} ov</div>
                    <div class="rail-claims">{', '.join((r['prc']['force_void'] + r['prc']['force_suppress'])[:2]) or 'none'}</div>
                </div>
            </div>
        </div>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>juris-calculus v1.2.0 — Tri-Rail Collision Heatmap</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: "Sarasa Gothic SC", "Microsoft YaHei", sans-serif; background:#0f172a; color:#e2e8f0; padding:40px; min-height:100vh; }}
h1 {{ color:#f8fafc; font-size:24px; margin-bottom:4px; }}
.subtitle {{ color:#94a3b8; font-size:14px; margin-bottom:24px; }}
.stats {{ display:flex; gap:16px; margin-bottom:32px; flex-wrap:wrap; }}
.stat {{ background:#1e293b; border:1px solid #334155; border-radius:8px; padding:14px 20px; }}
.stat .n {{ font-size:28px; font-weight:700; }}
.stat .l {{ font-size:11px; color:#94a3b8; margin-top:4px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(360px,1fr)); gap:16px; }}
.card {{ background:#1e293b; border-radius:8px; padding:18px; transition:all 0.2s; }}
.card:hover {{ transform:translateY(-2px); box-shadow:0 12px 24px rgba(0,0,0,0.4); }}
.tag {{ font-size:10px; font-weight:700; padding:2px 8px; border-radius:4px; display:inline-block; margin-bottom:8px; }}
.tag-COLLISION {{ background:#fee2e2; color:#991b1b; }}
.tag-ASYMMETRY {{ background:#fef9c3; color:#854d0e; }}
.tag-RESONANCE {{ background:#dcfce7; color:#166534; }}
.tag-PARALLAX {{ background:#dbeafe; color:#1e40af; }}
.case-id {{ font-size:16px; font-weight:700; color:#f1f5f9; margin-bottom:4px; }}
.desc {{ font-size:12px; color:#94a3b8; margin-bottom:12px; }}
.grid-3 {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; }}
.rail-box {{ background:#0f172a; border-radius:6px; padding:10px; text-align:center; }}
.rail-label {{ font-size:10px; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:4px; }}
.rail-state {{ font-size:14px; font-weight:700; }}
.rail-claims {{ font-size:11px; color:#64748b; margin-top:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.hk .rail-state {{ color:#22c55e; }}
.us .rail-state {{ color:#3b82f6; }}
.prc .rail-state {{ color:#f59e0b; }}
.footer {{ margin-top:40px; padding-top:20px; border-top:1px solid #1e293b; font-size:12px; color:#475569; }}
</style>
</head>
<body>
<h1>juris-calculus v1.2.0 — Tri-Rail Cross-Jurisdictional Collision Matrix</h1>
<div class="subtitle">HK Engine x US Engine x PRC-First Alignment Engine | {len(results)} Scenarios</div>
<div class="stats">
  {_build_stats(results)}
</div>
<div class="grid">
{''.join(cards)}
</div>
<div class="footer">juris-calculus v1.2.0-TriRail | Laupinco & WorkBuddy | deterministic harness output</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def _build_stats(results: Dict) -> str:
    from collections import Counter
    c = Counter(r["classification"] for r in results.values())
    stats_html = ""
    for cls, label, color in [
        ("CHINA_US_COLLISION", "COLLISION", "#ef4444"),
        ("HK_CN_ASYMMETRY", "ASYMMETRY", "#f59e0b"),
        ("TRI_RESONANCE", "RESONANCE", "#22c55e"),
        ("COMPLEX_PARALLAX", "PARALLAX", "#3b82f6"),
    ]:
        n = c.get(cls, 0)
        stats_html += f'<div class="stat"><div class="n" style="color:{color}">{n}</div><div class="l">{label}</div></div>'
    return stats_html


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the deterministic Tri-Rail matrix harness")
    parser.add_argument("--open", action="store_true", help="Open the generated HTML report in a browser")
    args = parser.parse_args()
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

    # 生成热力图
    html_path = report_path.parent / "trirail_heatmap_v1.2.0.html"
    generate_heatmap_html(results, html_path)
    print(f"[OK] Heatmap -> {html_path} ({os.path.getsize(html_path):,} bytes)")

    if args.open:
        import webbrowser
        webbrowser.open(str(html_path))
