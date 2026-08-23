"""Local storage probe is executable evidence, not a production capability."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from compiler_core.canonical_serialization import DigestV4, canonical_bytes
import compiler_core.storage as storage
from compiler_core.storage import (
    NAMESPACE_V4,
    StorageV4Error,
    V4TransactionStore,
    probe_local_storage,
)


def test_local_probe_is_unpromotable_path_free_and_digest_bound(tmp_path: Path) -> None:
    probe = probe_local_storage(tmp_path / "probe", quota_bytes=1_000_000)
    document = probe.to_dict()
    probe_digest = document.pop("probe_digest")

    assert document["scope"] == "test-local"
    assert document["production_allowed"] is False
    assert document["target_provider_claimed"] is False
    assert document["checks"] == [
        "content-addressed-roundtrip",
        "private-layout",
        "reopen-roundtrip",
        "stale-recovery-scan",
    ]
    assert probe_digest == str(DigestV4.from_bytes(canonical_bytes(document)))
    assert str(tmp_path.resolve()) not in json.dumps(probe.to_dict(), sort_keys=True)


def test_local_probe_rejects_too_small_quota_before_creation(tmp_path: Path) -> None:
    target = tmp_path / "too-small"
    with pytest.raises(StorageV4Error, match="^STORAGE_QUOTA:"):
        probe_local_storage(target, quota_bytes=1)
    assert not (target / NAMESPACE_V4).exists()


def test_local_probe_capacity_failure_is_typed_before_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "no-capacity"
    monkeypatch.setattr(
        storage.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100, used=99, free=1),
    )
    with pytest.raises(StorageV4Error, match="^STORAGE_CAPACITY:"):
        probe_local_storage(target, quota_bytes=1_000_000)
    assert not (target / NAMESPACE_V4).exists()


def test_local_probe_never_overwrites_an_existing_namespace(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    V4TransactionStore.create(target, quota_bytes=1_000_000)

    with pytest.raises(StorageV4Error, match="^STORAGE_ALREADY_EXISTS:"):
        probe_local_storage(target, quota_bytes=1_000_000)
