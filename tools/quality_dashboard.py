"""Quality dashboard — comprehensive data quality report."""
import yaml
from collections import Counter

with open('configs/zh_CN/rules.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
rules = data.get('rules', [])

total = len(rules)
claims = set(r.get('head_claim', '')[:80] for r in rules)
modalities = Counter(r.get('norm_modality', '?') for r in rules)
namespaces = Counter(r.get('namespace', '?') for r in rules)
with_exc = sum(1 for r in rules if r.get('exception_chain'))
with_anchor = sum(1 for r in rules if r.get('source_anchor'))
confs = [r.get('modality_confidence', 0) for r in rules]
qualities = Counter(r.get('data_quality', '?') for r in rules)

all_concepts = set()
for r in rules:
    for c in r.get('concepts', []):
        if isinstance(c, str):
            all_concepts.add(c)

print("=" * 60)
print("JC DATA QUALITY DASHBOARD")
print("=" * 60)
print(f"Total rules:        {total}")
print(f"Unique claims:      {len(claims)} ({len(claims)/total*100:.1f}%)")
print(f"Unique concepts:    {len(all_concepts)}")
print(f"Avg confidence:     {sum(confs)/len(confs):.3f}")
print(f"With exception:     {with_exc} ({with_exc/total*100:.1f}%)")
print(f"With source_anchor: {with_anchor} ({with_anchor/total*100:.1f}%)")
print(f"\nModality breakdown:")
for m, cnt in modalities.most_common():
    print(f"  {m:20s} {cnt:>6} ({cnt/total*100:.1f}%)")
print(f"\nTop namespaces:")
for ns, cnt in namespaces.most_common(10):
    print(f"  {ns:20s} {cnt:>6} ({cnt/total*100:.1f}%)")
print(f"\nData quality:")
for q, cnt in qualities.most_common():
    print(f"  {q:20s} {cnt:>6} ({cnt/total*100:.1f}%)")
