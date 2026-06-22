"""MDL vs False Positive empirical analysis."""
import yaml, math
from collections import Counter

with open('configs/zh_CN/rules.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
rules = data.get('rules', [])

total_concepts = len(set(c for r in rules for c in r.get('concepts', []) if isinstance(c, str)))


def mdl(rule):
    p = len(rule.get('premise_atoms', []))
    k = len(rule.get('exception_chain', []))
    c = len([x for x in rule.get('concepts', []) if isinstance(x, str)])
    k_bits = k * math.log2(max(1, k) + 1) if k > 0 else 0
    c_bits = c * math.log2(max(1, total_concepts)) if c > 0 else 0
    return p + k_bits + c_bits


# Compute MDL for all rules
mdls = [(r['id'], mdl(r), len(r.get('premise_atoms', [])), r.get('namespace', '?')) for r in rules]
mdls.sort(key=lambda x: x[1])

# Statistics
mdl_values = [m[1] for m in mdls]
avg_mdl = sum(mdl_values) / len(mdl_values)
low_mdl = [m for m in mdls if m[1] < 3]
high_mdl = [m for m in mdls if m[1] > 10]

print(f"=== MDL Analysis ===")
print(f"Total rules: {len(rules)}")
print(f"Avg MDL: {avg_mdl:.2f} bits")
print(f"Low MDL (<3): {len(low_mdl)} ({len(low_mdl)/len(rules)*100:.1f}%)")
print(f"High MDL (>10): {len(high_mdl)} ({len(high_mdl)/len(rules)*100:.1f}%)")
print(f"\nLowest MDL rules (most general, highest FP risk):")
for rid, m, p, ns in low_mdl[:10]:
    print(f"  {rid}: MDL={m:.1f}, premises={p}, ns={ns}")
print(f"\nHighest MDL rules (most specific):")
for rid, m, p, ns in high_mdl[-10:]:
    print(f"  {rid}: MDL={m:.1f}, premises={p}, ns={ns}")
