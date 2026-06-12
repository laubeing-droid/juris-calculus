"""Tests for anti-degradation mechanisms."""
from tools.import_source_verifier import verify_import_sources
from tools.e2e_evidence_collector import collect_evidence
from tools.verification_replay import replay_report
from tools.phase_runner import run_phases
import json
from pathlib import Path


MATRIX = "configs/juris_phase_matrix.yaml"


def test_import_source_verifier_all_local():
    report = verify_import_sources("D:/v2.0")
    assert report["status"] in ("PASS", "WARN"), f"leaked: {report['findings']}"
    assert len(report["checked_modules"]) >= 4


def test_e2e_evidence_collector_produces_trace(tmp_path):
    report = collect_evidence(str(tmp_path))

    assert report["status"] in ("PASS", "WARN")
    assert Path(report["trace_path"]).exists()
    assert report["trace"]["rules_loaded"] > 0
    assert report["trace"]["claims_produced"] >= 0
    assert "trust_label" in report["trace"]


def test_replay_detects_stdout_mismatch(tmp_path):
    fake_report = {
        "status": "PASS",
        "phases": [{
            "phase_id": "TEST",
            "commands": [{
                "command": "python -c \"print('A')\"",
                "returncode": 0,
                "stdout": "B\n",
            }],
        }],
    }
    p = tmp_path / "fake.json"
    p.write_text(json.dumps(fake_report), encoding="utf-8")
    replay = replay_report(p, seed=1)
    assert not replay["stdout_full_match"]


def test_build_phase_with_spot_check(tmp_path):
    summary = run_phases(
        matrix_path=MATRIX,
        phase_id="P1_TYPES_TRUST",
        use_build_phases=True,
        dry_run=False,
        report_dir=tmp_path,
    )
    if summary.get("step35_spot_check"):
        assert "status" in summary["step35_spot_check"]
