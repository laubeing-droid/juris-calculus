"""Dedicated tests for build_phases (P1-P11)."""
import yaml
from pathlib import Path

from tools.blueprint_contract_auditor import audit_matrix
from tools.phase_runner import run_phases


MATRIX = Path(__file__).resolve().parent.parent.parent / "configs" / "juris_phase_matrix.yaml"
EXPECTED_IDS = [
    "P1_TYPES_TRUST", "P2_CONFIG_RULE_PARSE", "P3_HORN_EVALUATOR",
    "P4_MOE_ROUTER", "P5_GATES_CONSTRAINTS", "P6_STEP_VERIFIER_AAF",
    "P7_ADVERSARIAL_REVIEW", "P8_MCP_OPERATION_INTERFACE",
    "P9_ADDON_FEDERATION", "P10_E2E_KG_AUDIT", "P11_PERF_PRUNE_COLDSTART",
]


def test_all_11_build_phases_present():
    matrix = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    bps = matrix.get("build_phases", [])
    assert len(bps) == 11
    assert [p["id"] for p in bps] == EXPECTED_IDS


def test_every_build_phase_has_required_fields():
    matrix = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    for p in matrix["build_phases"]:
        assert p.get("id"), f"{p.get('id','?')}: missing id"
        assert p.get("name"), f"{p['id']}: missing name"
        assert p.get("layer"), f"{p['id']}: missing layer"
        assert "physical_dependency" in p, f"{p['id']}: missing physical_dependency"
        assert isinstance(p.get("commands"), list) and p["commands"], f"{p['id']}: commands empty"


def test_dependency_chain_is_acyclic():
    matrix = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    ids = set(p["id"] for p in matrix["build_phases"])
    for p in matrix["build_phases"]:
        dep = p["physical_dependency"]
        if dep == "none":
            continue
        assert dep in ids, f"{p['id']}: dependency '{dep}' not found"
        dep_idx = EXPECTED_IDS.index(dep)
        cur_idx = EXPECTED_IDS.index(p["id"])
        assert dep_idx < cur_idx, f"{p['id']}: dependency '{dep}' comes after"


def test_build_phase_auditor_reports_11_build_phases():
    report = audit_matrix(str(MATRIX))
    assert report["build_phase_count"] == 11


def test_every_build_phase_dry_runs_individually(tmp_path):
    for pid in EXPECTED_IDS:
        summary = run_phases(
            matrix_path=str(MATRIX),
            phase_id=pid,
            use_build_phases=True,
            dry_run=True,
            report_dir=tmp_path,
        )
        assert summary["status"] == "PASS", f"{pid} dry-run failed"
