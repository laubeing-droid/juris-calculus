#!/usr/bin/env python3
"""
merge_us_legal_data.py — 合并所有美国法律术语数据为单一文件
═══════════════════════════════════════════════════════════════════
合并来源:
  1. US_Adapter.yaml (81条Horn规则)
  2. L0_overrides_us.yaml (86条约束规则)  
  3. llm_distilled_full.json (419条LLM蒸馏术语)
  4. state_combined_terms.json (3,259条原始术语)
  5. hk_us_divergence_matrix.json (对撞结果)
═══════════════════════════════════════════════════════════════════
"""
import json, yaml, os
from pathlib import Path
from collections import OrderedDict

EN_US = Path(__file__).parent.parent / "configs" / "en_US"

# ─── 加载所有来源 ───
def jload(path):
    with open(EN_US / path, 'r', encoding='utf-8') as f:
        return json.load(f)

def yload(path):
    with open(EN_US / path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

adapter = yload("US_Adapter.yaml")
overrides = yload("L0_overrides_us.yaml")
llm_distilled = jload("llm_distilled_full.json")
raw_terms = jload("state_combined_terms.json")
matrix = jload("hk_us_divergence_matrix.json")

# ─── 构建统一输出 ───
output = OrderedDict()

output["metadata"] = {
    "title": "United States Legal Data — Complete Corpus",
    "version": "v1.2.0",
    "sources": ["uscourts.gov", "justice.gov", "WA Federal", "WI State", "NJ State", "WA OCR Bilingual", "Armenian Glossary"],
    "statistics": {
        "horn_rules": len(adapter["rules"]),
        "constraint_rules": len(overrides.get("constraint_rules", [])),
        "llm_distilled_terms": len(llm_distilled),
        "raw_glossary_terms": len(raw_terms),
        "collision_entries": len(matrix.get("results", []))
    }
}

# ─── 1. Horn rules (from US_Adapter.yaml) ───
output["horn_rules"] = []
for r in adapter["rules"]:
    output["horn_rules"].append({
        "id": r["id"],
        "premise_atoms": r.get("premise_atoms", []),
        "head_claim": r.get("head_claim", ""),
        "concepts": r.get("concepts", []),
        "l0_primitive": r.get("l0_primitive", "?"),
        "l1_domain": r.get("l1_domain", ""),
        "structural_chain": r.get("structural_chain", ""),
        "namespace": r.get("namespace", "us_general"),
    })

# ─── 2. Constraint rules ───
output["constraint_rules"] = overrides.get("constraint_rules", [])

# ─── 3. L0 overrides ───
output["l0_overrides"] = overrides.get("overrides", {})

# ─── 4. Compiled concepts (from LLM-distilled) ───
output["compiled_concepts"] = []
for t in llm_distilled:
    output["compiled_concepts"].append({
        "term": t["term"],
        "l0_primitive": t.get("l0", ""),
        "structural_chain": t.get("chain", ""),
        "horn_premise_atom": t.get("horn", ""),
        "domains": t.get("domains", []),
        "cross_border_relevant": t.get("xb", False),
        "prc_mapping": t.get("prc", ""),
    })

# ─── 5. Raw glossary (deduplicated) ───
output["raw_glossary"] = sorted(raw_terms)

# ─── 6. Collision matrix summary ───
s = matrix.get("metadata", {}).get("stats", {})
output["collision_summary"] = {
    "total_terms_pressed": matrix.get("metadata", {}).get("total_terms", 0),
    "stats": s
}

# ─── 7. Domain distribution ───
from collections import Counter
l0_dist = Counter(t.get("l0", "?") for t in llm_distilled)
domain_dist = Counter(t.get("l1_domain", "?") for t in adapter["rules"])
output["l0_distribution"] = dict(l0_dist.most_common())
output["domain_distribution"] = dict(domain_dist.most_common())

# ─── 写入 ───
output_path = EN_US / "US_complete.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

size = os.path.getsize(output_path)
print(f"Written: {output_path} ({size:,} bytes)")
print(f"\nContents:")
print(f"  horn_rules:        {len(output['horn_rules'])}")
print(f"  constraint_rules:  {len(output['constraint_rules'])}")
print(f"  compiled_concepts: {len(output['compiled_concepts'])}")
print(f"  raw_glossary:      {len(output['raw_glossary'])}")
print(f"  collision_results: {output['collision_summary']['total_terms_pressed']:,}")
print(f"\nL0 distribution:")
for l0, cnt in l0_dist.most_common():
    print(f"  {l0}: {cnt}")
