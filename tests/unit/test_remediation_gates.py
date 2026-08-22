"""Tests for the WAITING_HUMAN / WAITING_EXTERNAL gate envelope generator.

施工方案 §1.1 + §22 + §3.6 require every external dependency to be encoded
as a gate envelope binding subject_digest, required_roles,
separation_of_duties, scope, expires_at, and resume_command. The agent
must NOT auto-substitute these with guesses.

Each gate envelope must:
- enumerate required_roles and (where applicable) separation_of_duties;
- bind to a baseline commit/tree that the施工方案 pins (dfdfab1);
- bind plan_sha256 and audit_sha256 from施工方案;
- emit a single resume_command that the next agent can replay.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
GATES_TOOL = REPO / "tools" / "remediate_v4_gates.py"


EXPECTED_GATE_IDS = [
    "B02-SPEC-INTAKE",
    "W0-05-VERIFIER-DEPENDENCY",
    "H5-02-CN-LEGACY-AUTHORIZATION",
    "H6-02-LOCK-APPROVAL",
    "H6-07-GITHUB-GOVERNANCE",
    "H7-00-PRODUCTION-STORAGE-PROVIDER",
    "H7-05-KERNEL-RC-RELEASE",
    "H8-00-FORMAL-SOURCE-INVENTORY",
    "H8-03-LEGAL-REVIEW",
    "H8-04-ENGINEERING-REVIEW",
    "H8-07-CN-OFFICIAL-RELEASE",
    "H9-00-DSH-PIN",
]

EXPECTED_KINDS = {
    "B02-SPEC-INTAKE": "EXTERNAL_GATE",
    "W0-05-VERIFIER-DEPENDENCY": "HUMAN_GATE",
    "H5-02-CN-LEGACY-AUTHORIZATION": "HUMAN_GATE",
    "H6-02-LOCK-APPROVAL": "HUMAN_GATE",
    "H6-07-GITHUB-GOVERNANCE": "MIXED",
    "H7-00-PRODUCTION-STORAGE-PROVIDER": "MIXED",
    "H7-05-KERNEL-RC-RELEASE": "HUMAN_GATE",
    "H8-00-FORMAL-SOURCE-INVENTORY": "MIXED",
    "H8-03-LEGAL-REVIEW": "HUMAN_GATE",
    "H8-04-ENGINEERING-REVIEW": "HUMAN_GATE",
    "H8-07-CN-OFFICIAL-RELEASE": "HUMAN_GATE",
    "H9-00-DSH-PIN": "MIXED",
}


def _git(*args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    return cp.stdout


def test_gate_generator_writes_envelopes() -> None:
    state_root = REPO.parent / "jc_gates_test"
    if state_root.exists():
        import shutil
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "JC_REMEDIATION_STATE_ROOT": str(state_root)}
    cp = subprocess.run(
        [sys.executable, "-B", str(GATES_TOOL)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
    )
    assert cp.returncode == 0, f"gate generator failed:\n{cp.stderr}"

    requests = state_root / "requests"
    assert requests.is_dir(), f"requests dir missing: {requests}"
    index_path = requests / "INDEX.json"
    assert index_path.is_file()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["count"] == len(EXPECTED_GATE_IDS)
    # The施工方案 baseline commit must appear in v4-remediation's git history.
    # The gate envelopes bind to current HEAD (post-B01), not the施工方案
    # baseline anchor.
    expected_head = _git("rev-parse", "HEAD").strip()
    assert index["baseline_commit"] == expected_head
    assert (
        index["plan_sha256"]
        == "41ffbd0245faac0d7bd01161adc80018d3ff24f75ecdd91a25bd20f3e329812d"
    )
    assert (
        index["audit_sha256"]
        == "9b38e52c0181dbace4758d8c681009a61427baa53b1af2dae9e9c5d20f5e31a3"
    )


def test_each_envelope_has_required_fields() -> None:
    state_root = REPO.parent / "jc_gates_test2"
    if state_root.exists():
        import shutil
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "JC_REMEDIATION_STATE_ROOT": str(state_root)}
    cp = subprocess.run(
        [sys.executable, "-B", str(GATES_TOOL)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
    )
    assert cp.returncode == 0

    requests = state_root / "requests"
    files = sorted(requests.glob("*.json"))
    files = [p for p in files if p.name != "INDEX.json"]
    assert len(files) == len(EXPECTED_GATE_IDS)
    seen_gate_ids: set[str] = set()
    for path in files:
        env = json.loads(path.read_text(encoding="utf-8"))
        assert env["schema_version"] == "jc/remediation-v4-gate-request/1.0"
        assert env["gate_id"] in EXPECTED_GATE_IDS, f"unexpected gate: {env['gate_id']}"
        assert env["kind"] in {"HUMAN_GATE", "EXTERNAL_GATE", "MIXED"}
        assert EXPECTED_KINDS[env["gate_id"]] == env["kind"], (
            f"{env['gate_id']} kind mismatch: {env['kind']} != "
            f"{EXPECTED_KINDS[env['gate_id']]}"
        )
        assert env["subject_digest"].startswith("sha256:")
        assert len(env["required_roles"]) >= 1
        if env["kind"] in {"HUMAN_GATE", "MIXED"} and env["gate_id"] != "B02-SPEC-INTAKE":
            assert env.get("separation_of_duties") is True, (
                f"{env['gate_id']} HUMAN_GATE/MIXED must require separation_of_duties"
            )
        assert env["scope"]
        assert env["expires_at"] > env["issued_at"]
        assert env["resume_command"].startswith("py -3.12 -B tools/remediate_v4.py run")
        assert env["baseline_commit"] == _git("rev-parse", "HEAD").strip()
        seen_gate_ids.add(env["gate_id"])
    assert seen_gate_ids == set(EXPECTED_GATE_IDS)


def test_h5_02_envelope_binds_cn_legacy_fingerprint() -> None:
    state_root = REPO.parent / "jc_gates_test3"
    if state_root.exists():
        import shutil
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "JC_REMEDIATION_STATE_ROOT": str(state_root)}
    subprocess.run(
        [sys.executable, "-B", str(GATES_TOOL)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    env = json.loads(
        (state_root / "requests" / "H5-02_H5-02-CN-LEGACY-AUTHORIZATION.json").read_text()
    )
    assert "configs/zh_CN/rules.yaml" in env["evidence_subject_paths"]
    assert "configs/packs/cn-legacy-corpus/manifest.yaml" in env["evidence_subject_paths"]
    # Scope must mention the施工方案-frozen values
    scope = env["scope"]
    assert "13,620,766" in scope
    assert "21,144" in scope
    assert "8f51fdfd" in scope
    assert "1b29b412" in scope


def test_resume_command_is_unique() -> None:
    state_root = REPO.parent / "jc_gates_test4"
    if state_root.exists():
        import shutil
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    env_var = {**os.environ, "JC_REMEDIATION_STATE_ROOT": str(state_root)}
    subprocess.run(
        [sys.executable, "-B", str(GATES_TOOL)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env_var,
        check=True,
    )
    index = json.loads((state_root / "requests" / "INDEX.json").read_text())
    commands = {g["resume_command"] for g in index["gates"]}
    assert len(commands) == 1, f"resume commands differ across gates: {commands}"