"""Detect rule conflicts: same head_claim different modality."""
import yaml
from collections import defaultdict

with open('configs/zh_CN/rules.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
rules = data.get('rules', [])

by_claim = defaultdict(list)
for r in rules:
    claim = r.get('head_claim', '')[:80]
    by_claim[claim].append(r)

conflicts = []
for claim, group in by_claim.items():
    if len(group) > 1:
        modalities = set(r.get('norm_modality', '') for r in group)
        if len(modalities) > 1:
            conflicts.append({'claim': claim, 'count': len(group), 'modalities': list(modalities), 'ids': [r['id'] for r in group[:5]]})

print(f"Total rules: {len(rules)}")
print(f"Unique head_claims: {len(by_claim)}")
print(f"Conflicts (same claim, different modality): {len(conflicts)}")
for c in conflicts[:10]:
    print(f"  {c['ids']}: {c['claim'][:60]} [{', '.join(c['modalities'])}]")
