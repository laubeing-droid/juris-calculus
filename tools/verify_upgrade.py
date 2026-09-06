"""Thin aggregation entry for one full V5 upgrade acceptance run (U11).

Runs the versioned task plan through the existing generic runner and writes a
structured acceptance summary. It reads only real exits and run logs: a task
that did not run, timed out, or exited nonzero fails the whole acceptance —
there is no manual pass flag.

Usage:
    python -B tools/verify_upgrade.py \
        --plan remediation/v5/tasks.v1.json --output work/v5-acceptance
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools.remediation.plan import load_plan  # noqa: E402
from tools.remediation.runner import run_plan  # noqa: E402

SUMMARY_SCHEMA = "jc/v5-upgrade-acceptance/1.0"
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=REPO / "remediation/v5/tasks.v1.json")
    parser.add_argument("--output", type=Path, default=REPO / "work/v5-acceptance")
    args = parser.parse_args()

    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "required-run.json"
    report_path = output_dir / "acceptance-summary.json"
    stale_dumps = output_dir / "required-run-failed-output"
    if stale_dumps.is_dir():
        import shutil

        shutil.rmtree(stale_dumps, ignore_errors=True)

    try:
        plan = load_plan(args.plan)
    except Exception as exc:  # PlanError or schema problem
        print(f"verify-upgrade refused: plan invalid: {exc}", file=sys.stderr)
        return EXIT_USAGE

    exit_code = run_plan(plan, root=REPO, log_path=log_path)

    try:
        run_log = json.loads(log_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"verify-upgrade failed: run log unreadable: {exc}", file=sys.stderr)
        return EXIT_FAILED

    task_rows = []
    all_passed = run_log.get("status") == "PASS"
    for task in run_log.get("tasks", ()):
        command_rows = []
        for command in task.get("commands", ()):
            command_rows.append({
                "exit_code": command.get("exit_code"),
                "accepted": command.get("accepted"),
                "duration_seconds": command.get("duration_seconds"),
                "failure_output_dir": command.get("failure_output_dir"),
            })
            if command.get("accepted") is not True:
                all_passed = False
        task_rows.append({"id": task.get("id"), "status": task.get("status"), "commands": command_rows})
        if task.get("status") != "PASSED":
            all_passed = False

    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "plan": str(args.plan),
        "run_log": str(log_path),
        "run_status": run_log.get("status"),
        "all_required_tasks_passed": all_passed,
        "tasks": task_rows,
        "claims": [
            "acceptance reflects only the run log written by this execution",
            "BUILD_ACCEPTED may be reported only when all_required_tasks_passed "
            "is true; production activation and legal correctness are separate "
            "claims that this summary never makes",
        ],
    }
    report_path.write_bytes(
        json.dumps(summary, ensure_ascii=False, indent=1).encode("utf-8") + b"\n")
    print(
        f"verify-upgrade: run_status={summary['run_status']} "
        f"all_passed={all_passed} summary={report_path}"
    )
    return EXIT_OK if all_passed else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
