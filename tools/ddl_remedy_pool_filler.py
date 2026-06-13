#!/usr/bin/env python3
"""Auto-fill reparation_chain_pool for Chinese legal rules by concept matching."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml


REMEDY_POOL_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "违约责任": {
        "type": "remedy_pool",
        "trigger": "breach_of_contract",
        "alternatives": [
            {"claim": "SpecificPerformance", "selector": "creditor"},
            {"claim": "Damages", "selector": "creditor"},
            {"claim": "Cure", "selector": "creditor"},
        ],
    },
    "侵权责任": {
        "type": "remedy_pool",
        "trigger": "tort_liability",
        "alternatives": [
            {"claim": "Restitution", "selector": "creditor"},
            {"claim": "Damages", "selector": "creditor"},
            {"claim": "Injunction", "selector": "creditor"},
        ],
    },
    "国家赔偿": {
        "type": "remedy_pool",
        "trigger": "state_compensation",
        "alternatives": [
            {"claim": "AdministrativeReview", "selector": "subject"},
            {"claim": "StateCompensation", "selector": "subject"},
        ],
    },
    "执行": {
        "type": "remedy_pool",
        "trigger": "enforcement_action",
        "alternatives": [
            {"claim": "EnforcementApplication", "selector": "creditor"},
            {"claim": "EnforcementObjection", "selector": "debtor"},
        ],
    },
}


def fill_remedy_pools(rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    filled: List[Dict[str, Any]] = []
    unfilled: List[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rid = str(rule.get("id", ""))
        concepts = [str(c).strip() for c in rule.get("concepts", []) or []]
        namespace = str(rule.get("namespace", ""))
        matched = None
        for key, template in REMEDY_POOL_TEMPLATES.items():
            if any(key in c for c in concepts):
                matched = template
                break
        if not matched:
            for key, template in REMEDY_POOL_TEMPLATES.items():
                if key in namespace:
                    matched = template
                    break
        if matched:
            filled.append({"rule_id": rid, "reparation_chain_pool": [matched], "source": "concept_match"})
        else:
            unfilled.append(rid)
    return {
        "rule_count": len(rules),
        "filled_count": len(filled),
        "unfilled_count": len(unfilled),
        "filled": filled,
        "unfilled": unfilled[:50],
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-fill DDL reparation_chain_pool by concept matching.")
    parser.add_argument("source")
    args = parser.parse_args()
    p = Path(args.source)
    rules = yaml.safe_load(p.read_text(encoding="utf-8")).get("rules", [])
    report = fill_remedy_pools(rules)
    print(json.dumps({k: v for k, v in report.items() if k != "filled"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
