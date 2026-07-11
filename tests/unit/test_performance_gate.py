"""Audited application performance budgets and YAML rule counting."""

import json

from tests.unit.test_audit_bundle import _fixture
from tools.perf_baseline import collect_baseline


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
