"""Concept disambiguator — find similar concepts for merging."""
import yaml
from collections import Counter


def edit_distance(s1, s2):
    if len(s1) < len(s2):
        return edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


with open('configs/zh_CN/rules.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
rules = data.get('rules', [])

# Count concept frequency
concept_freq = Counter()
for r in rules:
    for c in r.get('concepts', []):
        if isinstance(c, str):
            concept_freq[c] += 1

concepts = list(concept_freq.keys())
similar = []
for i in range(len(concepts)):
    for j in range(i + 1, min(len(concepts), i + 500)):
        c1, c2 = concepts[i], concepts[j]
        if abs(len(c1) - len(c2)) <= 2:
            dist = edit_distance(c1, c2)
            if 0 < dist <= 2:
                similar.append((c1, concept_freq[c1], c2, concept_freq[c2], dist))

similar.sort(key=lambda x: x[4])
print(f"Total concepts: {len(concepts)}")
print(f"Similar pairs (edit distance <= 2): {len(similar)}")
for c1, f1, c2, f2, d in similar[:30]:
    print(f"  [{d}] {c1}({f1}) <-> {c2}({f2})")
