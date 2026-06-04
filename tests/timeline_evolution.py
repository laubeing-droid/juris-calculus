#!/usr/bin/env python3
"""时间轴演化推理器：T1→T2→T3 分步注入事实，观察状态迁移"""
import sys; sys.path.insert(0, '.')
import yaml
from compiler_core.types import IRState, LegalFact, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml

HK_RULES = load_rules_from_yaml("configs/hk/rules.yaml")
CONFIG = DomainConfig(domain=LegalDomain.CIVIL)

# Load evolution rules
with open("configs/core_ontology.yaml", "r", encoding="utf-8") as f:
    onto = yaml.safe_load(f)
EVO = onto.get("evolution_rules", {})

def run_timeline(name, phases):
    """分阶段注入事实，观察状态迁移"""
    print(f"\n{'─'*90}")
    print(f"【{name}】时间轴演化推理")
    
    state = IRState(domain=LegalDomain.CIVIL, jurisdiction="HK")
    all_claims = {}
    
    for phase_name, facts_data in phases:
        print(f"\n  ▸ {phase_name}")
        for fdata in facts_data:
            fid = fdata["id"]
            conf = fdata.get("confidence", 1.0)
            state.facts[fid] = LegalFact(fid, extraction_confidence=conf)
            print(f"    注入: {fid} (conf={conf})")
        
        ev = FixpointEvaluator(HK_RULES, CONFIG)
        result = ev.evaluate(state)
        
        new_claims = {cid: c for cid, c in result.claims.items() 
                     if c.confidence > 0 and cid not in all_claims}
        rebutted = {cid: c for cid, c in result.claims.items() if c.confidence == 0}
        
        if new_claims:
            print(f"    → 新主张: {len(new_claims)}")
            for c in sorted(new_claims.values(), key=lambda x: -x.confidence):
                print(f"      {c.id:50s} conf={c.confidence:.2f}")
        
        if rebutted:
            print(f"    → 反驳: {len(rebutted)}")
            for log in result.rebuttal_log:
                print(f"      ⚡ {log['claim_id'][:45]} ← {log['trigger_fact']}")
        
        if result.rules_applied:
            print(f"    → 触发规则: {len(result.rules_applied)} (累计: {len(state.rules_applied)})")
        
        all_claims.update(new_claims)
    
    # Final summary
    accepted_rebutted = sum(1 for c in result.claims.values() if c.confidence == 0)
    print(f"\n  终态: {len(all_claims)} 活跃主张 + {accepted_rebutted} 反驳 | {len(result.rules_applied)} 规则触发")

# ═══════════════════════════════════════════════════════════
# 案例 1: Instalments — 分期交付时间轴
# ═══════════════════════════════════════════════════════════
run_timeline("Instalments: 分期交付演化", [
    ("T1 签约", [
        {"id": "ContractOfSale_Exists", "confidence": 1.0},
        {"id": "Delivery_ByInstalments", "confidence": 1.0},
        {"id": "Seller_Sells_InCourseOfBusiness", "confidence": 1.0},
        {"id": "Goods_BoughtByDescription", "confidence": 1.0},
    ]),
    ("T2 第一批交付完成", [
        {"id": "Goods_Delivered", "confidence": 0.5},  # 部分交付
    ]),
    ("T3 第二批有缺陷", [
        {"id": "Seller_DefectiveDeliveries", "confidence": 1.0},
        {"id": "Buyer_HasRightToReject", "confidence": 0.8},
    ]),
    ("T4 买方拒收该批", [
        {"id": "Buyer_IntimatesRefusal", "confidence": 1.0},
        {"id": "Buyer_FailsToPay", "confidence": 0.7},
    ]),
])

# ═══════════════════════════════════════════════════════════
# 案例 2: Perished_Goods — 欺诈触发合同自始无效
# ═══════════════════════════════════════════════════════════
run_timeline("Perished_Goods: 标的物灭失 + 卖方知情 → 欺诈", [
    ("T1 签约（卖方隐瞒灭失事实）", [
        {"id": "ContractOfSale_Exists", "confidence": 1.0},
        {"id": "ContractForSale_SpecificGoods", "confidence": 1.0},
        {"id": "Goods_Exist", "confidence": 1.0},  # 表面事实
        {"id": "Seller_RightToSell", "confidence": 1.0},
    ]),
    ("T2 买方发现货品签约前已灭失", [
        {"id": "Goods_Perished_BeforeContract", "confidence": 1.0},
        {"id": "Seller_DidNotKnow", "confidence": 0.0},  # ↓ 否定！
    ]),
    ("T3 证实卖方签约时知情", [
        {"id": "Seller_DidNotKnow", "confidence": 0.0},  # 确认: 卖方知情
        {"id": "Goods_Exist", "confidence": 0.0},  # 回溯: 货品不存在
    ]),
])

# ═══════════════════════════════════════════════════════════
# 案例 3: NemoDat — 无权处分 + 不容否认
# ═══════════════════════════════════════════════════════════
run_timeline("NemoDat: 非所有权人售卖 → 不容否认例外", [
    ("T1 签约（卖方自称有权）", [
        {"id": "ContractOfSale_Exists", "confidence": 1.0},
        {"id": "Goods_Sold", "confidence": 1.0},
        {"id": "Seller_RightToSell", "confidence": 1.0},  # 表面事实
        {"id": "Buyer_InGoodFaith", "confidence": 1.0},
        {"id": "Buyer_WithoutNotice", "confidence": 1.0},
    ]),
    ("T2 原主出现：卖方不是所有权人", [
        {"id": "Seller_NotOwner", "confidence": 1.0},
        {"id": "Seller_NoAuthority", "confidence": 1.0},
        {"id": "Seller_RightToSell", "confidence": 0.0},  # 撤回
    ]),
    ("T3 原主行为构成不容否认", [
        {"id": "Owner_Conduct_PrecludesDenyingAuthority", "confidence": 1.0},
    ]),
])
