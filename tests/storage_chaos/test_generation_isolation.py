from __future__ import annotations

from pathlib import Path

import pytest

from compiler_core.canonical_serialization import DigestV4
from compiler_core.storage import NAMESPACE_V4, StorageV4Error, V4TransactionStore


def test_v3_and_v4_state_generations_are_disjoint(tmp_path: Path) -> None:
    v3_root = tmp_path / "jc-v3-state"
    v3_root.mkdir()
    v3_payload = b"legacy-v3-cache-entry"
    v3_entry = v3_root / "shared-result.cache"
    v3_entry.write_bytes(v3_payload)

    store = V4TransactionStore.create(tmp_path, quota_bytes=1_000_000)
    v4_payload = b"formal-v4-result"
    stored = store.put_bytes("result", v4_payload)

    assert store.root == tmp_path / NAMESPACE_V4
    assert store.root != v3_root
    assert v3_entry.read_bytes() == v3_payload
    assert store.get_bytes(stored.digest) == v4_payload
    with pytest.raises(StorageV4Error, match="^STORAGE_NOT_FOUND:"):
        store.get_bytes(DigestV4.from_bytes(v3_payload))
    assert list((tmp_path / NAMESPACE_V4 / "objects").glob("*/*.blob")) == [
        tmp_path / NAMESPACE_V4 / "objects" / stored.digest.hex[:2]
        / f"{stored.digest.hex}.blob"
    ]


def test_v3_namespace_marker_cannot_open_as_v4(tmp_path: Path) -> None:
    store = V4TransactionStore.create(tmp_path, quota_bytes=1_000_000)
    marker = store.root / ".jc-v4-storage.json"
    marker.write_bytes(b'{"namespace":"jc-v3-state","schema_version":"jc/storage-root/1.0"}')
    with pytest.raises(StorageV4Error, match="^STORAGE_NAMESPACE:"):
        store.put_bytes("result", b"must-not-cross-generation")
    with pytest.raises(StorageV4Error, match="^STORAGE_NAMESPACE:"):
        V4TransactionStore.open(tmp_path, quota_bytes=1_000_000)
