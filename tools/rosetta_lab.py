#!/usr/bin/env python3
"""罗塞塔实验室: US核心概念 → L0原语链 → HK规则碰撞"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compiler_core.types import IRState, LegalFact, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml

# ═══════════════════════════════════════════
# 罗塞塔映射表: US概念 → L0原语链
# ═══════════════════════════════════════════

ROSETTA = {
    "Business_Judgment_Rule": {
        "L0_chain": ["Agent(Director)", "Power(Decision_Making)", "Status(Protected)"],
        "effect": "董事善意决策 → 法院不事后审查 → Status=Protected",
        "HK_analog": None,  # 香港法无成文的BJR
    },
    "Piercing_Corporate_Veil": {
        "L0_chain": ["Agent(Company)", "Power(Limited_Liability)", "Defect(Fraud_Or_Abuse)", "Agent(Shareholder_Personally_Liable)"],
        "effect": "公司人格被滥用 → 有限责任保护破裂 → 股东个人担责",
        "HK_analog": "Cap 622 s.729 公司人格否认",
    },
    "Duty_Of_Care": {
        "L0_chain": ["Agent(Director)", "Act(Decision_Or_Omission)", "Status(Breached_If_Negligent)"],
        "effect": "董事未尽合理注意 → 违反注意义务 → 可诉",
        "HK_analog": "Cap 622 s.465 董事以合理水平的谨慎、技巧及努力行事",
    },
    "Fiduciary_Duty_Loyalty": {
        "L0_chain": ["Agent(Director)", "Power(Decision_Making)", "Act(Must_Prioritize_Company)", "Defect(Self_Dealing) → Status(Voidable)"],
        "effect": "董事必须对公司忠诚 → 自我交易可撤销",
        "HK_analog": "Cap 622 s.466 董事不得进行有利益冲突的交易",
    },
    "Promissory_Estoppel": {
        "L0_chain": ["Status(Reliance_Established)", "Act(Promise_Made)", "Status(Enforceable_Despite_No_Consideration)"],
        "effect": "对方合理信赖 → 即使无对价也可强制执行",
        "HK_analog": "普通法允诺禁反言",
    },
}

# ═══════════════════════════════════════════
# 碰撞实验: US案例 → HK规则 → 找逻辑鸿沟
# ═══════════════════════════════════════════

def collision_test(ev, scenario_name: str, facts: dict, expected_L0_chain: list):
    """US案例用HK规则跑 → 检测L0链上的断点"""
    s = IRState(domain=LegalDomain.CIVIL, jurisdiction="HK")
    for fid, conf in facts.items():
        s.facts[fid] = LegalFact(fid, extraction_confidence=conf)

    try:
        res = ev.evaluate(s)
    except:
        return {"name": scenario_name, "status": "CRASHED", "claims": [], "L0_chain": expected_L0_chain}

    claims = [c.id for c in res.claims.values() if c.confidence > 0]
    state = s.state_tracker.get("Contract_Validity", "?")

    # 检测: L0链上的每个原语是否有对应的claim
    l0_covered = []
    l0_gaps = []
    for node in expected_L0_chain:
        primitive = node.split("(")[0]  # Agent, Power, Status, Act, Defect
        found = any(primitive.lower() in c.lower() for c in claims)
        (l0_covered if found else l0_gaps).append(node)

    return {
        "name": scenario_name,
        "status": "CONVERGED" if claims else "SILENT",
        "claims": claims,
        "state": state,
        "L0_chain": expected_L0_chain,
        "L0_covered": l0_covered,
        "L0_gaps": l0_gaps,
        "gap_is_jurisdictional": len(l0_gaps) > 0 and len(l0_covered) == 0,
    }


print("═══ 罗塞塔实验室 ═══")
print()

# ─── 映射表 ───
print("=== 1. US→L0 罗塞塔映射 ===")
for name, data in ROSETTA.items():
    chain = " → ".join(data["L0_chain"])
    hk = data.get("HK_analog", "无对应")
    print(f"  {name:30s} | {chain}")
    print(f"  {'':30s} | HK: {hk}")

# ─── 碰撞实验 ───
print()
print("=== 2. 碰撞实验: US案例 × HK规则 ===")

r = load_rules_from_yaml("configs/hk/rules.yaml")
cfg = DomainConfig(domain=LegalDomain.CIVIL)
ev = FixpointEvaluator(r, cfg)

scenarios = [
    ("Piercing_Veil", {
        "ContractOfSale_Exists": 1.0,
        "Director_Acted_UltraVires": 1.0,
        "Company_Used_As_AlterEgo": 1.0,
        "Fraud_On_Creditors": 1.0,
    }, ["Agent(Company)", "Power(Limited_Liability)", "Defect(Fraud_Or_Abuse)", "Agent(Shareholder_Personally_Liable)"]),

    ("Duty_Of_Care_Breach", {
        "ContractOfSale_Exists": 1.0,
        "Director_Acted_UltraVires": 1.0,
        "Board_Decision_NotInformed": 1.0,
    }, ["Agent(Director)", "Act(Decision_Or_Omission)", "Status(Breached_If_Negligent)"]),

    ("BJR_Protected", {
        "ContractOfSale_Exists": 1.0,
        "Director_Acted_InGoodFaith": 1.0,
        "Board_Decision_Informed": 1.0,
    }, ["Agent(Director)", "Power(Decision_Making)", "Status(Protected)"]),
]

for name, facts, chain in scenarios:
    result = collision_test(ev, name, facts, chain)
    gap_status = "🔴 鸿沟" if result.get("gap_is_jurisdictional") else ("✅ 覆盖" if not result["L0_gaps"] else "⚠️ 部分")
    print(f"  {gap_status} {name:25s} | claims={len(result['claims'])} | state={result['state']} | 覆盖={len(result['L0_covered'])}/链长{len(chain)}")
    if result["L0_gaps"]:
        for g in result["L0_gaps"]:
            print(f"      缺口: {g}")
    if result["L0_covered"]:
        for c in result["L0_covered"]:
            print(f"      命中: {c}")

# ─── 摘要 ───
print()
print("=== 3. 罗塞塔石碑评估 ===")
print(f"  5 US核心概念 → L0原语链映射完成")
print(f"  3 碰撞实验: HKRules→US场景")
print(f"  L0原语 = 跨法系公分母")
print(f"  未映射概念 = 下一批 Adapter 扩展目标 (Breach_By_Delay, Special_Damages, Foreseeable_Damages)")
