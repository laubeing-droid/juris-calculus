#!/usr/bin/env python3
"""Run relevance-sensitive symbolic benchmark fixtures."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator
from compiler_core.types import IRState, LegalDomain, LegalFact, LegalRule


def run_fixture(path: str | Path) -> Dict[str, Any]:
    fixture_path = _resolve(path)
    data = yaml.safe_load(fixture_path.read_text(encoding="utf-8")) or {}
    rules = [_rule(r) for r in data.get("rules", [])]
    base_claims = _claims_for(rules, data.get("base_facts", []), world_id="base")
    cases = []
    status = "PASS"
    for case in data.get("cases", []):
        claims = _claims_for(rules, case.get("facts", []), world_id=str(case.get("id", "case")))
        expected = case.get("expected", {})
        passed = _check(base_claims, claims, expected)
        if not passed:
            status = "FAIL"
        cases.append({
            "id": case.get("id"),
            "kind": case.get("kind"),
            "base_claims": sorted(base_claims),
            "claims": sorted(claims),
            "expected": expected,
            "status": "PASS" if passed else "FAIL",
        })
    metrics = _metrics(cases)
    return {
        "fixture": str(fixture_path),
        "case_count": len(cases),
        "status": status,
        "metrics": metrics,
        "cases": cases,
    }


def run_path(path: str | Path) -> Dict[str, Any]:
    target = _resolve(path)
    fixtures = list(_iter_fixtures(target))
    reports = [run_fixture(fixture) for fixture in fixtures]
    case_count = sum(report["case_count"] for report in reports)
    passed = sum(1 for report in reports for case in report["cases"] if case["status"] == "PASS")
    by_kind: Dict[str, Dict[str, int]] = {}
    for report in reports:
        for case in report["cases"]:
            kind = str(case.get("kind") or "UNKNOWN")
            by_kind.setdefault(kind, {"passed": 0, "total": 0})
            by_kind[kind]["total"] += 1
            if case["status"] == "PASS":
                by_kind[kind]["passed"] += 1
    metrics = {
        "overall_pass_rate": _rate(passed, case_count),
        "by_kind": {
            kind: {"pass_rate": _rate(v["passed"], v["total"]), **v}
            for kind, v in sorted(by_kind.items())
        },
        "invariance": _kind_rate(by_kind, ["SHOULD_NOT_CHANGE", "PARAPHRASE_INVARIANCE"]),
        "change_alignment": _kind_rate(by_kind, ["SHOULD_CHANGE", "EXCEPTION_SENSITIVITY", "TEMPORAL_SPLIT"]),
        "statute_confusion": _kind_rate(by_kind, ["STATUTE_CONFUSION"]),
    }
    return {
        "target": str(target),
        "fixture_count": len(fixtures),
        "case_count": case_count,
        "status": "PASS" if all(report["status"] == "PASS" for report in reports) else "FAIL",
        "metrics": metrics,
        "fixtures": reports,
    }


def compare_snapshot(report: Dict[str, Any], snapshot_path: str | Path) -> Dict[str, Any]:
    snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    current_cases = _case_index(report)
    snapshot_cases = _case_index(snapshot)
    regressions = []
    for case_id, snap_case in snapshot_cases.items():
        current = current_cases.get(case_id)
        if current is None:
            regressions.append({"case_id": case_id, "issue": "MISSING_CASE"})
            continue
        if current.get("claims") != snap_case.get("claims"):
            regressions.append({
                "case_id": case_id,
                "issue": "CLAIMS_CHANGED",
                "expected": snap_case.get("claims"),
                "actual": current.get("claims"),
            })
    return {
        "status": "PASS" if not regressions else "FAIL",
        "regression_count": len(regressions),
        "regressions": regressions,
    }


def _claims_for(rules: List[LegalRule], facts: List[str], world_id: str) -> Set[str]:
    state = IRState(world_id=world_id, domain=LegalDomain.CIVIL)
    for fact in facts:
        state.facts[fact] = LegalFact(fact, extraction_confidence=1.0)
    result = FixpointEvaluator(rules, DomainConfig(domain=LegalDomain.CIVIL)).evaluate(state)
    return {claim_id for claim_id, claim in result.claims.items() if claim.confidence > 0}


def _rule(raw: Dict[str, Any]) -> LegalRule:
    return LegalRule(
        id=raw["id"],
        premise_atoms=raw.get("premise_atoms", []),
        head_claim=raw.get("head_claim", ""),
        exception_chain=raw.get("exception_chain", []),
        concepts=raw.get("concepts", []),
        attacks=raw.get("attacks", []),
        source_anchor=raw.get("source_anchor", ""),
    )


def _check(base: Set[str], current: Set[str], expected: Dict[str, Any]) -> bool:
    if expected.get("same_claims_as_base"):
        return current == base
    if "must_add" in expected and not set(expected["must_add"]).issubset(current - base):
        return False
    if "must_remove" in expected and not set(expected["must_remove"]).issubset(base - current):
        return False
    if "must_include" in expected and not set(expected["must_include"]).issubset(current):
        return False
    if "must_exclude" in expected and set(expected["must_exclude"]) & current:
        return False
    return True


def _metrics(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(cases)
    passed = sum(1 for case in cases if case["status"] == "PASS")
    return {"pass_rate": _rate(passed, total), "passed": passed, "total": total}


def _iter_fixtures(path: Path) -> Iterable[Path]:
    if path.is_dir():
        yield from sorted([*path.glob("*.yaml"), *path.glob("*.yml")])
    else:
        yield path


def _rate(passed: int, total: int) -> float:
    return round(passed / total, 4) if total else 0.0


def _kind_rate(by_kind: Dict[str, Dict[str, int]], kinds: List[str]) -> float:
    passed = sum(by_kind.get(kind, {}).get("passed", 0) for kind in kinds)
    total = sum(by_kind.get(kind, {}).get("total", 0) for kind in kinds)
    return _rate(passed, total)


def _case_index(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    cases: Dict[str, Dict[str, Any]] = {}
    for fixture in report.get("fixtures", [report]):
        for case in fixture.get("cases", []):
            cases[f"{Path(fixture.get('fixture', '')).name}:{case.get('id')}"] = case
    return cases


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p


def main() -> int:
    parser = argparse.ArgumentParser(description="Run relevance-sensitive benchmark fixture or directory.")
    parser.add_argument("path")
    parser.add_argument("--out")
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    report = run_path(args.path)
    if args.snapshot:
        report["snapshot_regression"] = compare_snapshot(report, args.snapshot)
        if report["snapshot_regression"]["status"] != "PASS":
            report["status"] = "FAIL"
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
