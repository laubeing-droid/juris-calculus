"""Local RC performance accounting without production-SLO claims."""

from __future__ import annotations

import json
from pathlib import Path

from tools import remediate_v4 as runner
from tools.perf_baseline import assess_metrics, main


METRICS = {
    "cold_start_sec": 1.0,
    "warm_run_sec": 0.5,
    "branch_run_sec": 1.0,
    "peak_memory_bytes": 1024,
    "audit_event_count": 10,
    "audit_bundle_bytes": 2048,
}
BUDGETS = {
    "cold_start_sec": 2.0,
    "warm_run_sec": 1.0,
    "branch_run_sec": 2.0,
    "peak_memory_bytes": 2048,
    "audit_event_count": 20,
    "audit_bundle_bytes": 4096,
}


def test_complete_metrics_pass_only_as_local_unpromotable_evidence(
    tmp_path: Path,
) -> None:
    report = assess_metrics(dict(METRICS), dict(BUDGETS))

    assert report["status"] == "PASS"
    assert report["scope"] == "test-local"
    assert report["production_allowed"] is False
    assert report["target_provider_claimed"] is False

    metrics_path = tmp_path / "metrics.json"
    budgets_path = tmp_path / "budgets.yaml"
    output_path = tmp_path / "report.json"
    metrics_path.write_text(json.dumps({"metrics": METRICS}), encoding="utf-8")
    budgets_path.write_text(
        "budgets:\n" + "".join(f"  {name}: {value}\n" for name, value in BUDGETS.items()),
        encoding="utf-8",
    )
    assert main([
        "--metrics", str(metrics_path), "--budgets", str(budgets_path),
        "--output", str(output_path),
    ]) == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "PASS"


def test_missing_extra_boolean_or_nonpositive_budget_is_blocked() -> None:
    mutations = []
    missing = dict(BUDGETS)
    missing.pop("warm_run_sec")
    mutations.append(missing)
    mutations.append({**BUDGETS, "unapproved_metric": 1})
    mutations.append({**BUDGETS, "warm_run_sec": True})
    mutations.append({**BUDGETS, "warm_run_sec": 0})

    assert all(
        assess_metrics(dict(METRICS), mutation)["reason"] == "missing_numeric_budgets"
        for mutation in mutations
    )


def test_missing_boolean_or_negative_metric_is_blocked() -> None:
    mutations = []
    missing = dict(METRICS)
    missing.pop("audit_event_count")
    mutations.append(missing)
    mutations.append({**METRICS, "audit_event_count": True})
    mutations.append({**METRICS, "audit_event_count": -1})
    mutations.append(None)

    assert all(
        assess_metrics(mutation, dict(BUDGETS))["reason"] == "invalid_metrics"
        for mutation in mutations
    )


def test_budget_excess_and_exact_boundary_are_distinguished() -> None:
    boundary = {name: BUDGETS[name] for name in METRICS}
    exceeded = {**boundary, "warm_run_sec": BUDGETS["warm_run_sec"] + 0.001}

    assert assess_metrics(boundary, dict(BUDGETS))["status"] == "PASS"
    report = assess_metrics(exceeded, dict(BUDGETS))
    assert report["status"] == "FAIL"
    assert report["reason"] == "budget_exceeded"
    assert report["violations"] == [{
        "metric": "warm_run_sec",
        "actual": exceeded["warm_run_sec"],
        "maximum": BUDGETS["warm_run_sec"],
    }]


def test_regression_threshold_is_fail_closed_and_path_free(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"metrics": {**METRICS, "cold_start_sec": 0.5}}),
        encoding="utf-8",
    )
    report = assess_metrics(dict(METRICS), dict(BUDGETS), baseline)

    assert report["status"] == "FAIL"
    assert report["reason"] == "baseline_regressed"
    assert report["baseline_comparison"]["regressions"][0]["ratio"] == 2.0
    assert str(tmp_path.resolve()) not in json.dumps(report, sort_keys=True)

    raw = b'{"samples_ms":[8.0,9.0,10.0]}\n'
    raw_digest = "sha256:" + runner.sha256_hex(raw)
    raw_path = (
        tmp_path / "evidence" / "W7" / "target" / "raw"
        / f"{raw_digest.split(':', 1)[1]}.json"
    )
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(raw)
    evidence = {
        "source_artifact_digest": raw_digest,
        "provider_capability_digest": "sha256:" + "a" * 64,
        "actual": 10.0,
        "required": 20.0,
        "operator": "<=",
        "unit": "milliseconds",
    }
    assert runner._w7_target_check_evidence_problems(
        "W7-02", "p95", evidence, tmp_path,
    ) == []
    assert runner._w7_target_check_evidence_problems(
        "W7-02", "p95", {**evidence, "actual": 21.0}, tmp_path,
    ) == ["W7-02 target budget comparison failed: p95"]
