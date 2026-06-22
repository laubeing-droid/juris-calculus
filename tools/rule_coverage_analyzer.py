"""Rule coverage analyzer: unique claims, namespace distribution, concept stats."""
import yaml
from collections import Counter

with open('configs/zh_CN/rules.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
rules = data.get('rules', [])

claims = Counter(r.get('head_claim', '')[:80] for r in rules)
namespaces = Counter(r.get('namespace', 'unknown') for r in rules)
modalities = Counter(r.get('norm_modality', 'UNKNOWN') for r in rules)
confs = [r.get('modality_confidence', 0) for r in rules]
with_exc = sum(1 for r in rules if r.get('exception_chain'))
all_concepts = set()
for r in rules:
    for c in r.get('concepts', []):
        if isinstance(c, str):
            all_concepts.add(c)
qualities = Counter(r.get('data_quality', 'UNKNOWN') for r in rules)

print(f"=== Rule Coverage Analyzer ===")
print(f"Total rules: {len(rules)}")
print(f"Unique head_claims: {len(claims)} ({len(claims)/len(rules)*100:.1f}%)")
print(f"With exception_chain: {with_exc} ({with_exc/len(rules)*100:.1f}%)")
print(f"Unique concepts: {len(all_concepts)}")
print(f"Avg confidence: {sum(confs)/len(confs):.3f}")
print(f"\nNamespace distribution:")
for ns, cnt in namespaces.most_common(15):
    print(f"  {ns:20s}: {cnt:>5} ({cnt/len(rules)*100:.1f}%)")
print(f"\nModality distribution:")
for m, cnt in modalities.most_common():
    print(f"  {m:20s}: {cnt:>5} ({cnt/len(rules)*100:.1f}%)")
print(f"\nData quality distribution:")
for q, cnt in qualities.most_common():
    print(f"  {q:20s}: {cnt:>5} ({cnt/len(rules)*100:.1f}%)")
print(f"\nTop 10 duplicated claims:")
for claim, cnt in claims.most_common(10):
    if cnt > 1:
        print(f"  [{cnt}x] {claim[:70]}")
