#!/usr/bin/env python3
"""Replay one recorded verification command to reduce fake PASS risk."""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent


def replay_report(report_path: str | Path, seed: int = 0) -> Dict[str, Any]:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    commands = [
        command
        for phase in report.get("phases", [])
        for command in phase.get("commands", [])
        if command.get("returncode") == 0 and command.get("command")
    ]
    if not commands:
        return {"status": "FAIL", "issue": "no successful command found to replay"}

    rng = random.Random(seed)
    chosen = rng.choice(commands)
    proc = subprocess.run(
        chosen["command"],
        cwd=str(ROOT),
        shell=True,
        text=True,
        capture_output=True,
    )
    stdout_match = proc.stdout.strip() == (chosen.get("stdout") or "").strip()
    status = "PASS" if proc.returncode == chosen["returncode"] else "FAIL"
    return {
        "status": status,
        "stdout_full_match": stdout_match,
        "command": chosen["command"],
        "expected_returncode": chosen["returncode"],
        "actual_returncode": proc.returncode,
        "stdout_tail": proc.stdout[-1000:],
        "expected_stdout_head": (chosen.get("stdout") or "")[:200],
        "actual_stdout_head": proc.stdout[:200],
        "stderr_tail": proc.stderr[-1000:],
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a command from a phase verification report.")
    parser.add_argument("report")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    result = replay_report(args.report, args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
