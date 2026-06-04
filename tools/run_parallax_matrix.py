#!/usr/bin/env python3
"""
run_parallax_matrix.py — 港美跨法系分歧矩阵 v1.1.0
══════════════════════════════════════════════════════════════
65 条 HK Horn 规则 × 81 条 US 动态算子 → 5,265 对撞场景

三类视差特征:
  🎯 COINCIDENCE  — State_HK == State_US  (逻辑共振，安全路径)
  ⚠️  ASYMMETRY    — 一方 Defined, 另一方 Silent (套利空间)
  💥 COLLISION     — VALID vs VOID/VOIDABLE (硬核冲突，合规雷区)

输出:
  configs/en_US/hk_us_divergence_matrix.json  (完整对撞数据)
  reports/divergence_heatmap.html             (交互式热力图)
══════════════════════════════════════════════════════════════
"""

import sys
import json
import yaml
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compiler_core.constraint_validator import ConstraintValidator
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml, CriticalClarityFailure
from compiler_core.types import LegalFact, IRState
from compiler_core.domain_config import DomainConfig, LegalDomain


# ═══════════════════════════════════════════
# 对撞结果分类
# ═══════════════════════════════════════════

@dataclass
class CollisionResult:
    """单次对撞的完整结果"""
    pair_id: str                    # "HK-R3 × US-Automatic_stay"
    hk_rule_id: str
    us_rule_id: str
    hk_head_claim: str
    us_head_claim: str
    us_domain: str
    us_l0: str
    
    # 共享事实
    shared_facts: Dict[str, float]
    fact_count: int
    
    # 香港引擎输出
    hk_claims: List[str]            # head_claims produced
    hk_state: str                   # terminal state
    hk_rebuttals: int
    
    # 美国引擎输出
    us_claims: List[str]
    us_state: str
    us_rebuttals: int
    
    # 分歧分类
    parallax_type: str              # COINCIDENCE | ASYMMETRY | COLLISION
    parallax_detail: str            # 人类可读解释
    
    # L0 溯源
    hk_l0_trace: Dict[str, str]
    us_l0_trace: Dict[str, str]


# ═══════════════════════════════════════════
# 事实生成器
# ═══════════════════════════════════════════

# 桥接事实——在港美双法域都合理的领域上下文
BRIDGE_FACTS = {
    "contract": {
        "Contract_Validity": 0.9,
        "Consideration_Provided": 0.85,
        "Parties_Capacity_OK": 0.9,
        "No_Duress_Undue_Influence": 0.8,
    },
    "bankruptcy": {
        "Company_In_Financial_Distress": 0.9,
    },
    "fraud": {
        "Material_Fact_Concealed": 0.8,
        "Reliance_On_Concealment": 0.75,
    },
}


def generate_pair_facts(hk_rule: Dict, us_rule: Dict) -> Dict[str, float]:
    """
    为一对规则生成共享事实集。
    
    策略: 域名匹配 → 模拟跨境交叉主体纠纷。
    不仅注入双方前提，还注入冲突种子事实（如 Director_Acted_UltraVires、
    Fraud_Alleged、Bankruptcy_Petition_Filed 等），触发跨法系状态机。
    """
    facts = {}
    
    # 基础: HK/US 前提
    for atom in hk_rule.get("premise_atoms", []):
        facts[atom] = 1.0
    for atom in us_rule.get("premise_atoms", []):
        facts[atom] = 1.0
    
    # 领域桥接
    us_domain = us_rule.get("l1_domain", "Formation")
    domain_key = us_domain.lower().split("/")[0]
    bridge_map = {
        "formation": "contract",
        "validity": "contract",
        "performance": "contract",
        "breach": "contract",
        "remedy": "contract",
    }
    bridge_group = bridge_map.get(domain_key, "contract")
    for k, v in BRIDGE_FACTS.get(bridge_group, {}).items():
        if k not in facts:
            facts[k] = v
    
    # ═══ 冲突注入 — 模拟跨境张力 ═══
    # US Bankruptcy 域: 注入破产事实（触发 AUTOMATIC_STAY + DIP 约束）
    if "bankruptcy" in us_rule.get("id", "").lower() or us_rule.get("l0_primitive") == "Power":
        facts["Bankruptcy_Petition_Filed"] = 1.0
        facts["Chapter11_Filed"] = 0.9
        facts["AutomaticStay_InEffect"] = 1.0
        facts["Director_Acted_UltraVires"] = 0.85
    
    # US Criminal/Prosecutorial 域: 注入欺诈事实
    if any(kw in us_rule.get("id", "").lower() for kw in ["fraud", "acquittal", "jeopardy", "charge", "indictment", "grand_jury", "plea"]):
        facts["Fraud_Alleged"] = 0.8
        facts["Wrongful_Omission"] = 0.75
        facts["DOJ_Investigation_Active"] = 0.9
    
    # US Remedy/Validity 域: 注入跨境合同效力冲突种子
    if us_domain in ("Remedy/Sanction", "Validity"):
        facts["Buyer_FailsToPay"] = 0.9
        facts["Goods_Defective"] = 0.6
        facts["Consideration_Provided"] = 1.0
    
    return facts


# ═══════════════════════════════════════════
# 视差分类器 v2 — 刺穿伪共振
# ═══════════════════════════════════════════

# 有效状态 vs 无效/抑制状态
VALID_STATES = {"VALID", "ENFORCEABLE", "CONFIRMED", "ESTABLISHED"}
VOID_STATES = {"VOID", "VOIDABLE", "INVALID", "SUPPRESSED", "BARRED", "FINAL", "EXPIRED", "TERMINATED", "SILENT"}


def classify_parallax(hk_result: Dict, us_result: Dict) -> Tuple[str, str]:
    """
    三类视差特征判定 v2 — 刺穿伪共振。
    
    核心改进:
      1. 比较 claims 产出（不仅是 terminal state 名称）
      2. SUPPRESSED vs VALID → ASYMMETRY (不再是 COINCIDENCE)
      3. 一方产 claims 另一方静默 → ASYMMETRY
      4. 双方都产 claims 但内容不同 → 检查状态差异
    
    🎯 COINCIDENCE: 双方状态相同 AND 产出相同类型的 claims
    ⚠️  ASYMMETRY: 一方活跃一方静默, OR 状态类型不对称
    💥 COLLISION:  VALID vs VOID/VOIDABLE 硬核冲突
    """
    hk_state = hk_result.get("state", "?")
    us_state = us_result.get("state", "?")
    hk_claims = hk_result.get("claims", [])
    us_claims = us_result.get("claims", [])
    
    def normalize(s: str) -> str:
        s = s.upper().strip()
        if s in ("?", "", "UNKNOWN"):
            return "SILENT"
        return s
    
    ns_hk = normalize(hk_state)
    ns_us = normalize(us_state)
    
    hk_active = len(hk_claims) > 0
    us_active = len(us_claims) > 0
    
    # ── 先判断状态类型 ──
    hk_is_valid = ns_hk in VALID_STATES
    us_is_valid = ns_us in VALID_STATES
    hk_is_void = ns_hk in VOID_STATES
    us_is_void = ns_us in VOID_STATES
    
    # 💥 COLLISION: VALID vs VOID/SUPPRESSED 硬核冲突
    if (hk_is_valid and us_is_void) or (us_is_valid and hk_is_void):
        detail_parts = []
        if hk_is_valid and us_is_void:
            detail_parts.append(f"HK 认定有效({hk_state})，US 认定无效/抑制({us_state})")
        else:
            detail_parts.append(f"US 认定有效({us_state})，HK 认定无效/抑制({hk_state})")
        if hk_claims:
            detail_parts.append(f"HK claims: {', '.join(hk_claims[:3])}")
        if us_claims:
            detail_parts.append(f"US claims: {', '.join(us_claims[:3])}")
        return ("COLLISION", " | ".join(detail_parts))
    
    # ⚠️ ASYMMETRY: 一方活跃一方静默（不同时SILENT）
    if hk_active and not us_active:
        detail = f"HK 产出 {len(hk_claims)} 条主张 ({', '.join(hk_claims[:3])})，US 无输出"
        if ns_hk != ns_us:
            detail += f" | 状态: HK={hk_state} vs US={us_state}"
        return ("ASYMMETRY", detail)
    if us_active and not hk_active:
        detail = f"US 产出 {len(us_claims)} 条主张 ({', '.join(us_claims[:3])})，HK 无输出"
        if ns_hk != ns_us:
            detail += f" | 状态: HK={hk_state} vs US={us_state}"
        return ("ASYMMETRY", detail)
    
    # ⚠️ ASYMMETRY: 双方都活跃但状态不同(SILENT vs 非SILENT 或 状态类型不同)
    if hk_active and us_active:
        if ns_hk != ns_us:
            # SUPPRESSED vs VALID → 即使都在有效范畴，也是不对称
            if (ns_hk == "SUPPRESSED" and ns_us in VALID_STATES) or \
               (ns_us == "SUPPRESSED" and ns_hk in VALID_STATES):
                return ("ASYMMETRY", 
                        f"HK={hk_state}({len(hk_claims)} claims) vs US={us_state}({len(us_claims)} claims) — 一方抑制一方有效")
            
            # 其他状态差异
            hk_claim_strs = set(hk_claims)
            us_claim_strs = set(us_claims)
            only_hk = hk_claim_strs - us_claim_strs
            only_us = us_claim_strs - hk_claim_strs
            shared = hk_claim_strs & us_claim_strs
            
            detail = f"HK={hk_state}({len(hk_claims)} claims) vs US={us_state}({len(us_claims)} claims)"
            if shared:
                detail += f" | 共享: {len(shared)}"
            if only_hk:
                detail += f" | HK独有: {', '.join(list(only_hk)[:3])}"
            if only_us:
                detail += f" | US独有: {', '.join(list(only_us)[:3])}"
            return ("ASYMMETRY", detail)
        
        # 双方状态相同，但产出的 claims 不同 → check claim overlap
        hk_claim_strs = set(hk_claims)
        us_claim_strs = set(us_claims)
        if hk_claim_strs != us_claim_strs:
            only_hk = hk_claim_strs - us_claim_strs
            only_us = us_claim_strs - hk_claim_strs
            if only_hk or only_us:
                return ("ASYMMETRY", 
                        f"双方状态={hk_state} | HK独有claims: {len(only_hk)} | US独有claims: {len(only_us)}")
    
    # 🎯 COINCIDENCE: 双方完全静默 OR 双方状态相同且claims集合相同
    if not hk_active and not us_active:
        return ("COINCIDENCE", "双方均静默 — 无冲突")
    
    if ns_hk == ns_us:
        return ("COINCIDENCE", f"双方均={hk_state}，claims对齐 — 逻辑共振")
    
    # Fallback: 任何剩余的不对称
    return ("ASYMMETRY", f"HK={hk_state} vs US={us_state} — 未分类不对称")


# ═══════════════════════════════════════════
# 批量对撞引擎
# ═══════════════════════════════════════════

class ParallaxMatrixEngine:
    """
    65×81 批量对撞引擎。
    
    两套完全独立的异构计算空间:
      - $HK_Space$: FixpointEvaluator(configs/hk/rules.yaml, L0_overrides_hk.yaml)
      - $US_Space$: FixpointEvaluator(configs/en_US/US_Adapter.yaml, L0_overrides_us.yaml)
    
    对同一共享事实流 (Shared Fact Stream) 进行解耦并发观测。
    """
    
    def __init__(self):
        # 加载规则
        hk_path = str(Path(__file__).resolve().parents[1] / "configs" / "hk" / "rules.yaml")
        us_path = str(Path(__file__).resolve().parents[1] / "configs" / "en_US" / "US_Adapter.yaml")
        us_overrides = str(Path(__file__).resolve().parents[1] / "configs" / "en_US" / "L0_overrides_us.yaml")
        hk_overrides = str(Path(__file__).resolve().parents[1] / "configs" / "L0_overrides_hk.yaml")
        
        with open(hk_path, "r", encoding="utf-8") as f:
            self.hk_data = yaml.safe_load(f)
        with open(us_path, "r", encoding="utf-8") as f:
            self.us_data = yaml.safe_load(f)
        
        self.hk_rules = self.hk_data.get("rules", [])
        self.us_rules = self.us_data.get("rules", [])
        
        # 预创建共享引擎实例（避免5,184次YAML重载）
        print(f"[初始化] 加载 HK 规则引擎...")
        hk_rules_parsed = load_rules_from_yaml(hk_path)
        self.hk_engine = FixpointEvaluator(
            hk_rules_parsed, DomainConfig(domain=LegalDomain.CIVIL),
            overrides_path=hk_overrides
        )
        
        print(f"[初始化] 加载 US 规则引擎...")
        us_rules_parsed = load_rules_from_yaml(us_path)
        self.us_engine = FixpointEvaluator(
            us_rules_parsed, DomainConfig(domain=LegalDomain.CIVIL),
            overrides_path=us_overrides
        )
        
        print(f"[初始化] HK {len(self.hk_rules)} 条规则 | US {len(self.us_rules)} 条规则")
        print(f"         理论对撞次数: {len(self.hk_rules)} × {len(self.us_rules)} = {len(self.hk_rules) * len(self.us_rules)}")
    
    def run_single_pair(self, hk_rule: Dict, us_rule: Dict) -> CollisionResult:
        """运行单次对撞 — 复用共享引擎实例"""
        facts = generate_pair_facts(hk_rule, us_rule)
        
        # 构建独立 IRState（引擎复用，状态隔离）
        hk_fact_objs = {}
        for k, v in facts.items():
            hk_fact_objs[k] = LegalFact(id=k, description=k, extraction_confidence=v)
        
        us_fact_objs = {}
        for k, v in facts.items():
            us_fact_objs[k] = LegalFact(id=k, description=k, extraction_confidence=v)
        
        hk_state = IRState(facts=hk_fact_objs)
        us_state = IRState(facts=us_fact_objs)
        
        # 重置约束校验器振荡计数
        self.hk_engine.constraint_validator._modification_counts.clear()
        self.us_engine.constraint_validator._modification_counts.clear()
        
        # 独立不动点迭代 (优雅降级)
        hk_error = False
        try:
            hk_result = self.hk_engine.evaluate(hk_state)
        except (CriticalClarityFailure, Exception):
            hk_result = hk_state
            hk_error = True
        
        us_error = False
        try:
            us_result = self.us_engine.evaluate(us_state)
        except (CriticalClarityFailure, Exception):
            us_result = us_state
            us_error = True
        
        # 提取输出
        hk_claims_list = [cid for cid, c in hk_result.claims.items() if c.confidence > 0]
        us_claims_list = [cid for cid, c in us_result.claims.items() if c.confidence > 0]
        
        # 确定终端状态 — 从 state_tracker 提取最相关条目
        hk_terminal = self._extract_terminal_state(hk_result.state_tracker, hk_claims_list)
        us_terminal = self._extract_terminal_state(us_result.state_tracker, us_claims_list)
        
        # L0 溯源
        hk_l0 = {}
        us_l0 = {}
        
        pair_id = f"{hk_rule['id']} × {us_rule['id']}"
        
        # 分类
        result_hk = {"state": hk_terminal, "claims": hk_claims_list}
        result_us = {"state": us_terminal, "claims": us_claims_list}
        
        if hk_error or us_error:
            ptype = "ERROR"
            pdetail = f"Engine halt: HK_error={hk_error}, US_error={us_error}"
        else:
            ptype, pdetail = classify_parallax(result_hk, result_us)
        
        return CollisionResult(
            pair_id=pair_id,
            hk_rule_id=hk_rule["id"],
            us_rule_id=us_rule["id"],
            hk_head_claim=hk_rule.get("head_claim", ""),
            us_head_claim=us_rule.get("head_claim", ""),
            us_domain=us_rule.get("l1_domain", ""),
            us_l0=us_rule.get("l0_primitive", ""),
            shared_facts=facts,
            fact_count=len(facts),
            hk_claims=hk_claims_list,
            hk_state=hk_terminal,
            hk_rebuttals=len(hk_result.rebuttal_log),
            us_claims=us_claims_list,
            us_state=us_terminal,
            us_rebuttals=len(us_result.rebuttal_log),
            parallax_type=ptype,
            parallax_detail=pdetail,
            hk_l0_trace=hk_l0,
            us_l0_trace=us_l0,
        )
    
    def _extract_terminal_state(self, state_tracker: Dict, claims: List) -> str:
        """
        从 state_tracker 中提取最有意义的终端状态。
        优先级: Contract_Validity > 第一个非空条目 > default
        """
        if not state_tracker and not claims:
            return "?"
        if not state_tracker:
            return "VALID" if claims else "?"
        
        # 优先找 Contract_Validity
        if "Contract_Validity" in state_tracker:
            return state_tracker["Contract_Validity"]
        
        # 找 SUPPRESSED（跨法系关键状态）
        for k, v in state_tracker.items():
            if v == "SUPPRESSED":
                return v
        
        # 找 VOID/VOIDABLE
        for k, v in state_tracker.items():
            if v in ("VOID", "VOIDABLE"):
                return v
        
        # 第一个非空条目
        for k, v in state_tracker.items():
            if v:
                return v
        
        return "VALID" if claims else "?"
    
    def run_matrix(self, progress_callback=None) -> List[CollisionResult]:
        """运行完整的 65×81 对撞矩阵"""
        results = []
        total = len(self.hk_rules) * len(self.us_rules)
        
        for i, hk_rule in enumerate(self.hk_rules):
            for j, us_rule in enumerate(self.us_rules):
                try:
                    result = self.run_single_pair(hk_rule, us_rule)
                    results.append(result)
                except Exception as e:
                    # 降级: 记录失败对
                    results.append(CollisionResult(
                        pair_id=f"{hk_rule['id']} × {us_rule['id']}",
                        hk_rule_id=hk_rule["id"],
                        us_rule_id=us_rule["id"],
                        hk_head_claim=hk_rule.get("head_claim", ""),
                        us_head_claim=us_rule.get("head_claim", ""),
                        us_domain=us_rule.get("l1_domain", ""),
                        us_l0=us_rule.get("l0_primitive", ""),
                        shared_facts={},
                        fact_count=0,
                        hk_claims=[], hk_state="ERROR", hk_rebuttals=0,
                        us_claims=[], us_state="ERROR", us_rebuttals=0,
                        parallax_type="ERROR",
                        parallax_detail=str(e)[:200],
                        hk_l0_trace={}, us_l0_trace={},
                    ))
                
                idx = i * len(self.us_rules) + j + 1
                if progress_callback and idx % 500 == 0:
                    progress_callback(idx, total)
        
        return results
    
    def generate_summary(self, results: List[CollisionResult]) -> Dict:
        """生成统计摘要"""
        type_counts = Counter(r.parallax_type for r in results)
        domain_cross = defaultdict(lambda: defaultdict(int))
        
        for r in results:
            domain_cross[r.parallax_type][r.us_domain] += 1
        
        # COLLISION 详情 (Top 20)
        collisions = [r for r in results if r.parallax_type == "COLLISION"]
        asymmetries = [r for r in results if r.parallax_type == "ASYMMETRY"]
        
        return {
            "total_pairs": len(results),
            "type_distribution": dict(type_counts),
            "domain_cross_tabulation": {k: dict(v) for k, v in domain_cross.items()},
            "collisions_top20": [
                {
                    "pair": r.pair_id,
                    "hk_state": r.hk_state,
                    "us_state": r.us_state,
                    "detail": r.parallax_detail,
                    "us_domain": r.us_domain,
                    "hk_claims": r.hk_claims[:5],
                    "us_claims": r.us_claims[:5],
                }
                for r in sorted(collisions, key=lambda x: len(x.shared_facts), reverse=True)[:20]
            ],
            "asymmetries_top20": [
                {
                    "pair": r.pair_id,
                    "hk_state": r.hk_state,
                    "us_state": r.us_state,
                    "detail": r.parallax_detail,
                    "us_domain": r.us_domain,
                }
                for r in sorted(asymmetries, key=lambda x: len(x.shared_facts), reverse=True)[:20]
            ],
        }
    
    def generate_heatmap_html(self, results: List[CollisionResult], summary: Dict) -> str:
        """生成交互式热力图 HTML"""
        # 构建矩阵: rows=HK rules, cols=US rules
        hk_ids = [r["id"] for r in self.hk_rules]
        us_ids = [r["id"] for r in self.us_rules]
        
        # 索引映射
        matrix = {}
        for r in results:
            key = (r.hk_rule_id, r.us_rule_id)
            matrix[key] = r
        
        # 颜色映射
        color_map = {
            "COINCIDENCE": "#22c55e",  # green
            "ASYMMETRY":   "#f59e0b",  # amber
            "COLLISION":   "#ef4444",  # red
            "ERROR":       "#6b7280",  # gray
        }
        label_map = {
            "COINCIDENCE": "🎯",
            "ASYMMETRY":   "⚠️",
            "COLLISION":   "💥",
            "ERROR":       "❌",
        }
        
        # 构建 HTML 单元格
        cells_js = []
        for i, hk_id in enumerate(hk_ids):
            row_cells = []
            for j, us_id in enumerate(us_ids):
                r = matrix.get((hk_id, us_id))
                if r:
                    emoji = label_map.get(r.parallax_type, "?")
                    color = color_map.get(r.parallax_type, "#6b7280")
                    tooltip = f"{r.pair_id}|HK={r.hk_state}|US={r.us_state}|{r.parallax_detail}"
                    row_cells.append(f'{{c:"{color}",t:"{tooltip}",e:"{emoji}"}}')
                else:
                    row_cells.append(f'{{c:"#374151",t:"N/A",e:""}}')
            cells_js.append("[" + ",".join(row_cells) + "]")
        
        cells_str = ",\n        ".join(cells_js)
        
        # US 域名分组
        us_domain_groups = defaultdict(list)
        for j, us_rule in enumerate(self.us_rules):
            us_domain_groups[us_rule.get("l1_domain", "Other")].append(j)
        
        domain_colors_js = json.dumps({d: color_map.get("COINCIDENCE", "#22c55e") if d in ("Formation","Performance") else 
                                          color_map.get("ASYMMETRY", "#f59e0b") if d in ("Validity","Breach") else
                                          color_map.get("COLLISION", "#ef4444") for d in us_domain_groups})
        
        domain_ranges_js = json.dumps({d: [min(idx), max(idx)] for d, idx in us_domain_groups.items()})
        
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>juris-calculus v1.1.0 — HK×US Divergence Matrix</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ 
  font-family: "Sarasa Gothic SC", "Microsoft YaHei", sans-serif;
  background: #0a0a0f; color: #e5e7eb;
  min-height: 100vh;
}}
.header {{
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  padding: 32px 48px; border-bottom: 1px solid #1e293b;
}}
.header h1 {{ font-size: 24px; font-weight: 600; color: #f8fafc; }}
.header .subtitle {{ font-size: 14px; color: #94a3b8; margin-top: 8px; }}
.stats {{
  display: flex; gap: 24px; padding: 20px 48px;
  background: #111118; border-bottom: 1px solid #1e293b;
}}
.stat-card {{
  background: #1a1a2e; border: 1px solid #2d2d44; border-radius: 8px;
  padding: 16px 24px; min-width: 140px;
}}
.stat-card .value {{ font-size: 28px; font-weight: 700; }}
.stat-card .label {{ font-size: 12px; color: #94a3b8; margin-top: 4px; }}
.stat-card.coincidence .value {{ color: #22c55e; }}
.stat-card.asymmetry .value {{ color: #f59e0b; }}
.stat-card.collision .value {{ color: #ef4444; }}
.legend {{
  display: flex; gap: 24px; padding: 12px 48px; align-items: center;
  background: #111118; border-bottom: 1px solid #1e293b;
}}
.legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 13px; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 3px; }}
.container {{ padding: 16px 48px; overflow-x: auto; }}
.matrix-wrapper {{ position: relative; display: inline-block; }}
.matrix {{ display: grid; gap: 1px; background: #1e293b; }}
.cell {{
  width: 18px; height: 18px; cursor: pointer; border-radius: 2px;
  transition: transform 0.15s, box-shadow 0.15s;
}}
.cell:hover {{ transform: scale(2.2); box-shadow: 0 0 12px rgba(255,255,255,0.3); z-index: 10; position: relative; }}
.domain-labels {{ display: flex; margin-bottom: 8px; gap: 0; }}
.domain-label {{
  font-size: 10px; color: #94a3b8; text-align: center; 
  padding: 2px 4px; border-radius: 3px; white-space: nowrap;
}}
.domain-label.Formation {{ background: rgba(34,197,94,0.12); }}
.domain-label.Validity {{ background: rgba(245,158,11,0.12); }}
.domain-label.Breach {{ background: rgba(239,68,68,0.12); }}
.domain-label.Performance {{ background: rgba(34,197,94,0.08); }}
.domain-label.Remedy\\\\/Sanction {{ background: rgba(239,68,68,0.08); }}
.tooltip-panel {{
  position: fixed; bottom: 24px; right: 24px;
  background: #1a1a2e; border: 1px solid #3b82f6; border-radius: 10px;
  padding: 16px 20px; max-width: 420px; font-size: 13px;
  display: none; z-index: 100; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
}}
.tooltip-panel .pair {{ font-weight: 700; color: #f8fafc; margin-bottom: 4px; }}
.tooltip-panel .states {{ color: #94a3b8; margin-bottom: 4px; }}
.tooltip-panel .detail {{ color: #fbbf24; font-size: 12px; }}
.footer {{ padding: 24px 48px; color: #64748b; font-size: 12px; }}
</style>
</head>
<body>
<div class="header">
  <h1>juris-calculus v1.1.0 — 港美跨法系分歧矩阵</h1>
  <div class="subtitle">65 HK Cap 26 规则 × 81 US 联邦算子 | 共享事实流 | 异构多算子空间并发</div>
</div>

<div class="stats">
  <div class="stat-card">
    <div class="value" style="color:#f8fafc">{summary['total_pairs']:,}</div>
    <div class="label">总对撞次数</div>
  </div>
  <div class="stat-card coincidence">
    <div class="value">{summary['type_distribution'].get('COINCIDENCE', 0):,}</div>
    <div class="label">🎯 逻辑共振</div>
  </div>
  <div class="stat-card asymmetry">
    <div class="value">{summary['type_distribution'].get('ASYMMETRY', 0):,}</div>
    <div class="label">⚠️ 不对称盲点</div>
  </div>
  <div class="stat-card collision">
    <div class="value">{summary['type_distribution'].get('COLLISION', 0):,}</div>
    <div class="label">💥 硬核冲突</div>
  </div>
</div>

<div class="legend">
  <span style="color:#94a3b8;font-size:12px;">视差特征:</span>
  <div class="legend-item"><div class="legend-dot" style="background:#22c55e"></div> 🎯 COINCIDENCE</div>
  <div class="legend-item"><div class="legend-dot" style="background:#f59e0b"></div> ⚠️ ASYMMETRY</div>
  <div class="legend-item"><div class="legend-dot" style="background:#ef4444"></div> 💥 COLLISION</div>
  <span style="margin-left:24px;color:#94a3b8;font-size:11px;">X轴: 81 US规则 (按域分组) | Y轴: 65 HK规则</span>
</div>

<div class="container">
  <div class="matrix-wrapper">
    <div id="heatmap"></div>
  </div>
</div>

<div class="tooltip-panel" id="tooltip">
  <div class="pair" id="tt-pair"></div>
  <div class="states" id="tt-states"></div>
  <div class="detail" id="tt-detail"></div>
</div>

<div class="footer">
  juris-calculus Cross-Jurisdictional Logic Parallax Matrix | Laupinco & WorkBuddy | v1.1.0-CrossBorder
</div>

<script>
const CELL_W = 18, CELL_H = 18, GAP = 1;

const cells = [
  {cells_str}
];

const hkLabels = {json.dumps([r["id"] for r in self.hk_rules])};
const usLabels = {json.dumps([r["id"] for r in self.us_rules])};
const usDomains = {json.dumps([r.get("l1_domain", "?") for r in self.us_rules])};
const domainColors = {domain_colors_js};
const domainRanges = {domain_ranges_js};

const COLS = cells[0].length;
const ROWS = cells.length;

const heatmap = document.getElementById('heatmap');
heatmap.style.display = 'grid';
heatmap.style.gridTemplateColumns = `repeat(${{COLS}}, ${{CELL_W}}px)`;
heatmap.style.gridTemplateRows = `repeat(${{ROWS}}, ${{CELL_H}}px)`;
heatmap.style.gap = GAP + 'px';
heatmap.style.width = (COLS * (CELL_W + GAP)) + 'px';
heatmap.style.height = (ROWS * (CELL_H + GAP)) + 'px';

// Render cells
for (let i = 0; i < ROWS; i++) {{
  for (let j = 0; j < COLS; j++) {{
    const cell = cells[i][j];
    const div = document.createElement('div');
    div.className = 'cell';
    div.style.background = cell.c;
    div.title = cell.t;
    div.textContent = cell.e;
    div.style.fontSize = '8px';
    div.style.display = 'flex';
    div.style.alignItems = 'center';
    div.style.justifyContent = 'center';
    div.style.color = '#fff';
    
    div.addEventListener('click', () => {{
      const tooltip = document.getElementById('tooltip');
      const parts = cell.t.split('|');
      document.getElementById('tt-pair').textContent = parts[0] || '';
      document.getElementById('tt-states').textContent = 'HK=' + (parts[1]||'?') + ' | US=' + (parts[2]||'?');
      document.getElementById('tt-detail').textContent = parts[3] || '';
      tooltip.style.display = 'block';
      setTimeout(() => {{ tooltip.style.display = 'none'; }}, 8000);
    }});
    
    heatmap.appendChild(div);
  }}
}}

// Domain group header
const headerRow = document.createElement('div');
headerRow.style.display = 'flex';
headerRow.style.gap = '4px';
headerRow.style.marginBottom = '8px';
headerRow.style.flexWrap = 'wrap';
for (const [domain, range] of Object.entries(domainRanges)) {{
  const w = (range[1] - range[0] + 1) * (CELL_W + GAP);
  const lbl = document.createElement('div');
  lbl.className = 'domain-label ' + domain;
  lbl.textContent = domain + ' (' + (range[1]-range[0]+1) + ')';
  lbl.style.width = w + 'px';
  lbl.style.fontSize = '10px';
  headerRow.appendChild(lbl);
}}
heatmap.parentElement.insertBefore(headerRow, heatmap);
</script>
</body>
</html>'''
        return html


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

def progress(idx, total):
    pct = idx / total * 100
    bar_len = 40
    filled = int(pct / 100 * bar_len)
    bar = "#" * filled + "-" * (bar_len - filled)
    # Use ASCII-safe characters
    sys.stdout.write(f"\r  [{bar}] {idx}/{total} ({pct:.1f}%)")
    sys.stdout.flush()


if __name__ == "__main__":
    print("=" * 60)
    print("  Parallax Matrix Engine -- 65x81 Divergence Matrix v1.1.0")
    print("  HK Cap 26 x US Federal Dual-Source Operators")
    print("=" * 60)
    print()
    
    engine = ParallaxMatrixEngine()
    
    print("\n[对撞] 开始 65×81 = 5,265 次跨法系对撞...")
    results = engine.run_matrix(progress_callback=progress)
    print()  # newline after progress bar
    
    # 统计
    summary = engine.generate_summary(results)
    
    print(f"\n=== Collision Statistics ===")
    print(f"  Total: {summary['total_pairs']:,}")
    for ptype, count in summary["type_distribution"].items():
        label = {"COINCIDENCE": "[COINC]", "ASYMMETRY": "[ASYMM]", "COLLISION": "[COLL!]", "ERROR": "[ERROR]"}.get(ptype, ptype)
        pct = count / summary["total_pairs"] * 100
        print(f"  {label} {ptype}: {count:,} ({pct:.1f}%)")
    
    # 域交叉表
    print(f"\n=== Domain Cross-Tabulation ===")
    for ptype in ["COLLISION", "ASYMMETRY", "COINCIDENCE"]:
        if ptype in summary["domain_cross_tabulation"]:
            print(f"  [{ptype}]")
            for domain, count in sorted(summary["domain_cross_tabulation"][ptype].items(), key=lambda x: -x[1]):
                if count > 0:
                    print(f"    {domain}: {count}")
    
    # Top COLLISION
    if summary["collisions_top20"]:
        print(f"\n=== COLLISION High-Risk Top 20 ===")
        for i, c in enumerate(summary["collisions_top20"], 1):
            print(f"  {i:2d}. {c['pair']}")
            print(f"      HK={c['hk_state']} | US={c['us_state']} | domain={c['us_domain']}")
            print(f"      {c['detail']}")
    
    # Top ASYMMETRY
    if summary["asymmetries_top20"]:
        print(f"\n=== ASYMMETRY Blind Spots Top 20 ===")
        for i, a in enumerate(summary["asymmetries_top20"], 1):
            print(f"  {i:2d}. {a['pair']}")
            print(f"      HK={a['hk_state']} | US={a['us_state']} | domain={a['us_domain']}")
            print(f"      {a['detail']}")
    
    # ── 保存 JSON ──
    output_dir = Path(__file__).resolve().parents[1] / "configs" / "en_US"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    matrix_json_path = output_dir / "hk_us_divergence_matrix.json"
    
    # 序列化结果
    serialized = []
    for r in results:
        serialized.append({
            "pair_id": r.pair_id,
            "hk_rule_id": r.hk_rule_id,
            "us_rule_id": r.us_rule_id,
            "hk_head_claim": r.hk_head_claim,
            "us_head_claim": r.us_head_claim,
            "us_domain": r.us_domain,
            "us_l0": r.us_l0,
            "fact_count": r.fact_count,
            "hk_state": r.hk_state,
            "us_state": r.us_state,
            "hk_claims": r.hk_claims,
            "us_claims": r.us_claims,
            "hk_rebuttals": r.hk_rebuttals,
            "us_rebuttals": r.us_rebuttals,
            "parallax_type": r.parallax_type,
            "parallax_detail": r.parallax_detail,
        })
    
    output = {
        "metadata": {
            "version": "v1.1.0-CrossBorder",
            "hk_rules_count": len(engine.hk_rules),
            "us_rules_count": len(engine.us_rules),
            "total_collisions": summary["total_pairs"],
            "generated_at": __import__('datetime').datetime.now().isoformat(),
        },
        "summary": summary,
        "results": serialized,
    }
    
    with open(matrix_json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    import os
    json_size = os.path.getsize(matrix_json_path)
    print(f"\n[OK] Matrix JSON -> {matrix_json_path} ({json_size:,} bytes)")
    
    # ── 生成热力图 HTML ──
    html = engine.generate_heatmap_html(results, summary)
    html_path = Path(__file__).resolve().parents[1] / "reports" / "divergence_heatmap.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    html_size = os.path.getsize(html_path)
    print(f"[OK] Heatmap -> {html_path} ({html_size:,} bytes)")
    
    print(f"\n=== Matrix Complete ===")
    print(f"  Dimension: {len(engine.hk_rules)} x {len(engine.us_rules)} = {summary['total_pairs']:,}")
    print(f"  COINCIDENCE: {summary['type_distribution'].get('COINCIDENCE',0):,}")
    print(f"  ASYMMETRY:  {summary['type_distribution'].get('ASYMMETRY',0):,}")
    print(f"  COLLISION:  {summary['type_distribution'].get('COLLISION',0):,}")
    print(f"  ERROR:      {summary['type_distribution'].get('ERROR',0):,}")
