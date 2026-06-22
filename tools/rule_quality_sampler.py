"""Sample rules for quality audit + exception_chain completeness."""
import yaml, random
random.seed(42)
with open('configs/zh_CN/rules.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
rules = data.get('rules', [])
sample = random.sample(rules, min(200, len(rules)))
with_exc = sum(1 for r in rules if r.get('exception_chain') and len(r['exception_chain']) > 0)
need_exc = sum(1 for r in rules if any(kw in r.get('head_claim', '') for kw in ['除外', '但是', '除非', '例外', '不包括']))
print(f"=== Exception Chain Completeness ===")
print(f"With exception_chain: {with_exc}/{len(rules)} ({with_exc/len(rules)*100:.1f}%)")
print(f"Needing exception (keywords): {need_exc}")
print(f"Gap: ~{need_exc - with_exc} rules may need exception_chain")
