"""Integration and tamper tests for the executable V4 task runner."""
from __future__ import annotations

import hashlib
import json
import os
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
