"""Audited application performance budgets and YAML rule counting."""

import json
from pathlib import Path

from tests.unit.test_audit_bundle import _fixture
from tools.perf_baseline import collect_baseline


def _write_baseline(path: Path, metrics: dict[str, int | float]) -> None:
    path.write_text(json.dumps({"metrics": metrics}), encoding="utf-8")


def test_fixed_fixture_counts_mapping_rules_and_applies_numeric_budgets(tmp_path) -> None:
    """Unit tests verify accounting deterministically; dedicated runs enforce machine budgets."""

    _, request = _fixture(tmp_path / "configs")
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(request.to_dict()), encoding="utf-8")

    budgets = tmp_path / "budgets.yaml"
    budgets.write_text(
        "budgets:\n  cold_start_sec: 60\n  warm_run_sec: 60\n  branch_run_sec: 60\n"
        "  peak_memory_bytes: 1073741824\n  audit_event_count: 1000\n  audit_bundle_bytes: 10485760\n",
        encoding="utf-8",
    )
    report = collect_baseline(tmp_path / "configs", input_path, tmp_path / "state", budgets)

    assert report["status"] == "PASS"
    assert report["baseline_comparison"]["status"] == "NOT_REQUESTED"
    assert report["metrics"]["corpus_rule_count"] == 1
    assert report["digests"]["cold_result"] == report["digests"]["warm_result"]


def test_missing_budgets_is_blocked(tmp_path) -> None:
    """Missing numeric ceilings cannot silently pass the performance gate."""

    _, request = _fixture(tmp_path / "configs")
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(request.to_dict()), encoding="utf-8")
    budgets = tmp_path / "budgets.yaml"
    budgets.write_text("schema_version: '3.0'\n", encoding="utf-8")

    report = collect_baseline(tmp_path / "configs", input_path, tmp_path / "state", budgets)

    assert report["status"] == "BLOCKED"


def test_valid_baseline_without_regression_reports_pass(tmp_path) -> None:
    """显式baseline存在且全部指标未达1.5倍时，比较结果为PASS。"""

    _, request = _fixture(tmp_path / "configs")
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(request.to_dict()), encoding="utf-8")
    budgets = tmp_path / "budgets.yaml"
    budgets.write_text(
        "budgets:\n  cold_start_sec: 60\n  warm_run_sec: 60\n  branch_run_sec: 60\n"
        "  peak_memory_bytes: 1073741824\n  audit_event_count: 1000\n  audit_bundle_bytes: 10485760\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    _write_baseline(
        baseline,
        {
            "cold_start_sec": 60,
            "warm_run_sec": 60,
            "branch_run_sec": 60,
            "peak_memory_bytes": 1073741824,
            "audit_event_count": 1000,
            "audit_bundle_bytes": 10485760,
            "corpus_rule_count": 999999,
        },
    )

    report = collect_baseline(tmp_path / "configs", input_path, tmp_path / "state", budgets, baseline)

    assert report["status"] == "PASS"
    assert report["reason"] == "within_budget"
    assert report["baseline_comparison"] == {
        "status": "PASS",
        "checked_metrics": [
            "cold_start_sec",
            "warm_run_sec",
            "branch_run_sec",
            "peak_memory_bytes",
            "audit_event_count",
            "audit_bundle_bytes",
        ],
        "regressions": [],
    }


def test_baseline_regression_fails_even_when_budgets_pass(tmp_path) -> None:
    """只要某指标达到1.5倍阈值，就必须返回baseline_regressed。"""

    _, request = _fixture(tmp_path / "configs")
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(request.to_dict()), encoding="utf-8")
    budgets = tmp_path / "budgets.yaml"
    budgets.write_text(
        "budgets:\n  cold_start_sec: 60\n  warm_run_sec: 60\n  branch_run_sec: 60\n"
        "  peak_memory_bytes: 1073741824\n  audit_event_count: 1000\n  audit_bundle_bytes: 10485760\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    _write_baseline(
        baseline,
        {
            "cold_start_sec": 0.0001,
            "warm_run_sec": 60,
            "branch_run_sec": 60,
            "peak_memory_bytes": 1073741824,
            "audit_event_count": 1000,
            "audit_bundle_bytes": 10485760,
        },
    )

    report = collect_baseline(tmp_path / "configs", input_path, tmp_path / "state", budgets, baseline)

    assert report["status"] == "FAIL"
    assert report["reason"] == "baseline_regressed"
    assert report["baseline_comparison"]["status"] == "FAIL"
    assert report["baseline_comparison"]["regressions"][0]["metric"] == "cold_start_sec"
    assert report["baseline_comparison"]["regressions"][0]["ratio"] >= 1.5


def test_invalid_baseline_is_blocked(tmp_path) -> None:
    """baseline 缺失或缺少受检指标都不得假通过。"""

    _, request = _fixture(tmp_path / "configs")
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(request.to_dict()), encoding="utf-8")
    budgets = tmp_path / "budgets.yaml"
    budgets.write_text(
        "budgets:\n  cold_start_sec: 60\n  warm_run_sec: 60\n  branch_run_sec: 60\n"
        "  peak_memory_bytes: 1073741824\n  audit_event_count: 1000\n  audit_bundle_bytes: 10485760\n",
        encoding="utf-8",
    )

    missing = collect_baseline(tmp_path / "configs", input_path, tmp_path / "state-a", budgets, tmp_path / "absent.json")
    assert missing["status"] == "BLOCKED"
    assert missing["reason"] == "invalid_baseline_report"
    assert missing["baseline_comparison"]["status"] == "BLOCKED"

    incomplete = tmp_path / "baseline-incomplete.json"
    _write_baseline(incomplete, {"cold_start_sec": 1})
    blocked = collect_baseline(tmp_path / "configs", input_path, tmp_path / "state-b", budgets, incomplete)
    assert blocked["status"] == "BLOCKED"
    assert blocked["reason"] == "invalid_baseline_report"
    assert blocked["baseline_comparison"]["status"] == "BLOCKED"
