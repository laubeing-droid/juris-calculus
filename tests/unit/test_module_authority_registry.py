"""W9：模块 authority 四类清册回归测试。

方案 §15：对 compiler_core 全量模块建立 FORMAL_CORE / ADVISORY /
COMPATIBILITY / REMOVE_OR_EXTERNALIZE 清册；新增模块必须先分类。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "docs" / "architecture" / "module-authority-v4.json"
VALID_CLASSES = {"FORMAL_CORE", "ADVISORY", "COMPATIBILITY", "REMOVE_OR_EXTERNALIZE"}


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _all_compiler_core_modules() -> set[str]:
    core_root = REPO_ROOT / "compiler_core"
    return {
        f"compiler_core.{path.stem}"
        for path in core_root.glob("*.py")
        if path.stem != "__init__"
    }


def test_registry_covers_every_module(registry) -> None:
    classified = {entry["module"] for entry in registry["modules"]}
    actual = _all_compiler_core_modules()
    missing = sorted(actual - classified)
    unknown = sorted(classified - actual)
    assert not missing, f"unclassified modules: {missing}"
    assert not unknown, f"stale registry entries: {unknown}"


def test_registry_classes_valid_and_unique(registry) -> None:
    seen: set[str] = set()
    for entry in registry["modules"]:
        assert entry["class"] in VALID_CLASSES, entry["module"]
        assert entry["rationale"].strip(), entry["module"]
        assert entry["module"] not in seen, f"duplicate entry: {entry['module']}"
        seen.add(entry["module"])


def test_formal_core_contains_protected_kernel(registry) -> None:
    formal = {entry["module"] for entry in registry["modules"] if entry["class"] == "FORMAL_CORE"}
    required = {
        "compiler_core.contracts",
        "compiler_core.contracts_v4",
        "compiler_core.application",
        "compiler_core.evaluator",
        "compiler_core.argumentation",
        "compiler_core.independent_grounded_checker",
        "compiler_core.audit_bundle",
        "compiler_core.rule_packs",
        "compiler_core.version",
        "compiler_core.client",
        "compiler_core.cli",
    }
    assert required <= formal


def test_advisory_modules_never_formal(registry) -> None:
    """ADVISORY 与 REMOVE_OR_EXTERNALIZE 不得同时出现在 FORMAL_CORE。"""

    classes: dict[str, set[str]] = {}
    for entry in registry["modules"]:
        classes.setdefault(entry["module"], set()).add(entry["class"])
    conflicted = {module for module, items in classes.items() if len(items) > 1}
    assert not conflicted
