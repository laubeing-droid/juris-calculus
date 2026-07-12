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

_BASELINE_METRICS = (
    "cold_start_sec",
    "warm_run_sec",
    "branch_run_sec",
    "peak_memory_bytes",
    "audit_event_count",
    "audit_bundle_bytes",
)
_REGRESSION_RATIO = 1.5


def collect_baseline(
    config_root: Path,
    input_path: Path,
    state_root: Path,
    budgets_path: Path = ROOT / "configs" / "perf_patterns.yaml",
    baseline_report_path: Path | None = None,
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
    baseline_comparison = _baseline_comparison(metrics, baseline_report_path)
    if baseline_comparison["status"] == "BLOCKED":
        return {
            "status": "BLOCKED",
            "reason": "invalid_baseline_report",
            "metrics": metrics,
            "budgets": budgets if isinstance(budgets, dict) else {},
            "violations": [],
            "baseline_comparison": baseline_comparison,
        }
    if not isinstance(budgets, dict) or not budgets:
        return {
            "status": "BLOCKED",
            "reason": "missing_numeric_budgets",
            "metrics": metrics,
            "violations": [],
            "baseline_comparison": baseline_comparison,
        }
    violations = [
        {"metric": name, "actual": metrics[name], "maximum": maximum}
        for name, maximum in sorted(budgets.items())
        if name not in metrics or metrics[name] > maximum
    ]
    has_regressions = baseline_comparison["status"] == "FAIL"
    if violations and has_regressions:
        status = "FAIL"
        reason = "budget_exceeded_and_baseline_regressed"
    elif violations:
        status = "FAIL"
        reason = "budget_exceeded"
    elif has_regressions:
        status = "FAIL"
        reason = "baseline_regressed"
    else:
        status = "PASS"
        reason = "within_budget"
    return {
        "status": status,
        "reason": reason,
        "metrics": metrics,
        "budgets": budgets,
        "violations": violations,
        "baseline_comparison": baseline_comparison,
        "digests": {
            "cold_result": cold.result.semantic.result_digest,
            "warm_result": warm.result.semantic.result_digest,
            "branch_result": branch.result.semantic.result_digest,
        },
    }


def _baseline_comparison(metrics: dict[str, Any], baseline_report_path: Path | None) -> dict[str, Any]:
    """比较固定性能指标与既有基线；无请求时不参与顶层判定。"""

    result = {
        "status": "NOT_REQUESTED",
        "checked_metrics": list(_BASELINE_METRICS),
        "regressions": [],
    }
    if baseline_report_path is None:
        return result
    try:
        payload = json.loads(Path(baseline_report_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {**result, "status": "BLOCKED"}
    if not isinstance(payload, dict):
        return {**result, "status": "BLOCKED"}
    baseline_metrics = payload.get("metrics")
    if not isinstance(baseline_metrics, dict):
        return {**result, "status": "BLOCKED"}

    regressions: list[dict[str, Any]] = []
    for name in _BASELINE_METRICS:
        baseline_value = baseline_metrics.get(name)
        current_value = metrics.get(name)
        if not isinstance(baseline_value, (int, float)) or isinstance(baseline_value, bool) or baseline_value <= 0:
            return {**result, "status": "BLOCKED"}
        if not isinstance(current_value, (int, float)) or isinstance(current_value, bool):
            return {**result, "status": "BLOCKED"}
        ratio = round(float(current_value) / float(baseline_value), 6)
        if ratio >= _REGRESSION_RATIO:
            regressions.append({
                "metric": name,
                "current": current_value,
                "baseline": baseline_value,
                "ratio": ratio,
            })
    return {
        "status": "FAIL" if regressions else "PASS",
        "checked_metrics": list(_BASELINE_METRICS),
        "regressions": regressions,
    }


def main(argv: list[str] | None = None) -> int:
    """Write one deterministic-shape JSON report and map PASS/FAIL/BLOCKED to 0/1/2."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--budgets", type=Path, default=ROOT / "configs" / "perf_patterns.yaml")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = collect_baseline(args.config_root, args.input, args.state_root, args.budgets, args.baseline)
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
