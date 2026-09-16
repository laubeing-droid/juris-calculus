"""JC-03 tool identity contracts (source and installed lanes).

The receipt producer and the cross-repo verifier must cite the producer
that actually ran: a ``--runtime-commit`` that disagrees with the
checked-out HEAD is refused; the recorded identity carries the tree and
the worktree dirtiness; the installed lane derives identity only from
the dist origin manifest and the wheel bytes, never from a git call in
some other working directory.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

from tools.generate_c06_entry_receipts import resolve_runtime_identity  # noqa: E402
from tools.verify_c06_integration import (  # noqa: E402
    VerificationError,
    _installed_origin_checks,
    resolve_runtime_identity as resolve_verify_identity,
)


def _head() -> str:
    return subprocess.run(  # noqa: S603 - fixed argv
        ["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True,
        text=True, check=True, shell=False,
    ).stdout.strip()


def test_generator_rejects_a_runtime_commit_that_is_not_head() -> None:
    with pytest.raises(SystemExit, match="RUNTIME_COMMIT_MISMATCH"):
        resolve_runtime_identity("0" * 40)
    with pytest.raises(SystemExit, match="RUNTIME_COMMIT_INVALID"):
        resolve_runtime_identity("not-a-sha")


def test_generator_identity_records_tree_and_dirtiness() -> None:
    identity = resolve_runtime_identity(None)
    assert identity["commit"] == _head()
    assert identity["tree"]
    assert isinstance(identity["worktree_dirty"], bool)
    assert identity["dirty_entries"] == [] or identity["worktree_dirty"]


def test_verifier_rejects_a_runtime_commit_that_is_not_head() -> None:
    with pytest.raises(VerificationError, match="RUNTIME_COMMIT_MISMATCH"):
        resolve_verify_identity("0" * 40)
    with pytest.raises(VerificationError, match="RUNTIME_COMMIT_INVALID"):
        resolve_verify_identity("zzz")


def _minimal_wheel(path: Path, record: bytes) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("juris_calculus-5.0.1.dist-info/RECORD", record)


def test_installed_origin_checks_bind_wheel_and_record() -> None:
    record = b"compiler_core/__init__.py,sha256=abc,10\n"
    with tempfile.TemporaryDirectory() as raw:
        temporary = Path(raw)
        wheel = temporary / "juris_calculus-5.0.1-py3-none-any.whl"
        _minimal_wheel(wheel, record)
        manifest = {
            "schema_version": "jc/dist-origin/1.0",
            "mode": "installed",
            "source_commit": "a" * 40,
            "source_tree": "b" * 40,
            "worktree_dirty_at_build": False,
            "wheel": wheel.name,
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "record_entries_sha256": hashlib.sha256(record).hexdigest(),
        }
        checks = _installed_origin_checks(manifest, temporary / "m.json", wheel)
        assert all(row["passed"] for row in checks)

        tampered = dict(manifest, wheel_sha256="0" * 64)
        with pytest.raises(VerificationError):
            _installed_origin_checks(tampered, temporary / "m.json", wheel)

        drifted_record = dict(
            manifest, record_entries_sha256="0" * 64,
        )
        with pytest.raises(VerificationError):
            _installed_origin_checks(drifted_record, temporary / "m.json", wheel)

        bad_schema = dict(manifest, schema_version="jc/dist-origin/9.9")
        with pytest.raises(VerificationError):
            _installed_origin_checks(bad_schema, temporary / "m.json", wheel)


def test_installed_origin_manifest_shape_is_enforced() -> None:
    manifest = {
        "schema_version": "jc/dist-origin/1.0",
        "mode": "installed",
        "source_commit": "short",
        "source_tree": "b" * 40,
        "worktree_dirty_at_build": False,
        "wheel": "x.whl",
        "wheel_sha256": "0" * 64,
        "record_entries_sha256": "0" * 64,
    }
    with pytest.raises(VerificationError):
        _installed_origin_checks(manifest, Path("m.json"), None)


def test_verifier_installed_mode_rejects_origin_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import verify_c06_integration as verifier

    manifest = tmp_path / "origin.json"
    manifest.write_text(json.dumps({
        "schema_version": "jc/dist-origin/1.0",
        "mode": "installed",
        "source_commit": "a" * 40,
        "source_tree": "b" * 40,
        "worktree_dirty_at_build": False,
        "wheel": "x.whl",
        "wheel_sha256": "0" * 64,
        "record_entries_sha256": "0" * 64,
    }), encoding="utf-8")
    report = tmp_path / "run.json"
    report.write_text(json.dumps({
        "schema_version": "jc/c06-installed-run/1.0",
        "runtime_commit": "c" * 40,
        "engine_version": "5.0.1",
        "witnesses": [],
    }), encoding="utf-8")

    class Args:
        origin_manifest = manifest
        installed_wheel = None
        installed_report = report
        output = tmp_path / "evidence.json"

    with pytest.raises(VerificationError, match="RUNTIME_ORIGIN_MISMATCH"):
        verifier.run_installed_verification(Args())
