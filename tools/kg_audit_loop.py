#!/usr/bin/env python3
"""Run dual knowledge graph audits and merge root-cause findings."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kg_audit_common import ROOT, write_json


AUDITORS = {
    "correctness": "tools/kg_correctness_auditor.py",
    "completeness": "tools/kg_completeness_auditor.py",
}


def run_dual_audit(contracts: str = "configs/juris_contracts.yaml",
                   out_dir: str = "reports/kg_audit",
                   mode: str = "local") -> Dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_root = ROOT / out_dir
    out_root.mkdir(parents=True, exist_ok=True)
    child_reports = []
    for role, script in AUDITORS.items():
        out_path = out_root / f"{stamp}_{role}.json"
        command = _command_for(role, script, contracts, out_path, mode)
        proc = subprocess.Popen(
            command,
            cwd=str(ROOT),
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate()
        report = _load_child_report(out_path)
        child_reports.append({
            "role": role,
            "pid": proc.pid,
            "command": command,
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "report_path": str(out_path),
            "report": report,
        })

    merged_findings = _merge_findings(child_reports)
    summary = {
        "status": "PASS" if not merged_findings and all(r["returncode"] == 0 for r in child_reports) else "FAIL",
        "role": "kg_audit_loop",
        "pid": os.getpid(),
        "mode": mode,
        "child_reports": child_reports,
        "merged_findings": merged_findings,
        "blueprint_repair_queue": _repair_queue(merged_findings),
    }
    summary_path = out_root / f"{stamp}_summary.json"
    write_json(summary_path, summary)
    summary["summary_path"] = str(summary_path)
    return summary


def _command_for(role: str, script: str, contracts: str, out_path: Path, mode: str) -> str:
    if mode == "claude" and shutil.which("claude"):
        prompt = (
            f"Run {role} knowledge graph audit for juris-calculus. "
            f"Use {script} as the executable specification, contracts={contracts}, "
            f"and write JSON report to {out_path}."
        )
        return f'claude -p --allowedTools "Read(*),Write(*),Bash(*)" "{prompt}"'
    return f"python {script} --contracts {contracts} --out {out_path}"


def _load_child_report(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"status": "FAIL", "findings": [{"issue": "child report missing", "root_cause_node": str(path)}]}
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_findings(child_reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for child in child_reports:
        for item in child.get("report", {}).get("findings", []):
            key = "|".join([
                str(item.get("contract_id", "")),
                str(item.get("field_path", "")),
                str(item.get("issue", "")),
            ])
            merged[key] = item
    return list(merged.values())


def _repair_queue(findings: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    queue = []
    for item in findings:
        queue.append({
            "root_cause_node": str(item.get("root_cause_node", "")),
            "contract_id": str(item.get("contract_id", "")),
            "field_path": str(item.get("field_path", "")),
            "suggestion": str(item.get("blueprint_patch_suggestion", "")),
        })
    return queue


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run dual knowledge graph audit loop.")
    parser.add_argument("--contracts", default="configs/juris_contracts.yaml")
    parser.add_argument("--out-dir", default="reports/kg_audit")
    parser.add_argument("--mode", choices=["local", "claude"], default="local")
    args = parser.parse_args(argv)
    summary = run_dual_audit(args.contracts, args.out_dir, args.mode)
    print(f"status={summary['status']} findings={len(summary['merged_findings'])} report={summary['summary_path']}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
