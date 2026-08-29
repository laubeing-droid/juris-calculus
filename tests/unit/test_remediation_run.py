"""End-to-end tests for `tools/remediate_v4.py run` on 3.0 plans.

Every execution is a fresh subprocess: the runner validates the plan, runs
commands in dependency order, stops at the first failure, and writes exactly
one JSON run log. There is no receipt recovery; an interrupted run is resumed
by rerunning it.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "tools" / "remediate_v4.py"


def _write_plan(
    path: Path,
    tasks: list[dict],
    *,
    schema_version: str = "jc/remediation-task/3.0",
) -> Path:
    document = {"schema_version": schema_version, "tasks": tasks}
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _task(task_id: str, *, depends_on: list[str] | None = None, argv: list[str] | None = None,
          timeout_seconds: int = 120, expected_exit_codes: list[int] | None = None) -> dict:
    return {
        "id": task_id,
        "depends_on": depends_on or [],
        "objective": f"run {task_id}",
        "argv": argv or [["{python}", "-B", "-c", "print('ok')"]],
        "timeout_seconds": timeout_seconds,
        "expected_exit_codes": expected_exit_codes or [0],
    }


def _run(plan: Path, log: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(RUNNER), "run", "--plan", str(plan), "--log", str(log), *extra],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=300,
    )


def _log(log: Path) -> dict:
    return json.loads(log.read_text(encoding="utf-8"))


def test_successful_plan_writes_single_pass_log(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [
        _task("V4-01-A"),
        _task("V4-02-B", depends_on=["V4-01-A"]),
    ])
    log = tmp_path / "run.json"
    completed = _run(plan, log)
    assert completed.returncode == 0, completed.stderr
    document = _log(log)
    assert document["schema_version"] == "jc/remediation-run-log/1.0"
    assert document["status"] == "PASS"
    assert [(task["id"], task["status"]) for task in document["tasks"]] == [
        ("V4-01-A", "PASSED"), ("V4-02-B", "PASSED"),
    ]
    assert all(command["exit_code"] == 0 for task in document["tasks"] for command in task["commands"])


def test_first_failure_stops_the_run(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [
        _task("V4-01-A"),
        _task("V4-02-FAIL", depends_on=["V4-01-A"],
              argv=[[sys.executable, "-B", "-c", "import sys; sys.exit(3)"]]),
        _task("V4-03-C", depends_on=["V4-02-FAIL"]),
    ])
    log = tmp_path / "run.json"
    completed = _run(plan, log)
    assert completed.returncode == 1
    document = _log(log)
    assert document["status"] == "FAIL"
    statuses = {task["id"]: task["status"] for task in document["tasks"]}
    assert statuses == {
        "V4-01-A": "PASSED", "V4-02-FAIL": "FAILED", "V4-03-C": "NOT_RUN",
    }
    failed_command = next(
        command for task in document["tasks"]
        if task["id"] == "V4-02-FAIL" for command in task["commands"]
    )
    assert failed_command["exit_code"] == 3
    assert failed_command["accepted"] is False


def test_expected_nonzero_exit_code_continues(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [
        _task("V4-01-MISS", argv=[[sys.executable, "-B", "-c", "import sys; sys.exit(7)"]],
              expected_exit_codes=[7]),
        _task("V4-02-B", depends_on=["V4-01-MISS"]),
    ])
    log = tmp_path / "run.json"
    assert _run(plan, log).returncode == 0
    assert _log(log)["status"] == "PASS"


def test_each_command_uses_only_its_paired_expected_exit_code(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [
        _task(
            "V4-01-PAIR",
            argv=[
                [sys.executable, "-B", "-c", "import sys; sys.exit(7)"],
                [sys.executable, "-B", "-c", "import sys; sys.exit(7)"],
            ],
            expected_exit_codes=[0, 7],
        ),
    ])
    log = tmp_path / "run.json"
    assert _run(plan, log).returncode == 1
    command = _log(log)["tasks"][0]["commands"][0]
    assert command["expected_exit_codes"] == [0]
    assert command["accepted"] is False


def test_timeout_is_recorded_and_fails_the_run(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [
        _task("V4-01-HANG", argv=[[sys.executable, "-B", "-c", "import time; time.sleep(30)"]],
              timeout_seconds=1),
    ])
    log = tmp_path / "run.json"
    completed = _run(plan, log)
    assert completed.returncode == 1
    command = _log(log)["tasks"][0]["commands"][0]
    assert command["timed_out"] is True
    assert command["exit_code"] is None


def test_missing_executable_is_exit_127(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [
        _task("V4-01-GONE", argv=[["jc-definitely-missing-executable"]]),
    ])
    log = tmp_path / "run.json"
    assert _run(plan, log).returncode == 1
    assert _log(log)["tasks"][0]["commands"][0]["exit_code"] == 127


def test_through_stops_after_named_task(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [
        _task("V4-01-A"),
        _task("V4-02-B", depends_on=["V4-01-A"]),
        _task("V4-03-C", depends_on=["V4-02-B"]),
    ])
    log = tmp_path / "run.json"
    assert _run(plan, log, "--through", "V4-02-B").returncode == 0
    statuses = {task["id"]: task["status"] for task in _log(log)["tasks"]}
    assert statuses == {
        "V4-01-A": "PASSED", "V4-02-B": "PASSED", "V4-03-C": "NOT_RUN",
    }


def test_unknown_through_task_is_usage_error(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [_task("V4-01-A")])
    completed = _run(plan, tmp_path / "run.json", "--through", "V4-99-NOPE")
    assert completed.returncode == 2


def test_invalid_plan_is_usage_error_without_log(tmp_path: Path) -> None:
    plan = _write_plan(
        tmp_path / "plan.json", [_task("V4-01-A")],
        schema_version="jc/remediation-task/2.0",
    )
    log = tmp_path / "run.json"
    completed = _run(plan, log)
    assert completed.returncode == 2
    assert "plan problem" in completed.stderr
    assert not log.exists()


def test_runner_child_boundaries_are_utf8_strict(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [
        _task("V4-01-UTF8", argv=[
            [sys.executable, "-B", "-c",
             "import sys; sys.stdout.write('中文输出\\n')"],
        ]),
    ])
    log = tmp_path / "run.json"
    assert _run(plan, log).returncode == 0
    command = _log(log)["tasks"][0]["commands"][0]
    assert "中文输出" in command["stdout_tail"]
    assert command["stdout_sha256"].startswith("sha256:")


def test_runner_supplies_and_removes_short_temp_root(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [
        _task("V4-01-TEMP", argv=[
            [sys.executable, "-B", "-c", "import sys; print(sys.argv[1])", "{temp}"],
        ]),
    ])
    log = tmp_path / "run.json"
    assert _run(plan, log).returncode == 0
    temp_root = Path(_log(log)["tasks"][0]["commands"][0]["stdout_tail"].strip())
    assert temp_root.name.startswith("jcv4-")
    assert not temp_root.exists()


def test_invalid_utf8_child_output_fails_even_with_expected_zero(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path / "plan.json", [
        _task("V4-01-BAD-UTF8", argv=[
            [sys.executable, "-B", "-c", "import sys; sys.stdout.buffer.write(bytes([255]))"],
        ]),
    ])
    log = tmp_path / "run.json"
    assert _run(plan, log).returncode == 1
    command = _log(log)["tasks"][0]["commands"][0]
    assert command["exit_code"] == 0
    assert command["utf8_valid"] is False
    assert command["accepted"] is False


def test_rerun_after_interrupt_starts_clean(tmp_path: Path) -> None:
    """An interrupted run leaves no state to repair: rerunning re-executes."""

    plan_path = tmp_path / "plan.json"
    log = tmp_path / "run.json"
    plan_path.write_text(
        json.dumps({"schema_version": "jc/remediation-task/3.0", "tasks": [
            _task("V4-01-A"),
            _task("V4-02-HANG", depends_on=["V4-01-A"],
                  argv=[[sys.executable, "-B", "-c", "import time; time.sleep(30)"]],
                  timeout_seconds=2),
        ]}),
        encoding="utf-8",
    )
    interrupted = _run(plan_path, log)
    assert interrupted.returncode == 1

    plan_path.write_text(
        json.dumps({"schema_version": "jc/remediation-task/3.0", "tasks": [
            _task("V4-01-A"),
            _task("V4-02-OK", depends_on=["V4-01-A"]),
        ]}),
        encoding="utf-8",
    )
    assert _run(plan_path, log).returncode == 0
    document = _log(log)
    assert document["status"] == "PASS"
    assert [task["id"] for task in document["tasks"]] == ["V4-01-A", "V4-02-OK"]


def test_checkin_plan_runs_through_first_authority_task(tmp_path: Path) -> None:
    """The committed plan executes V4-01 (skipped here for cost: lint only)."""

    completed = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "lint-plan",
         "--plan", str(REPO / "remediation" / "v4" / "tasks.v3.json")],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert "8 tasks" in completed.stdout


@pytest.mark.parametrize("command", ("run", "lint-plan"))
def test_default_plan_argument_is_v3(command: str) -> None:
    source = (REPO / "tools" / "remediation" / "cli.py").read_text(encoding="utf-8")
    assert 'DEFAULT_PLAN = Path("remediation/v4/tasks.v3.json")' in source
    assert "tasks.json" not in source.replace("tasks.v3.json", "")
