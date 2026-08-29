"""Load and validate a 3.0 remediation task plan.

The plan contract is intentionally small: id, depends_on, objective, argv,
timeout_seconds, and expected_exit_codes. Validation covers the closed field
set, schema version, argv/exit-code arity, unique ids, known dependencies,
and dependency cycles. The historical tasks.json stays byte-frozen and is
never an input here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from tools.remediation.process import expand_argv

SCHEMA_VERSION = "jc/remediation-task/3.0"
TASK_FIELDS = frozenset({
    "id", "depends_on", "objective", "argv", "timeout_seconds", "expected_exit_codes",
})
PLAN_FIELDS = frozenset({"schema_version", "tasks"})


class PlanError(ValueError):
    """Raised when a plan document violates the 3.0 contract."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass(frozen=True)
class PlanTask:
    id: str
    depends_on: tuple[str, ...]
    objective: str
    argv: tuple[tuple[str, ...], ...]
    timeout_seconds: int
    expected_exit_codes: tuple[int, ...]

    def expanded_commands(self, *, python: str, root: str, temp: str) -> list[list[str]]:
        return [
            expand_argv(command, python=python, root=root, temp=temp)
            for command in self.argv
        ]


@dataclass(frozen=True)
class Plan:
    path: Path
    tasks: tuple[PlanTask, ...]
    order: tuple[PlanTask, ...] = field(default_factory=tuple)

    def task(self, task_id: str) -> PlanTask:
        for candidate in self.tasks:
            if candidate.id == task_id:
                return candidate
        raise KeyError(task_id)


def lint_document(document: Any) -> list[str]:
    """Return every contract problem in an already-parsed plan document."""

    problems: list[str] = []
    if not isinstance(document, dict) or set(document) != set(PLAN_FIELDS):
        return [f"plan fields must be exactly {sorted(PLAN_FIELDS)}"]
    if document["schema_version"] != SCHEMA_VERSION:
        problems.append(
            f"schema_version must be {SCHEMA_VERSION}; got {document['schema_version']!r}"
        )
    raw_tasks = document["tasks"]
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return problems + ["tasks must be a non-empty array"]
    by_id: dict[str, PlanTask] = {}
    for index, raw in enumerate(raw_tasks):
        label = f"tasks[{index}]"
        if not isinstance(raw, dict) or set(raw) != set(TASK_FIELDS):
            problems.append(f"{label} fields must be exactly {sorted(TASK_FIELDS)}")
            continue
        task_id = raw["id"]
        if not isinstance(task_id, str) or not task_id:
            problems.append(f"{label}.id must be a non-empty string")
            continue
        if task_id in by_id:
            problems.append(f"duplicate task id: {task_id}")
            continue
        depends_on = raw["depends_on"]
        if not isinstance(depends_on, list) or any(
            not isinstance(item, str) or not item for item in depends_on
        ):
            problems.append(f"{task_id}.depends_on must be an array of strings")
            continue
        if task_id in depends_on:
            problems.append(f"{task_id} depends on itself")
        objective = raw["objective"]
        if not isinstance(objective, str) or not objective.strip():
            problems.append(f"{task_id}.objective must be a non-empty string")
        raw_argv = raw["argv"]
        argv_valid = (
            isinstance(raw_argv, list) and bool(raw_argv)
            and all(
                isinstance(command, list) and bool(command)
                and all(isinstance(item, str) and item for item in command)
                for command in raw_argv
            )
        )
        if not argv_valid:
            problems.append(f"{task_id}.argv must be a non-empty array of non-empty string arrays")
        timeout = raw["timeout_seconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 14400:
            problems.append(f"{task_id}.timeout_seconds must be an integer in [1, 14400]")
        expected = raw["expected_exit_codes"]
        expected_valid = (
            isinstance(expected, list) and bool(expected)
            and all(
                isinstance(code, int) and not isinstance(code, bool) and 0 <= code <= 255
                for code in expected
            )
        )
        if not expected_valid:
            problems.append(f"{task_id}.expected_exit_codes must be integers in [0, 255]")
        if argv_valid and expected_valid and len(raw_argv) != len(expected):
            problems.append(
                f"{task_id} argv length {len(raw_argv)} != expected_exit_codes length {len(expected)}"
            )
        if argv_valid and expected_valid:
            by_id[task_id] = PlanTask(
                id=task_id, depends_on=tuple(depends_on), objective=objective,
                argv=tuple(tuple(command) for command in raw_argv),
                timeout_seconds=timeout, expected_exit_codes=tuple(expected),
            )
    for task in by_id.values():
        for dependency in task.depends_on:
            if dependency not in by_id:
                if dependency in {raw.get("id") for raw in raw_tasks if isinstance(raw, dict)}:
                    problems.append(
                        f"{dependency} is skipped because its own fields are invalid"
                    )
                else:
                    problems.append(f"{task.id} depends on unknown task {dependency}")
    problems.extend(_cycle_problems(by_id))
    return problems


def _cycle_problems(by_id: dict[str, PlanTask]) -> list[str]:
    problems: list[str] = []
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(task_id: str) -> None:
        state[task_id] = 1
        stack.append(task_id)
        for dependency in by_id[task_id].depends_on:
            if dependency not in by_id:
                continue
            marker = state.get(dependency, 0)
            if marker == 1:
                cycle = stack[stack.index(dependency):] + [dependency]
                problems.append("dependency cycle: " + " -> ".join(cycle))
            elif marker == 0:
                visit(dependency)
        stack.pop()
        state[task_id] = 2

    for task_id in sorted(by_id):
        if state.get(task_id, 0) == 0:
            visit(task_id)
    return problems


def execution_order(tasks: tuple[PlanTask, ...]) -> tuple[PlanTask, ...]:
    """Return a deterministic topological order (dependents after dependencies)."""

    by_id = {task.id: task for task in tasks}
    done: dict[str, bool] = {}
    order: list[PlanTask] = []

    def visit(task: PlanTask) -> None:
        pending = done.get(task.id)
        if pending is True:
            return
        if pending is False:
            raise PlanError(["dependency cycle through " + task.id])
        done[task.id] = False
        for dependency in task.depends_on:
            if dependency in by_id:
                visit(by_id[dependency])
        done[task.id] = True
        order.append(task)

    for task in sorted(by_id.values(), key=lambda item: item.id):
        visit(task)
    return tuple(order)


def load_plan(path: Path) -> Plan:
    """Parse, lint, and order a plan file; raise PlanError on any problem."""

    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlanError([f"plan is unreadable: {type(exc).__name__}: {exc}"]) from exc
    problems = lint_document(document)
    _validate_against_schema(path, document, problems)
    if problems:
        raise PlanError(problems)
    tasks: tuple[PlanTask, ...] = tuple(
        PlanTask(
            id=raw["id"], depends_on=tuple(raw["depends_on"]), objective=raw["objective"],
            argv=tuple(tuple(command) for command in raw["argv"]),
            timeout_seconds=raw["timeout_seconds"],
            expected_exit_codes=tuple(raw["expected_exit_codes"]),
        )
        for raw in document["tasks"]
    )
    return Plan(path=path, tasks=tasks, order=execution_order(tasks))


def _validate_against_schema(path: Path, document: Any, problems: list[str]) -> None:
    """Cross-check the document with task.v3.schema.json when jsonschema exists."""

    try:
        import jsonschema
    except ImportError:
        return
    schema_path = path.parent / "task.v3.schema.json"
    if not schema_path.is_file():
        schema_path = (
            Path(__file__).resolve().parents[2] / "remediation/v4/task.v3.schema.json"
        )
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        problems.append(f"task schema is unreadable: {type(exc).__name__}: {exc}")
        return
    try:
        jsonschema.validate(document, schema, cls=jsonschema.Draft202012Validator)
    except jsonschema.ValidationError as exc:
        problems.append(f"schema validation failed at {list(exc.absolute_path)}: {exc.message}")
    except jsonschema.SchemaError as exc:
        problems.append(f"task schema itself is invalid: {exc.message}")
