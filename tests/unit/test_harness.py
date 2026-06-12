"""Tests for Harness constraint mechanisms (7.4.3) and self-healing loop (7.4.4)."""
from tools.shape_checker import check_shapes
from tools.module_interface_checker import check_interfaces
from tools.self_healing_loop import run_healing_loop


def test_shape_checker_all_core_classes_pass():
    report = check_shapes()
    assert report["status"] == "PASS", f"findings: {report['findings']}"
    assert report["results"]["LegalFact"] == "PASS"
    assert report["results"]["LegalClaim"] == "PASS"
    assert report["results"]["IRState"] == "PASS"


def test_module_interface_checker_all_pass():
    report = check_interfaces()
    assert report["status"] == "PASS", f"findings: {report['findings']}"
    assert len(report["results"]) >= 5


def test_self_healing_loop_runs(tmp_path):
    result = run_healing_loop(
        baseline_path="reports/perf/baseline1.json",
        out_dir=str(tmp_path),
    )
    assert "report_path" in result
    assert result["report"]["status"] in ("PASS", "DEGRADED")
