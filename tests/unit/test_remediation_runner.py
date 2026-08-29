"""Unit tests for the 3.0 remediation plan contract and runner helpers.

The runner validates the plan, executes commands in dependency order, stops
at the first failure, and writes one run log. These tests pin that contract
without any receipt, approval, or wave-gate machinery.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.remediation.plan import PlanError, execution_order, lint_document, load_plan
from tools.remediation.process import expand_argv


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "tools" / "remediate_v4.py"
V3_PLAN = REPO / "remediation" / "v4" / "tasks.v3.json"
FROZEN_TASKS = REPO / "remediation" / "v4" / "tasks.json"
FROZEN_SCHEMA = REPO / "remediation" / "v4" / "task.schema.json"
FROZEN_TASKS_SHA256 = "F0EB863BB2DF8F663F4B6AF2C4B572FA5F5DC210854E562834A10227ED9E41A0"
FROZEN_SCHEMA_SHA256 = "B83D7F25ADA32D17A40483D4EEAF3F39E2C5CAB3CD898E15814DCE9295256F04"


def _plan_document(**overrides):
    task = {
        "id": "V4-01-SMOKE",
        "depends_on": [],
        "objective": "run one command",
        "argv": [["{python}", "-B", "-c", "print('ok')"]],
        "timeout_seconds": 60,
        "expected_exit_codes": [0],
    }
    task.update(overrides)
    return {"schema_version": "jc/remediation-task/3.0", "tasks": [task]}


def test_old_tasks_json_and_schema_bytes_are_frozen() -> None:
    assert (
        hashlib.sha256(FROZEN_TASKS.read_bytes()).hexdigest().upper()
        == FROZEN_TASKS_SHA256
    )
    assert (
        hashlib.sha256(FROZEN_SCHEMA.read_bytes()).hexdigest().upper()
        == FROZEN_SCHEMA_SHA256
    )


def test_runner_entrypoint_delegates_to_remediation_cli() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "from tools.remediation.cli import main" in source
    assert len(source.splitlines()) < 40


def test_runner_help_succeeds() -> None:
    completed = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "--help"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert completed.returncode == 0
    assert "lint-plan" in completed.stdout and "run" in completed.stdout


def test_checked_in_v3_plan_is_valid_and_ordered() -> None:
    plan = load_plan(V3_PLAN)
    assert [task.id for task in plan.order][0] == "V4-01-AUTHORITY"
    assert plan.order[-1].id == "V4-08-FULL"
    for task in plan.tasks:
        assert task.objective.strip()
        assert task.argv and len(task.argv) == len(task.expected_exit_codes)
        assert 0 < task.timeout_seconds <= 14400


@pytest.mark.parametrize(
    ("mutation", "problem_fragment"),
    (
        ({"schema_version": "jc/remediation-task/2.0"}, "schema_version"),
        ({"extra": 1}, "fields must be exactly"),
        ({"argv": [["a"], ["b"]], "expected_exit_codes": [0]}, "length"),
        ({"id": "V4-01-SMOKE", "depends_on": ["V4-02-MISSING"]}, "unknown task"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"expected_exit_codes": [999]}, "expected_exit_codes"),
        ({"objective": "   "}, "objective"),
    ),
)
def test_lint_rejects_contract_mutations(mutation: dict, problem_fragment: str) -> None:
    overrides = {key: value for key, value in mutation.items() if key != "schema_version"}
    document = _plan_document(**overrides)
    if "schema_version" in mutation:
        document["schema_version"] = mutation["schema_version"]
    problems = lint_document(document)
    assert problems, f"expected a problem containing {problem_fragment!r}"
    assert any(problem_fragment in problem for problem in problems), problems


def test_lint_rejects_dependency_cycle() -> None:
    document = _plan_document()
    document["tasks"].append({
        "id": "V4-02-CYCLE",
        "depends_on": ["V4-01-SMOKE"],
        "objective": "back edge",
        "argv": [["{python}", "-B", "-c", "print('x')"]],
        "timeout_seconds": 60,
        "expected_exit_codes": [0],
    })
    document["tasks"][0]["depends_on"] = ["V4-02-CYCLE"]
    problems = lint_document(document)
    assert any("dependency cycle" in problem for problem in problems)


def test_duplicate_task_ids_are_rejected() -> None:
    document = _plan_document()
    document["tasks"] = [document["tasks"][0], document["tasks"][0]]
    assert any("duplicate task id" in problem for problem in lint_document(document))


def test_execution_order_places_dependencies_first() -> None:
    from tools.remediation.plan import PlanTask

    tasks = (
        PlanTask("V4-03-C", (), "c", (("%py",),), 60, (0,)),
        PlanTask("V4-01-A", ("V4-02-B",), "a", (("%py",),), 60, (0,)),
        PlanTask("V4-02-B", (), "b", (("%py",),), 60, (0,)),
    )
    order = [task.id for task in execution_order(tasks)]
    assert order.index("V4-02-B") < order.index("V4-01-A") < order.index("V4-03-C")


def test_expand_argv_placeholders() -> None:
    expanded = expand_argv(
        ("{python}", "-B", "{root}", "{temp}/suite"),
        python="python.exe", root=str(REPO), temp="D:/jcv4-test",
    )
    assert expanded == ["python.exe", "-B", str(REPO), "D:/jcv4-test/suite"]


def test_load_plan_rejects_unreadable_document(tmp_path: Path) -> None:
    bad = tmp_path / "plan.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(PlanError):
        load_plan(bad)


def test_lint_plan_cli_reports_problems(tmp_path: Path) -> None:
    document = _plan_document(id="invalid-id")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(document), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "lint-plan", "--plan", str(plan_path)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert completed.returncode == 2
    assert "plan problem" in completed.stderr
