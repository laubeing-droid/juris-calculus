from tools.kg_completeness_auditor import audit_completeness
from tools.kg_correctness_auditor import audit_correctness
from tools.kg_audit_loop import run_dual_audit


def test_kg_correctness_audit_passes_current_contracts():
    report = audit_correctness("configs/juris_contracts.yaml")

    assert report["status"] == "PASS"
    assert report["findings"] == []


def test_kg_completeness_audit_passes_current_contracts():
    report = audit_completeness("configs/juris_contracts.yaml")

    assert report["status"] == "PASS"
    assert report["findings"] == []


def test_kg_dual_audit_loop_records_independent_children(tmp_path):
    summary = run_dual_audit(
        contracts="configs/juris_contracts.yaml",
        out_dir=str(tmp_path),
        mode="local",
    )

    assert summary["status"] == "PASS"
    assert len(summary["child_reports"]) == 2
    assert {child["role"] for child in summary["child_reports"]} == {"correctness", "completeness"}
    assert all(child["pid"] for child in summary["child_reports"])
    assert summary["blueprint_repair_queue"] == []
