from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

import compiler_core.storage as storage
from compiler_core.storage import StorageV4Error, V4TransactionStore


def test_unverified_dacl_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = V4TransactionStore.create(tmp_path, quota_bytes=1_000_000)
    if os.name == "nt":
        def unavailable(path: Path) -> tuple[str, frozenset[str]]:
            del path
            storage._fail(
                "STORAGE_CAPABILITY_BLOCKED",
                "Windows owner or DACL verification is unavailable",
            )

        monkeypatch.setattr(storage, "_windows_acl_sids", unavailable)
        expected = "STORAGE_CAPABILITY_BLOCKED"
    else:
        store.root.chmod(0o755)
        expected = "STORAGE_PERMISSION"
    with pytest.raises(StorageV4Error, match=rf"^{expected}:"):
        V4TransactionStore.open(tmp_path, quota_bytes=1_000_000)


def test_everyone_write_ace_fails_closed(tmp_path: Path) -> None:
    store = V4TransactionStore.create(tmp_path, quota_bytes=1_000_000)
    if os.name == "nt":
        completed = subprocess.run(
            [
                "icacls.exe", str(store.root), "/grant",
                "*S-1-1-0:(OI)(CI)F",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        assert completed.returncode == 0, "STORAGE_CAPABILITY_BLOCKED: icacls failed"
        expected = "STORAGE_DACL"
    else:
        store.root.chmod(0o777)
        expected = "STORAGE_PERMISSION"
    with pytest.raises(StorageV4Error, match=rf"^{expected}:"):
        V4TransactionStore.open(tmp_path, quota_bytes=1_000_000)


def test_owner_change_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    V4TransactionStore.create(tmp_path, quota_bytes=1_000_000)
    if os.name == "nt":
        current = storage._current_windows_sid()
        monkeypatch.setattr(
            storage,
            "_windows_acl_sids",
            lambda path: ("S-1-5-18", frozenset({current, "S-1-5-18"})),
        )
        expected = "STORAGE_DACL"
    else:
        current_uid = os.geteuid()
        monkeypatch.setattr(storage.os, "geteuid", lambda: current_uid + 1)
        expected = "STORAGE_PERMISSION"
    with pytest.raises(StorageV4Error, match=rf"^{expected}:"):
        V4TransactionStore.open(tmp_path, quota_bytes=1_000_000)
