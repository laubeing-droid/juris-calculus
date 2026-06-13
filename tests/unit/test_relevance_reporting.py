import json

from tools.relevance_sensitivity_runner import compare_snapshot, run_path


def test_relevance_snapshot_detects_claim_changes(tmp_path):
    report = run_path("tests/relevance_sensitivity")
    snapshot = json.loads(json.dumps(report))
    snapshot["fixtures"][0]["cases"][0]["claims"] = ["Different"]
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    diff = compare_snapshot(report, snapshot_path)

    assert diff["status"] == "FAIL"
    assert diff["regression_count"] == 1


def test_relevance_report_can_be_written(tmp_path):
    report = run_path("tests/relevance_sensitivity")
    out = tmp_path / "report.json"
    out.write_text(json.dumps(report), encoding="utf-8")

    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "PASS"
