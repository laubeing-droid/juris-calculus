#!/usr/bin/env python3
"""Phase 3-4: US 10案全量基准 — Baseline vs HK 62规则"""
import sys; sys.path.insert(0, '.')
from compiler_core.types import IRState, LegalFact, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml

CONFIG = DomainConfig(domain=LegalDomain.CIVIL)
US_RULES = load_rules_from_yaml("configs/en_US/rules.yaml")
HK_RULES = load_rules_from_yaml("configs/hk/rules.yaml")

# ─── US 10案事实集 ───
# 每个案例：合同买卖法框架下的事实构造
# 命名：ContractFormed/ContractExists = contract formed
# 具体事实因案由调整

CASES = {
    "Twitter v. Musk": [
        LegalFact("ContractOfSale_Exists", extraction_confidence=1.0),
        LegalFact("Seller_RightToSell", extraction_confidence=1.0),
        LegalFact("Buyer_QuietPossession", extraction_confidence=0.9),
        LegalFact("Goods_BoughtByDescription", extraction_confidence=1.0),
        LegalFact("Seller_Sells_InCourseOfBusiness", extraction_confidence=1.0),
        LegalFact("Buyer_WrongfullyRefusesAcceptance", extraction_confidence=0.85),
        LegalFact("Buyer_FailsToPay", extraction_confidence=1.0),
        LegalFact("AvailableMarket_Exists", extraction_confidence=0.7),
    ],
    "Bradford v. Walmart": [
        LegalFact("ContractOfSale_Exists", extraction_confidence=1.0),
        LegalFact("Seller_Sells_InCourseOfBusiness", extraction_confidence=1.0),
        LegalFact("Goods_BoughtByDescription", extraction_confidence=1.0),
        LegalFact("Defects_Drawn_To_Buyer_Attention", extraction_confidence=1.0),  # ← rebuttal
        LegalFact("Buyer_ExaminedGoods_BeforeContract", extraction_confidence=0.5),
    ],
    "Tynes v. Florida DJJ": [
        # Employment — outside sale of goods scope
        LegalFact("ContractOfSale_Exists", extraction_confidence=0.3),
    ],
    "In re Marriott": [
        # Data breach — outside scope
        LegalFact("ContractOfSale_Exists", extraction_confidence=0.3),
    ],
    "SEC v. Ripple": [
        LegalFact("ContractOfSale_Exists", extraction_confidence=0.5),
        LegalFact("Seller_RightToSell", extraction_confidence=0.5),
        LegalFact("Goods_BoughtByDescription", extraction_confidence=0.5),
    ],
    "Waymo v. Uber": [
        # Trade secrets — outside scope
        LegalFact("ContractOfSale_Exists", extraction_confidence=0.2),
    ],
    "US v. Google": [
        LegalFact("ContractOfSale_Exists", extraction_confidence=0.2),
    ],
    "Chevron v. Donziger": [
        LegalFact("ContractOfSale_Exists", extraction_confidence=0.2),
    ],
    "Apple v. Samsung": [
        LegalFact("ContractOfSale_Exists", extraction_confidence=0.4),
        LegalFact("Seller_Sells_InCourseOfBusiness", extraction_confidence=0.8),
        LegalFact("Goods_BoughtByDescription", extraction_confidence=0.8),
    ],
    "NRA v. Vullo": [
        LegalFact("ContractOfSale_Exists", extraction_confidence=0.1),
    ],
}

print("=" * 80)
print("US 10案全量基准：Baseline (US 8条) vs Test (HK 62条)")
print("=" * 80)

results = []
for case_name, facts in CASES.items():
    # ─── US Baseline ───
    us_state = IRState(domain=LegalDomain.CIVIL, jurisdiction="US")
    for f in facts: us_state.facts[f.id] = f
    us_ev = FixpointEvaluator(US_RULES, CONFIG)
    try:
        us_result = us_ev.evaluate(us_state)
        us_claims = len(us_result.claims)
        us_rebuttals = len(us_result.rebuttal_log)
    except Exception as e:
        us_claims = -1
        us_rebuttals = 0

    # ─── HK Test ───
    hk_state = IRState(domain=LegalDomain.CIVIL, jurisdiction="HK")
    for f in facts: hk_state.facts[f.id] = f
    hk_ev = FixpointEvaluator(HK_RULES, CONFIG)
    try:
        hk_result = hk_ev.evaluate(hk_state)
        hk_claims = len(hk_result.claims)
        hk_rebuttals = len(hk_result.rebuttal_log)
        # Count non-rebutted claims (confidence > 0)
        hk_active = sum(1 for c in hk_result.claims.values() if c.confidence > 0)
        # Get top claims
        top = sorted(hk_result.claims.values(), key=lambda c: c.confidence, reverse=True)[:3]
        top_str = "; ".join(f"{c.id}({c.confidence:.2f})" for c in top)
    except Exception as e:
        hk_claims = -1
        hk_rebuttals = 0
        hk_active = 0
        top_str = f"ERROR: {e}"

    delta = hk_active - us_claims if us_claims >= 0 else "N/A"
    results.append({
        "case": case_name,
        "us": us_claims,
        "hk": hk_active,
        "hk_total": hk_claims,
        "hk_rebutted": hk_rebuttals,
        "delta": delta,
        "top_hk": top_str,
    })
    
    # Print row
    us_s = str(us_claims) if us_claims >= 0 else "ERR"
    delta_s = f"+{delta}" if isinstance(delta, int) and delta > 0 else str(delta)
    print(f"{case_name:25s} | US={us_s:>3s} | HK={hk_active:>2d}({hk_rebuttals}R) | Δ={delta_s:>4s} | {top_str[:80]}")

# Summary
us_total = sum(1 for r in results if isinstance(r["us"], int) and r["us"] > 0)
hk_total = sum(1 for r in results if isinstance(r["hk"], int) and r["hk"] > 0)
hk_with_rebuttal = sum(1 for r in results if r["hk_rebutted"] > 0 and r["hk"] > 0)

print(f"\n{'='*80}")
print(f"Baseline (US 8): {us_total}/10 收敛")
print(f"Test (HK 62):   {hk_total}/10 收敛")
print(f"HK 含反驳案例:    {hk_with_rebuttal}/10")
print(f"诚实拒算率:  US={10-us_total}/10 → HK={10-hk_total}/10")
