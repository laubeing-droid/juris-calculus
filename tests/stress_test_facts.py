#!/usr/bin/env python3
"""事实生成器 + 深度压力测试：7种标准场景 × 62条HK规则"""
import sys; sys.path.insert(0, '.')
import json, time
from compiler_core.types import IRState, LegalFact, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.config_paths import rules_path as _cp_rules

HK_RULES = load_rules_from_yaml(_cp_rules("hk"))
CONFIG = DomainConfig(domain=LegalDomain.CIVIL)

with open("tests/fact_templates/scenarios.json", "r", encoding="utf-8") as f:
    SCENARIOS = json.load(f)

print("=" * 90)
print("事实生成器深度压力测试：7 场景 × 62 HK 规则")
print("=" * 90)

for name, sc in SCENARIOS.items():
    print(f"\n{'─'*90}")
    print(f"【{name}】{sc['description']}")
    print(f"  预期深度: {sc['expected_depth']}")
    
    state = IRState(domain=LegalDomain.CIVIL, jurisdiction="HK")
    for fdata in sc["facts"]:
        state.facts[fdata["id"]] = LegalFact(
            fdata["id"],
            extraction_confidence=fdata["confidence"]
        )
    
    ev = FixpointEvaluator(HK_RULES, CONFIG)
    result = ev.evaluate(state)
    
    # Metrics
    active_claims = {cid: c for cid, c in result.claims.items() if c.confidence > 0}
    rebutted_claims = {cid: c for cid, c in result.claims.items() if c.confidence == 0}
    
    # Path depth = number of unique rules applied
    depth = len(result.rules_applied)
    
    # Chain depth: find longest dependency chain
    max_chain = 0
    for claim_id in active_claims:
        chain = 1
        for rule_id in result.rules_applied:
            rule = {r.id: r for r in HK_RULES}.get(rule_id)
            if rule and claim_id in str(rule.head_claim):
                chain += len([e for e in rule.exception_chain if e in result.rules_applied])
        max_chain = max(max_chain, chain)
    
    print(f"  迭代次数: {result.iteration_count}  |  触发规则: {depth}  |  链深度: {max_chain}")
    print(f"  活跃主张: {len(active_claims)}  |  反驳拦截: {len(rebutted_claims)}")
    
    # Show claims sorted by confidence
    all_claims = sorted(result.claims.values(), key=lambda c: c.confidence, reverse=True)
    for c in all_claims[:6]:
        tag = ""
        if c.confidence == 0:
            tag = " [REBUTTED]"
        elif c.requires_human_review:
            tag = " [⚠ REVIEW]"
        elif c.confidence >= 0.5:
            tag = " [STRONG]"
        print(f"    {c.id:50s} conf={c.confidence:.2f}{tag}")
    
    # Rebuttal detail
    if result.rebuttal_log:
        print(f"  Rebuttal详情:")
        for log in result.rebuttal_log:
            print(f"    ⚡ {log['claim_id'][:50]} ← {log['trigger_fact']}")
    
    if depth < 3:
        print(f"  ⚠ 深度不足({depth}<3): 事实未能触发深层逻辑链——建议注入条件性/矛盾性事实")

print(f"\n{'='*90}")
print(f"全场景通过")
