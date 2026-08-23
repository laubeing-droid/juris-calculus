"""Independent mutation checks for the repository-owned V4 contract fixture."""

from __future__ import annotations

from copy import deepcopy
import json
from math import prod
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/v4_contract/object-state-matrix.json"
AXES = ("execution", "review", "completeness", "certificate", "transport")


def _fixture_problems(document: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    objects = document.get("object_types", [])
    object_ids = [row.get("id") for row in objects if isinstance(row, dict)]
    if len(objects) != 73 or len(object_ids) != len(set(object_ids)):
        problems.append("object inventory")
    if any(row.get("formal") is not True for row in objects):
        problems.append("formal ownership")
    if any(
        row.get("schema_kind") == "object" and row.get("additional_properties") is not False
        for row in objects
    ):
        problems.append("closed object")

    axes = document.get("axes", {})
    if document.get("cartesian_cardinality") != prod(len(axes.get(name, [])) for name in AXES) * len(axes.get("decision", [])):
        problems.append("cartesian cardinality")
    constraints = document.get("decision_constraints", {})
    if set(constraints) != set(axes.get("decision", [])):
        problems.append("decision coverage")
    valid = sum(
        prod(len(row.get(name, [])) for name in AXES)
        for row in constraints.values()
        if isinstance(row, dict)
    )
    if document.get("valid_combination_count") != valid:
        problems.append("valid combination count")
    if constraints.get("accepted_formal_result", {}).get("certificate") != ["formal_verified"]:
        problems.append("formal certificate")
    if constraints.get("blocked", {}).get("transport") != ["error"]:
        problems.append("blocked transport")
    if constraints.get("engine_error", {}).get("execution") != ["engine_error"]:
        problems.append("engine error")
    return problems


def test_repository_fixture_oracle_detects_mutations() -> None:
    baseline = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert baseline["schema_version"] == "jc/v4-object-state-matrix/1.0"
    assert _fixture_problems(baseline) == []

    mutations = []
    duplicate = deepcopy(baseline)
    duplicate["object_types"][1]["id"] = duplicate["object_types"][0]["id"]
    mutations.append(duplicate)
    open_object = deepcopy(baseline)
    open_object["object_types"][1]["additional_properties"] = True
    mutations.append(open_object)
    nonformal = deepcopy(baseline)
    nonformal["object_types"][0]["formal"] = False
    mutations.append(nonformal)
    wrong_cartesian = deepcopy(baseline)
    wrong_cartesian["cartesian_cardinality"] += 1
    mutations.append(wrong_cartesian)
    wrong_valid = deepcopy(baseline)
    wrong_valid["valid_combination_count"] += 1
    mutations.append(wrong_valid)
    fail_open = deepcopy(baseline)
    fail_open["decision_constraints"]["blocked"]["transport"] = ["success"]
    mutations.append(fail_open)

    assert all(_fixture_problems(mutated) for mutated in mutations)
