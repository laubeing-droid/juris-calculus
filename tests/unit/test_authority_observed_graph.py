"""Observed authority graph contract tests: Git tracked files, local AST, policy.

The authority observation consults only the manual module-authority policy,
the Git tracked Python list, local AST imports and dynamic-import sites, and
pyproject entrypoints. No external code database exists in the V4 world.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from tools.remediation.observed_graph import (
    EXIT_FAILURE,
    EXIT_OK,
    build_parser,
    build_report,
    mode_exit_code,
)

REPO = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO / "docs" / "architecture" / "module-authority.json"


CLASSES = {
    "FORMAL_CORE": {"deployable": True, "production_wheel": True,
                    "may_import": ["FORMAL_CORE"]},
    "PUBLIC_ADAPTER": {"deployable": True, "production_wheel": True,
                       "may_import": ["FORMAL_CORE", "PUBLIC_ADAPTER", "RUNTIME_OUTPUT"]},
    "RUNTIME_OUTPUT": {"deployable": True, "production_wheel": True,
                       "may_import": ["FORMAL_CORE", "RUNTIME_OUTPUT"]},
    "SOURCE_TOOL": {"deployable": False, "production_wheel": False,
                    "may_import": ["FORMAL_CORE", "SOURCE_TOOL"]},
    "EXPERIMENT_ONLY": {"deployable": False, "production_wheel": False, "may_import": []},
    "CANDIDATE_ASSET": {"deployable": False, "production_wheel": False, "may_import": []},
    "BUILD_ONLY": {"deployable": False, "production_wheel": False, "may_import": []},
    "TEST_ONLY": {"deployable": False, "production_wheel": False, "may_import": []},
    "REMOVE": {"deployable": False, "production_wheel": False, "may_import": []},
}
AUTHORITY_ROLES = {
    "application": {"target_path": "pkg/application.py", "closure_task": "t"},
    "contract": {"target_path": "pkg/contracts.py", "closure_task": "t"},
    "certificate_issuer": {"target_path": "pkg/certificates.py", "closure_task": "t"},
    "independent_checker": {"target_path": "pkg/checker.py", "closure_task": "t"},
}


def _policy(**overrides) -> dict:
    policy = {
        "schema_version": "jc/module-authority/1.0",
        "classes": {name: dict(row) for name, row in CLASSES.items()},
        "path_rules": [
            {"path": "pkg/application.py", "class": "FORMAL_CORE", "rationale": "r"},
            {"path": "pkg/contracts.py", "class": "FORMAL_CORE", "rationale": "r"},
            {"path": "pkg/certificates.py", "class": "FORMAL_CORE", "rationale": "r"},
            {"path": "pkg/checker.py", "class": "FORMAL_CORE", "rationale": "r"},
            {"path": "pkg/render.py", "class": "RUNTIME_OUTPUT", "rationale": "r"},
            {"path": "pkg/core.py", "class": "FORMAL_CORE", "rationale": "r"},
            {"path": "pkg/__init__.py", "class": "FORMAL_CORE", "rationale": "r"},
        ],
        "prefix_rules": [{"prefix": "addons/", "class": "EXPERIMENT_ONLY", "rationale": "r"}],
        "declared_dynamic_edges": [],
        "entrypoints": [],
        "external_imports": {
            "deployable_allowlist": ["yaml"],
            "class_allowlist": {"FORMAL_CORE": ["yaml"], "RUNTIME_OUTPUT": ["yaml"]},
            "forbidden_roots": ["requests"],
        },
        "authority_roles": json.loads(json.dumps(AUTHORITY_ROLES)),
        "runtime_output": {
            "forbidden_reachability_paths": ["pkg/application.py"],
            "closure_task": "t",
        },
        "backlog_closure_tasks": {"class_edge": "t", "wheel": "t", "authority": "t", "external": "t"},
    }
    for key, value in overrides.items():
        if value is None:
            policy.pop(key, None)
        else:
            policy[key] = value
    return policy


def _git(repo: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True,
        env={
            **__import__("os").environ,
            "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
        },
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")


def _mini_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative, content in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(repo, "init")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-m", "init")
    return repo


def _write_policy(repo: Path, policy: dict) -> Path:
    path = repo.parent / "policy.json"
    path.write_text(json.dumps(policy, indent=1), encoding="utf-8")
    return path


BASE_FILES = {
    "pkg/__init__.py": "",
    "pkg/application.py": "",
    "pkg/contracts.py": "",
    "pkg/certificates.py": "",
    "pkg/checker.py": "",
    "pkg/render.py": "import pkg.core\n",
    "pkg/core.py": "import pkg.contracts\n",
    "addons/helper.py": "",
}


def test_clean_mini_repo_reports_clean_and_exits_zero(tmp_path: Path) -> None:
    repo = _mini_repo(tmp_path, BASE_FILES)
    report = build_report(repo, _write_policy(repo, _policy()))
    assert report["status"] == "CLEAN"
    assert report["structural_errors"] == [] and report["backlog"] == []
    assert report["worktree_dirty_paths"] == []
    assert mode_exit_code(report, "require-clean") == EXIT_OK
    assert report["schema_version"] == "jc/observed-authority-graph/2.0"


def test_report_is_deterministic(tmp_path: Path) -> None:
    repo = _mini_repo(tmp_path, BASE_FILES)
    policy_path = _write_policy(repo, _policy())
    first = build_report(repo, policy_path)
    second = build_report(repo, policy_path)
    assert first["report_digest"] == second["report_digest"]


def test_import_edge_between_tracked_modules_is_observed(tmp_path: Path) -> None:
    repo = _mini_repo(tmp_path, BASE_FILES)
    report = build_report(repo, _write_policy(repo, _policy()))
    edges = {
        (edge["source"], edge["target"])
        for edge in report["edges"] if edge["kind"] == "import"
    }
    assert ("pkg/render.py", "pkg/core.py") in edges
    assert ("pkg/core.py", "pkg/contracts.py") in edges


def test_forbidden_class_edge_lands_in_backlog(tmp_path: Path) -> None:
    files = {**BASE_FILES, "pkg/core.py": "import pkg.secret_helper\n",
             "pkg/secret_helper.py": "", }
    repo = _mini_repo(tmp_path, files)
    policy = _policy()
    policy["path_rules"].append(
        {"path": "pkg/secret_helper.py", "class": "TEST_ONLY", "rationale": "r"}
    )
    report = build_report(repo, _write_policy(repo, policy))
    kinds = {(item["kind"], item["source"], item["target"]) for item in report["backlog"]}
    assert ("class_edge", "pkg/core.py", "pkg/secret_helper.py") in kinds
    assert mode_exit_code(report, "require-clean") == EXIT_FAILURE
    assert mode_exit_code(report, "record") == EXIT_OK


def test_unclassified_and_stale_rules_are_structural(tmp_path: Path) -> None:
    repo = _mini_repo(tmp_path, {**BASE_FILES, "pkg/mystery.py": ""})
    policy = _policy()
    policy["path_rules"].append(
        {"path": "pkg/ghost.py", "class": "FORMAL_CORE", "rationale": "r"}
    )
    report = build_report(repo, _write_policy(repo, policy))
    codes = {error["code"] for error in report["structural_errors"]}
    assert {"UNCLASSIFIED_PYTHON", "STALE_EXACT_RULE"} <= codes
    assert mode_exit_code(report, "record") == EXIT_FAILURE


def test_dynamic_import_requires_declaration(tmp_path: Path) -> None:
    files = {
        **BASE_FILES,
        "pkg/core.py": (
            "import importlib\n\n\ndef load(name):\n"
            "    return importlib.import_module('pkg.' + name)\n"
        ),
    }
    repo = _mini_repo(tmp_path, files)
    undeclared = build_report(repo, _write_policy(repo, _policy()))
    assert any(
        error["code"] == "UNDECLARED_DYNAMIC_IMPORT" and error["source"] == "pkg/core.py"
        for error in undeclared["structural_errors"]
    )
    policy = _policy(declared_dynamic_edges=[{
        "importer": "pkg/core.py", "line": 5, "kind": "dynamic_import",
        "target_pattern": "pkg.*", "target_class": "FORMAL_CORE",
        "closure_task": "t",
    }])
    declared = build_report(repo, _write_policy(repo, policy))
    assert declared["structural_errors"] == []
    assert any(
        edge["source"] == "pkg/core.py" and edge["kind"] == "dynamic_import"
        and edge["target"] == "pattern:pkg.*"
        for edge in declared["edges"]
    )
    stale = build_report(repo, _write_policy(repo, _policy(declared_dynamic_edges=[{
        "importer": "pkg/core.py", "line": 99, "kind": "dynamic_import",
        "target_pattern": "x", "target_class": "FORMAL_CORE", "closure_task": "t",
    }])))
    assert any(error["code"] == "STALE_DYNAMIC_DECLARATION" for error in stale["structural_errors"])


def test_forbidden_external_import_lands_in_backlog(tmp_path: Path) -> None:
    files = {**BASE_FILES, "pkg/core.py": "import requests\n"}
    repo = _mini_repo(tmp_path, files)
    report = build_report(repo, _write_policy(repo, _policy()))
    assert any(
        item["kind"] == "external_import" and item["module"] == "requests"
        for item in report["backlog"]
    )


def test_runtime_output_may_not_reach_application(tmp_path: Path) -> None:
    files = {**BASE_FILES, "pkg/render.py": "import pkg.application\n"}
    repo = _mini_repo(tmp_path, files)
    report = build_report(repo, _write_policy(repo, _policy()))
    assert any(
        item["kind"] == "runtime_output_reachability" and item["source"] == "pkg/render.py"
        for item in report["backlog"]
    )


def test_policy_shape_mutations_are_structural(tmp_path: Path) -> None:
    repo = _mini_repo(tmp_path, BASE_FILES)
    broken_classes = _policy(classes={name: row for name, row in CLASSES.items() if name != "REMOVE"})
    report = build_report(repo, _write_policy(repo, broken_classes))
    assert any(error["code"] == "POLICY_CLASS_SET" for error in report["structural_errors"])

    duplicate = _policy()
    duplicate["path_rules"].append(
        {"path": "pkg/core.py", "class": "FORMAL_CORE", "rationale": "r2"}
    )
    report = build_report(repo, _write_policy(repo, duplicate))
    assert any(error["code"] == "DUPLICATE_EXACT_RULE" for error in report["structural_errors"])

    missing_role = _policy(authority_roles={
        name: row for name, row in AUTHORITY_ROLES.items() if name != "contract"
    })
    report = build_report(repo, _write_policy(repo, missing_role))
    assert any(error["code"] == "AUTHORITY_ROLE_SET" for error in report["structural_errors"])


def test_entrypoint_mismatch_is_structural(tmp_path: Path) -> None:
    files = {**BASE_FILES, "pyproject.toml": (
        "[project]\nname = 'x'\n[project.scripts]\njc = 'pkg.core:main'\n"
    )}
    repo = _mini_repo(tmp_path, files)
    report = build_report(repo, _write_policy(repo, _policy()))
    assert any(error["code"] == "ENTRYPOINT_POLICY_MISMATCH" for error in report["structural_errors"])
    policy = _policy(entrypoints=[{"name": "jc", "target": "pkg.core:main",
                                   "class": "FORMAL_CORE"}])
    ok = build_report(repo, _write_policy(repo, policy))
    assert ok["structural_errors"] == []


def test_cli_writes_report_and_honors_mode(tmp_path: Path) -> None:
    repo = _mini_repo(tmp_path, BASE_FILES)
    policy_path = _write_policy(repo, _policy())
    output = tmp_path / "report.json"
    parser = build_parser()
    args = parser.parse_args([
        "--root", str(repo), "--policy", str(policy_path),
        "--output", str(output), "--mode", "require-clean",
    ])
    from tools.remediation.observed_graph import main

    assert main(["--root", str(repo), "--policy", str(policy_path),
                 "--output", str(output), "--mode", "require-clean"]) == EXIT_OK
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["status"] == "CLEAN"


def test_repository_policy_is_clean_without_external_databases() -> None:
    """The live repository conforms to its own module-authority policy."""

    report = build_report(REPO, POLICY_PATH)
    assert report["structural_errors"] == [], report["structural_errors"]
    assert report["backlog"] == [], [item["kind"] for item in report["backlog"]]
    assert report["status"] == "CLEAN"
    assert "codegraph" not in json.dumps(report)
    assert mode_exit_code(report, "require-clean") == EXIT_OK


def test_production_wheel_policy_matches_real_wheel_inputs() -> None:
    """The policy's production set is exactly the wheel gate's payload set."""

    from tools.wheel_gate import EXPLICIT_RESOURCE_PATHS, PRODUCTION_CLASSES, expected_payload_paths

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    production = {
        rule["path"] for rule in policy["path_rules"]
        if policy["classes"][rule["class"]]["production_wheel"] is True
    }
    assert {
        name for name, row in policy["classes"].items() if row["production_wheel"]
    } == PRODUCTION_CLASSES
    assert expected_payload_paths(REPO) == production | set(EXPLICIT_RESOURCE_PATHS)
