#!/usr/bin/env python3
"""
gen_us_adapter.py — US Glossary L0 → US_Adapter.yaml 转换器
============================================================================
输入: US_GLOSSARY_PATH 环境变量 或 ./data/US_glossary_L0_unified.json (81 terms)
输出: configs/en_US/US_Adapter.yaml + configs/en_US/L0_overrides_us.yaml

原理:
  1. 读取 unified JSON → 按 L0 原语分组
  2. 解析 horn_premise_atom (A AND B → C) → 拆分为 premise_atoms + head_claim
  3. 解析 structural_chain → 生成概念映射
  4. 解析 edge_case_trigger → 生成 constraint_rules
  5. 输出 engine-readable YAML 配置
============================================================================
"""

import json
import os
import yaml
import re
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple

# ═══════════════════════════════════════════
# 路径（repo-internal 用相对路径，外部输入用环境变量）
# ═══════════════════════════════════════════
ROOT = Path(__file__).parent.parent
INPUT_JSON = Path(os.environ.get("US_GLOSSARY_PATH", ROOT / "data" / "US_glossary_L0_unified.json"))
OUTPUT_ADAPTER = ROOT / "configs" / "en_US" / "US_Adapter.yaml"
OUTPUT_OVERRIDES = ROOT / "configs" / "en_US" / "L0_overrides_us.yaml"

# ═══════════════════════════════════════════
# 解析器
# ═══════════════════════════════════════════

def parse_horn_atom(horn_text: str) -> Tuple[List[str], str]:
    """
    解析 "A AND B AND C → D" 或 "A → D"
    返回 (premise_atoms, head_claim)
    """
    if "→" not in horn_text:
        return ([], horn_text.strip())
    
    left, right = horn_text.split("→", 1)
    # Split on AND, also handle commas
    premises = re.split(r'\s+AND\s+|\s*,\s*(?=[A-Z])', left.strip())
    premises = [p.strip() for p in premises if p.strip()]
    head = right.strip()
    return (premises, head)


def term_to_rule_id(term: str, index: int) -> str:
    """将术语名转换为规则 ID: US-{L0}-{sanitized_term}"""
    # Remove parentheticals
    clean = re.sub(r'\s*\([^)]*\)', '', term)
    # Replace spaces/slashes with underscore
    clean = re.sub(r'[\s/]+', '_', clean)
    # Remove non-alphanumeric except underscore
    clean = re.sub(r'[^a-zA-Z0-9_]', '', clean)
    return f"US-{clean}"


def parse_edge_case(edge_text: str) -> Dict:
    """
    解析 edge_case_trigger: "Condition → Consequence" 或自由文本
    返回 constraint rule 结构
    """
    if not edge_text or "→" not in edge_text:
        return None
    
    parts = edge_text.split("→", 1)
    trigger = parts[0].strip()
    consequence = parts[1].strip()
    
    return {
        "trigger": trigger,
        "consequence": consequence,
    }


def extract_concepts_from_chain(chain: str) -> List[str]:
    """从 structural_chain 中提取概念关键词"""
    concepts = set()
    # Extract Agent(...), Act(...), Status(...), etc.
    matches = re.findall(r'(Agent|Asset|Act|Status|Power|Defect)\(([^)]+)\)', chain)
    for l0, val in matches:
        # Split on keywords
        for part in re.split(r'[_\s]+AND\s+|[_\s]+OR\s+|[_\s]+', val):
            part = part.strip('_').strip()
            if part and len(part) > 1:
                concepts.add(part)
    return sorted(concepts)


# ═══════════════════════════════════════════
# 主转换逻辑
# ═══════════════════════════════════════════

def convert():
    # 加载 JSON
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        terms = json.load(f)
    
    print(f"Loaded {len(terms)} terms from {INPUT_JSON}")
    
    # ── 分组 ──
    rules: List[Dict] = []
    L0_map: Dict[str, str] = {}
    constraint_rules: List[Dict] = []
    
    # 按 perspective 分组统计
    perspective_counts = defaultdict(int)
    domain_counts = defaultdict(int)
    l0_counts = defaultdict(int)
    
    skipped = 0
    
    for i, term in enumerate(terms):
        l0_primitive = term["l0_mapping"]["primary_primitive"]
        chain = term["l0_mapping"]["structural_chain"]
        domain = term.get("l1_domain", "General")
        horn = term.get("horn_premise_atom", "")
        edge = term.get("edge_case_trigger", "")
        perspective = term.get("perspective", "Judicial")
        
        perspective_counts[perspective] += 1
        domain_counts[domain] += 1
        l0_counts[l0_primitive] += 1
        
        # ── 生成 Horn 规则 ──
        premises, head = parse_horn_atom(horn)
        if not premises or not head:
            skipped += 1
            continue
        
        concepts = extract_concepts_from_chain(chain)
        
        rule_id = term_to_rule_id(term["term"], i)
        
        # 域映射
        domain_map = {
            "Formation": "formation",
            "Validity": "validity",
            "Performance": "performance",
            "Breach": "breach",
            "Remedy/Sanction": "remedy",
            "General": "general",
        }
        ns = f"us_{domain_map.get(domain, 'general')}"
        
        rule = {
            "id": rule_id,
            "term": term["term"],
            "origin": term["origin"],
            "perspective": perspective,
            "premise_atoms": premises,
            "head_claim": head,
            "concepts": concepts,
            "l0_primitive": l0_primitive,
            "l1_domain": domain,
            "structural_chain": chain,
            "exception_chain": [],
            "head_type": "HORN",
            "mechanical_exception": True,
            "namespace": ns,
            "output_type": "Terminal_Output_Node",
        }
        rules.append(rule)
        
        # ── 生成 L0 映射 ──
        L0_map[head] = l0_primitive
        for p in premises:
            if p not in L0_map:
                L0_map[p] = l0_primitive  # 继承主原语
        
        # ── 生成 constraint rules (from edge_case) ──
        edge_parsed = parse_edge_case(edge)
        if edge_parsed:
            # 生成触发事实
            trigger_clean = re.sub(r'[_\s]+', '_', edge_parsed["trigger"])
            # 尝试提取状态名
            state_match = re.search(r'Status[=:]\s*(\w+)', edge_parsed["consequence"])
            new_state = state_match.group(1) if state_match else "SUPPRESSED"
            
            constraint_rules.append({
                "id": f"US-CONSTRAINT-{rule_id}",
                "description": f"Edge case for {term['term']}",
                "trigger_fact": trigger_clean,
                "action": "force_state",
                "target": head,
                "new_state": new_state,
                "source_edge_case": edge,
                "reason": f"US {term['term']} edge case trigger",
            })
    
    # ── 统计 ──
    print(f"\n═══ 转换统计 ═══")
    print(f"  总术语: {len(terms)}")
    print(f"  已生成规则: {len(rules)}")
    print(f"  跳过(无premise): {skipped}")
    print(f"  L0映射条目: {len(L0_map)}")
    print(f"  Constraint规则: {len(constraint_rules)}")
    print(f"\n  L0分布: {dict(l0_counts)}")
    print(f"  Perspective分布: {dict(perspective_counts)}")
    print(f"  域分布: {dict(domain_counts)}")
    
    # ── 构建 YAML 结构 ──
    
    # 1. US_Adapter.yaml (概念定义 + 规则)
    adapter_yaml = {
        "jurisdiction": "US",
        "family": "Common_Law",
        "description": (
            f"美国联邦法 L0 适配器 — 从 uscourts.gov 和 justice.gov "
            f"提取的 {len(rules)} 条概念算子。涵盖破产法(Chapter 7/11/13)、"
            f"民事诉讼、刑事诉讼、证据规则、宪法保护等领域。"
        ),
        "sources": [
            "https://www.uscourts.gov/glossary",
            "https://www.justice.gov/usao/justice-101/glossary",
        ],
        "l0_distribution": dict(l0_counts),
        "perspective_distribution": dict(perspective_counts),
        "domain_distribution": dict(domain_counts),
        "concepts": [],
        "rules": rules,
    }
    
    # 构建 concept 定义层
    for primitive in ["Agent", "Act", "Status", "Power", "Asset", "Defect"]:
        primitive_rules = [r for r in rules if r["l0_primitive"] == primitive]
        if not primitive_rules:
            continue
        
        concept_def = {
            "primitive": primitive,
            "count": len(primitive_rules),
            "domains": sorted(set(r["l1_domain"] for r in primitive_rules)),
            "mappings": {},
        }
        
        for r in primitive_rules:
            concept_def["mappings"][r["head_claim"]] = {
                "domain": r["l1_domain"],
                "chain": r["structural_chain"],
                "premises": r["premise_atoms"],
            }
        
        adapter_yaml["concepts"].append(concept_def)
    
    # 2. L0_overrides_us.yaml (US 特有 L0 覆写)
    overrides_yaml = {
        "jurisdiction": "US",
        "family": "Common_Law",
        "description": (
            "美国联邦法对 L0 原语的覆写。"
            "US 普通法继承了英国普通法的核心特征（对价、禁反言），"
            "但增加了宪法层面的权利保护（Due Process, Double Jeopardy）"
            "和破产法的特殊状态机（Automatic Stay, Discharge）。"
        ),
        "overrides": {
            "Act": {
                "legal_intent": {
                    "value": "Optional",
                    "reason": "普通法承认严格责任——特定行为（如危险品运输）无意图也可构成 Act",
                },
            },
            "Agent": {
                "capacity_required": {
                    "value": "Conditional",
                    "reason": "美国法：未成年人可签订必需品合同；公司代理人需授权但表见代理可越权",
                },
            },
            "Status": {
                "valid_transitions": {
                    "value": [
                        "Established→Valid",
                        "Valid→Void",
                        "Valid→Voidable",
                        "Valid→Terminated",
                        "Valid→PENDING",
                        "PENDING→Valid",
                        "CONDITIONAL→Valid",
                        "VALID→SUPPRESSED",       # 破产法 Automatic Stay
                        "SUPPRESSED→VALID",        # Stay lifted
                        "Valid→Breached",
                        "Breached→Remedied",
                        "VOIDABLE→VOID",           # 法院确认无效
                        "VOIDABLE→VALID",          # 追认/治愈
                    ],
                    "reason": (
                        "美国法状态机：增加 SUPPRESSED 状态（破产自动中止）、"
                        "VOIDABLE 双向转换（可追认/可确认无效）"
                    ),
                },
            },
            "Defect": {
                "additional_defects": {
                    "value": [
                        "Consideration_Failure",
                        "Promissory_Estoppel_Bar",
                        "Due_Process_Violation",         # 宪法缺陷
                        "Double_Jeopardy_Attached",      # 一事不再理
                        "Fraud_on_the_Court",            # 欺诈法庭
                        "Automatic_Stay_Violation",      # 违反自动中止
                        "Wrongful_Omission",             # 欺诈性不作为（DOJ视角）
                    ],
                    "reason": "美国法特有缺陷：宪法保护 + 破产法 + 检察视角",
                },
            },
            "Power": {
                "Consideration": {
                    "value": "Required",
                    "reason": "美国普通法继承英国对价原则——无对价无合同（promissory estoppel 为例外）",
                },
                "Automatic_Stay_Suppression": {
                    "value": "Enabled",
                    "reason": "Chapter 11/13 自动中止——债权人 Power(Collect) 被全局抑制",
                },
                "Director_Power": {
                    "value": "Subject_to_Bankruptcy_Override",
                    "reason": "美国法下：进入 Chapter 11 后，DIP 或 Trustee 接管董事经营权力",
                },
            },
        },
        "constraint_rules": [
            # 核心约束1: Automatic Stay
            {
                "id": "US-AUTOMATIC_STAY",
                "description": "破产自动中止：所有债权人催收权力全局抑制",
                "trigger_fact": "Bankruptcy_Petition_Filed",
                "action": "suppress_power",
                "target": "Creditor_Collect",
                "effect": "Power(Collect)=0 → 所有催收行为中止",
                "irreversible": False,  # 可通过 Motion to Lift Stay 解除
                "reason": "11 U.S.C. §362 — Automatic Stay",
            },
            # 核心约束2: DIP 权力替代
            {
                "id": "US-DIP_MANAGEMENT_DISPLACEMENT",
                "description": "Chapter 11 DIP/Trustee 替代原管理层——董事经营权力被抑制",
                "trigger_fact": "Chapter11_Filed",
                "additional_conditions": ["Trustee_Appointed"],
                "action": "suppress_power",
                "target": "Director_Operational_Power",
                "effect": "Power(Director, Operate)=0 → DIP/Trustee 接管",
                "irreversible": False,
                "reason": "11 U.S.C. §1107-1108 — DIP powers; §1104 — Trustee appointment",
            },
            # 核心约束3: 确认后不可逆
            {
                "id": "US-CONFIRMATION_IRREVERSIBLE",
                "description": "Chapter 11 Plan 确认后——状态不可逆（除欺诈撤销外）",
                "trigger_fact": "Plan_Confirmed",
                "action": "force_state",
                "target": "Reorganization_Status",
                "new_state": "CONFIRMED",
                "irreversible": True,
                "reason": "11 U.S.C. §1141 — Effect of confirmation",
            },
            # 核心约束4: Double Jeopardy
            {
                "id": "US-DOUBLE_JEOPARDY",
                "description": "一事不再理——无罪判决后禁止再诉",
                "trigger_fact": "Acquittal_Entered",
                "action": "force_state",
                "target": "Criminal_Liability",
                "new_state": "FINAL",
                "irreversible": True,
                "reason": "U.S. Const. Amend. V — Double Jeopardy Clause",
            },
            # 核心约束5: Due Process
            {
                "id": "US-DUE_PROCESS",
                "description": "正当程序——未听证不得剥夺财产/自由",
                "trigger_fact": "Due_Process_Violation_Alleged",
                "action": "force_state",
                "target": "Agency_Action",
                "new_state": "VOID",
                "irreversible": False,
                "reason": "U.S. Const. Amend. V, XIV — Due Process Clause",
            },
        ] + constraint_rules,  # 追加所有 edge_case 衍生的约束
    }
    
    # ── 写入文件 ──
    OUTPUT_ADAPTER.parent.mkdir(parents=True, exist_ok=True)
    
    with open(OUTPUT_ADAPTER, "w", encoding="utf-8") as f:
        f.write("# ═══════════════════════════════════════════\n")
        f.write("# US_Adapter.yaml — 美国联邦法 L0 适配器\n")
        f.write(f"# Auto-generated from: {INPUT_JSON}\n")
        f.write(f"# Terms: {len(terms)} | Rules: {len(rules)} | Constraints: {len(constraint_rules)}\n")
        f.write("# ═══════════════════════════════════════════\n\n")
        yaml.dump(adapter_yaml, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120)
    
    print(f"\n✅ US_Adapter.yaml → {OUTPUT_ADAPTER} ({OUTPUT_ADAPTER.stat().st_size:,} bytes)")
    
    with open(OUTPUT_OVERRIDES, "w", encoding="utf-8") as f:
        f.write("# ═══════════════════════════════════════════\n")
        f.write("# L0_overrides_us.yaml — 美国联邦法 L0 覆写\n")
        f.write(f"# Auto-generated from: {INPUT_JSON}\n")
        f.write(f"# Constraint rules: {len(overrides_yaml['constraint_rules'])}\n")
        f.write("# ═══════════════════════════════════════════\n\n")
        yaml.dump(overrides_yaml, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120)
    
    print(f"✅ L0_overrides_us.yaml → {OUTPUT_OVERRIDES} ({OUTPUT_OVERRIDES.stat().st_size:,} bytes)")
    
    # ── 同步更新 USAdapter L0_MAP ──
    gen_adapter_py_code(L0_map)
    
    return len(rules), len(constraint_rules), len(L0_map)


def gen_adapter_py_code(L0_map: Dict[str, str]):
    """生成 USAdapter._L0_MAP 的 Python 代码片段，供手动合并"""
    output_path = ROOT / "adapter" / "_us_L0_map_generated.py"
    
    lines = ["# AUTO-GENERATED by gen_us_adapter.py — USAdapter._L0_MAP"]
    lines.append(f"# {len(L0_map)} entries\n")
    lines.append("_US_L0_MAP = {")
    for concept, l0 in sorted(L0_map.items()):
        # 转义概念名
        safe_concept = concept.replace("'", "\\'")
        lines.append(f"    '{safe_concept}': '{l0}',")
    lines.append("}")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    print(f"✅ _US_L0_MAP 代码片段 → {output_path}")


if __name__ == "__main__":
    n_rules, n_constraints, n_map = convert()
    print(f"\n═══ 转换完成 ═══")
    print(f"  Horn 规则: {n_rules}")
    print(f"  约束规则: {n_constraints}")
    print(f"  L0 映射: {n_map}")
