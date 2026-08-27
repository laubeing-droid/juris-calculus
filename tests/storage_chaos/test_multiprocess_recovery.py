from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import time

import pytest

from compiler_core.canonical_serialization import DigestV4
from compiler_core.storage import (
    NAMESPACE_V4,
    StorageV4Error,
    V4TransactionStore,
    _harden_windows,
)


_PAYLOAD = b"juris-calculus-v4-cross-process"


def _write_same_object(state_root: str) -> None:
    store = V4TransactionStore.open(Path(state_root), quota_bytes=1_000_000)
    stored = store.put_bytes("worker", _PAYLOAD)
    if store.get_bytes(stored.digest) != _PAYLOAD:
        raise AssertionError("published bytes differ")


def _join_all(processes: list[multiprocessing.Process], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    try:
        for process in processes:
            process.join(max(0.0, deadline - time.monotonic()))
        assert all(not process.is_alive() for process in processes)
        assert [process.exitcode for process in processes] == [0] * len(processes)
    finally:
        for process in processes:
            if process.is_alive():
                process.kill()
                process.join(10)


@pytest.mark.parametrize("process_count", [2, 10, 100])
def test_cross_process_lock_and_stale_staging_recovery(
    tmp_path: Path,
    process_count: int,
) -> None:
    store = V4TransactionStore.create(tmp_path, quota_bytes=1_000_000)
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_write_same_object, args=(str(tmp_path),))
        for _ in range(process_count)
    ]
    for process in processes:
        process.start()
    _join_all(processes, timeout=120)

    digest = DigestV4.from_bytes(_PAYLOAD)
    objects = list((tmp_path / NAMESPACE_V4 / "objects").glob("*/*.blob"))
    assert [path.name for path in objects] == [f"{digest.hex}.blob"]
    assert store.get_bytes(digest) == _PAYLOAD

    staging = tmp_path / NAMESPACE_V4 / "staging"
    stale_paths = (staging / "dead.1.stage", staging / "dead.1.lease")
    for path, content in zip(stale_paths, (b"partial", b"lease"), strict=True):
        path.write_bytes(content)
        if os.name == "nt":
            _harden_windows(path)
        else:
            path.chmod(0o600)
    assert V4TransactionStore.open(tmp_path, quota_bytes=1_000_000).recover() == 2
    assert list(staging.iterdir()) == []
    assert len(list((tmp_path / NAMESPACE_V4 / "quarantine").iterdir())) == 2


def test_content_address_dedup_quota_and_collision(tmp_path: Path) -> None:
    store = V4TransactionStore.create(tmp_path, quota_bytes=len(_PAYLOAD))
    first = store.put_bytes("result", _PAYLOAD)
    assert store.put_bytes("retry", _PAYLOAD) == first

    with pytest.raises(StorageV4Error, match="^STORAGE_QUOTA:"):
        store.put_bytes("result", b"x")

    object_path = (
        tmp_path / NAMESPACE_V4 / "objects" / first.digest.hex[:2]
        / f"{first.digest.hex}.blob"
    )
    object_path.write_bytes(b"attacker replacement")
    with pytest.raises(StorageV4Error, match="^STORAGE_COLLISION:"):
        store.get_bytes(first.digest)


@pytest.mark.parametrize("kind", ["../escape", "a/b", ".hidden", "", "x" * 129])
def test_staging_kind_is_a_logical_identifier(tmp_path: Path, kind: str) -> None:
    store = V4TransactionStore.create(tmp_path, quota_bytes=1_000_000)
    with pytest.raises(StorageV4Error, match="^STORAGE_IDENTIFIER:"):
        store.put_bytes(kind, b"content")
