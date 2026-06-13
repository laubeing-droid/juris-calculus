#!/usr/bin/env python3
"""Automated promotion gate for neural-to-symbolic candidate promotion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.promotion_candidate import PromotionCandidate, PromotionState, required_gates


def evaluate_candidate(candidate: Dict[str, Any], available_gate_results: Dict[str, str] | None = None) -> Dict[str, Any]:
    gates = required_gates()
    results: Dict[str, str] = dict(available_gate_results or {})
    issues: List[Dict[str, Any]] = []
    state = PromotionState.DRAFT

    cid = candidate.get("candidate_id", "")
    source_spans = candidate.get("source_spans", []) or []
    confidence = candidate.get("confidence", 0.0)

    for gate in gates:
        result = results.get(gate, "MISSING")
        if result not in {"PASS", "NOT_APPLICABLE"}:
            issues.append({"gate": gate, "result": result, "issue": f"GATE_{result}"})

    if not source_spans:
        issues.append({"gate": "source_anchor", "result": "MISSING_SOURCE_SPANS", "issue": "SOURCE_SPANS_EMPTY"})
    if confidence < 0.5:
        issues.append({"gate": "confidence", "result": "LOW_CONFIDENCE", "issue": "CONFIDENCE_BELOW_0_5"})
    if confidence < 0.01:
        issues.append({"gate": "confidence", "result": "INVALID_CONFIDENCE", "issue": "CONFIDENCE_TOO_LOW"})

    hard = [i for i in issues if i["issue"].startswith("GATE_FAIL") or i["issue"] == "SOURCE_SPANS_EMPTY"]
    if hard:
        state = PromotionState.BLOCKED
    elif issues:
        if any("MISSING" in i["result"] for i in issues):
            state = PromotionState.SHADOW_ONLY
        else:
            state = PromotionState.REPAIRABLE
    else:
        rollback = candidate.get("rollback_trigger", "")
        if all(v in {"PASS", "NOT_APPLICABLE"} for v in results.values()) and rollback:
            state = PromotionState.FINAL_AUTOMATED
        elif all(v in {"PASS", "NOT_APPLICABLE"} for v in results.values()):
            state = PromotionState.PROMOTABLE
        else:
            state = PromotionState.VALIDATED

    return {
        "candidate_id": cid,
        "state": state.value,
        "gate_count": len(gates),
        "passed_gates": sum(1 for v in results.values() if v in {"PASS", "NOT_APPLICABLE"}),
        "finding_count": len(issues),
        "issues": issues,
        "status": "PASS" if state in {PromotionState.PROMOTABLE, PromotionState.FINAL_AUTOMATED, PromotionState.VALIDATED} else "FAIL",
    }


def evaluate_batch(candidates_path: str | Path, gate_results: Dict[str, str] | None = None) -> Dict[str, Any]:
    path = Path(candidates_path)
    records: List[Dict[str, Any]] = []
    count = 0
    passed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        count += 1
        candidate = json.loads(line)
        report = evaluate_candidate(candidate, gate_results)
        records.append(report)
        if report["status"] == "PASS":
            passed += 1

    return {
        "path": str(path),
        "candidate_count": count,
        "passed_count": passed,
        "records": records,
        "status": "PASS" if passed == count else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Promotion gate for neural-to-symbolic candidate promotion.")
    parser.add_argument("candidates", nargs="?")
    parser.add_argument("--single", action="store_true", help="Evaluate a single inline candidate from stdin.")
    parser.add_argument("--source-anchor", default="PASS")
    parser.add_argument("--type-check", default="PASS")
    parser.add_argument("--relevance", default="PASS")
    parser.add_argument("--smt", default="PASS")
    parser.add_argument("--shadow", default="PASS")
    parser.add_argument("--neural-contract", default="PASS")
    parser.add_argument("--promotion-policy", default="PASS")
    args = parser.parse_args()

    gate_results = {
        "source_anchor": args.source_anchor,
        "type_check": args.type_check,
        "relevance_benchmark": args.relevance,
        "smt_sidecar": args.smt,
        "shadow_divergence": args.shadow,
        "neural_contract_auditor": args.neural_contract,
        "promotion_policy": args.promotion_policy,
    }

    if args.single:
        candidate = json.loads(sys.stdin.read())
        report = evaluate_candidate(candidate, gate_results)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "PASS" else 1
    elif args.candidates:
        report = evaluate_batch(args.candidates, gate_results)
        print(json.dumps({k: v for k, v in report.items() if k != "records"}, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "PASS" else 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
