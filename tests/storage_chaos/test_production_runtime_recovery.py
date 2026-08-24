from __future__ import annotations

from pathlib import Path

import pytest

from compiler_core.canonical_serialization import canonical_bytes
from tools import local_production


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) if not isinstance(value, bytes) else value)


def test_backup_restores_only_to_independent_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / "deployment/releases/r1"
    current = {
        "release_id": "r1", "manifest_path": str(release / "release.json"),
    }
    _write(tmp_path / "deployment/current.json", current)
    _write(tmp_path / "deployment/previous.json", {"production_rollback_allowed": False})
    _write(tmp_path / "deployment/profile-registry.json", {"active_profile": "r1"})
    _write(release / "release.json", {"release_id": "r1"})
    _write(release / "config/runtime-config.json", {"release_id": "r1"})
    _write(release / "config/formal-profile.json", {"profile_id": "r1"})
    _write(release / "evidence/positive-chain.json", {"release_id": "r1"})
    _write(tmp_path / "identity/service-runtime.json", b"service")
    _write(tmp_path / "packs/pack.json", {"pack": "r1"})
    _write(tmp_path / "trust/trust.json", {"trust": "r1"})
    _write(tmp_path / "runtime-state/objects/value", b"runtime")
    monkeypatch.setattr(
        local_production, "production_status", lambda _root: {"release_id": "r1"}
    )
    monkeypatch.setattr(
        local_production, "_efs_evidence",
        lambda _path: {"encrypted": True, "algorithm": "EFS-AES-256"},
    )

    backup = local_production.backup_state(tmp_path)
    before = (tmp_path / "runtime-state/objects/value").read_bytes()
    restored = local_production.restore_rehearsal(tmp_path, backup["backup_id"])

    assert restored["status"] == "RESTORE_REHEARSAL_VERIFIED"
    assert (tmp_path / "runtime-state/objects/value").read_bytes() == before
    rehearsal = (
        tmp_path / "operations/restore-rehearsals" / backup["backup_id"]
        / "payload/runtime-state/objects/value"
    )
    assert rehearsal.read_bytes() == before


def test_rollback_requires_a_verified_previous_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(
        tmp_path / "deployment/previous.json",
        {"schema_version": "jc/local-production-previous/1.0", "production_rollback_allowed": False},
    )
    with pytest.raises(ValueError, match="not rollbackable"):
        local_production.rollback_release(tmp_path)

