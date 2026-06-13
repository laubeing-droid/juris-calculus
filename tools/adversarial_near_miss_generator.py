#!/usr/bin/env python3
"""LexGuard-style perturbation template generator for legal relevance sensitivity."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent


PERTURBATION_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "SHOULD_NOT_CHANGE": {
        "party_name_swap": {"kind": "SHOULD_NOT_CHANGE", "desc": "Swap party name to unrelated entity", "mutate": {"base_facts": {"party_name": "original"}, "mutated_facts": {"party_name": "X_CORP"}}, "expected": {"same_claims_as_base": True}},
        "location_change": {"kind": "SHOULD_NOT_CHANGE", "desc": "Change venue location", "mutate": {"base_facts": {"venue": "Beijing"}, "mutated_facts": {"venue": "Shanghai"}}, "expected": {"same_claims_as_base": True}},
        "stylistic_reformulation": {"kind": "PARAPHRASE_INVARIANCE", "desc": "Rephrase facts without changing legal content", "mutate": {"base_facts": {"text": "defendant breached the contract"}, "mutated_facts": {"text": "the contract was not honored by the defendant"}}, "expected": {"same_claims_as_base": True}},
        "irrelevant_expert": {"kind": "SHOULD_NOT_CHANGE", "desc": "Add irrelevant expert opinion", "mutate": {"base_facts": {}, "mutated_facts": {"expert_opinion": "Prof. X declares the law unfair"}}, "expected": {"same_claims_as_base": True}},
    },
    "SHOULD_CHANGE": {
        "payment_status_flip": {"kind": "SHOULD_CHANGE", "desc": "Flip payment from completed to not completed", "mutate": {"base_facts": {"payment_completed": True}, "mutated_facts": {"payment_completed": False}}, "expected": {"must_remove": ["Breach_Established"], "must_include": ["No_Breach_For_Nonpayment"]}},
        "intent_change": {"kind": "SHOULD_CHANGE", "desc": "Change intent from negligent to intentional", "mutate": {"base_facts": {"intent": "negligent"}, "mutated_facts": {"intent": "intentional"}}, "expected": {"must_include": ["Intentional_Tort"]}},
        "add_exception_defense": {"kind": "EXCEPTION_SENSITIVITY", "desc": "Add self-defense fact", "mutate": {"base_facts": {}, "mutated_facts": {"defense": "self_defense"}, "expected": {"must_include": ["Defense_Available"]}}},
    },
    "STATUTE_CONFUSION": {
        "inject_similar_statute": {"kind": "STATUTE_CONFUSION", "desc": "Inject irrelevant similar statute", "mutate": {"base_facts": {}, "mutated_facts": {"irrelevant_statute": "Criminal Code Article 264 (theft)"}}, "expected": {"same_claims_as_base": True}},
    },
    "TEMPORAL_SPLIT": {
        "statute_expired": {"kind": "TEMPORAL_SPLIT", "desc": "Move event to after statute expiry", "mutate": {"base_facts": {"event_date": "2022-01-01"}, "mutated_facts": {"event_date": "2025-01-01"}}, "expected": {"must_remove": ["Claim_May_Proceed"], "must_include": ["Claim_Time_Barred"]}},
    },
}


def generate_cases(base_facts: Dict[str, Any] | None = None, limit: int | None = None) -> Dict[str, Any]:
    facts = base_facts or {"contract_exists": True, "payment_due": True}
    cases: List[Dict[str, Any]] = []
    idx = 0
    for family, templates in PERTURBATION_TEMPLATES.items():
        for template_id, template in templates.items():
            idx += 1
            if limit and idx > limit:
                break
            case = {
                "id": f"near_miss_{template_id}_{idx:03d}",
                "kind": template["kind"],
                "template": template_id,
                "description": template["desc"],
                "base_facts": {**facts, **template["mutate"]["base_facts"]},
                "mutated_facts": {**facts, **template["mutate"]["mutated_facts"]},
                "expected": template["expected"],
            }
            cases.append(case)
        if limit and idx >= limit:
            break
    return {
        "case_count": len(cases),
        "status": "PASS",
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="LexGuard-style adversarial near-miss case generator.")
    parser.add_argument("--out")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    report = generate_cases(limit=args.limit)
    if args.out:
        import yaml
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(yaml.safe_dump(report, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(json.dumps({"out": str(out_path), "case_count": report["case_count"]}, ensure_ascii=False))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
