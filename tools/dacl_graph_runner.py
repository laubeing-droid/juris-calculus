#!/usr/bin/env python3
"""Build and audit a typed DACL overlay graph from legal rules and facts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml
from compiler_core.dacl_graph import DACLGraph, build_dacl_graph
from compiler_core.types import LegalRule


def run(source: str | Path, out: str | Path | None = None) -> Dict[str, Any]:
    source_path = _resolve(source)
    data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    raw_rules = data.get("rules", [])
    rules = [_legal_rule_from_dict(item) for item in raw_rules if isinstance(item, dict)]
    graph = build_dacl_graph(rules)
    audit = graph.audit()
    result = {
        "source": str(source_path),
        "node_count": audit["node_count"],
        "edge_count": audit["edge_count"],
        "finding_count": audit["finding_count"],
        "blocking_count": audit["blocking_count"],
        "status": audit["status"],
        "findings": [f for f in audit["findings"] if f.get("issue") != "ORPHAN_NODE"],
        "graph": graph.to_dict() if not out else None,
    }
    if out:
        out_path = _resolve(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        result["out"] = str(out_path)
    return result


def _legal_rule_from_dict(data: Dict[str, Any]) -> LegalRule:
    return LegalRule(
        id=str(data.get("id", "")),
        premise_atoms=[str(item) for item in data.get("premise_atoms", []) or []],
        head_claim=str(data.get("head_claim", "")),
        exception_chain=[str(item) for item in data.get("exception_chain", []) or []],
        attacks=[str(item) for item in data.get("attacks", []) or []],
        priority_over=[str(item) for item in data.get("priority_over", []) or []],
        source_anchor=str(data.get("source_anchor", "")),
        valid_from=str(data.get("valid_from", "")),
        valid_to=str(data.get("valid_to", "")),
        jurisdiction=str(data.get("jurisdiction", "")),
        authority_rank=str(data.get("authority_rank", "")),
    )


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and audit a typed DACL graph from a rule YAML file.")
    parser.add_argument("source")
    parser.add_argument("--out")
    parser.add_argument("--verify-against-horn", action="store_true", help="Compare DACL graph claims against Horn evaluator output.")
    args = parser.parse_args()
    report = run(args.source, out=args.out)
    if args.verify_against_horn:
        from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
        from compiler_core.types import IRState, LegalDomain, LegalFact
        rules = load_rules_from_yaml(str(_resolve(args.source)))
        state = IRState(domain=LegalDomain.CIVIL, jurisdiction="test")
        state.facts["contract_exists"] = LegalFact(id="contract_exists", description="contract_exists", extraction_confidence=1.0)
        try:
            evaluator = FixpointEvaluator(rules=rules)
            eval_result = evaluator.evaluate(state)
            horn_claims = {claim.id for claim in eval_result.claims.values() if claim.confidence > 0}
            dacl_claim_ids = {node.node_id for node in report.get("graph", {}).get("nodes", {}).values() if node.get("type") == "Claim"} if report.get("graph") else set()
            divergence = bool(horn_claims or dacl_claim_ids) and horn_claims != dacl_claim_ids
            report["horn_claim_count"] = len(horn_claims)
            report["dacl_claim_count"] = len(dacl_claim_ids)
            report["compilation_divergence"] = divergence
            report["status"] = "COMPILATION_DIVERGENCE" if divergence else report["status"]
        except Exception as exc:
            report["horn_error"] = str(exc)
    print(json.dumps({k: v for k, v in report.items() if k != "graph"}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
