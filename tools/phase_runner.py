#!/usr/bin/env python3
"""Run phase gates and write verification evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.blueprint_contract_auditor import audit_matrix, load_matrix

def run_phases(matrix_path: str | Path = "configs/juris_phase_matrix.yaml",
               phase_id: str | None = None,
               run_all: bool = False,
               use_build_phases: bool = False,
               dry_run: bool = False,
               report_dir: str | Path | None = None) -> Dict[str, Any]:
    matrix = load_matrix(matrix_path)
    contract_report = audit_matrix(matrix_path)
    if contract_report["status"] != "PASS":
        return _summary("FAIL", [], [contract_report])

    source_key = "build_phases" if use_build_phases else "phases"
    phases = matrix.get(source_key, [])
    selected = _select_phases(phases, phase_id, run_all or (use_build_phases and not phase_id))
    if not selected:
        raise ValueError(f"No phase selected. Use --phase <ID>, --all, or --all-build.")

    reports: List[Dict[str, Any]] = []
    for phase in selected:
        reports.append(_run_phase(phase, dry_run=dry_run))
        if reports[-1]["status"] != "PASS":
            break

    summary = _summary("PASS" if all(r["status"] == "PASS" for r in reports) else "FAIL", reports, [contract_report])
    out_dir = _report_dir(matrix, report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_path = out_dir / f"verification_{stamp}_{os.getpid()}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["report_path"] = str(out_path)
    step35 = matrix.get("anti_degradation", {}).get("step35_spot_check", {})
    if step35.get("enforced") and not dry_run:
        if summary["status"] == "PASS":
            from tools.verification_replay import replay_report
            replay_result = replay_report(str(out_path), seed=os.getpid() % 100)
            summary["step35_spot_check"] = replay_result
            if replay_result["status"] != "PASS":
                summary["status"] = "FAIL"
                out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary

def _run_phase(phase: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    phase_id = phase["id"]
    commands = phase.get("commands", [])
    results: List[Dict[str, Any]] = []
    status = "PASS"
    for command in commands:
        result = _run_command(command, dry_run=dry_run)
        results.append(result)
        if result["returncode"] != 0:
            status = "FAIL"
            break
    return {
        "phase_id": phase_id,
        "name": phase.get("name", ""),
        "role": "verification",
        "pid": os.getpid(),
        "status": status,
        "commands": results,
    }

def _run_command(command: str, dry_run: bool = False) -> Dict[str, Any]:
    started = time.time()
    if dry_run:
        return {
            "command": command,
            "command_hash": _hash(command),
            "returncode": 0,
            "stdout": "[dry-run]",
            "stderr": "",
            "duration_seconds": 0.0,
        }
    proc = subprocess.Popen(
        command,
        cwd=str(ROOT),
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate()
    return {
        "command": command,
        "command_hash": _hash(command),
        "pid": proc.pid,
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "duration_seconds": round(time.time() - started, 3),
    }

def _select_phases(phases: Iterable[Dict[str, Any]], phase_id: str | None, run_all: bool) -> List[Dict[str, Any]]:
    phases = list(phases)
    if run_all:
        return phases
    if phase_id:
        return [p for p in phases if p.get("id") == phase_id]
    return []

def _summary(status: str, phase_reports: List[Dict[str, Any]], preflight: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "status": status,
        "role": "verification",
        "pid": os.getpid(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "preflight": preflight,
        "phases": phase_reports,
    }

def _report_dir(matrix: Dict[str, Any], report_dir: str | Path | None) -> Path:
    chosen = Path(report_dir or matrix.get("report_dir", "reports/phase_report"))
    if not chosen.is_absolute():
        chosen = ROOT / chosen
    return chosen

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run juris-calculus phase gates.")
    parser.add_argument("--matrix", default="configs/juris_phase_matrix.yaml")
    parser.add_argument("--phase")
    parser.add_argument("--build-phase")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--all-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-dir")
    args = parser.parse_args(argv)
    phase_id = args.phase or args.build_phase
    use_build = bool(args.build_phase or args.all_build)
    summary = run_phases(args.matrix, phase_id, args.all, use_build, args.dry_run, args.report_dir)
    print(f"status={summary['status']} report={summary.get('report_path', '')}")
    return 0 if summary["status"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
