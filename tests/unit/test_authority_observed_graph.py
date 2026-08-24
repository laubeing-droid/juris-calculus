"""W0-03 authority policy and observed-graph contract tests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "tools" / "remediation" / "observed_graph.py"
POLICY = REPO / "docs" / "architecture" / "module-authority.json"
CODEGRAPH = REPO / ".codegraph" / "codegraph.db"
RUNNER = REPO / "tools" / "remediate_v4.py"

CLASSES = [
    "FORMAL_CORE", "PUBLIC_ADAPTER", "RUNTIME_OUTPUT", "SOURCE_TOOL",
    "EXPERIMENT_ONLY", "CANDIDATE_ASSET", "BUILD_ONLY", "TEST_ONLY", "REMOVE",
]


def _load(path: Path, name: str):
    assert path.is_file(), f"W0-03 implementation missing: {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True,
    )
    return completed.stdout.strip()


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _classes() -> dict[str, dict]:
    deployable = {"FORMAL_CORE", "PUBLIC_ADAPTER", "RUNTIME_OUTPUT"}
    all_classes = list(CLASSES)
    return {
        name: {
            "deployable": name in deployable,
            "production_wheel": name in deployable,
            "may_import": (
                ["FORMAL_CORE"] if name == "FORMAL_CORE"
                else ["FORMAL_CORE", "PUBLIC_ADAPTER", "RUNTIME_OUTPUT"]
                if name in {"PUBLIC_ADAPTER", "RUNTIME_OUTPUT"}
                else all_classes
            ),
        }
        for name in CLASSES
    }


def _fixture_policy(dynamic_line: int) -> dict:
    classes = {
        "pkg/__init__.py": "PUBLIC_ADAPTER",
        "pkg/adapter.py": "PUBLIC_ADAPTER",
        "pkg/app.py": "FORMAL_CORE",
        "pkg/bundle.py": "FORMAL_CORE",
        "pkg/cert.py": "FORMAL_CORE",
        "pkg/checker.py": "FORMAL_CORE",
        "pkg/contracts.py": "FORMAL_CORE",
        "pkg/core.py": "FORMAL_CORE",
        "pkg/render.py": "RUNTIME_OUTPUT",
        "source/__init__.py": "SOURCE_TOOL",
        "source/tool.py": "SOURCE_TOOL",
        "plugins/__init__.py": "EXPERIMENT_ONLY",
        "plugins/loader.py": "EXPERIMENT_ONLY",
        "addons/__init__.py": "EXPERIMENT_ONLY",
        "addons/example.py": "EXPERIMENT_ONLY",
    }
    return {
        "schema_version": "jc/module-authority/1.0",
        "classes": _classes(),
        "path_rules": [
            {"path": path, "class": authority_class, "rationale": "fixture policy"}
            for path, authority_class in sorted(classes.items())
        ],
        "prefix_rules": [],
        "authority_roles": {
            "application": {"target_path": "pkg/app.py", "closure_task": "W4-05"},
            "contract": {"target_path": "pkg/contracts.py", "closure_task": "W1-01"},
            "certificate_issuer": {"target_path": "pkg/cert.py", "closure_task": "W4-04"},
            "independent_checker": {"target_path": "pkg/checker.py", "closure_task": "W3-04"},
        },
        "entrypoints": [
            {"name": "jc", "target": "pkg.adapter:main", "class": "PUBLIC_ADAPTER"},
        ],
        "declared_dynamic_edges": [
            {
                "importer": "plugins/loader.py", "line": dynamic_line,
                "kind": "dynamic_import", "target_pattern": "addons.*",
                "target_class": "EXPERIMENT_ONLY", "closure_task": "W5-CUTOVER",
            }
        ],
        "external_imports": {
            "deployable_allowlist": [],
            "forbidden_roots": ["requests", "httpx", "socket", "tkinter"],
        },
        "runtime_output": {
            "forbidden_reachability_paths": ["pkg/app.py"],
            "closure_task": "W4-03",
        },
        "backlog_closure_tasks": {
            "class_edge": "W5-CUTOVER", "wheel": "W6-01",
            "authority": "W4-04", "external": "W5-CUTOVER",
        },
    }


def _codegraph_db(
    root: Path, target: Path, *, false_call_edge: bool = False,
    false_import_edge: bool = False, reverse_rows: bool = False,
) -> None:
    tracked_python = _git(root, "ls-files", "*.py").splitlines()
    if reverse_rows:
        tracked_python.reverse()
    connection = sqlite3.connect(target)
    try:
        connection.executescript(
            """
            CREATE TABLE files (
              path TEXT PRIMARY KEY, content_hash TEXT NOT NULL, language TEXT NOT NULL,
              size INTEGER NOT NULL, modified_at INTEGER NOT NULL, indexed_at INTEGER NOT NULL,
              node_count INTEGER DEFAULT 0, errors TEXT
            );
            CREATE TABLE nodes (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
              qualified_name TEXT NOT NULL, file_path TEXT NOT NULL,
              language TEXT NOT NULL, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
              start_column INTEGER NOT NULL, end_column INTEGER NOT NULL,
              docstring TEXT, signature TEXT, visibility TEXT, is_exported INTEGER DEFAULT 0,
              is_async INTEGER DEFAULT 0, is_static INTEGER DEFAULT 0,
              is_abstract INTEGER DEFAULT 0, decorators TEXT, type_parameters TEXT,
              updated_at INTEGER NOT NULL
            );
            CREATE TABLE edges (
              id INTEGER PRIMARY KEY, source TEXT NOT NULL, target TEXT NOT NULL,
              kind TEXT NOT NULL, metadata TEXT, line INTEGER, col INTEGER, provenance TEXT
            );
            CREATE TABLE unresolved_refs (
              id INTEGER PRIMARY KEY, from_node_id TEXT NOT NULL,
              reference_name TEXT NOT NULL, reference_kind TEXT NOT NULL,
              line INTEGER NOT NULL, col INTEGER NOT NULL, candidates TEXT,
              file_path TEXT NOT NULL DEFAULT '', language TEXT NOT NULL DEFAULT 'unknown'
            );
            """
        )
        for path in tracked_python:
            payload = (root / path).read_bytes()
            connection.execute(
                "INSERT INTO files VALUES (?, ?, 'python', ?, 0, 0, 0, NULL)",
                (path.replace("\\", "/"), hashlib.sha256(payload).hexdigest(), len(payload)),
            )
        if false_call_edge:
            connection.execute(
                "INSERT INTO nodes VALUES "
                "('method:a','method','to_dict','pkg.A.to_dict','pkg/core.py','python',1,1,0,1,NULL,NULL,NULL,0,0,0,0,NULL,NULL,0)"
            )
            connection.execute(
                "INSERT INTO nodes VALUES "
                "('method:b','method','to_dict','source.B.to_dict','source/tool.py','python',1,1,0,1,NULL,NULL,NULL,0,0,0,0,NULL,NULL,0)"
            )
            connection.execute(
                "INSERT INTO edges(source,target,kind,line,col) VALUES "
                "('method:a','method:b','calls',1,0)"
            )
        if false_import_edge:
            connection.execute(
                "INSERT INTO nodes VALUES "
                "('import:fake','import','source.tool','source.tool','pkg/app.py','python',1,1,0,1,NULL,NULL,NULL,0,0,0,0,NULL,NULL,0)"
            )
            connection.execute(
                "INSERT INTO edges(source,target,kind,line,col) VALUES "
                "('file:pkg/app.py','import:fake','imports',1,0)"
            )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture()
def authority_fixture(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    files = {
        "pkg/__init__.py": "from .core import run\n",
        "pkg/adapter.py": "from pkg.app import execute\ndef main(): return execute()\n",
        "pkg/app.py": "from pkg.core import run\ndef execute(): return run()\n",
        "pkg/bundle.py": "from pkg.app import execute\ndef verify(): return execute()\n",
        "pkg/cert.py": "def issue(): return 'certificate'\n",
        "pkg/checker.py": "def check(): return True\n",
        "pkg/contracts.py": "class Contract: pass\n",
        "pkg/core.py": (
            "class Same:\n    def to_dict(self): return {}\n\n"
            "def run():\n    from source.tool import helper\n    return helper()\n"
        ),
        "pkg/render.py": "from pkg.bundle import verify\ndef render(): return verify()\n",
        "source/__init__.py": "",
        "source/tool.py": (
            "from pkg.contracts import Contract\n"
            "class Same:\n    def to_dict(self): return {}\ndef helper(): return Contract\n"
        ),
        "plugins/__init__.py": "",
        "plugins/loader.py": (
            "import importlib\n\n"
            "def load(name):\n"
            "    return importlib.import_module('addons.' + name)\n"
        ),
        "addons/__init__.py": "",
        "addons/example.py": "VALUE = 1\n",
    }
    for path, payload in files.items():
        _write(root / path, payload)
    _write(
        root / "pyproject.toml",
        """[project]\nname='fixture'\nversion='1'\n[project.scripts]\njc='pkg.adapter:main'\n[tool.setuptools.packages.find]\ninclude=['pkg*','source*','plugins*','addons*']\n""",
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Authority Fixture")
    _git(root, "config", "user.email", "authority@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    dynamic_line = next(
        index for index, line in enumerate(files["plugins/loader.py"].splitlines(), 1)
        if "import_module" in line
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(_fixture_policy(dynamic_line)), encoding="utf-8")
    database = tmp_path / "codegraph.db"
    _codegraph_db(root, database, false_call_edge=True, false_import_edge=True)
    return {"root": root, "policy": policy, "codegraph": database}


def test_fixture_detects_ast_dynamic_reexport_wheel_and_reachability(
    authority_fixture: dict[str, Path],
) -> None:
    observed = _load(SCRIPT, "authority_observed_fixture")
    report = observed.build_report(
        authority_fixture["root"], authority_fixture["policy"], authority_fixture["codegraph"]
    )
    assert report["structural_errors"] == []
    assert report["coverage"]["unclassified"] == []
    edges = report["edges"]
    assert any(
        edge["source"] == "pkg/core.py" and edge["target"] == "source/tool.py"
        and edge["scope"] == "function" for edge in edges
    )
    assert any(edge["kind"] == "dynamic_import" and edge["target"] == "pattern:addons.*" for edge in edges)
    assert any(
        edge["kind"] == "reexport" and edge["source"] == "pkg/__init__.py"
        and edge["target"] == "pkg/core.py" for edge in edges
    )
    assert report["entrypoints"][0]["target"] == "pkg.adapter:main"
    class_edge = next(
        item for item in report["backlog"]
        if item["kind"] == "class_edge" and item["source"] == "pkg/core.py"
        and item["target"] == "source/tool.py"
    )
    assert ["pkg/adapter.py", "pkg/app.py", "pkg/core.py", "source/tool.py"] in class_edge["entrypoint_paths"]
    assert not any(
        item["kind"] == "class_edge" and item["source"] == "source/tool.py"
        and item["target"] == "pkg/contracts.py" for item in report["backlog"]
    )
    wheel_forbidden = {
        item["source"] for item in report["backlog"] if item["kind"] == "wheel_forbidden"
    }
    assert {"source/tool.py", "plugins/loader.py", "addons/example.py"} <= wheel_forbidden
    runtime = next(
        item for item in report["backlog"] if item["kind"] == "runtime_output_reachability"
    )
    assert runtime["path"] == ["pkg/render.py", "pkg/bundle.py", "pkg/app.py"]
    assert all(edge["evidence"] != "codegraph_call" for edge in edges)
    assert report["codegraph"]["secondary_call_edges"] == 1
    assert report["codegraph"]["secondary_import_edges"] == 1
    assert observed.mode_exit_code(report, "record") == 0
    assert observed.mode_exit_code(report, "require-clean") == 4
    clean = {**report, "backlog": [], "structural_errors": []}
    assert observed.mode_exit_code(clean, "require-clean") == 0


def test_stale_codegraph_and_missing_policy_are_structural_failures(
    authority_fixture: dict[str, Path],
) -> None:
    observed = _load(SCRIPT, "authority_observed_stale")
    (authority_fixture["root"] / "pkg" / "core.py").write_text("VALUE = 2\n", encoding="utf-8")
    report = observed.build_report(
        authority_fixture["root"], authority_fixture["policy"], authority_fixture["codegraph"]
    )
    assert any(item["code"] == "CODEGRAPH_CONTENT_MISMATCH" for item in report["structural_errors"])
    assert observed.mode_exit_code(report, "record") == 4
    assert observed.mode_exit_code(report, "require-clean") == 4

    policy = json.loads(authority_fixture["policy"].read_text(encoding="utf-8"))
    policy["path_rules"] = [
        item for item in policy["path_rules"] if item["path"] != "pkg/contracts.py"
    ]
    authority_fixture["policy"].write_text(json.dumps(policy), encoding="utf-8")
    report = observed.build_report(
        authority_fixture["root"], authority_fixture["policy"], authority_fixture["codegraph"]
    )
    assert "pkg/contracts.py" in report["coverage"]["unclassified"]


def test_codegraph_logical_evidence_is_deterministic_and_rejects_health_gaps(
    authority_fixture: dict[str, Path], tmp_path: Path,
) -> None:
    observed = _load(SCRIPT, "authority_observed_deterministic")
    second = tmp_path / "reversed-codegraph.db"
    _codegraph_db(
        authority_fixture["root"], second, false_call_edge=True,
        false_import_edge=True, reverse_rows=True,
    )
    connection = sqlite3.connect(second)
    try:
        connection.execute("UPDATE files SET modified_at=999, indexed_at=123456")
        connection.commit()
    finally:
        connection.close()
    first_report = observed.build_report(
        authority_fixture["root"], authority_fixture["policy"], authority_fixture["codegraph"]
    )
    second_report = observed.build_report(
        authority_fixture["root"], authority_fixture["policy"], second
    )
    assert hashlib.sha256(authority_fixture["codegraph"].read_bytes()).digest() != hashlib.sha256(second.read_bytes()).digest()
    assert first_report == second_report

    connection = sqlite3.connect(second)
    try:
        connection.execute("DELETE FROM files WHERE path='pkg/core.py'")
        connection.execute(
            "INSERT INTO files VALUES ('orphan.py', ?, 'python', 1, 0, 0, 0, NULL)",
            (hashlib.sha256(b'x').hexdigest(),),
        )
        connection.execute("UPDATE files SET errors='parse failure' WHERE path='pkg/app.py'")
        connection.execute(
            "INSERT INTO unresolved_refs(from_node_id,reference_name,reference_kind,line,col) "
            "VALUES ('n','missing','import',1,0)"
        )
        connection.commit()
    finally:
        connection.close()
    unhealthy = observed.build_report(
        authority_fixture["root"], authority_fixture["policy"], second
    )
    codes = {item["code"] for item in unhealthy["structural_errors"]}
    assert {
        "CODEGRAPH_MISSING_PYTHON", "CODEGRAPH_ORPHAN_PYTHON",
        "CODEGRAPH_PARSE_ERRORS", "CODEGRAPH_UNRESOLVED_REFS",
    } <= codes


def test_duplicate_policy_and_authority_targets_are_structural(
    authority_fixture: dict[str, Path],
) -> None:
    observed = _load(SCRIPT, "authority_observed_policy_mutation")
    policy = json.loads(authority_fixture["policy"].read_text(encoding="utf-8"))
    policy["path_rules"].append(dict(policy["path_rules"][0]))
    policy["authority_roles"]["contract"]["target_path"] = "pkg/app.py"
    authority_fixture["policy"].write_text(json.dumps(policy), encoding="utf-8")
    report = observed.build_report(
        authority_fixture["root"], authority_fixture["policy"], authority_fixture["codegraph"]
    )
    codes = {item["code"] for item in report["structural_errors"]}
    assert {"DUPLICATE_EXACT_RULE", "DUPLICATE_AUTHORITY_TARGET"} <= codes


def test_repository_policy_has_exact_python_and_codegraph_coverage() -> None:
    observed = _load(SCRIPT, "authority_observed_repository")
    assert POLICY.is_file(), "manual W0-03 policy is missing"
    report = observed.build_report(REPO, POLICY, CODEGRAPH)
    assert report["structural_errors"] == []
    assert report["coverage"]["unclassified"] == []
    assert report["coverage"]["stale_exact_rules"] == []
    assert report["coverage"]["tracked_python"] == report["coverage"]["classified_python"]
    assert report["codegraph"]["content_mismatches"] == []
    assert report["authority_roles"] == {
        "application": "compiler_core/application.py",
        "certificate_issuer": "compiler_core/certificates.py",
        "contract": "compiler_core/contracts.py",
        "independent_checker": "compiler_core/independent_checker.py",
    }
    assert report["status"] == "OPEN_VIOLATIONS"
    assert not any(
        item["kind"] == "authority_target_missing" for item in report["backlog"]
    )
    assert any(
        item["kind"] == "runtime_output_reachability"
        and item["source"] == "compiler_core/rendering.py"
        and item["target"] == "compiler_core/application.py"
        for item in report["backlog"]
    )


def test_state_artifact_declaration_is_revalidated(tmp_path: Path) -> None:
    runner = _load(RUNNER, "authority_runner_artifact")
    assert hasattr(runner, "_declared_state_artifacts"), "runner does not bind state artifacts"
    state_root = tmp_path / "state"
    evidence = state_root / "evidence" / "authority" / "report.json"
    _write(evidence, '{"status":"recorded"}\n')
    digest = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
    stdout = tmp_path / "stdout.bin"
    stdout.write_text(
        f"JC_ARTIFACT\tauthority-observed-graph\t{evidence}\t{digest}\n",
        encoding="utf-8",
    )
    command_results = [{
        "stdout": {
            "path": str(stdout), "sha256": hashlib.sha256(stdout.read_bytes()).hexdigest(),
            "bytes": len(stdout.read_bytes()),
        }
    }]
    assert runner._declared_state_artifacts(command_results, state_root) == {
        "state-artifact:authority-observed-graph": digest,
    }
    evidence.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        runner._declared_state_artifacts(command_results, state_root)


def test_state_artifact_marker_rejects_escape_bad_digest_and_duplicate(tmp_path: Path) -> None:
    runner = _load(RUNNER, "authority_runner_artifact_negative")
    state_root = tmp_path / "state"
    evidence = state_root / "evidence" / "ok.json"
    outside = tmp_path / "outside.json"
    _write(evidence, "ok")
    _write(outside, "outside")

    def command_for(lines: list[str]) -> list[dict]:
        stdout = tmp_path / (hashlib.sha256("\n".join(lines).encode()).hexdigest() + ".bin")
        stdout.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return [{"stdout": {"path": str(stdout), "sha256": _sha(stdout), "bytes": stdout.stat().st_size}}]

    good_digest = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
    outside_digest = "sha256:" + hashlib.sha256(outside.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="escapes"):
        runner._declared_state_artifacts(command_for([
            f"JC_ARTIFACT\tescape\t{outside}\t{outside_digest}"
        ]), state_root)
    with pytest.raises(ValueError, match="grammar"):
        runner._declared_state_artifacts(command_for([
            f"JC_ARTIFACT\tbad\t{evidence}\tsha256:BAD"
        ]), state_root)
    line = f"JC_ARTIFACT\tduplicate\t{evidence}\t{good_digest}"
    with pytest.raises(ValueError, match="duplicate"):
        runner._declared_state_artifacts(command_for([line, line]), state_root)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_runner_receipt_binds_and_revalidates_declared_state_artifact(tmp_path: Path) -> None:
    repo = tmp_path / "runner-repo"
    (repo / "tools").mkdir(parents=True)
    shutil.copy2(RUNNER, repo / "tools" / "remediate_v4.py")
    schema_dir = repo / "remediation" / "v4"
    schema_dir.mkdir(parents=True)
    for name in ("task.schema.json", "receipt.schema.json", "issue-map.json"):
        shutil.copy2(REPO / "remediation" / "v4" / name, schema_dir / name)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Artifact Fixture")
    _git(repo, "config", "user.email", "artifact@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "baseline")

    required = [
        "schema_version", "task_digest", "run_id", "task_id", "attempt", "status",
        "input_receipt_digests", "start_commit", "start_tree", "result_commit",
        "result_tree", "command_results", "changed_paths", "allowlist", "test_reports",
        "artifact_digests", "completion_assertions", "previous_receipt_digest",
        "runner_version", "receipt_digest",
    ]
    command = (
        "import hashlib,os; from pathlib import Path; "
        "p=Path(os.environ['JC_REMEDIATION_STATE_ROOT'])/'evidence'/'fixture.json'; "
        "p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b'bound evidence\\n'); "
        "d='sha256:'+hashlib.sha256(p.read_bytes()).hexdigest(); "
        "print('JC_ARTIFACT\\tfixture\\t'+str(p.resolve())+'\\t'+d)"
    )
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "schema_version": "jc/remediation-v4-task/2.0",
        "tasks": [{
            "id": "ART", "wave": "ART", "mode": "AUTO", "depends_on": [],
            "audit_ids": ["P0-01"], "objective": "bind state artifact",
            "allowed_paths": ["tools/**"], "argv": [["{python}", "-c", command]],
            "expected_exit_codes": [0], "timeout_seconds": 30,
            "completion_assertions": [{"id": "commands", "kind": "all_commands_passed"}],
            "rollback": "stop", "required_receipt_fields": required,
        }],
    }), encoding="utf-8")
    state_root = tmp_path / "state"
    argv = [
        sys.executable, "-B", str(repo / "tools" / "remediate_v4.py"), "run",
        "--plan", str(plan), "--state-root", str(state_root), "--through", "ALL",
    ]
    first = subprocess.run(argv, cwd=repo, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    receipt = json.loads(
        (state_root / "tasks" / "ART" / "1" / "receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["artifact_digests"]["state-artifact:fixture"].startswith("sha256:")
    (state_root / "evidence" / "fixture.json").write_text("tampered", encoding="utf-8")
    resumed = subprocess.run(argv, cwd=repo, capture_output=True, text=True)
    assert resumed.returncode == 5
    assert "JC_ARTIFACT digest mismatch" in resumed.stderr


def test_authority_cli_records_report_and_require_clean_fails(tmp_path: Path) -> None:
    state_root = tmp_path / "authority-state"
    base = [
        sys.executable, "-B", str(RUNNER), "authority",
        "--policy", str(POLICY), "--codegraph", str(CODEGRAPH),
        "--state-root", str(state_root),
    ]
    recorded = subprocess.run([*base, "--record"], cwd=REPO, capture_output=True, text=True)
    assert recorded.returncode == 0, recorded.stderr
    marker = next(line for line in recorded.stdout.splitlines() if line.startswith("JC_ARTIFACT\t"))
    _, label, raw_path, digest = marker.split("\t")
    report_path = Path(raw_path)
    assert label == "authority-observed-graph"
    assert report_path.is_relative_to(state_root / "evidence")
    assert digest == "sha256:" + hashlib.sha256(report_path.read_bytes()).hexdigest()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "OPEN_VIOLATIONS"
    require_clean = subprocess.run(
        [*base, "--require-clean"], cwd=REPO, capture_output=True, text=True,
    )
    assert require_clean.returncode == 4
