import json
from pathlib import Path

from tools.blueprint_contract_auditor import audit_matrix
from compiler_core.experience_contracts import ExperienceContractRegistry
from tools.phase_runner import run_phases
from tools.verification_replay import replay_report


def test_phase_matrix_contracts_are_valid():
    report = audit_matrix("configs/juris_phase_matrix.yaml")

    assert report["status"] == "PASS"
    assert report["phase_count"] >= 6


def test_experience_contract_registry_loads_three_level_chain():
    registry = ExperienceContractRegistry()
    contract = registry.get("criminal_multi_party_binding")

    assert "moe_domain_routing" in registry.list_ids()
    assert contract is not None
    assert contract.ref_docs
    assert contract.ref_code
    assert contract.ref_tests
    assert "scenario" in contract.pseudocode


def test_phase_runner_dry_run_writes_report(tmp_path):
    summary = run_phases(
        matrix_path="configs/juris_phase_matrix.yaml",
        phase_id="L1",
        dry_run=True,
        report_dir=tmp_path,
    )

    report_path = Path(summary["report_path"])
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert saved["phases"][0]["phase_id"] == "L1"
    assert saved["phases"][0]["commands"][0]["stdout"] == "[dry-run]"


def test_verification_replay_detects_successful_recorded_command(tmp_path):
    report = {
        "status": "PASS",
        "phases": [
            {
                "phase_id": "TEST",
                "commands": [
                    {
                        "command": "python -c \"print('replay-ok')\"",
                        "returncode": 0,
                    }
                ],
            }
        ],
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    replay = replay_report(report_path, seed=1)

    assert replay["status"] == "PASS"
    assert replay["actual_returncode"] == 0
