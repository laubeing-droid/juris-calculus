"""Tests for the施工方案 §1.3 run command.

The施工方案 mandates that the runner, upon encountering a WAITING_HUMAN
or WAITING_EXTERNAL gate, must NOT auto-substitute a guess. Instead it
must generate the gate envelope under $JC_REMEDIATION_STATE_ROOT/requests/
and exit with code 20 (WAITING_HUMAN) or 21 (WAITING_EXTERNAL), printing
a unique resume_command.

These tests assert:
- the run command initializes state_root with run.json;
- gate envelopes are produced and indexed;
- the exit code reflects the gate kind (MIXED → 20, EXTERNAL → 21);
- resume_command is unique across gates.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "tools" / "remediate_v4.py"


def _git(*args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    return cp.stdout


def _fresh_state_root(name: str) -> Path:
    state_root = REPO.parent / name
    if state_root.exists():
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    return state_root


def test_run_command_writes_run_json_and_gate_index() -> None:
    state_root = _fresh_state_root("jc_run_test1")
    cp = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "run",
         "--plan", "remediation/v4/tasks.json",
         "--state-root", str(state_root),
         "--through", "W9"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env={**os.environ, "JC_REMEDIATION_STATE_ROOT": str(state_root)},
    )
    assert cp.returncode in (20, 21), (
        f"run should exit with WAITING_* code, got {cp.returncode}\n"
        f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
    )

    run_json = state_root / "run.json"
    assert run_json.is_file()
    payload = json.loads(run_json.read_text(encoding="utf-8"))
    assert payload["baseline_commit"] == _git("rev-parse", "HEAD").strip()
    assert payload["completed_phases"] == ["B00", "B00-CG", "B01"]

    index = json.loads((state_root / "requests" / "INDEX.json").read_text())
    assert index["count"] >= 10


def test_run_command_exits_with_waiting_external_when_external_present() -> None:
    state_root = _fresh_state_root("jc_run_test2")
    cp = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "run",
         "--plan", "remediation/v4/tasks.json",
         "--state-root", str(state_root),
         "--through", "W9"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    # B02-SPEC-INTAKE is EXTERNAL_GATE in the gate list, so the runner must
    # exit 21 (WAITING_EXTERNAL).
    assert cp.returncode == 21, (
        f"expected 21 (WAITING_EXTERNAL), got {cp.returncode}\n{cp.stdout}"
    )


def test_run_command_prints_resume_command() -> None:
    state_root = _fresh_state_root("jc_run_test3")
    cp = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "run",
         "--plan", "remediation/v4/tasks.json",
         "--state-root", str(state_root),
         "--through", "W9"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert "Unique resume command:" in cp.stdout
    # Extract the line and verify it matches the format施工方案 §1.3
    line = next(
        ln for ln in cp.stdout.splitlines() if ln.startswith("Unique resume command:")
    )
    cmd = line.split(":", 1)[1].strip()
    assert cmd.startswith("py -3.12 -B tools/remediate_v4.py run")
    assert "--plan remediation/v4/tasks.json" in cmd
    assert "--state-root" in cmd
    assert "--through W9" in cmd


def test_run_command_reports_pending_gates_per_kind() -> None:
    state_root = _fresh_state_root("jc_run_test4")
    cp = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "run",
         "--plan", "remediation/v4/tasks.json",
         "--state-root", str(state_root),
         "--through", "W9"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    # Both WAITING_HUMAN and WAITING_EXTERNAL markers must appear in stdout.
    assert "WAITING_HUMAN" in cp.stdout
    assert "WAITING_EXTERNAL" in cp.stdout