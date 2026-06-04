#!/usr/bin/env python3
"""通用规则剪枝器: 检测被 rebuttal/constraint 覆盖的规则 → 移入 provenance.yaml"""
import sys, yaml
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

def load_coverage() -> tuple:
    """加载 constraint_rules + rebuttal_criteria 覆盖的事实集"""
    with open(BASE / "configs/L0_overrides_hk.yaml", encoding="utf-8") as f:
        ov = yaml.safe_load(f)
    constraint_facts = {cr['trigger_fact'] for cr in ov.get('constraint_rules', [])}

    with open(BASE / "configs/core_ontology.yaml", encoding="utf-8") as f:
        onto = yaml.safe_load(f)
    rebuttal_facts = set()
    for c in onto.get("concepts", {}).values():
        for rb in c.get("attributes", {}).get("rebuttal_criteria", []):
            if isinstance(rb, dict):
                rebuttal_facts.add(rb.get("fact", ""))
    return constraint_facts, rebuttal_facts

def scan(rules_path: str) -> list:
    """扫描 rules.yaml，返回可剪枝的规则列表"""
    with open(rules_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    rules = data["rules"]

    constraint_facts, rebuttal_facts = load_coverage()
    all_premises = set()
    for r in rules:
        all_premises.update(r.get("premise_atoms", []))

    candidates = []
    for r in rules:
        concepts = set(r.get("concepts", []))
        head = r.get("head_claim", "")
        is_referenced = head in all_premises
        covered_by_constraint = bool(concepts & constraint_facts)
        covered_by_rebuttal = bool(concepts & rebuttal_facts)

        if (covered_by_constraint or covered_by_rebuttal) and not is_referenced:
            # 假阳性过滤: 检测规则是否是正面规则 (premise_atoms 不含否定词)
            has_positive_logic = any(
                "MustPay" in a or "Entitled" in a or "MayClaim" in a
                for a in r.get("premise_atoms", [])
            )
            if not has_positive_logic:
                candidates.append({
                    "id": r["id"],
                    "head": head,
                    "concepts": sorted(concepts),
                    "covered_by": "constraint" if covered_by_constraint else "rebuttal",
                    "premise_atoms": r.get("premise_atoms", []),
                })

    return candidates

def prune(rules_path: str, dry_run: bool = True) -> dict:
    """执行剪枝: 移除候选规则 → provenance.yaml"""
    candidates = scan(rules_path)

    if not candidates:
        return {"pruned": 0, "candidates": []}

    if dry_run:
        return {"pruned": 0, "candidates": candidates, "dry_run": True}

    # 正式剪枝
    with open(rules_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    pruned_ids = {c["id"] for c in candidates}
    pruned_rules = [r for r in data["rules"] if r["id"] in pruned_ids]
    data["rules"] = [r for r in data["rules"] if r["id"] not in pruned_ids]

    # 保存 rules
    with open(rules_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, width=200)

    # 追加 provenance
    prov_path = Path(rules_path).parent / "provenance.yaml"
    with open(prov_path, encoding="utf-8") as f:
        prov = yaml.safe_load(f) or {"metadata": {}, "pruned_rules": []}

    for r in pruned_rules:
        prov.setdefault("pruned_rules", []).append({
            "id": r["id"],
            "original_premise_atoms": r.get("premise_atoms", []),
            "original_head_claim": r.get("head_claim", ""),
            "replaced_by": f"constraint_rules or rebuttal_criteria (concepts: {r.get('concepts', [])})",
        })

    with open(prov_path, "w", encoding="utf-8") as f:
        yaml.dump(prov, f, allow_unicode=True, sort_keys=False, width=200)

    return {"pruned": len(pruned_rules), "candidates": candidates, "rules_remaining": len(data["rules"])}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="通用规则剪枝器")
    parser.add_argument("--rules", default="configs/hk/rules.yaml", help="规则文件路径")
    parser.add_argument("--dry-run", action="store_true", default=True, help="试运行(默认)")
    parser.add_argument("--apply", action="store_true", help="执行剪枝")
    args = parser.parse_args()

    if args.apply:
        result = prune(args.rules, dry_run=False)
        print(f"剪枝: {result['pruned']} 条规则 → provenance.yaml")
        print(f"剩余: {result['rules_remaining']} 条")
    else:
        candidates = scan(args.rules)
        print(f"候选剪枝: {len(candidates)} 条")
        for c in candidates:
            print(f"  {c['id']:30s} head={c['head'][:35]:35s} via={c['covered_by']}")
        if not candidates:
            print("  ✅ 无需剪枝")
        print(f"\n确认后执行: python tools/pruner.py --rules configs/hk/rules.yaml --apply")
