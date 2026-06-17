"""Check rule freshness: valid_from/valid_to/source_anchor coverage."""
import yaml
with open('configs/zh_CN/rules.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
rules = data.get('rules', [])
with_from = sum(1 for r in rules if r.get('valid_from'))
with_to = sum(1 for r in rules if r.get('valid_to'))
with_anchor = sum(1 for r in rules if r.get('source_anchor'))
print(f"=== Rule Freshness ===")
print(f"Total: {len(rules)}")
print(f"valid_from: {with_from} ({with_from/len(rules)*100:.1f}%)")
print(f"valid_to: {with_to} ({with_to/len(rules)*100:.1f}%)")
print(f"source_anchor: {with_anchor} ({with_anchor/len(rules)*100:.1f}%)")
