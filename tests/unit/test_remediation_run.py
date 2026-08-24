"""Integration and tamper tests for the executable V4 task runner."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "tools" / "remediate_v4.py"
REQUIRED_RECEIPT_FIELDS = [
    "schema_version", "task_digest", "run_id", "task_id", "attempt", "status",
    "input_receipt_digests", "start_commit", "start_tree", "result_commit",
    "result_tree", "command_results", "changed_paths", "allowlist",
    "test_reports", "artifact_digests", "completion_assertions",
    "previous_receipt_digest", "runner_version", "receipt_digest",
]


def _auto_task(task_id: str, argv: list[str], *, depends_on: list[str] | None = None,
               expected: int = 0, timeout: float = 10, allowed: list[str] | None = None) -> dict:
    return {
        "id": task_id, "wave": task_id, "mode": "AUTO",
        "depends_on": depends_on or [], "audit_ids": ["P0-01"],
        "objective": f"execute {task_id}", "allowed_paths": allowed or ["tests/**"],
        "argv": [argv], "expected_exit_codes": [expected], "timeout_seconds": timeout,
        "completion_assertions": [{"id": "commands", "kind": "all_commands_passed"}],
        "rollback": "stop and repair", "required_receipt_fields": REQUIRED_RECEIPT_FIELDS,
    }


def _gate_task(task_id: str, depends_on: list[str], *, subject_paths: list[str] | None = None,
               minimum_signers: int = 1, separation: bool = False) -> dict:
    return {
        "id": task_id, "wave": task_id, "mode": "EXTERNAL_GATE",
        "depends_on": depends_on, "audit_ids": ["P0-01"],
        "objective": f"approve {task_id}", "allowed_paths": ["tests/**"],
        "approval": {
            "evidence_kind": "CRYPTOGRAPHIC_SIGNATURE",
            "gate_id": f"{task_id}-APPROVAL", "subject": f"subject {task_id}",
            "subject_paths": subject_paths or ["tests/unit/test_remediation_run.py"],
            "required_roles": ["external_provider"], "allowed_scopes": [task_id],
            "minimum_signers": minimum_signers, "separation_of_duties": separation,
        },
    }


def _write_plan(tmp_path: Path, tasks: list[dict]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps({"schema_version": "jc/remediation-v4-task/2.0", "tasks": tasks}),
        encoding="utf-8",
    )
    return plan


def _run(plan: Path, state_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(RUNNER), "run", "--plan", str(plan),
         "--state-root", str(state_root), "--through", "ALL"],
        cwd=str(REPO), capture_output=True, text=True,
    )


def _run_in_repo(repo: Path, plan: Path, state_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(repo / "tools" / "remediate_v4.py"), "run",
         "--plan", str(plan), "--state-root", str(state_root), "--through", "ALL"],
        cwd=str(repo), capture_output=True, text=True,
    )


def _receipt(state_root: Path, task_id: str, attempt: int = 1) -> dict:
    return json.loads(
        (state_root / "tasks" / task_id / str(attempt) / "receipt.json").read_text(encoding="utf-8")
    )


def _digest(receipt: dict) -> str:
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _raw_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _install_trusted_key(state_root: Path, private_key: Ed25519PrivateKey, key_id: str = "test-key") -> None:
    public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    trust = state_root / "trust"
    trust.mkdir(parents=True, exist_ok=True)
    (trust / "trusted_keys.json").write_text(json.dumps({"keys": [{
        "key_id": key_id, "public_key_base64": __import__("base64").b64encode(public).decode(),
        "roles": ["external_provider"], "scopes": ["G1"], "test_only": True,
    }]}), encoding="utf-8")


def _install_approval(state_root: Path, request: dict, private_key: Ed25519PrivateKey, *,
                      role: str = "external_provider", scope: str = "G1",
                      key_id: str = "test-key", subject_digest: str | None = None,
                      expired: bool = False, filename: str = "approval.json") -> None:
    now = datetime.now(timezone.utc)
    approval = {
        "schema_version": "jc/remediation-v4-approval/2.0",
        "evidence_kind": "CRYPTOGRAPHIC_SIGNATURE",
        "gate_id": request["gate_id"], "task_id": request["task_id"],
        "request_digest": request["request_digest"],
        "subject_digest": subject_digest or request["subject_digest"], "decision": "APPROVE",
        "signer": {"key_id": key_id, "role": role, "scope": scope},
        "issued_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now - timedelta(minutes=1) if expired else now + timedelta(hours=1)).isoformat(),
    }
    signature = private_key.sign(_canonical(approval))
    approval["signature"] = {
        "algorithm": "Ed25519", "value": __import__("base64").b64encode(signature).decode(),
        "public_key_id": key_id,
    }
    directory = state_root / "approvals" / request["task_id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(json.dumps(approval), encoding="utf-8")


def _user_directive_task(task_id: str, *, mode: str = "HUMAN_GATE",
                         argv: list[str] | None = None,
                         allowed: list[str] | None = None,
                         depends_on: list[str] | None = None,
                         subject_paths: list[str] | None = None,
                         minimum_signers: int = 1,
                         separation: bool = False) -> dict:
    task = {
        "id": task_id, "wave": task_id, "mode": mode,
        "depends_on": depends_on or [], "audit_ids": ["P0-01"],
        "objective": f"approve and execute {task_id}",
        "allowed_paths": allowed or ["docs/**"],
        "approval": {
            "evidence_kind": "USER_DIRECTIVE",
            "gate_id": f"{task_id}-APPROVAL", "subject": f"subject {task_id}",
            "subject_paths": subject_paths or [],
            "required_roles": ["authorized_reviewer"],
            "allowed_scopes": [task_id], "minimum_signers": minimum_signers,
            "separation_of_duties": separation,
        },
    }
    if argv is not None:
        task.update({
            "argv": [argv], "expected_exit_codes": [0], "timeout_seconds": 10,
            "completion_assertions": [{"id": "commands", "kind": "all_commands_passed"}],
            "rollback": "stop and repair", "required_receipt_fields": REQUIRED_RECEIPT_FIELDS,
        })
    return task


def _install_user_directive(state_root: Path, request: dict, *,
                            remove: str | None = None,
                            decision: str = "APPROVE",
                            role: str = "authorized_reviewer") -> dict:
    authority_path = (state_root / "authority" / "user-directive.txt").resolve()
    authority_path.parent.mkdir(parents=True, exist_ok=True)
    authority_path.write_bytes(b"test user directive")
    directive = {
        "schema_version": "jc/remediation-v4-user-directive/1.0",
        "evidence_kind": "USER_DIRECTIVE", "run_id": request["run_id"],
        "gate_id": request["gate_id"], "task_id": request["task_id"],
        "request_digest": request["request_digest"],
        "subject_digest": request["subject_digest"], "decision": decision,
        "scope": request["allowed_scopes"][0],
        "authority_source": {
            "locator": str(authority_path),
            "sha256": _raw_digest(authority_path),
        },
        "signer": {
            "key_id": "authorized-user", "role": role,
            "scope": request["allowed_scopes"][0],
        },
        "issued_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    }
    if remove is not None:
        directive.pop(remove)
    directory = state_root / "directives" / request["task_id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "directive.json").write_text(json.dumps(directive), encoding="utf-8")
    return directive


def _isolated_runner_repo(tmp_path: Path):
    repo = tmp_path / "isolated-repo"
    sources = [
        "pyproject.toml",
        "requirements/core.lock",
        "tools/remediate_v4.py",
        "tools/supply_chain_gate.py",
        "remediation/v4/tasks.json",
        "remediation/v4/task.schema.json",
        "remediation/v4/receipt.schema.json",
        "remediation/v4/approval.schema.json",
        "remediation/v4/user-directive.schema.json",
        "remediation/v4/issue-map.json",
        "remediation/v4/approvals/W0-05-dependency-decision.json",
        "tests/fixtures/keys/v4-test-ed25519.json",
            "tests/unit/test_remediation_run.py",
    ]
    for relative in sources:
        source = REPO / relative
        assert source.is_file(), relative
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def git(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True,
        )
        return completed.stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Runner Integration")
    git("config", "user.email", "runner@example.invalid")
    git("add", ".")
    git("commit", "-qm", "baseline")
    return repo, git


def test_real_minimal_dag_writes_chained_receipts(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [
        _auto_task("A", ["{python}", "-c", "print('a')"]),
        _auto_task("B", ["{python}", "-c", "print('b')"], depends_on=["A"]),
    ])
    state_root = tmp_path / "state"
    result = _run(plan, state_root)
    assert result.returncode == 0, result.stderr
    first = _receipt(state_root, "A")
    second = _receipt(state_root, "B")
    assert first["status"] == second["status"] == "COMPLETED"
    assert second["input_receipt_digests"] == {"A": first["receipt_digest"]}
    assert second["command_results"][0]["argv"][0] == sys.executable
    assert Path(second["command_results"][0]["stdout"]["path"]).read_bytes() == b"b\r\n" or Path(second["command_results"][0]["stdout"]["path"]).read_bytes() == b"b\n"


def test_auto_task_binds_nonempty_committed_delta_in_receipt(tmp_path: Path) -> None:
    repo = tmp_path / "isolated-repo"
    runner = repo / "tools" / "remediate_v4.py"
    runner.parent.mkdir(parents=True)
    shutil.copy2(RUNNER, runner)
    schema_dir = repo / "remediation" / "v4"
    schema_dir.mkdir(parents=True)
    shutil.copy2(REPO / "remediation" / "v4" / "task.schema.json", schema_dir)
    shutil.copy2(REPO / "remediation" / "v4" / "receipt.schema.json", schema_dir)
    shutil.copy2(REPO / "remediation" / "v4" / "issue-map.json", schema_dir)

    def git(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True,
        )
        return completed.stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Runner Integration")
    git("config", "user.email", "runner@example.invalid")
    git("add", "tools/remediate_v4.py", "remediation/v4/task.schema.json",
        "remediation/v4/receipt.schema.json", "remediation/v4/issue-map.json")
    git("commit", "-qm", "baseline")
    baseline = git("rev-parse", "HEAD")

    command = (
        "from pathlib import Path; import subprocess; "
        "p=Path('docs/_runner_committed_delta.txt'); p.parent.mkdir(parents=True); "
        "p.write_bytes(b'bound bytes\\n'); "
        "subprocess.run(['git','add','--',p.as_posix()],check=True); "
        "subprocess.run(['git','commit','-qm','runner integration delta'],check=True)"
    )
    plan = _write_plan(tmp_path / "plan", [
        _auto_task(
            "DELTA", ["{python}", "-c", command],
            allowed=["docs/_runner_committed_delta.txt"],
        )
    ])
    state_root = tmp_path / "state"
    result = _run_in_repo(repo, plan, state_root)
    assert result.returncode == 0, result.stderr

    receipt = _receipt(state_root, "DELTA")
    expected_digest = "sha256:" + hashlib.sha256(b"bound bytes\n").hexdigest()
    assert receipt["status"] == "COMPLETED"
    assert receipt["start_commit"] == baseline
    assert receipt["result_commit"] == git("rev-parse", "HEAD")
    assert receipt["result_commit"] != receipt["start_commit"]
    assert receipt["changed_paths"] == ["docs/_runner_committed_delta.txt"]
    assert receipt["artifact_digests"] == {
        "result-path:docs/_runner_committed_delta.txt": expected_digest,
    }
    assert receipt["allowlist"] == {"allowed": True, "violations": []}
    assert git("status", "--porcelain") == ""


def test_branching_dag_siblings_bind_sequential_execution_frontier(tmp_path: Path) -> None:
    repo, _ = _isolated_runner_repo(tmp_path)

    def commit_command(path: str, content: str, message: str) -> str:
        return (
            "from pathlib import Path; import subprocess; "
            f"p=Path({path!r}); p.parent.mkdir(parents=True, exist_ok=True); "
            f"p.write_bytes({content.encode()!r}); "
            "subprocess.run(['git','add','--',p.as_posix()],check=True); "
            f"subprocess.run(['git','commit','-qm',{message!r}],check=True)"
        )

    plan = _write_plan(tmp_path / "plan", [
        _auto_task(
            "A", [sys.executable, "-c", commit_command("docs/a.txt", "a\n", "A")],
            allowed=["docs/a.txt"],
        ),
        _auto_task(
            "B", [sys.executable, "-c", commit_command("docs/b.txt", "b\n", "B")],
            depends_on=["A"], allowed=["docs/b.txt"],
        ),
        _auto_task(
            "C", [sys.executable, "-c", commit_command("docs/c.txt", "c\n", "C")],
            depends_on=["A"], allowed=["docs/c.txt"],
        ),
        _auto_task(
            "D", [sys.executable, "-c", commit_command("docs/d.txt", "d\n", "D")],
            depends_on=["B", "C"], allowed=["docs/d.txt"],
        ),
    ])
    state_root = tmp_path / "state"
    result = _run_in_repo(repo, plan, state_root)
    assert result.returncode == 0, result.stderr

    first = _receipt(state_root, "A")
    sibling = _receipt(state_root, "B")
    current = _receipt(state_root, "C")
    joined = _receipt(state_root, "D")
    assert sibling["start_commit"] == first["result_commit"]
    assert current["input_receipt_digests"] == {"A": first["receipt_digest"]}
    assert current["start_commit"] == sibling["result_commit"]
    assert current["changed_paths"] == ["docs/c.txt"]
    assert current["allowlist"] == {"allowed": True, "violations": []}
    assert joined["input_receipt_digests"] == {
        "B": sibling["receipt_digest"], "C": current["receipt_digest"],
    }
    assert joined["start_commit"] == current["result_commit"]
    assert joined["changed_paths"] == ["docs/d.txt"]

    resumed = _run_in_repo(repo, plan, state_root)
    assert resumed.returncode == 0, resumed.stderr
    assert not (state_root / "tasks" / "C" / "2").exists()
    assert not (state_root / "tasks" / "D" / "2").exists()


def test_branching_dag_failed_sibling_retries_from_same_frontier(tmp_path: Path) -> None:
    repo, _ = _isolated_runner_repo(tmp_path)

    def commit_command(path: str, content: str, message: str) -> str:
        return (
            "from pathlib import Path; import subprocess; "
            f"p=Path({path!r}); p.parent.mkdir(parents=True, exist_ok=True); "
            f"p.write_bytes({content.encode()!r}); "
            "subprocess.run(['git','add','--',p.as_posix()],check=True); "
            f"subprocess.run(['git','commit','-qm',{message!r}],check=True)"
        )

    retry_command = (
        "import os, pathlib, subprocess, sys; "
        "flag=pathlib.Path(os.environ['JC_REMEDIATION_STATE_ROOT'])/'retry-c'; "
        "sys.exit(9) if not flag.exists() else None; "
        "p=pathlib.Path('docs/c.txt'); p.parent.mkdir(parents=True,exist_ok=True); "
        "p.write_bytes(b'c\\n'); "
        "subprocess.run(['git','add','--',p.as_posix()],check=True); "
        "subprocess.run(['git','commit','-qm','C'],check=True)"
    )
    plan = _write_plan(tmp_path / "plan", [
        _auto_task(
            "A", [sys.executable, "-c", commit_command("docs/a.txt", "a\n", "A")],
            allowed=["docs/a.txt"],
        ),
        _auto_task(
            "B", [sys.executable, "-c", commit_command("docs/b.txt", "b\n", "B")],
            depends_on=["A"], allowed=["docs/b.txt"],
        ),
        _auto_task(
            "C", [sys.executable, "-c", retry_command],
            depends_on=["A"], allowed=["docs/c.txt"],
        ),
    ])
    state_root = tmp_path / "state"
    first_run = _run_in_repo(repo, plan, state_root)
    assert first_run.returncode == 4, first_run.stderr

    first = _receipt(state_root, "A")
    sibling = _receipt(state_root, "B")
    failed = _receipt(state_root, "C")
    assert failed["status"] == "FAILED"
    assert failed["input_receipt_digests"] == {"A": first["receipt_digest"]}
    assert failed["start_commit"] == failed["result_commit"] == sibling["result_commit"]
    assert failed["changed_paths"] == []

    (state_root / "retry-c").write_text("retry", encoding="utf-8")
    second_run = _run_in_repo(repo, plan, state_root)
    assert second_run.returncode == 0, second_run.stderr
    retried = _receipt(state_root, "C", 2)
    assert retried["previous_receipt_digest"] == failed["receipt_digest"]
    assert retried["start_commit"] == sibling["result_commit"]
    assert retried["changed_paths"] == ["docs/c.txt"]
    assert not (state_root / "tasks" / "B" / "2").exists()


def test_allowed_but_uncommitted_path_fails_and_is_preserved(tmp_path: Path) -> None:
    repo, git = _isolated_runner_repo(tmp_path)
    plan = _write_plan(tmp_path / "plan", [
        _auto_task(
            "DIRTY",
            [sys.executable, "-c", (
                "from pathlib import Path; p=Path('docs/dirty.txt'); "
                "p.parent.mkdir(parents=True,exist_ok=True); p.write_text('dirty')"
            )],
            allowed=["docs/dirty.txt"],
        ),
    ])
    state_root = tmp_path / "state"
    result = _run_in_repo(repo, plan, state_root)
    assert result.returncode == 3, result.stderr

    receipt = _receipt(state_root, "DIRTY")
    assert receipt["status"] == "FAILED"
    assert receipt["start_commit"] == receipt["result_commit"]
    assert receipt["changed_paths"] == []
    assert not any(
        key.startswith("result-path:") or key.startswith("deleted-path:")
        for key in receipt["artifact_digests"]
    )
    clean = next(
        item for item in receipt["completion_assertions"]
        if item["id"] == "runner-clean-worktree"
    )
    assert clean["ok"] is False
    assert (repo / "docs" / "dirty.txt").read_text(encoding="utf-8") == "dirty"
    assert git("status", "--porcelain", "--untracked-files=all") == "?? docs/dirty.txt"


def test_divergent_head_rejects_before_task_command(tmp_path: Path) -> None:
    repo, git = _isolated_runner_repo(tmp_path)
    plan_dir = tmp_path / "plan"
    plan = _write_plan(plan_dir, [
        _auto_task(
            "A",
            [sys.executable, "-c", (
                "from pathlib import Path; import subprocess; "
                "p=Path('docs/a.txt'); p.parent.mkdir(parents=True,exist_ok=True); "
                "p.write_text('a'); subprocess.run(['git','add','--',p.as_posix()],check=True); "
                "subprocess.run(['git','commit','-qm','A'],check=True)"
            )],
            allowed=["docs/a.txt"],
        ),
    ])
    state_root = tmp_path / "state"
    first_run = _run_in_repo(repo, plan, state_root)
    assert first_run.returncode == 0, first_run.stderr
    first = _receipt(state_root, "A")

    git("checkout", "-q", first["start_commit"])
    (repo / "docs").mkdir()
    (repo / "docs" / "divergent.txt").write_text("divergent", encoding="utf-8")
    git("add", "--", "docs/divergent.txt")
    git("commit", "-qm", "divergent")
    sentinel_command = (
        "import os; from pathlib import Path; "
        "Path(os.environ['JC_REMEDIATION_STATE_ROOT']).joinpath('b-ran').write_text('ran')"
    )
    _write_plan(plan_dir, [
        _auto_task(
            "A",
            [sys.executable, "-c", (
                "from pathlib import Path; import subprocess; "
                "p=Path('docs/a.txt'); p.parent.mkdir(parents=True,exist_ok=True); "
                "p.write_text('a'); subprocess.run(['git','add','--',p.as_posix()],check=True); "
                "subprocess.run(['git','commit','-qm','A'],check=True)"
            )],
            allowed=["docs/a.txt"],
        ),
        _auto_task(
            "B", [sys.executable, "-c", sentinel_command],
            depends_on=["A"], allowed=["docs/b.txt"],
        ),
    ])
    second_run = _run_in_repo(repo, plan, state_root)
    assert second_run.returncode == 5
    assert "does not descend from execution frontier" in second_run.stderr
    assert not (state_root / "b-ran").exists()
    assert not (state_root / "tasks" / "B").exists()


def test_failure_exit_code_is_receipted(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_auto_task("FAIL", ["{python}", "-c", "raise SystemExit(7)"])])
    state_root = tmp_path / "state"
    result = _run(plan, state_root)
    assert result.returncode == 4
    receipt = _receipt(state_root, "FAIL")
    assert receipt["status"] == "FAILED"
    assert receipt["command_results"][0]["exit_code"] == 7


def test_missing_executable_is_receipted_not_raised(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_auto_task("MISSING", ["definitely-not-a-real-executable-7f9d"])])
    state_root = tmp_path / "state"
    result = _run(plan, state_root)
    assert result.returncode == 4
    receipt = _receipt(state_root, "MISSING")
    assert receipt["status"] == "FAILED"
    assert receipt["command_results"][0]["exit_code"] == 127


def test_timeout_is_receipted(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [
        _auto_task("SLOW", ["{python}", "-c", "import time; time.sleep(2)"], timeout=0.05)
    ])
    state_root = tmp_path / "state"
    result = _run(plan, state_root)
    assert result.returncode == 4
    receipt = _receipt(state_root, "SLOW")
    assert receipt["status"] == "TIMED_OUT"
    assert receipt["command_results"][0]["timed_out"] is True


def test_resume_skips_valid_dependency_and_retries_failure(tmp_path: Path) -> None:
    command = (
        "import os,pathlib; p=pathlib.Path(os.environ['JC_REMEDIATION_STATE_ROOT'])/'go'; "
        "raise SystemExit(0 if p.exists() else 9)"
    )
    plan = _write_plan(tmp_path, [
        _auto_task("A", ["{python}", "-c", "print('once')"]),
        _auto_task("B", ["{python}", "-c", command], depends_on=["A"]),
    ])
    state_root = tmp_path / "state"
    assert _run(plan, state_root).returncode == 4
    (state_root / "go").write_text("continue", encoding="utf-8")
    result = _run(plan, state_root)
    assert result.returncode == 0, result.stderr
    assert not (state_root / "tasks" / "A" / "2").exists()
    assert _receipt(state_root, "B", 2)["previous_receipt_digest"] == _receipt(state_root, "B", 1)["receipt_digest"]


def test_interrupted_attempt_is_preserved_and_resumed(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_auto_task("A", ["{python}", "-c", "print('recovered')"])])
    state_root = tmp_path / "state"
    partial = state_root / "tasks" / "A" / "1"
    partial.mkdir(parents=True)
    (partial / "stdout-001.bin").write_bytes(b"partial")
    result = _run(plan, state_root)
    assert result.returncode == 0, result.stderr
    assert (partial / "interrupted.json").is_file()
    assert _receipt(state_root, "A", 2)["status"] == "COMPLETED"
    assert _run(plan, state_root).returncode == 0


def test_allowed_paths_violation_fails_without_cleanup(tmp_path: Path) -> None:
    target = REPO / "tests" / "_runner_scope_violation.tmp"
    target.unlink(missing_ok=True)
    plan = _write_plan(tmp_path, [
        _auto_task(
            "SCOPE", ["{python}", "-c", "from pathlib import Path; Path('tests/_runner_scope_violation.tmp').write_text('x')"],
            allowed=["docs/**"],
        )
    ])
    try:
        result = _run(plan, tmp_path / "state")
        assert result.returncode == 6
        assert target.exists(), "runner must not clean an out-of-scope user path"
        assert _receipt(tmp_path / "state", "SCOPE")["allowlist"]["violations"] == ["tests/_runner_scope_violation.tmp"]
    finally:
        target.unlink(missing_ok=True)


def test_stdout_tamper_breaks_resume(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_auto_task("A", ["{python}", "-c", "print('bound')"])])
    state_root = tmp_path / "state"
    assert _run(plan, state_root).returncode == 0
    receipt = _receipt(state_root, "A")
    Path(receipt["command_results"][0]["stdout"]["path"]).write_bytes(b"tampered")
    assert _run(plan, state_root).returncode == 5


def test_task_definition_change_invalidates_completed_receipt(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_auto_task("A", ["{python}", "-c", "print('v1')"])])
    state_root = tmp_path / "state"
    assert _run(plan, state_root).returncode == 0
    first = _receipt(state_root, "A")
    _write_plan(tmp_path, [_auto_task("A", ["{python}", "-c", "print('v2')"])])
    assert _run(plan, state_root).returncode == 0
    second = _receipt(state_root, "A", 2)
    assert first["task_digest"] != second["task_digest"]
    assert Path(second["command_results"][0]["stdout"]["path"]).read_bytes().strip() == b"v2"


def test_result_tree_tamper_breaks_resume_even_with_rehashed_receipt(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_auto_task("A", ["{python}", "-c", "print('tree')"])])
    state_root = tmp_path / "state"
    assert _run(plan, state_root).returncode == 0
    path = state_root / "tasks" / "A" / "1" / "receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["result_tree"] = "0" * 40
    receipt["receipt_digest"] = _digest(receipt)
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert _run(plan, state_root).returncode == 5


def test_receipt_chain_tamper_breaks_resume(tmp_path: Path) -> None:
    command = (
        "import os,pathlib; p=pathlib.Path(os.environ['JC_REMEDIATION_STATE_ROOT'])/'go'; "
        "raise SystemExit(0 if p.exists() else 9)"
    )
    plan = _write_plan(tmp_path, [_auto_task("A", ["{python}", "-c", command])])
    state_root = tmp_path / "state"
    assert _run(plan, state_root).returncode == 4
    (state_root / "go").write_text("go", encoding="utf-8")
    assert _run(plan, state_root).returncode == 0
    path = state_root / "tasks" / "A" / "2" / "receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["previous_receipt_digest"] = "sha256:" + "0" * 64
    receipt["receipt_digest"] = _digest(receipt)
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert _run(plan, state_root).returncode == 5


def test_only_reached_gate_gets_request(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [
        _auto_task("A", ["{python}", "-c", "print('ready')"]),
        _gate_task("G1", ["A"]),
        _gate_task("G2", ["G1"]),
    ])
    state_root = tmp_path / "state"
    result = _run(plan, state_root)
    assert result.returncode == 21, result.stderr
    requests = list((state_root / "requests").rglob("*.json"))
    assert len(requests) == 1
    assert json.loads(requests[0].read_text(encoding="utf-8"))["task_id"] == "G1"
    assert "G2" not in result.stdout


def test_valid_ed25519_approval_is_consumed(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_gate_task("G1", [])])
    state_root = tmp_path / "state"
    assert _run(plan, state_root).returncode == 21
    request_path = next((state_root / "requests" / "G1").glob("*.json"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    key = Ed25519PrivateKey.generate()
    _install_trusted_key(state_root, key)
    _install_approval(state_root, request, key)
    result = _run(plan, state_root)
    assert result.returncode == 0, result.stderr
    receipt = _receipt(state_root, "G1")
    assert receipt["status"] == "COMPLETED"
    assert receipt["artifact_digests"]["request"] == request["request_digest"]


def test_invalid_approval_subject_role_scope_key_and_expiry_stay_waiting(tmp_path: Path) -> None:
    cases = ["subject", "role", "scope", "key", "expiry"]
    for case in cases:
        case_root = tmp_path / case
        plan = _write_plan(case_root, [_gate_task("G1", [])])
        state_root = case_root / "state"
        assert _run(plan, state_root).returncode == 21
        request = json.loads(next((state_root / "requests" / "G1").glob("*.json")).read_text(encoding="utf-8"))
        trusted = Ed25519PrivateKey.generate()
        signing = Ed25519PrivateKey.generate() if case == "key" else trusted
        _install_trusted_key(state_root, trusted)
        _install_approval(
            state_root, request, signing,
            role="wrong-role" if case == "role" else "external_provider",
            scope="wrong-scope" if case == "scope" else "G1",
            subject_digest="sha256:" + "0" * 64 if case == "subject" else None,
            expired=case == "expiry",
        )
        assert _run(plan, state_root).returncode == 21, case
        assert not (state_root / "tasks" / "G1").exists(), case


def test_same_signer_cannot_satisfy_separation_of_duties(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_gate_task("G1", [], minimum_signers=2, separation=True)])
    state_root = tmp_path / "state"
    assert _run(plan, state_root).returncode == 21
    request = json.loads(next((state_root / "requests" / "G1").glob("*.json")).read_text(encoding="utf-8"))
    key = Ed25519PrivateKey.generate()
    _install_trusted_key(state_root, key)
    _install_approval(state_root, request, key, filename="one.json")
    _install_approval(state_root, request, key, filename="two.json")
    assert _run(plan, state_root).returncode == 21


def test_old_approval_invalidates_when_subject_artifact_changes(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir()
    (state_root / "input.txt").write_text("v1", encoding="utf-8")
    plan = _write_plan(tmp_path, [
        _gate_task("G1", [], subject_paths=["$JC_REMEDIATION_STATE_ROOT/input.txt"])
    ])
    assert _run(plan, state_root).returncode == 21
    request = json.loads(next((state_root / "requests" / "G1").glob("*.json")).read_text(encoding="utf-8"))
    key = Ed25519PrivateKey.generate()
    _install_trusted_key(state_root, key)
    _install_approval(state_root, request, key)
    (state_root / "input.txt").write_text("v2", encoding="utf-8")
    result = _run(plan, state_root)
    assert result.returncode == 21
    assert len(list((state_root / "requests" / "G1").glob("*.json"))) == 2
    assert not (state_root / "tasks" / "G1").exists()


def test_cached_gate_request_tamper_fails_closed(tmp_path: Path) -> None:
    repo, _ = _isolated_runner_repo(tmp_path)
    plan = _write_plan(tmp_path / "plan", [_user_directive_task("G1")])
    state_root = tmp_path / "state"
    assert _run_in_repo(repo, plan, state_root).returncode == 20
    request_path = next((state_root / "requests" / "G1").glob("*.json"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["minimum_signers"] = 0
    unsigned_request = {
        key: value for key, value in request.items() if key != "request_digest"
    }
    request["request_digest"] = (
        "sha256:" + hashlib.sha256(_canonical(unsigned_request)).hexdigest()
    )
    request_path.write_text(json.dumps(request), encoding="utf-8")

    result = _run_in_repo(repo, plan, state_root)
    assert result.returncode == 5, result.stderr
    assert "gate request" in result.stderr
    assert not (state_root / "tasks" / "G1").exists()


def test_cached_gate_request_binds_current_task_and_dependency_state(tmp_path: Path) -> None:
    repo, _ = _isolated_runner_repo(tmp_path)
    task = _user_directive_task(
        "M1", mode="MIXED", argv=[sys.executable, "-c", "print('v1')"],
    )
    plan = _write_plan(tmp_path / "plan", [task])
    state_root = tmp_path / "state"
    assert _run_in_repo(repo, plan, state_root).returncode == 20
    request = json.loads(
        next((state_root / "requests" / "M1").glob("*.json")).read_text(encoding="utf-8")
    )
    assert request["task_digest"] == "sha256:" + hashlib.sha256(_canonical(task)).hexdigest()
    assert request["input_receipt_digests"] == {}
    assert request["start_commit"]

    changed_task = _user_directive_task(
        "M1", mode="MIXED", argv=[sys.executable, "-c", "print('v2')"],
    )
    _write_plan(tmp_path / "plan", [changed_task])
    result = _run_in_repo(repo, plan, state_root)
    assert result.returncode == 5, result.stderr
    assert "current task/state" in result.stderr
    assert not (state_root / "tasks" / "M1").exists()


def test_subject_digest_uses_portable_repo_and_state_labels(tmp_path: Path) -> None:
    requests = []
    for name in ("one", "two"):
        case_root = tmp_path / name
        repo, _ = _isolated_runner_repo(case_root)
        state_root = case_root / "state"
        state_root.mkdir(parents=True)
        (state_root / "input.txt").write_bytes(b"same state evidence\n")
        task = _user_directive_task(
            "G1",
            subject_paths=[
                "tools/remediate_v4.py",
                "$JC_REMEDIATION_STATE_ROOT/input.txt",
            ],
        )
        plan = _write_plan(case_root / "plan", [task])
        assert _run_in_repo(repo, plan, state_root).returncode == 20
        requests.append(json.loads(
            next((state_root / "requests" / "G1").glob("*.json")).read_text(encoding="utf-8")
        ))
    assert requests[0]["subject_digest"] == requests[1]["subject_digest"]


def test_user_directive_requires_closed_approve_policy_binding(tmp_path: Path) -> None:
    repo, _ = _isolated_runner_repo(tmp_path)
    cases = [
        "missing-signer", "reject", "wrong-role", "wrong-request",
        "wrong-scope", "future-issued-at", "bad-authority-hash",
        "missing-authority", "extra-field",
    ]
    for case in cases:
        case_root = tmp_path / case
        plan = _write_plan(case_root / "plan", [_user_directive_task("G1")])
        state_root = case_root / "state"
        assert _run_in_repo(repo, plan, state_root).returncode == 20
        request = json.loads(
            next((state_root / "requests" / "G1").glob("*.json")).read_text(encoding="utf-8")
        )
        directive = _install_user_directive(state_root, request)
        if case == "missing-signer":
            directive.pop("signer")
        elif case == "reject":
            directive["decision"] = "REJECT"
        elif case == "wrong-role":
            directive["signer"]["role"] = "untrusted"
        elif case == "wrong-request":
            directive["request_digest"] = "sha256:" + "0" * 64
        elif case == "wrong-scope":
            directive["scope"] = directive["signer"]["scope"] = "wrong-scope"
        elif case == "future-issued-at":
            directive["issued_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        elif case == "bad-authority-hash":
            directive["authority_source"]["sha256"] = "sha256:" + "0" * 64
        elif case == "missing-authority":
            directive["authority_source"]["locator"] = str(
                (state_root / "authority" / "missing.txt").resolve()
            )
        elif case == "extra-field":
            directive["unbound"] = True
        directive_path = state_root / "directives" / "G1" / "directive.json"
        directive_path.write_text(json.dumps(directive), encoding="utf-8")

        result = _run_in_repo(repo, plan, state_root)
        assert result.returncode == 20, (case, result.stderr)
        assert "Traceback" not in result.stderr, case
        assert not (state_root / "tasks" / "G1").exists(), case


def test_duplicate_user_directive_signer_cannot_meet_threshold(tmp_path: Path) -> None:
    repo, _ = _isolated_runner_repo(tmp_path)
    plan = _write_plan(tmp_path / "plan", [
        _user_directive_task("G1", minimum_signers=2, separation=True),
    ])
    state_root = tmp_path / "state"
    assert _run_in_repo(repo, plan, state_root).returncode == 20
    request = json.loads(
        next((state_root / "requests" / "G1").glob("*.json")).read_text(encoding="utf-8")
    )
    _install_user_directive(state_root, request)
    directive_dir = state_root / "directives" / "G1"
    shutil.copy2(directive_dir / "directive.json", directive_dir / "copy.json")

    assert _run_in_repo(repo, plan, state_root).returncode == 20
    assert not (state_root / "tasks" / "G1").exists()


def test_mixed_argv_requires_auto_execution_contract_before_request(tmp_path: Path) -> None:
    repo, _ = _isolated_runner_repo(tmp_path)
    task = _user_directive_task("M1", mode="MIXED")
    task.update({
        "argv": [[sys.executable, "-c", "print('unsafe incomplete contract')"]],
        "expected_exit_codes": [0],
        "required_receipt_fields": REQUIRED_RECEIPT_FIELDS,
    })
    plan = _write_plan(tmp_path / "plan", [task])
    state_root = tmp_path / "state"

    result = _run_in_repo(repo, plan, state_root)
    assert result.returncode == 4, result.stderr
    assert "completion_assertions" in result.stderr
    assert "rollback" in result.stderr
    assert not (state_root / "requests").exists()


def test_mixed_gate_with_zero_committed_delta_does_not_complete(tmp_path: Path) -> None:
    repo, _ = _isolated_runner_repo(tmp_path)
    plan = _write_plan(tmp_path / "plan", [
        _user_directive_task(
            "M1", mode="MIXED", argv=[sys.executable, "-c", "print('no delta')"],
        )
    ])
    state_root = tmp_path / "state"
    assert _run_in_repo(repo, plan, state_root).returncode == 20
    request = json.loads(
        next((state_root / "requests" / "M1").glob("*.json")).read_text(encoding="utf-8")
    )
    request_path = next((state_root / "requests" / "M1").glob("*.json"))
    directive = _install_user_directive(state_root, request)
    directive_path = state_root / "directives" / "M1" / "directive.json"

    result = _run_in_repo(repo, plan, state_root)
    assert result.returncode == 4, result.stderr
    receipt = _receipt(state_root, "M1")
    assert receipt["status"] == "FAILED"
    assert len(receipt["command_results"]) == 1
    assert receipt["changed_paths"] == []
    key_id = directive["signer"]["key_id"]
    assert receipt["artifact_digests"]["request-raw"] == _raw_digest(request_path)
    assert receipt["artifact_digests"][f"approval-raw:{key_id}"] == _raw_digest(directive_path)
    assert (
        receipt["artifact_digests"][f"authority-source:{key_id}"]
        == directive["authority_source"]["sha256"]
    )
    assert any(
        assertion["id"] == "runner-mixed-committed-delta" and not assertion["ok"]
        for assertion in receipt["completion_assertions"]
    )


def test_valid_user_directive_mixed_receipt_binds_execution_delta(tmp_path: Path) -> None:
    repo, git = _isolated_runner_repo(tmp_path)
    dependency_command = (
        "from pathlib import Path; import subprocess; "
        "p=Path('docs/dependency.txt'); p.parent.mkdir(parents=True); "
        "p.write_bytes(b'dependency\\n'); "
        "subprocess.run(['git','add','--',p.as_posix()],check=True); "
        "subprocess.run(['git','commit','-qm','dependency delta'],check=True)"
    )
    command = (
        "from pathlib import Path; import subprocess; "
        "p=Path('docs/mixed.txt'); p.parent.mkdir(parents=True, exist_ok=True); "
        "p.write_bytes(b'bound\\n'); "
        "subprocess.run(['git','add','--',p.as_posix()],check=True); "
        "subprocess.run(['git','commit','-qm','mixed delta'],check=True)"
    )
    plan = _write_plan(tmp_path / "plan", [
        _auto_task(
            "A", [sys.executable, "-c", dependency_command],
            allowed=["docs/dependency.txt"],
        ),
        _user_directive_task(
            "M1", mode="MIXED", argv=[sys.executable, "-c", command],
            allowed=["docs/mixed.txt"], depends_on=["A"],
        )
    ])
    state_root = tmp_path / "state"
    baseline_commit = git("rev-parse", "HEAD")
    assert _run_in_repo(repo, plan, state_root).returncode == 20
    dependency_receipt = _receipt(state_root, "A")
    assert dependency_receipt["start_commit"] == baseline_commit
    request_path = next((state_root / "requests" / "M1").glob("*.json"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    directive = _install_user_directive(state_root, request)
    directive_path = state_root / "directives" / "M1" / "directive.json"
    assert request["start_commit"] == dependency_receipt["result_commit"]
    assert request["input_receipt_digests"] == {"A": dependency_receipt["receipt_digest"]}

    result = _run_in_repo(repo, plan, state_root)
    assert result.returncode == 0, result.stderr
    receipt = _receipt(state_root, "M1")
    expected = "sha256:" + hashlib.sha256(b"bound\n").hexdigest()
    assert receipt["status"] == "COMPLETED"
    assert receipt["start_commit"] == dependency_receipt["result_commit"]
    assert receipt["result_commit"] == git("rev-parse", "HEAD")
    assert receipt["changed_paths"] == ["docs/mixed.txt"]
    assert receipt["artifact_digests"]["result-path:docs/mixed.txt"] == expected
    assert receipt["artifact_digests"]["request"] == request["request_digest"]
    assert receipt["artifact_digests"]["request-raw"] == _raw_digest(request_path)
    key_id = directive["signer"]["key_id"]
    assert receipt["artifact_digests"][f"approval:{key_id}"] == _digest(directive)
    assert receipt["artifact_digests"][f"approval-raw:{key_id}"] == _raw_digest(directive_path)
    assert (
        receipt["artifact_digests"][f"authority-source:{key_id}"]
        == directive["authority_source"]["sha256"]
    )
    assert len(receipt["command_results"]) == 1
    assert receipt["allowlist"] == {"allowed": True, "violations": []}


def test_manual_mixed_gate_receipts_preapproved_committed_delta(tmp_path: Path) -> None:
    repo, git = _isolated_runner_repo(tmp_path)
    plan = _write_plan(tmp_path / "plan", [
        _user_directive_task("M1", mode="MIXED", allowed=["docs/manual.txt"]),
    ])
    state_root = tmp_path / "state"
    start_commit = git("rev-parse", "HEAD")
    assert _run_in_repo(repo, plan, state_root).returncode == 20
    request_path = next((state_root / "requests" / "M1").glob("*.json"))
    request = json.loads(request_path.read_text(encoding="utf-8"))

    manual_path = repo / "docs" / "manual.txt"
    manual_path.parent.mkdir(parents=True)
    manual_path.write_bytes(b"manual approved delta\n")
    git("add", "--", "docs/manual.txt")
    git("commit", "-qm", "manual mixed delta")
    directive = _install_user_directive(state_root, request)
    directive_path = state_root / "directives" / "M1" / "directive.json"

    result = _run_in_repo(repo, plan, state_root)
    assert result.returncode == 0, result.stderr
    receipt = _receipt(state_root, "M1")
    key_id = directive["signer"]["key_id"]
    assert receipt["status"] == "COMPLETED"
    assert receipt["start_commit"] == start_commit
    assert receipt["result_commit"] == git("rev-parse", "HEAD")
    assert receipt["command_results"] == []
    assert receipt["changed_paths"] == ["docs/manual.txt"]
    assert receipt["allowlist"] == {"allowed": True, "violations": []}
    assert receipt["artifact_digests"]["request-raw"] == _raw_digest(request_path)
    assert receipt["artifact_digests"][f"approval-raw:{key_id}"] == _raw_digest(directive_path)
    assert receipt["artifact_digests"][f"authority-source:{key_id}"] == directive["authority_source"]["sha256"]


def test_w0_05_verifier_binds_dependency_key_and_target_matrix(tmp_path: Path) -> None:
    repo, _ = _isolated_runner_repo(tmp_path)
    command = [
        sys.executable, "-B", str(repo / "tools" / "remediate_v4.py"),
        "verify-wave", "W0-05",
    ]
    result = subprocess.run(command, cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "13 exact lock hashes" in result.stdout
    assert "9 decision artifacts" in result.stdout
    assert "6 target downloads" in result.stdout

    lock_path = repo / "requirements" / "core.lock"
    lock_text = lock_path.read_text(encoding="utf-8")
    lock_path.write_text(lock_text.replace("06a32a98", "16a32a98", 1), encoding="utf-8")
    tampered = subprocess.run(command, cwd=repo, capture_output=True, text=True)
    assert tampered.returncode == 4
    assert "13-hash authority" in tampered.stderr

    lock_path.write_text(lock_text, encoding="utf-8")
    plan_path = repo / "remediation" / "v4" / "tasks.json"
    plan_text = plan_path.read_text(encoding="utf-8")
    plan = json.loads(plan_text)
    task = next(item for item in plan["tasks"] if item["id"] == "W0-05")
    install = next(argv for argv in task["argv"] if argv[:5] == ["{python}", "-B", "-m", "pip", "install"])
    first_link = install.index("--find-links")
    del install[first_link:first_link + 2]
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    incomplete_wheelhouse = subprocess.run(command, cwd=repo, capture_output=True, text=True)
    assert incomplete_wheelhouse.returncode == 4
    assert "offline/hash-bound" in incomplete_wheelhouse.stderr

    plan = json.loads(plan_text)
    task = next(item for item in plan["tasks"] if item["id"] == "W0-05")
    smoke = next(
        argv for argv in task["argv"]
        if argv[:3] == ["{python}", "-B", "-c"] and "locked-runtime" in argv[-1]
    )
    smoke[3] = smoke[3].replace("sys.argv[1]", "'.'")
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    embedded_path = subprocess.run(command, cwd=repo, capture_output=True, text=True)
    assert embedded_path.returncode == 4
    assert "RFC8032 smoke test" in embedded_path.stderr

    plan = json.loads(plan_text)
    task = next(item for item in plan["tasks"] if item["id"] == "W0-05")
    task["allowed_paths"][8] = "remediation/v4/approvals/W0-05*"
    task["approval"]["subject_paths"][8] = "remediation/v4/approvals/W0-05*"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    broadened_scope = subprocess.run(command, cwd=repo, capture_output=True, text=True)
    assert broadened_scope.returncode == 4
    assert "exact scoped-path contract" in broadened_scope.stderr
