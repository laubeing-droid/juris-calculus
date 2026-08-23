#!/usr/bin/env python3
"""Assess measured V4 performance metrics against explicit numeric budgets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_BASELINE_METRICS = (
    "cold_start_sec",
    "warm_run_sec",
    "branch_run_sec",
    "peak_memory_bytes",
    "audit_event_count",
    "audit_bundle_bytes",
)
_REGRESSION_RATIO = 1.5


def assess_metrics(
    metrics: object,
    budgets: object,
    baseline_report_path: Path | None = None,
) -> dict[str, Any]:
    """Fail closed on incomplete local metrics or budgets; never promote them."""

    scope = {
        "scope": "test-local",
        "production_allowed": False,
        "target_provider_claimed": False,
    }
    if not isinstance(metrics, dict):
        return {
            **scope,
            "status": "BLOCKED",
            "reason": "invalid_metrics",
            "metrics": {},
            "budgets": budgets if isinstance(budgets, dict) else {},
            "violations": [],
            "baseline_comparison": {
                "status": "NOT_REQUESTED",
                "checked_metrics": list(_BASELINE_METRICS),
                "regressions": [],
            },
        }
    baseline_comparison = _baseline_comparison(metrics, baseline_report_path)
    if baseline_comparison["status"] == "BLOCKED":
        return {
            **scope,
            "status": "BLOCKED",
            "reason": "invalid_baseline_report",
            "metrics": metrics,
            "budgets": budgets if isinstance(budgets, dict) else {},
            "violations": [],
            "baseline_comparison": baseline_comparison,
        }
    if (
        not isinstance(budgets, dict)
        or set(budgets) != set(_BASELINE_METRICS)
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value <= 0
            for value in budgets.values()
        )
    ):
        return {
            **scope,
            "status": "BLOCKED",
            "reason": "missing_numeric_budgets",
            "metrics": metrics,
            "budgets": budgets if isinstance(budgets, dict) else {},
            "violations": [],
            "baseline_comparison": baseline_comparison,
        }
    if any(
        name not in metrics
        or not isinstance(metrics[name], (int, float))
        or isinstance(metrics[name], bool)
        or metrics[name] < 0
        for name in _BASELINE_METRICS
    ):
        return {
            **scope,
            "status": "BLOCKED",
            "reason": "invalid_metrics",
            "metrics": metrics,
            "budgets": budgets,
            "violations": [],
            "baseline_comparison": baseline_comparison,
        }
    violations = [
        {"metric": name, "actual": metrics[name], "maximum": budgets[name]}
        for name in _BASELINE_METRICS
        if metrics[name] > budgets[name]
    ]
    has_regressions = baseline_comparison["status"] == "FAIL"
    if violations and has_regressions:
        status, reason = "FAIL", "budget_exceeded_and_baseline_regressed"
    elif violations:
        status, reason = "FAIL", "budget_exceeded"
    elif has_regressions:
        status, reason = "FAIL", "baseline_regressed"
    else:
        status, reason = "PASS", "within_budget"
    return {
        **scope,
        "status": status,
        "reason": reason,
        "metrics": metrics,
        "budgets": budgets,
        "violations": violations,
        "baseline_comparison": baseline_comparison,
    }


def assess_report(
    metrics_path: Path,
    budgets_path: Path = ROOT / "configs" / "perf_patterns.yaml",
    baseline_report_path: Path | None = None,
) -> dict[str, Any]:
    """Read one measurement report and fail closed on malformed boundary input."""

    try:
        metrics_document = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        metrics_document = {}
    try:
        budgets_document = yaml.safe_load(
            Path(budgets_path).read_text(encoding="utf-8")
        ) or {}
    except (OSError, UnicodeError, yaml.YAMLError):
        budgets_document = {}
    metrics = (
        metrics_document.get("metrics")
        if isinstance(metrics_document, dict) and set(metrics_document) == {"metrics"}
        else None
    )
    budgets = (
        budgets_document.get("budgets")
        if isinstance(budgets_document, dict) and set(budgets_document) == {"budgets"}
        else None
    )
    return assess_metrics(metrics, budgets, baseline_report_path)


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
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--budgets", type=Path, default=ROOT / "configs" / "perf_patterns.yaml")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = assess_report(args.metrics, args.budgets, args.baseline)
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
