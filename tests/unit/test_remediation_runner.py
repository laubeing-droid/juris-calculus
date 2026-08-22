"""Unit tests for the V4 remediation runner.

These tests are deliberately written BEFORE the runner implementation, per施工方案 §3.8:
"先增加/改写会失败的测试；runner 执行 red_commands，只在非零退出且错误类型/断言命中
red_failure_assertions 时记录有效红灯；测试未运行、因 import/语法/环境错误失败或意外
通过都不得进入实现".

Each test exercises one contract surface defined in施工方案 §3 / §7 B00 and §23-§25.
They are intentionally dependency-free: they do not import pytest plugins beyond what
already ships with the project, and they do not shell out.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "tools" / "remediate_v4.py"
REMEDIATION_DIR = REPO / "remediation" / "v4"


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("remediate_v4_test_module", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_runner(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-B", str(RUNNER), *args]
    return subprocess.run(
        cmd,
        cwd=str(cwd or REPO),
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


# ---------------------------------------------------------------------------
# Bootstrap presence
# ---------------------------------------------------------------------------

def test_runner_entrypoint_exists() -> None:
    """tools/remediate_v4.py 必须作为唯一 orchestration CLI 存在 (§3.1)。"""
    assert RUNNER.is_file(), f"missing runner: {RUNNER}"


def test_remediation_v4_directory_exists() -> None:
    assert REMEDIATION_DIR.is_dir(), f"missing remediation directory: {REMEDIATION_DIR}"


def test_required_artifacts_present() -> None:
    required = [
        "tasks.json",
        "task.schema.json",
        "receipt.schema.json",
        "approval.schema.json",
        "issue-map.json",
        "file-disposition.json",
    ]
    for name in required:
        path = REMEDIATION_DIR / name
        assert path.is_file(), f"missing remediation artifact: {path}"


# ---------------------------------------------------------------------------
# Schema validation (§3.2, §3.5, §3.6)
# ---------------------------------------------------------------------------

def test_tasks_json_validates_against_task_schema() -> None:
    """tasks.json 必须能被 task.schema.json 验证，且无环、依赖可解。"""
    from jsonschema import Draft202012Validator  # type: ignore

    schema = json.loads((REMEDIATION_DIR / "task.schema.json").read_text(encoding="utf-8"))
    plan = json.loads((REMEDIATION_DIR / "tasks.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.validate(plan)


def test_issue_map_has_44_entries() -> None:
    """issue-map.json 必须恰好 44 项：P0=15, P1=20, P2=7, P3=2。"""
    issue_map = json.loads((REMEDIATION_DIR / "issue-map.json").read_text(encoding="utf-8"))
    issues = issue_map.get("issues") or issue_map
    assert isinstance(issues, list), "issue-map.json must contain an issues list"
    by_severity: dict[str, int] = {}
    for entry in issues:
        sev = entry.get("severity")
        if sev is None:
            continue
        by_severity[sev] = by_severity.get(sev, 0) + 1
    assert by_severity.get("P0") == 15, f"P0 count: {by_severity.get('P0')}"
    assert by_severity.get("P1") == 20, f"P1 count: {by_severity.get('P1')}"
    assert by_severity.get("P2") == 7, f"P2 count: {by_severity.get('P2')}"
    assert by_severity.get("P3") == 2, f"P3 count: {by_severity.get('P3')}"


def test_file_disposition_includes_zh_cn_rules_yaml() -> None:
    """configs/zh_CN/rules.yaml 必须有 HISTORY_BOUND 处置绑定冻结指纹 (§0.14)。"""
    disposition = json.loads((REMEDIATION_DIR / "file-disposition.json").read_text(encoding="utf-8"))
    entries = {e["path"]: e for e in disposition.get("paths", disposition)}
    assert "configs/zh_CN/rules.yaml" in entries, "missing CN legacy rules entry"
    entry = entries["configs/zh_CN/rules.yaml"]
    assert entry.get("disposition") == "DELETE_CURRENT"
    assert entry.get("terminal_state") == "HISTORY_BOUND"
    fp = entry.get("frozen_fingerprint") or {}
    assert fp.get("sha256") == "032206c349154d77eeef771d2b40dcfb62e1f7724c420ba4c09e69aaf88e8a44"
    assert fp.get("bytes") == 13620766
    assert fp.get("unique_rule_ids") == 21144


def test_file_disposition_no_v3_only_authority_paths() -> None:
    """V3-only authority paths 不得登记为 KEEP_REWRITE；必须迁入 V4 后删除。"""
    disposition = json.loads((REMEDIATION_DIR / "file-disposition.json").read_text(encoding="utf-8"))
    entries = {e["path"]: e for e in disposition.get("paths", disposition)}
    forbidden_keep = {
        "compiler_core/compat_v3_v4.py",
        "compiler_core/proleg_translator.py",
    }
    for path in forbidden_keep:
        if path in entries:
            assert entries[path]["disposition"] != "KEEP_REWRITE", (
                f"{path} must not be KEEP_REWRITE in V4-only topology"
            )


# ---------------------------------------------------------------------------
# DAG cycle / dependency / duplicate id checks (§3.2)
# ---------------------------------------------------------------------------

def test_tasks_dag_is_acyclic() -> None:
    plan = json.loads((REMEDIATION_DIR / "tasks.json").read_text(encoding="utf-8"))
    tasks = plan.get("tasks", plan)
    by_id = {t["id"]: t for t in tasks}

    state: dict[str, int] = {tid: 0 for tid in by_id}  # 0=white 1=gray 2=black

    def dfs(node: str) -> None:
        if state[node] == 1:
            raise AssertionError(f"cycle detected at {node}")
        if state[node] == 2:
            return
        state[node] = 1
        for dep in by_id[node].get("depends_on", []):
            assert dep in by_id, f"unknown dep {dep} in {node}"
            dfs(dep)
        state[node] = 2

    for tid in by_id:
        dfs(tid)


def test_task_ids_unique_and_idempotent() -> None:
    plan = json.loads((REMEDIATION_DIR / "tasks.json").read_text(encoding="utf-8"))
    tasks = plan.get("tasks", plan)
    ids = [t["id"] for t in tasks]
    assert len(ids) == len(set(ids)), "duplicate task ids"


def test_every_task_has_allowed_paths() -> None:
    plan = json.loads((REMEDIATION_DIR / "tasks.json").read_text(encoding="utf-8"))
    tasks = plan.get("tasks", plan)
    for t in tasks:
        assert "allowed_paths" in t and t["allowed_paths"], f"task {t['id']} missing allowed_paths"
        if t.get("mode") in {"AUTO", "MIXED"}:
            assert t.get("audit_ids"), f"task {t['id']} (mode={t.get('mode')}) missing audit_ids"


# ---------------------------------------------------------------------------
# Runner CLI surface (§3.7, §24)
# ---------------------------------------------------------------------------

def test_runner_lint_plan_passes_on_checked_in_plan() -> None:
    result = _run_runner("lint-plan", "--plan", "remediation/v4/tasks.json")
    assert result.returncode == 0, f"lint-plan failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_runner_lint_plan_rejects_cycle() -> None:
    """故意写一个含环的 plan 必须非零退出。"""
    cycle_plan = REMEDIATION_DIR / "_test_cycle.json"
    try:
        cycle_plan.write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "id": "X1",
                            "depends_on": ["X2"],
                            "allowed_paths": ["compiler_core/__init__.py"],
                            "audit_ids": ["P0-01"],
                            "objective": "cycle test",
                            "mode": "AUTO",
                        },
                        {
                            "id": "X2",
                            "depends_on": ["X1"],
                            "allowed_paths": ["compiler_core/__init__.py"],
                            "audit_ids": ["P0-01"],
                            "objective": "cycle test",
                            "mode": "AUTO",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        result = _run_runner("lint-plan", "--plan", str(cycle_plan))
        assert result.returncode != 0, "cycle plan should fail lint"
    finally:
        if cycle_plan.exists():
            cycle_plan.unlink()


def test_runner_lint_plan_rejects_unknown_dep() -> None:
    bad_plan = REMEDIATION_DIR / "_test_unknown_dep.json"
    try:
        bad_plan.write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "id": "Y1",
                            "depends_on": ["Z9"],
                            "allowed_paths": ["compiler_core/__init__.py"],
                            "audit_ids": ["P0-01"],
                            "objective": "unknown dep",
                            "mode": "AUTO",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        result = _run_runner("lint-plan", "--plan", str(bad_plan))
        assert result.returncode != 0, "unknown dep must fail lint"
    finally:
        if bad_plan.exists():
            bad_plan.unlink()


def test_runner_help_succeeds() -> None:
    result = _run_runner("--help")
    assert result.returncode == 0, "--help should not fail"
    assert "remediate_v4" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_runner_authority_check_reports_module_authority() -> None:
    """§3.1 authority 命令必须报告 module-authority 唯一性。"""
    result = _run_runner("authority", "--check")
    assert result.returncode in (0, 3), f"unexpected exit: {result.returncode}\n{result.stdout}\n{result.stderr}"


def test_committed_delta_binds_added_modified_and_deleted_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "receipt-repo"
    repo.mkdir()

    def git(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True,
        )
        return completed.stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Receipt Test")
    git("config", "user.email", "receipt@example.invalid")
    (repo / "modified.txt").write_text("before\n", encoding="utf-8")
    (repo / "deleted.txt").write_text("deleted bytes\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "baseline")
    baseline = git("rev-parse", "HEAD")

    (repo / "modified.txt").write_text("after\n", encoding="utf-8")
    (repo / "deleted.txt").unlink()
    (repo / "added.txt").write_text("added bytes\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "result")
    result = git("rev-parse", "HEAD")

    runner = _load_runner_module()
    monkeypatch.setattr(runner, "ROOT", repo)
    changed_paths, artifact_digests = runner._committed_delta(baseline, result)

    assert changed_paths == ["added.txt", "deleted.txt", "modified.txt"]
    assert artifact_digests == {
        "deleted-path:deleted.txt": "sha256:" + hashlib.sha256(b"deleted bytes\n").hexdigest(),
        "result-path:added.txt": "sha256:" + hashlib.sha256(b"added bytes\n").hexdigest(),
        "result-path:modified.txt": "sha256:" + hashlib.sha256(b"after\n").hexdigest(),
    }


def test_w0_object_state_matrix_gate_passes() -> None:
    result = _run_runner("verify-wave", "W0-01")
    assert result.returncode == 0, f"matrix gate failed:\n{result.stdout}\n{result.stderr}"
    assert "formal types" in result.stdout


def test_w0_object_state_matrix_gate_rejects_critical_mutations(tmp_path: Path) -> None:
    source = REPO / "tests" / "fixtures" / "v4_contract" / "object-state-matrix.json"
    baseline = json.loads(source.read_text(encoding="utf-8"))

    mutations = []
    accepted_without_certificate = json.loads(json.dumps(baseline))
    accepted_without_certificate["decision_constraints"]["accepted_formal_result"]["certificate"] = ["none"]
    mutations.append(accepted_without_certificate)

    blocked_transport_success = json.loads(json.dumps(baseline))
    blocked_transport_success["decision_constraints"]["blocked"]["transport"] = ["success"]
    mutations.append(blocked_transport_success)

    unknown_formal = json.loads(json.dumps(baseline))
    unknown_formal["decision_constraints"]["unknown"]["certificate"] = ["formal_verified"]
    mutations.append(unknown_formal)

    open_formal_object = json.loads(json.dumps(baseline))
    next(item for item in open_formal_object["object_types"] if item["schema_kind"] == "object")[
        "additional_properties"
    ] = True
    mutations.append(open_formal_object)

    missing_contract_type = json.loads(json.dumps(baseline))
    missing_contract_type["object_types"].pop()
    mutations.append(missing_contract_type)

    for index, payload in enumerate(mutations):
        path = tmp_path / f"invalid-{index}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = _run_runner("object-state-matrix", "--path", str(path))
        assert result.returncode != 0, f"mutation {index} unexpectedly passed"
