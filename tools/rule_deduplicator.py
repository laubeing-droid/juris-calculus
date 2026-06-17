"""Find duplicate rules by head_claim Jaccard similarity."""
import yaml
from itertools import combinations


def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


with open('configs/zh_CN/rules.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
rules = data.get('rules', [])

duplicates = []
for r1, r2 in combinations(rules[:500], 2):
    c1, c2 = r1.get('head_claim', ''), r2.get('head_claim', '')
    if len(c1) > 20 and len(c2) > 20:
        sim = jaccard(c1, c2)
        if sim > 0.8:
            duplicates.append((r1['id'], r2['id'], round(sim, 2)))

print(f"Duplicates found (sample 500): {len(duplicates)}")
for d in duplicates[:20]:
    print(f"  {d[0]} <-> {d[1]} (sim={d[2]})")
