"""Durable, isolated, content-addressed storage for V4 formal artifacts."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import csv
import errno
from functools import lru_cache
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time
import uuid
from typing import Iterator

from compiler_core.canonical_serialization import DigestV4, canonical_bytes


NAMESPACE_V4 = "jc-v4-state"
ROOT_MARKER = ".jc-v4-storage.json"
ROOT_SCHEMA = "jc/storage-root/1.0"
_REPARSE_POINT = 0x400
_IDENTIFIER = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


class StorageV4Error(RuntimeError):
    """Stable fail-closed storage error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise StorageV4Error(code, detail)


def _checkpoint(name: str) -> None:
    """Test seam for process-kill/fault injection; production is a no-op."""

    del name


def _identifier(value: object, field: str) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 128
        or value[0] not in _IDENTIFIER - {".", "_", "-"}
        or any(character not in _IDENTIFIER for character in value)
    ):
        _fail("STORAGE_IDENTIFIER", f"{field} is not a logical identifier")
    return value


def _is_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _file_id(path: Path) -> tuple[int, int]:
    try:
        info = path.lstat()
    except OSError as exc:
        _io_fail(exc, f"cannot stat {path.name}")
    if _is_reparse(info):
        _fail("STORAGE_REPARSE", f"reparse point is forbidden: {path.name}")
    return info.st_dev, info.st_ino


def _io_fail(exc: OSError, detail: str) -> None:
    if exc.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)}:
        _fail("STORAGE_CAPACITY", detail)
    if exc.errno in {errno.EACCES, errno.EPERM, errno.EROFS}:
        _fail("STORAGE_PERMISSION", detail)
    _fail("STORAGE_IO", f"{detail}: {exc}")


def _safe_root(value: object) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        _fail("STORAGE_ROOT", "state_root must be an absolute pathlib.Path")
    raw = str(value)
    if os.name == "nt" and raw.startswith(("\\\\", "\\\\?\\", "\\\\.\\")):
        _fail("STORAGE_ROOT", "UNC and device state roots are forbidden")
    root = Path(os.path.abspath(raw))
    if root == Path(root.anchor):
        _fail("STORAGE_ROOT", "filesystem roots are forbidden")
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current /= part
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if _is_reparse(info):
                _fail("STORAGE_REPARSE", "state root traverses a reparse point")
    return root


def _mkdir(path: Path) -> None:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or _is_reparse(info):
            _fail("STORAGE_LAYOUT", f"storage directory is unsafe: {path.name}")
    except OSError as exc:
        _io_fail(exc, f"cannot create {path.name}")
    if os.name != "nt":
        try:
            path.chmod(0o700)
        except OSError as exc:
            _io_fail(exc, f"cannot secure {path.name}")


def _open_flags(*, write: bool, create: bool = False) -> int:
    flags = os.O_WRONLY if write else os.O_RDONLY
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return flags


def _open_exact(path: Path, *, write: bool, create: bool = False) -> int:
    try:
        if os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            open_file = kernel32.CreateFileW
            open_file.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
            ]
            open_file.restype = wintypes.HANDLE
            handle = open_file(
                str(path), 0x40000000 if write else 0x80000000, 0x7, None,
                1 if create else 3, 0x00200000 | (0x80000000 if write else 0), None,
            )
            if handle == wintypes.HANDLE(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                descriptor = msvcrt.open_osfhandle(
                    handle, getattr(os, "O_BINARY", 0) | (os.O_WRONLY if write else os.O_RDONLY),
                )
            except Exception:
                kernel32.CloseHandle(handle)
                raise
        else:
            descriptor = os.open(path, _open_flags(write=write, create=create), 0o600)
    except OSError as exc:
        _io_fail(exc, f"cannot open {path.name}")
    info = os.fstat(descriptor)
    try:
        path_info = path.lstat()
    except OSError as exc:
        os.close(descriptor)
        _io_fail(exc, f"cannot restat {path.name}")
    if (
        not stat.S_ISREG(info.st_mode)
        or _is_reparse(info)
        or _is_reparse(path_info)
        or (info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino)
    ):
        os.close(descriptor)
        _fail("STORAGE_LAYOUT", f"storage file is not regular: {path.name}")
    return descriptor


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        try:
            written = os.write(descriptor, view)
        except OSError as exc:
            _io_fail(exc, "artifact write failed")
        if written <= 0:
            _fail("STORAGE_IO", "artifact write made no progress")
        view = view[written:]


def _flush_file(descriptor: int) -> None:
    try:
        os.fsync(descriptor)
    except OSError as exc:
        _io_fail(exc, "file durability is unavailable")


def _flush_directory(path: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        _io_fail(exc, f"directory durability is unavailable: {path.name}")


def _move_write_through(source: Path, target: Path) -> None:
    if os.name != "nt":
        try:
            os.link(source, target, follow_symlinks=False)
            source.unlink()
        except FileExistsError:
            _fail("STORAGE_COLLISION", "artifact target already exists")
        except OSError as exc:
            _io_fail(exc, "atomic artifact publication failed")
        return
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    move = kernel32.MoveFileExW
    move.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    move.restype = ctypes.c_int
    if not move(str(source), str(target), 0x8):
        error = ctypes.get_last_error()
        if error in {80, 183}:
            _fail("STORAGE_COLLISION", "artifact target already exists")
        _io_fail(ctypes.WinError(error), "write-through artifact publication failed")


@lru_cache(maxsize=1)
def _current_windows_sid() -> str:
    completed = subprocess.run(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if completed.returncode != 0:
        _fail("STORAGE_CAPABILITY_BLOCKED", "current Windows SID is unavailable")
    try:
        row = next(csv.reader([completed.stdout.strip()]))
    except (StopIteration, csv.Error):
        _fail("STORAGE_CAPABILITY_BLOCKED", "current Windows SID is malformed")
    if len(row) < 2 or not row[1].startswith("S-"):
        _fail("STORAGE_CAPABILITY_BLOCKED", "current Windows SID is malformed")
    return row[1]


def _harden_windows(path: Path) -> None:
    sid = _current_windows_sid()
    rights = "(OI)(CI)F" if path.is_dir() else "F"
    commands = (
        ["icacls.exe", str(path), "/setowner", f"*{sid}"],
        [
            "icacls.exe", str(path), "/inheritance:r", "/grant:r",
            f"*{sid}:{rights}", f"*S-1-5-18:{rights}",
        ],
        [
            "icacls.exe", str(path), "/remove:g",
            "*S-1-1-0", "*S-1-5-11", "*S-1-5-32-544", "*S-1-5-32-545",
            "*S-1-3-4",
        ],
    )
    for command in commands:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=20,
        )
        if completed.returncode != 0:
            _fail("STORAGE_CAPABILITY_BLOCKED", "owner-only Windows DACL cannot be set")


def _windows_acl_sids(path: Path) -> tuple[str, frozenset[str]]:
    import ctypes
    from ctypes import wintypes

    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    result = ctypes.windll.advapi32.GetNamedSecurityInfoW(
        str(path), 1, 0x1 | 0x4,
        ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(descriptor),
    )
    if result != 0 or not owner.value or not dacl.value:
        _fail("STORAGE_CAPABILITY_BLOCKED", "Windows owner or DACL is unavailable")

    def sid_text(pointer: int) -> str:
        value = wintypes.LPWSTR()
        if not ctypes.windll.advapi32.ConvertSidToStringSidW(
            ctypes.c_void_p(pointer), ctypes.byref(value)
        ):
            _fail("STORAGE_CAPABILITY_BLOCKED", "Windows SID cannot be decoded")
        try:
            return value.value
        finally:
            ctypes.windll.kernel32.LocalFree(value)

    class AclSizeInformation(ctypes.Structure):
        _fields_ = [
            ("AceCount", wintypes.DWORD),
            ("AclBytesInUse", wintypes.DWORD),
            ("AclBytesFree", wintypes.DWORD),
        ]

    try:
        owner_sid = sid_text(owner.value)
        info = AclSizeInformation()
        if not ctypes.windll.advapi32.GetAclInformation(
            dacl, ctypes.byref(info), ctypes.sizeof(info), 2
        ):
            _fail("STORAGE_CAPABILITY_BLOCKED", "Windows DACL cannot be inspected")
        allowed: set[str] = set()
        for index in range(info.AceCount):
            ace = ctypes.c_void_p()
            if not ctypes.windll.advapi32.GetAce(dacl, index, ctypes.byref(ace)):
                _fail("STORAGE_CAPABILITY_BLOCKED", "Windows ACE cannot be inspected")
            ace_type = ctypes.c_ubyte.from_address(ace.value).value
            if ace_type == 0:
                allowed.add(sid_text(ace.value + 8))
            elif ace_type not in {1}:
                _fail("STORAGE_CAPABILITY_BLOCKED", "unsupported Windows ACE type")
        return owner_sid, frozenset(allowed)
    finally:
        ctypes.windll.kernel32.LocalFree(descriptor)


def _verify_security(path: Path, *, file: bool = False) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        _io_fail(exc, f"cannot inspect {path.name}")
    if _is_reparse(info):
        _fail("STORAGE_REPARSE", f"reparse point is forbidden: {path.name}")
    if (file and not stat.S_ISREG(info.st_mode)) or (
        not file and not stat.S_ISDIR(info.st_mode)
    ):
        _fail("STORAGE_LAYOUT", f"storage node has the wrong type: {path.name}")
    if os.name == "nt":
        current = _current_windows_sid()
        owner, allowed = _windows_acl_sids(path)
        if owner != current or current not in allowed or "S-1-1-0" in allowed:
            _fail("STORAGE_DACL", "Windows storage owner/DACL is not service-only")
        if not allowed <= {current, "S-1-5-18"}:
            _fail("STORAGE_DACL", "Windows storage grants an unapproved principal")
    else:
        expected = 0o600 if file else 0o700
        if stat.S_IMODE(info.st_mode) != expected or info.st_uid != os.geteuid():
            _fail("STORAGE_PERMISSION", "POSIX storage owner/mode is not private")


@dataclass(frozen=True, slots=True)
class StoredObjectV4:
    digest: DigestV4
    size_bytes: int


@dataclass(frozen=True, slots=True)
class LocalStorageProbeV4:
    """Test/local storage evidence; never a production StorageCapabilityV4."""

    platform: str
    quota_bytes: int
    available_bytes: int
    object_digest: DigestV4
    object_bytes: int
    recovered_entries: int
    checks: tuple[str, ...]
    probe_digest: DigestV4

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "jc/local-storage-probe/1.0",
            "scope": "test-local",
            "production_allowed": False,
            "target_provider_claimed": False,
            "platform": self.platform,
            "namespace": NAMESPACE_V4,
            "quota_bytes": self.quota_bytes,
            "available_bytes": self.available_bytes,
            "object_digest": str(self.object_digest),
            "object_bytes": self.object_bytes,
            "recovered_entries": self.recovered_entries,
            "checks": list(self.checks),
            "probe_digest": str(self.probe_digest),
        }


class V4TransactionStore:
    """One-writer, crash-recoverable V4 object store under a fixed namespace."""

    def __init__(self, state_root: Path, *, quota_bytes: int, create: bool = False) -> None:
        if type(quota_bytes) is not int or quota_bytes <= 0:
            _fail("STORAGE_QUOTA", "quota_bytes must be a positive integer")
        self.state_root = _safe_root(state_root)
        self.root = self.state_root / NAMESPACE_V4
        self.quota_bytes = quota_bytes
        if create:
            self._create()
        self._open()

    @classmethod
    def create(cls, state_root: Path, *, quota_bytes: int) -> V4TransactionStore:
        return cls(state_root, quota_bytes=quota_bytes, create=True)

    @classmethod
    def open(cls, state_root: Path, *, quota_bytes: int) -> V4TransactionStore:
        return cls(state_root, quota_bytes=quota_bytes)

    def _create(self) -> None:
        _mkdir(self.state_root)
        if self.root.exists() or self.root.is_symlink():
            _fail("STORAGE_ALREADY_EXISTS", "V4 namespace already exists")
        _mkdir(self.root)
        if os.name == "nt":
            _harden_windows(self.root)
        for name in ("locks", "staging", "objects", "quarantine"):
            _mkdir(self.root / name)
            if os.name == "nt":
                _harden_windows(self.root / name)
        marker = canonical_bytes({"schema_version": ROOT_SCHEMA, "namespace": NAMESPACE_V4})
        descriptor = _open_exact(self.root / ROOT_MARKER, write=True, create=True)
        try:
            _write_all(descriptor, marker)
            _flush_file(descriptor)
        finally:
            os.close(descriptor)
        if os.name == "nt":
            _harden_windows(self.root / ROOT_MARKER)
        lock = _open_exact(self.root / "locks" / "writer.lock", write=True, create=True)
        try:
            _write_all(lock, b"\0")
            _flush_file(lock)
        finally:
            os.close(lock)
        if os.name == "nt":
            _harden_windows(self.root / "locks" / "writer.lock")
        _flush_directory(self.root / "locks")
        _flush_directory(self.root)
        _flush_directory(self.state_root)

    def _open(self) -> None:
        if not self.root.is_dir():
            _fail("STORAGE_NOT_FOUND", "V4 namespace does not exist")
        _verify_security(self.root)
        expected = canonical_bytes({"schema_version": ROOT_SCHEMA, "namespace": NAMESPACE_V4})
        marker_path = self.root / ROOT_MARKER
        marker = self._read_path(marker_path, expected_digest=None)
        if marker != expected:
            _fail("STORAGE_NAMESPACE", "storage marker is not the V4 namespace")
        self._directory_ids = {
            name: _file_id(self.root / name)
            for name in ("locks", "staging", "objects", "quarantine")
        }
        for name in self._directory_ids:
            _verify_security(self.root / name)
        lock_path = self.root / "locks" / "writer.lock"
        _verify_security(lock_path, file=True)
        self._marker_id = _file_id(marker_path)
        self._lock_file_id = _file_id(lock_path)
        self._containment_ids = {
            path: _file_id(path)
            for path in self._containment_chain()
        }
        self._verify_layout()

    def _containment_chain(self) -> tuple[Path, ...]:
        chain: list[Path] = []
        current = Path(self.root.anchor)
        for part in self.root.parts[1:]:
            current /= part
            chain.append(current)
        return tuple(chain)

    def _verify_layout(self) -> None:
        for path, expected in self._containment_ids.items():
            if _file_id(path) != expected:
                _fail("STORAGE_TOCTOU", "storage containment identity changed")
        _verify_security(self.root)
        marker_path = self.root / ROOT_MARKER
        if _file_id(marker_path) != self._marker_id or self._read_path(
            marker_path, expected_digest=None,
        ) != canonical_bytes({"schema_version": ROOT_SCHEMA, "namespace": NAMESPACE_V4}):
            _fail("STORAGE_NAMESPACE", "storage marker changed after open")
        lock_path = self.root / "locks" / "writer.lock"
        if _file_id(lock_path) != self._lock_file_id:
            _fail("STORAGE_TOCTOU", "writer lock identity changed")
        _verify_security(lock_path, file=True)
        for name, expected in self._directory_ids.items():
            path = self.root / name
            if _file_id(path) != expected:
                _fail("STORAGE_TOCTOU", f"storage directory identity changed: {name}")
            _verify_security(path)

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self._verify_layout()
        path = self.root / "locks" / "writer.lock"
        _verify_security(path, file=True)
        descriptor = _open_exact(path, write=True)
        try:
            if os.name == "nt":
                import msvcrt

                deadline = time.monotonic() + 30
                while True:
                    try:
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            _fail("STORAGE_LOCK_TIMEOUT", "cross-process lock timed out")
                        time.sleep(0.01)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX)
            self._verify_layout()
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                try:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _object_path(self, digest: DigestV4, *, create_shard: bool) -> Path:
        if type(digest) is not DigestV4:
            _fail("STORAGE_DIGEST", "object key must be DigestV4")
        shard = self.root / "objects" / digest.hex[:2]
        if not shard.exists() and not shard.is_symlink():
            if not create_shard:
                return shard / f"{digest.hex}.blob"
            _mkdir(shard)
            if os.name == "nt":
                _harden_windows(shard)
            _flush_directory(self.root / "objects")
        _verify_security(shard)
        return shard / f"{digest.hex}.blob"

    def _read_path(self, path: Path, *, expected_digest: DigestV4 | None) -> bytes:
        _verify_security(path, file=True)
        parent_before = _file_id(path.parent)
        descriptor = _open_exact(path, write=False)
        try:
            before = os.fstat(descriptor)
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 65_536)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            after.st_dev, after.st_ino, after.st_size
        ) or _file_id(path.parent) != parent_before:
            _fail("STORAGE_TOCTOU", "object or parent identity changed during read")
        payload = b"".join(chunks)
        if expected_digest is not None and DigestV4.from_bytes(payload) != expected_digest:
            _fail("STORAGE_COLLISION", "stored bytes do not match the content digest")
        return payload

    def _usage(self) -> int:
        total = 0
        for shard in (self.root / "objects").iterdir():
            info = shard.lstat()
            if not stat.S_ISDIR(info.st_mode) or _is_reparse(info):
                _fail("STORAGE_LAYOUT", "object shard is unsafe")
            _verify_security(shard)
            for path in shard.iterdir():
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or _is_reparse(info):
                    _fail("STORAGE_LAYOUT", "object entry is unsafe")
                _verify_security(path, file=True)
                total += info.st_size
        return total

    def _recover_locked(self) -> int:
        staging = self.root / "staging"
        quarantine = self.root / "quarantine"
        recovered = 0
        for path in sorted(staging.iterdir(), key=lambda item: item.name):
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or _is_reparse(info):
                _fail("STORAGE_LAYOUT", "staging entry is unsafe")
            _verify_security(path, file=True)
            target = quarantine / f"{path.name}.{uuid.uuid4().hex}.orphan"
            _move_write_through(path, target)
            recovered += 1
        if recovered:
            _flush_directory(staging)
            _flush_directory(quarantine)
        return recovered

    def recover(self) -> int:
        with self._lock():
            return self._recover_locked()

    def put_bytes(self, kind: str, content: bytes) -> StoredObjectV4:
        _identifier(kind, "kind")
        if type(content) is not bytes:
            _fail("STORAGE_CONTENT", "content must be immutable bytes")
        digest = DigestV4.from_bytes(content)
        with self._lock():
            self._recover_locked()
            target = self._object_path(digest, create_shard=True)
            if target.exists() or target.is_symlink():
                existing = self._read_path(target, expected_digest=digest)
                if existing != content:
                    _fail("STORAGE_COLLISION", "digest already binds different bytes")
                return StoredObjectV4(digest, len(content))
            if self._usage() + len(content) > self.quota_bytes:
                _fail("STORAGE_QUOTA", "V4 state quota would be exceeded")

            stem = f"{kind}.{os.getpid()}.{uuid.uuid4().hex}"
            stage = self.root / "staging" / f"{stem}.stage"
            lease = self.root / "staging" / f"{stem}.lease"
            lease_payload = canonical_bytes({
                "schema_version": "jc/storage-lease/1.0",
                "owner_pid": os.getpid(),
                "object_digest": str(digest),
            })
            lease_descriptor = _open_exact(lease, write=True, create=True)
            try:
                _write_all(lease_descriptor, lease_payload)
                _flush_file(lease_descriptor)
            finally:
                os.close(lease_descriptor)
            if os.name == "nt":
                _harden_windows(lease)
            _checkpoint("lease-durable")

            stage_descriptor = _open_exact(stage, write=True, create=True)
            try:
                if os.name == "nt":
                    _harden_windows(stage)
                _write_all(stage_descriptor, content)
                _checkpoint("stage-written")
                _flush_file(stage_descriptor)
            finally:
                os.close(stage_descriptor)
            _checkpoint("stage-durable")
            if self._read_path(stage, expected_digest=digest) != content:
                _fail("STORAGE_COLLISION", "staging verification differs")

            parent_id = _file_id(target.parent)
            _move_write_through(stage, target)
            _checkpoint("object-published")
            if _file_id(target.parent) != parent_id:
                _fail("STORAGE_TOCTOU", "object parent identity changed during publish")
            _flush_directory(target.parent)
            _checkpoint("directory-durable")
            self._read_path(target, expected_digest=digest)
            try:
                lease.unlink()
            except OSError as exc:
                _io_fail(exc, "lease cleanup failed")
            _flush_directory(self.root / "staging")
            return StoredObjectV4(digest, len(content))

    def get_bytes(self, digest: DigestV4) -> bytes:
        with self._lock():
            target = self._object_path(digest, create_shard=False)
            if not target.exists() and not target.is_symlink():
                _fail("STORAGE_NOT_FOUND", "content digest is absent")
            return self._read_path(target, expected_digest=digest)


def probe_local_storage(state_root: Path, *, quota_bytes: int) -> LocalStorageProbeV4:
    """Exercise one fresh local store without claiming a target production provider."""

    payload = b"juris-calculus-v4-local-storage-probe"
    if type(quota_bytes) is not int or quota_bytes < len(payload):
        _fail("STORAGE_QUOTA", "local probe quota is smaller than its fixed payload")
    root = _safe_root(state_root)
    existing = root.parent
    while not existing.exists():
        existing = existing.parent
    available = shutil.disk_usage(existing).free
    if available < quota_bytes:
        _fail("STORAGE_CAPACITY", "local probe quota exceeds available capacity")

    store = V4TransactionStore.create(root, quota_bytes=quota_bytes)
    stored = store.put_bytes("local-probe", payload)
    if store.get_bytes(stored.digest) != payload:
        _fail("STORAGE_COLLISION", "local probe round-trip differs")
    reopened = V4TransactionStore.open(root, quota_bytes=quota_bytes)
    if reopened.get_bytes(stored.digest) != payload:
        _fail("STORAGE_COLLISION", "local probe reopen differs")
    recovered = reopened.recover()
    body = {
        "schema_version": "jc/local-storage-probe/1.0",
        "scope": "test-local",
        "production_allowed": False,
        "target_provider_claimed": False,
        "platform": "windows" if os.name == "nt" else "posix",
        "namespace": NAMESPACE_V4,
        "quota_bytes": quota_bytes,
        "available_bytes": available,
        "object_digest": str(stored.digest),
        "object_bytes": stored.size_bytes,
        "recovered_entries": recovered,
        "checks": [
            "content-addressed-roundtrip",
            "private-layout",
            "reopen-roundtrip",
            "stale-recovery-scan",
        ],
    }
    return LocalStorageProbeV4(
        platform=body["platform"],
        quota_bytes=quota_bytes,
        available_bytes=available,
        object_digest=stored.digest,
        object_bytes=stored.size_bytes,
        recovered_entries=recovered,
        checks=tuple(body["checks"]),
        probe_digest=DigestV4.from_bytes(canonical_bytes(body)),
    )


__all__ = [
    "LocalStorageProbeV4",
    "NAMESPACE_V4",
    "StoredObjectV4",
    "StorageV4Error",
    "V4TransactionStore",
    "probe_local_storage",
]
