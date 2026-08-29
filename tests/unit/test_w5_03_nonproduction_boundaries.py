"""Current source-tool and candidate-asset isolation contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "docs/architecture/module-authority.json"
DISPOSITION = ROOT / "remediation/v4/file-disposition.json"
SOURCE_TOOL_PATHS = (
    "compiler_core/analysis.py",
    "compiler_core/rule_lookup.py",
    "compiler_core/training.py",
)
DEPLOYABLE_CLASSES = {"FORMAL_CORE", "PUBLIC_ADAPTER", "RUNTIME_OUTPUT"}
NONPRODUCTION_CLASSES = {"SOURCE_TOOL", "EXPERIMENT_ONLY", "CANDIDATE_ASSET"}


def _authority() -> dict:
    return json.loads(AUTHORITY.read_text(encoding="utf-8"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            if node.module == "compiler_core":
                imports.update(f"compiler_core.{alias.name}" for alias in node.names)
    return imports


def _module_path(module: str) -> str:
    return module.replace(".", "/") + ".py"


def _class_for(module: str, exact: dict[str, str], prefixes: list[dict]) -> str | None:
    path = _module_path(module)
    if path in exact:
        return exact[path]
    for rule in prefixes:
        if path.startswith(rule["prefix"]):
            return rule["class"]
    return None


def test_authority_declares_three_offline_source_tools() -> None:
    authority = _authority()
    exact = {item["path"]: item["class"] for item in authority["path_rules"]}

    assert {path: exact[path] for path in SOURCE_TOOL_PATHS} == {
        path: "SOURCE_TOOL" for path in SOURCE_TOOL_PATHS
    }


def test_deployable_python_has_no_source_tool_experiment_or_candidate_import() -> None:
    authority = _authority()
    exact = {item["path"]: item["class"] for item in authority["path_rules"]}
    prefixes = authority["prefix_rules"]
    violations: list[str] = []
    for path, module_class in exact.items():
        source_path = ROOT / path
        if module_class not in DEPLOYABLE_CLASSES or not source_path.is_file():
            continue
        for imported in _imports(source_path):
            target_class = _class_for(imported, exact, prefixes)
            if target_class in NONPRODUCTION_CLASSES:
                violations.append(f"{path} -> {imported} ({target_class})")

    assert violations == []


def test_public_surfaces_omit_offline_commands_and_advisory_tools() -> None:
    paths = (
        "compiler_core/__init__.py",
        "compiler_core/cli.py",
        "compiler_core/client.py",
        "compiler_core/contracts.py",
        "compiler_core/mcp.py",
    )
    forbidden = (
        "compiler_core.analysis",
        "compiler_core.training",
        "compiler_core.rule_lookup",
        "compiler_core.rule_governance",
        "jc_analyze_strategy",
        "jc_analyze_similar_cases",
        "jc_lookup_rule",
        'add_parser("analyze"',
        'add_parser("training"',
        'add_parser("rules"',
    )

    for path in paths:
        source = (ROOT / path).read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{path} retains {marker}"


def test_disposition_preserves_candidates_and_classifies_source_tools() -> None:
    document = json.loads(DISPOSITION.read_text(encoding="utf-8"))
    by_path = {item["path"]: item for item in document["paths"]}
    for path in SOURCE_TOOL_PATHS:
        item = by_path[path]
        assert item == {
            "path": path,
            "authority_class": "SOURCE_TOOL",
            "production_wheel": False,
        }

    for path in (
        "configs/zh_CN/source_manifest.yaml",
        "configs/zh_CN/ontology_map.yaml",
        "configs/zh_CN/domain_config.example.yaml",
        "configs/packs/hk-legacy-corpus/manifest.yaml",
        "configs/packs/us-federal-legacy-corpus/manifest.yaml",
        "configs/packs/us-l0-adapter-legacy-corpus/manifest.yaml",
        "pipeline/pipeline.py",
    ):
        assert (ROOT / path).is_file(), f"candidate/source asset was moved or deleted: {path}"


def test_nonproduction_assets_add_no_distribution_or_deployment_authority() -> None:
    tracked = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    ).stdout.splitlines()
    normalized = [path.replace("\\", "/") for path in tracked]

    assert [path for path in normalized if path.endswith("pyproject.toml")] == ["pyproject.toml"]
    assert sorted(path for path in normalized if path.startswith(".github/workflows/")) == [
        ".github/workflows/auto-release.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/release-audit.yml",
    ]
    deployment_names = {
        "Dockerfile", "Chart.yaml", "Procfile", "fly.toml",
        "compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml",
        "deployment.yml", "deployment.yaml",
    }
    assert not {
        path for path in normalized
        if path.split("/")[-1] in deployment_names
        and path.startswith(("addons/", "compiler_core/", "configs/", "pipeline/"))
    }
