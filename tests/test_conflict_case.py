#!/usr/bin/env python3
"""Phase 2 验证：标准冲突案 — US vs HK 合同效力冲突 + Lex Loci 加权"""
import sys; sys.path.insert(0, '.')
import json
from compiler_core.types import IRState, LegalFact, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.config_paths import rules_path as _cp_rules

# ─── 构造冲突场景 ───
# 香港供货商签了一份中英文合同，卖给美国买家一批定制零件。
# 合同有"签字+盖章"但美国法下缺乏独立的 consideration 对价条款。
# US 规则：缺 Consideration → Contract 不成立
# HK 规则：签字即成立（Cap 26 不额外要求 consideration 的独立形式条款，只要"卖方转让产权+买方付钱"）

facts = [
    # 双方签了合同
    LegalFact('ContractOfSale_Exists', extraction_confidence=1.0),
    # 卖方
    LegalFact('Seller_RightToSell', extraction_confidence=1.0),
    LegalFact('Seller_Sells_InCourseOfBusiness', extraction_confidence=1.0),
    LegalFact('Goods_BoughtByDescription', extraction_confidence=1.0),
    LegalFact('Goods_FreeOfUndisclosedEncumbrance', extraction_confidence=0.9),
    LegalFact('Buyer_QuietPossession', extraction_confidence=0.9),
    # 买方拒收
    LegalFact('Buyer_WrongfullyRefusesAcceptance', extraction_confidence=0.85),
    LegalFact('Buyer_FailsToPay', extraction_confidence=1.0),
    LegalFact('AvailableMarket_Exists', extraction_confidence=0.7),
]

# ─── 分别跑 US 和 HK ───
config = DomainConfig(domain=LegalDomain.CIVIL, taint_threshold=0.5)

print("=" * 60)
print("US 规则（8条 UCC）")
print("=" * 60)
us_rules = load_rules_from_yaml(_cp_rules("en_US"))
us_state = IRState(domain=LegalDomain.CIVIL, jurisdiction='US')
for f in facts: us_state.facts[f.id] = f
us_ev = FixpointEvaluator(us_rules, config)
us_result = us_ev.evaluate(us_state)
print(f"Claims: {len(us_result.claims)}")
for c in us_result.claims.values():
    print(f"  {c.id:40s} conf={c.confidence:.2f}")
print(f"Rebuttals: {len(us_result.rebuttal_log)}")

print()
print("=" * 60)
print("HK 规则（24条 Cap 26）")
print("=" * 60)
hk_rules = load_rules_from_yaml(_cp_rules("hk"))
hk_state = IRState(domain=LegalDomain.CIVIL, jurisdiction='HK')
for f in facts: hk_state.facts[f.id] = f
hk_ev = FixpointEvaluator(hk_rules, config)
hk_result = hk_ev.evaluate(hk_state)
print(f"Claims: {len(hk_result.claims)}")
for c in hk_result.claims.values():
    print(f"  {c.id:40s} conf={c.confidence:.2f}")
print(f"Rebuttals: {len(hk_result.rebuttal_log)}")

# ─── Lex Loci 加权合并 ───
print()
print("=" * 60)
print("Lex Loci 加权合并")
print("=" * 60)

from compiler_core.constraint_validator import ConstraintValidator
from compiler_core.config_paths import rules_path as _cp_rules
cv = ConstraintValidator()

all_claims = {}
# US claims — weight from Lex Loci
for claim_id, claim in us_result.claims.items():
    weight = 1.0  # US jurisdiction default
    # Find most relevant ontology weight
    for onto_name in cv.ontology:
        if onto_name.lower() in claim_id.lower() or claim_id.lower() in onto_name.lower():
            w = cv.get_lex_loci_weight(onto_name, 'US')
            if w > 0:
                weight = w
                break
    weighted_conf = claim.confidence * weight
    all_claims[claim_id] = {'source': 'US', 'conf': claim.confidence, 'weight': weight, 'weighted': weighted_conf}

for claim_id, claim in hk_result.claims.items():
    weight = 0.2  # HK as fallback
    for onto_name in cv.ontology:
        if onto_name.lower() in claim_id.lower() or claim_id.lower() in onto_name.lower():
            w = cv.get_lex_loci_weight(onto_name, 'HK')
            if w > 0:
                weight = w
                break
    weighted_conf = claim.confidence * weight
    if claim_id not in all_claims:
        all_claims[claim_id] = {'source': 'HK', 'conf': claim.confidence, 'weight': weight, 'weighted': weighted_conf}
    else:
        # Conflict resolution: max weighted score wins
        if weighted_conf > all_claims[claim_id]['weighted']:
            all_claims[claim_id] = {'source': 'HK', 'conf': claim.confidence, 'weight': weight, 'weighted': weighted_conf}

print(f"{'Claim':45s} {'Source':>4s} {'Conf':>6s} {'Wt':>6s} {'Weighted':>8s}")
print("-" * 80)
for claim_id, data in sorted(all_claims.items()):
    print(f"{claim_id:45s} {data['source']:>4s} {data['conf']:6.2f} {data['weight']:6.2f} {data['weighted']:8.4f}")

# Audit summary
total_rebuttals = len(us_result.rebuttal_log) + len(hk_result.rebuttal_log)
print(f"\nAudit: {total_rebuttals} rebuttals detected")
print(f"US jurisdiction claims: {len(us_result.claims)}")
print(f"HK jurisdiction claims: {len(hk_result.claims)}")
print(f"Lex Loci merged claims: {len(all_claims)}")


def test_conflict_case_excludes_unanchored_hk_candidates():
    """无来源锚的 HK 规则只能留在 corpus，不得产生跨法域合并结论。"""
    assert len(us_result.claims) == 0
    assert len(hk_result.claims) == 0
    assert us_ev.inventory["corpus_total"] == 0
    assert hk_ev.inventory["candidate_only_total"] > 0
    assert all_claims == {}
