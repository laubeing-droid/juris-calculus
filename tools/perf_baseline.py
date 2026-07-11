#!/usr/bin/env python3
"""Measure the audited application path against committed numeric budgets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import tracemalloc
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.audit_bundle import evaluate_registered_case
from compiler_core.contracts import CaseRequest
from compiler_core.rule_packs import RulePackRegistry


def collect_baseline(
    config_root: Path,
    input_path: Path,
    state_root: Path,
    budgets_path: Path = ROOT / "configs" / "perf_patterns.yaml",
) -> dict[str, Any]:
    """运行固定CaseRequest的冷/热/分支审计，并按预算fail closed。"""

    request = CaseRequest.from_dict(json.loads(Path(input_path).read_text(encoding="utf-8")))
    registry = RulePackRegistry(Path(config_root), development_override=True)
    corpus_document = yaml.safe_load(registry.load_corpus_pack(request.rule_pack_id).rule_paths[0].read_text(encoding="utf-8")) or {}
    rules = corpus_document.get("rules", []) if isinstance(corpus_document, dict) else []
    if not isinstance(rules, list):
        raise ValueError("rules must be an array")

    tracemalloc.start()
    started = time.perf_counter()
    cold = evaluate_registered_case(request, registry, state_root=Path(state_root) / "cold")
    cold_seconds = time.perf_counter() - started
    started = time.perf_counter()
    warm = evaluate_registered_case(request, registry, state_root=Path(state_root) / "warm")
    warm_seconds = time.perf_counter() - started

    branch_payload = request.to_dict()
    branch_payload["facts"][0].update({
        "status": "disputed",
        "human_reviewed": False,
        "alternatives": [{"value": True}, {"value": False}],
    })
    started = time.perf_counter()
    branch = evaluate_registered_case(CaseRequest.from_dict(branch_payload), registry, state_root=Path(state_root) / "branch")
    branch_seconds = time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    metrics = {
        "cold_start_sec": round(cold_seconds, 6),
        "warm_run_sec": round(warm_seconds, 6),
        "branch_run_sec": round(branch_seconds, 6),
        "peak_memory_bytes": peak_bytes,
        "audit_event_count": len(cold.events),
        "audit_bundle_bytes": sum(path.stat().st_size for path in cold.run_directory.iterdir()),
        "corpus_rule_count": len(rules),
    }
    budgets_document = yaml.safe_load(Path(budgets_path).read_text(encoding="utf-8")) or {}
    budgets = budgets_document.get("budgets", {})
    if not isinstance(budgets, dict) or not budgets:
        return {"status": "BLOCKED", "reason": "missing_numeric_budgets", "metrics": metrics, "violations": []}
    violations = [
        {"metric": name, "actual": metrics[name], "maximum": maximum}
        for name, maximum in sorted(budgets.items())
        if name not in metrics or metrics[name] > maximum
    ]
    return {
        "status": "FAIL" if violations else "PASS",
        "reason": "budget_exceeded" if violations else "within_budget",
        "metrics": metrics,
        "budgets": budgets,
        "violations": violations,
        "digests": {
            "cold_result": cold.result.semantic.result_digest,
            "warm_result": warm.result.semantic.result_digest,
            "branch_result": branch.result.semantic.result_digest,
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Write one deterministic-shape JSON report and map PASS/FAIL/BLOCKED to 0/1/2."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--budgets", type=Path, default=ROOT / "configs" / "perf_patterns.yaml")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = collect_baseline(args.config_root, args.input, args.state_root, args.budgets)
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
