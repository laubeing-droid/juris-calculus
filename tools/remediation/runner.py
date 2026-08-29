"""Generic dependency-ordered task runner.

The runner does exactly four things: validate the plan, execute commands in
dependency order, stop at the first failure, and write one run log for the
execution. There is no receipt recovery, rebinding, supersession, human or
external gate: an interrupted run is resumed by rerunning it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import uuid
from typing import Any

from tools.remediation.plan import Plan, PlanTask
from tools.remediation.process import child_environment, run_command
from tools.remediation.run_log import command_record, write_run_log

SCHEMA_VERSION = "jc/remediation-run-log/1.0"
EXIT_OK = 0
EXIT_TASK_FAILED = 1
STATUS_PASSED = "PASSED"
STATUS_FAILED = "FAILED"
STATUS_NOT_RUN = "NOT_RUN"


def _now_wire() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _plan_digest(plan: Plan) -> str:
    return "sha256:" + hashlib.sha256(plan.path.read_bytes()).hexdigest()


def _execute_tasks(
    selected: list[PlanTask],
    *,
    root: Path,
    python: str,
    temp: str,
    environment: dict[str, str],
) -> tuple[list[dict[str, Any]], bool, set[str]]:
    task_records: list[dict[str, Any]] = []
    seen: set[str] = set()
    failed = False
    for task in selected:
        if task.id in seen:
            continue
        seen.add(task.id)
        if failed:
            task_records.append({"id": task.id, "status": STATUS_NOT_RUN, "commands": []})
            continue
        commands: list[dict[str, Any]] = []
        for command, expected in zip(
            task.expanded_commands(python=python, root=str(root), temp=temp),
            task.expected_exit_codes,
            strict=True,
        ):
            result = run_command(
                command, cwd=root, timeout_seconds=task.timeout_seconds, env=environment,
            )
            record = command_record(result, expected_exit_codes=(expected,))
            commands.append(record)
            if not record["accepted"]:
                failed = True
                break
        task_records.append({
            "id": task.id,
            "status": STATUS_FAILED if failed else STATUS_PASSED,
            "commands": commands,
        })
    return task_records, failed, seen


def run_plan(
    plan: Plan,
    *,
    root: Path,
    log_path: Path,
    through: str | None = None,
    extra_environment: dict[str, str] | None = None,
    python: str | None = None,
) -> int:
    """Execute the plan topologically, stop at first failure, and log the run."""

    order = plan.order
    if through is not None and through not in {task.id for task in plan.tasks}:
        raise KeyError(f"unknown --through task: {through}")
    selected: list[PlanTask] = []
    for task in order:
        selected.append(task)
        if task.id == through:
            break
    root = Path(root).resolve()
    python = python or sys.executable
    environment = child_environment(extra_environment)
    started_at = _now_wire()
    temp_parent = root.anchor if os.name == "nt" else None
    with tempfile.TemporaryDirectory(prefix="jcv4-", dir=temp_parent) as temp:
        task_records, failed, seen = _execute_tasks(
            selected, root=root, python=python, temp=temp, environment=environment,
        )
    for task in plan.tasks:
        if task.id not in seen:
            task_records.append({"id": task.id, "status": STATUS_NOT_RUN, "commands": []})
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": uuid.uuid4().hex[:16],
        "started_at": started_at,
        "finished_at": _now_wire(),
        "plan_path": str(plan.path),
        "plan_sha256": _plan_digest(plan),
        "root": str(root),
        "python": python,
        "through": through,
        "status": "FAIL" if failed else "PASS",
        "tasks": task_records,
    }
    write_run_log(log_path, payload)
    return EXIT_TASK_FAILED if failed else EXIT_OK
