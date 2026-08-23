from __future__ import annotations

import errno
import multiprocessing
import os
from pathlib import Path

import pytest

from compiler_core.canonical_serialization import DigestV4
import compiler_core.storage as storage
from compiler_core.storage import NAMESPACE_V4, StorageV4Error, V4TransactionStore


_POWER_LOSS_PAYLOAD = b"durable-v4-object"
_KILL_POINTS = (
    "lease-durable",
    "stage-written",
    "stage-durable",
    "object-published",
    "directory-durable",
)


def _die_at_checkpoint(state_root: str, checkpoint: str) -> None:
    def die(name: str) -> None:
        if name == checkpoint:
            os._exit(77)

    storage._checkpoint = die
    store = V4TransactionStore.open(Path(state_root), quota_bytes=1_000_000)
    store.put_bytes("kill", _POWER_LOSS_PAYLOAD)


@pytest.mark.parametrize("checkpoint", _KILL_POINTS)
def test_write_point_kill_recovers_only_complete_or_absent(
    tmp_path: Path,
    checkpoint: str,
) -> None:
    V4TransactionStore.create(tmp_path, quota_bytes=1_000_000)
    context = multiprocessing.get_context("spawn")
    process = context.Process(target=_die_at_checkpoint, args=(str(tmp_path), checkpoint))
    process.start()
    process.join(30)
    if process.is_alive():
        process.kill()
        process.join(10)
    assert process.exitcode == 77

    restarted = V4TransactionStore.open(tmp_path, quota_bytes=1_000_000)
    assert restarted.recover() >= 1
    assert list((tmp_path / NAMESPACE_V4 / "staging").iterdir()) == []

    digest = DigestV4.from_bytes(_POWER_LOSS_PAYLOAD)
    target = (
        tmp_path / NAMESPACE_V4 / "objects" / digest.hex[:2]
        / f"{digest.hex}.blob"
    )
    if target.exists():
        assert restarted.get_bytes(digest) == _POWER_LOSS_PAYLOAD
    for object_path in (tmp_path / NAMESPACE_V4 / "objects").glob("*/*.blob"):
        assert DigestV4.from_bytes(object_path.read_bytes()).hex == object_path.stem


def test_directory_fsync_preserves_replayable_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = V4TransactionStore.create(tmp_path, quota_bytes=1_000_000)
    events: list[str] = []
    real_flush = storage._flush_directory

    def record_flush(path: Path) -> None:
        events.append(f"flush:{path.name}")
        real_flush(path)

    monkeypatch.setattr(storage, "_flush_directory", record_flush)
    monkeypatch.setattr(storage, "_checkpoint", lambda name: events.append(name))
    stored = store.put_bytes("result", _POWER_LOSS_PAYLOAD)

    assert events.index("object-published") < events.index(f"flush:{stored.digest.hex[:2]}")
    assert events.index(f"flush:{stored.digest.hex[:2]}") < events.index("directory-durable")
    assert events.index("directory-durable") < events.index("flush:staging")
    reopened = V4TransactionStore.open(tmp_path, quota_bytes=1_000_000)
    assert reopened.get_bytes(stored.digest) == _POWER_LOSS_PAYLOAD


@pytest.mark.parametrize(
    ("error_number", "expected_code"),
    [(errno.ENOSPC, "STORAGE_CAPACITY"), (errno.EROFS, "STORAGE_PERMISSION")],
)
def test_disk_full_and_read_only_leave_no_partial_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
    expected_code: str,
) -> None:
    store = V4TransactionStore.create(tmp_path, quota_bytes=1_000_000)
    if error_number == errno.ENOSPC:
        monkeypatch.setattr(
            storage,
            "_write_all",
            lambda descriptor, payload: storage._io_fail(
                OSError(error_number, "injected storage failure"), "artifact write",
            ),
        )
    else:
        real_open = storage._open_exact

        def fail_create(path: Path, *, write: bool, create: bool = False) -> int:
            if create:
                storage._io_fail(OSError(error_number, "injected storage failure"), path.name)
            return real_open(path, write=write, create=create)

        monkeypatch.setattr(storage, "_open_exact", fail_create)
    with pytest.raises(StorageV4Error, match=rf"^{expected_code}:"):
        store.put_bytes("failure", _POWER_LOSS_PAYLOAD)
    assert list((tmp_path / NAMESPACE_V4 / "objects").glob("*/*.blob")) == []
