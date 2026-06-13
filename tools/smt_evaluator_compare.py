#!/usr/bin/env python3
"""Side-by-side SMT constraint check against Horn evaluator output."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.smt_sidecar import limitation_constraint, money_cap_constraint, SMTSidecar
from compiler_core.types import IRState, LegalFact, LegalDomain, LegalRule


def extract_constraints(rules: List[LegalRule]) -> List[Dict[str, Any]]:
    constraints: List[Dict[str, Any]] = []
    for rule in rules:
        if rule.valid_from and rule.valid_to and rule.valid_from > rule.valid_to:
            constraints.append({
                "name": f"temporal_{rule.id}",
                "op": "<=",
                "left": rule.valid_from,
                "right": rule.valid_to,
            })
        if rule.authority_rank and rule.authority_rank.lower() in {"statute", "regulation", "constitution"}:
            for prio in rule.priority_over or []:
                constraints.append({
                    "name": f"priority_{rule.id}_over_{prio}",
                    "op": "mutually_exclusive",
                    "states": {rule.id: True, prio: False},
                })
    return constraints


def compare(source: str | Path, facts: Dict[str, float] | None = None, jurisdiction: str = "zh_CN") -> Dict[str, Any]:
    source_path = _resolve(source)
    rules = load_rules_from_yaml(str(source_path))
    state = IRState(domain=LegalDomain.CIVIL, jurisdiction=jurisdiction)
    default_facts = facts or {"breach_alleged": 1.0, "contract_exists": 1.0}
    for fid, conf in default_facts.items():
        state.facts[fid] = LegalFact(id=fid, description=fid, extraction_confidence=conf)

    evaluator = FixpointEvaluator(rules=rules)
    try:
        result = evaluator.evaluate(state)
        horn_claims = {claim.id: claim.confidence for claim in result.claims.values() if claim.confidence > 0}
    except Exception as exc:
        horn_claims = {"ERROR": str(exc)}

    smt_constraints = extract_constraints(rules)
    smt_constraints.append(limitation_constraint("2021-01-01", "2026-06-13", 3 * 365, "limitation_default"))

    sidecar = SMTSidecar()
    smt_result = sidecar.check(smt_constraints)

    divergences: List[Dict[str, Any]] = []
    if smt_result.status == "UNSAT":
        for claim_id in horn_claims:
            divergences.append({
                "claim": claim_id,
                "horn_confidence": horn_claims[claim_id],
                "smt_status": "CONTRADICTION",
                "unsat_core": smt_result.unsat_core,
            })

    report = {
        "source": str(source_path),
        "jurisdiction": jurisdiction,
        "horn_claims": horn_claims,
        "horn_claim_count": len(horn_claims),
        "smt_status": smt_result.status,
        "smt_constraint_count": len(smt_constraints),
        "smt_unsat_core": smt_result.unsat_core,
        "divergence_count": len(divergences),
        "divergences": divergences,
        "smt_available": sidecar.available,
        "status": "PASS" if not divergences else "DIVERGENCE_DETECTED",
    }
    return report


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p


def main() -> int:
    parser = argparse.ArgumentParser(description="Side-by-side SMT vs Horn evaluator comparison.")
    parser.add_argument("source")
    parser.add_argument("--jurisdiction", default="zh_CN")
    parser.add_argument("--facts-json")
    args = parser.parse_args()
    facts = None
    if args.facts_json:
        facts = json.loads(args.facts_json)
    report = compare(args.source, facts=facts, jurisdiction=args.jurisdiction)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
