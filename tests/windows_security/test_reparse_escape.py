from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from compiler_core.storage import StorageV4Error, V4TransactionStore


def _make_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            pytest.fail("STORAGE_CAPABILITY_BLOCKED: directory symlink creation failed")
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        pytest.fail("STORAGE_CAPABILITY_BLOCKED: junction creation failed")


def _remove_directory_link(link: Path) -> None:
    if link.is_symlink():
        link.unlink()
    else:
        link.rmdir()


def test_state_reparse_cannot_escape_root(tmp_path: Path) -> None:
    store = V4TransactionStore.create(tmp_path / "state", quota_bytes=1_000_000)
    objects = store.root / "objects"
    original = tmp_path / "original-objects"
    outside = tmp_path / "outside"
    outside.mkdir()
    objects.rename(original)
    _make_directory_link(objects, outside)
    try:
        with pytest.raises(StorageV4Error, match="^STORAGE_REPARSE:"):
            store.put_bytes("escape", b"must-not-leave-state-root")
        assert list(outside.iterdir()) == []
    finally:
        _remove_directory_link(objects)
        original.rename(objects)


def test_state_root_reparse_is_rejected_before_creation(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    _make_directory_link(alias, target)
    try:
        with pytest.raises(StorageV4Error, match="^STORAGE_REPARSE:"):
            V4TransactionStore.create(alias, quota_bytes=1_000_000)
        assert list(target.iterdir()) == []
    finally:
        _remove_directory_link(alias)


def test_directory_identity_swap_fails_before_write(tmp_path: Path) -> None:
    store = V4TransactionStore.create(tmp_path, quota_bytes=1_000_000)
    objects = store.root / "objects"
    original = store.root / "objects-original"
    objects.rename(original)
    objects.mkdir(mode=0o700)
    try:
        with pytest.raises(StorageV4Error, match="^STORAGE_TOCTOU:"):
            store.put_bytes("swap", b"must-not-write")
        assert list(objects.iterdir()) == []
    finally:
        objects.rmdir()
        original.rename(objects)
