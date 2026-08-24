from __future__ import annotations

from base64 import b64encode

import builtins
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import glob
import http.client
import io
import os
from pathlib import Path
import socket
import subprocess
from typing import Callable, TypeVar
import urllib.request
from unittest.mock import patch

import pytest

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import DigestV4, digest_value
from compiler_core.contracts import (
    ArtifactHandleV4,
    CaseArtifactV4,
    CaseInputBundleV4,
    CanonicalTimeV4,
    ContentRefV4,
    ContractV4Error,
    DEFAULT_RESOURCE_LIMITS_V4,
    HARD_MAX_RESOURCE_LIMITS_V4,
    SignatureEnvelopeV4,
)


_T = TypeVar("_T")
_EXTERNAL_IO_TARGETS: tuple[tuple[object, str], ...] = (
    (builtins, "open"),
    (io, "open"),
    (os, "open"),
    (os, "stat"),
    (os, "lstat"),
    (os, "readlink"),
    (os, "fspath"),
    (os, "listdir"),
    (os, "scandir"),
    (Path, "open"),
    (Path, "read_bytes"),
    (Path, "read_text"),
    (Path, "stat"),
    (Path, "resolve"),
    (Path, "readlink"),
    (Path, "is_symlink"),
    (Path, "glob"),
    (Path, "rglob"),
    (Path, "iterdir"),
    (glob, "glob"),
    (glob, "iglob"),
    (socket, "socket"),
    (socket, "create_connection"),
    (socket, "getaddrinfo"),
    (urllib.request, "urlopen"),
    (http.client, "HTTPConnection"),
    (http.client, "HTTPSConnection"),
    (subprocess, "Popen"),
    (subprocess, "run"),
)
if hasattr(Path, "is_junction"):
    _EXTERNAL_IO_TARGETS += ((Path, "is_junction"),)


def _call_with_zero_external_io(action: Callable[[], _T]) -> _T:
    calls: list[str] = []

    def blocked(owner: object, name: str) -> Callable[..., object]:
        def fail(*_args: object, **_kwargs: object) -> object:
            calls.append(f"{getattr(owner, '__name__', type(owner).__name__)}.{name}")
            raise AssertionError("artifact resolver attempted external I/O")

        return fail

    result: _T | None = None
    error: Exception | None = None
    with ExitStack() as stack:
        for owner, name in _EXTERNAL_IO_TARGETS:
            stack.enter_context(patch.object(owner, name, blocked(owner, name)))
        try:
            result = action()
        except Exception as caught:  # re-raised after tripwires are restored
            error = caught
    assert calls == [], f"unexpected external I/O calls: {calls}"
    if error is not None:
        raise error
    return result  # type: ignore[return-value]


def _ref(content: bytes, kind: str = "opaque-bytes") -> ContentRefV4:
    return ContentRefV4(kind=kind, digest=DigestV4.from_bytes(content))


def _one_nibble_digest_change(digest: DigestV4) -> DigestV4:
    replacement = "0" if digest[-1] != "0" else "1"
    return DigestV4(f"{digest[:-1]}{replacement}")


def _resolver(content: bytes = b"bound artifact bytes") -> tuple[ArtifactResolverV4, ContentRefV4]:
    resolver = ArtifactResolverV4(max_artifact_bytes=1024)
    content_ref = _ref(content)
    resolver.register_bytes(
        artifact_id="artifact-1",
        content_ref=content_ref,
        artifact_kind="source-bundle",
        media_type="application/json",
        scope="formal-run",
        content=content,
    )
    return resolver, content_ref


def _handle(
    content_ref: ContentRefV4,
    *,
    size_bytes: int,
    max_bytes: int,
    artifact_id: str = "artifact-1",
    scope: str = "formal-run",
    media_type: str = "application/json",
    artifact_kind: str = "source-bundle",
    status: str = "PASS",
) -> ArtifactHandleV4:
    run_identity_ref = ContentRefV4(
        kind="run-identity", digest=DigestV4.from_bytes(b"run-identity")
    )
    expires_at = CanonicalTimeV4("2099-12-31T23:59:59Z")
    body = {
        "artifact_id": artifact_id,
        "kind": artifact_kind,
        "content_ref": content_ref.to_dict(),
        "run_identity_ref": run_identity_ref.to_dict(),
        "scope": scope,
        "media_type": media_type,
        "size_bytes": size_bytes,
        "expires_at": expires_at.to_dict(),
        "max_bytes": max_bytes,
    }
    signature = SignatureEnvelopeV4(
        algorithm="Ed25519",
        key_id="unverified-key",
        issuer="caller",
        role="caller",
        scope=scope,
        kind=artifact_kind,
        schema_version="jc/4.0",
        subject_digest=content_ref.digest,
        run_identity_ref=run_identity_ref,
        status=status,
        issued_at=CanonicalTimeV4("2026-08-22T08:00:00Z"),
        expires_at=expires_at,
        nonce="nonce-1",
        evidence_refs=(content_ref,),
        payload_digest=digest_value(body),
        policy_digest=DigestV4.from_bytes(b"unverified-policy"),
        revocation_ref=None,
        signature="caller-controlled-signature",
    )
    return ArtifactHandleV4(
        artifact_id=artifact_id,
        kind=artifact_kind,
        content_ref=content_ref,
        run_identity_ref=run_identity_ref,
        scope=scope,
        media_type=media_type,
        size_bytes=size_bytes,
        expires_at=expires_at,
        max_bytes=max_bytes,
        signature=signature,
    )


def _error_without_external_io(callable_: Callable[[], object]) -> ContractV4Error:
    try:
        _call_with_zero_external_io(callable_)
    except ContractV4Error as caught:
        return caught
    raise AssertionError("expected ContractV4Error")


def _error_code(callable_: Callable[[], object]) -> str:
    return _error_without_external_io(callable_).code


def test_caller_claimed_pass_cannot_create_trust() -> None:
    resolver, content_ref = _resolver()
    caller_claim = {**content_ref.to_dict(), "status": "PASS", "trusted": True}

    assert _error_code(lambda: resolver.resolve_content(
        caller_claim,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=1024,
    )) == "ARTIFACT_REFERENCE_TYPE"
    resolved = _call_with_zero_external_io(
        lambda: resolver.resolve_content(
            content_ref,
            expected_artifact_kind="source-bundle",
            expected_media_type="application/json",
            expected_scope="formal-run",
            max_bytes=1024,
        )
    )
    assert type(resolved) is bytes
    assert resolved == b"bound artifact bytes"
    assert not hasattr(resolved, "trusted")


def test_raw_dict_string_and_pathlike_refs_are_rejected_before_coercion() -> None:
    class PoisonPathLike:
        calls = 0

        def __fspath__(self) -> str:
            self.calls += 1
            raise AssertionError("resolver attempted filesystem coercion")

    resolver, content_ref = _resolver()
    poison = PoisonPathLike()
    raw_refs = (
        content_ref.to_dict(),
        "artifact-1",
        Path("relative") / "artifact.bin",
        poison,
    )
    for raw_ref in raw_refs:
        assert _error_code(lambda raw_ref=raw_ref: resolver.resolve_content(
            raw_ref,
            expected_artifact_kind="source-bundle",
            expected_media_type="application/json",
            expected_scope="formal-run",
            max_bytes=1024,
        )) == "ARTIFACT_REFERENCE_TYPE"
    assert poison.calls == 0


@pytest.mark.parametrize("path_canary", [
    r"C:\CANARY_JC_SECRET\artifact.bin",
    r"C:CANARY_JC_SECRET\artifact.bin",
    r"\CANARY_JC_SECRET\artifact.bin",
    "/CANARY_JC_SECRET/artifact.bin",
    r".\CANARY_JC_SECRET\artifact.bin",
    r"..\CANARY_JC_SECRET\artifact.bin",
    "../CANARY_JC_SECRET/artifact.bin",
    r"\\CANARY_JC_SECRET\share\artifact.bin",
    "//CANARY_JC_SECRET/share/artifact.bin",
    r"\\?\C:\CANARY_JC_SECRET\artifact.bin",
    r"\\?\UNC\CANARY_JC_SECRET\share\artifact.bin",
    r"\\.\PhysicalDrive0\CANARY_JC_SECRET",
    r"\\.\GLOBALROOT\Device\CANARY_JC_SECRET",
    r"\\.\PIPE\CANARY_JC_SECRET",
    r"\\CANARY_JC_SECRET\pipe\artifact",
    "file:///CANARY_JC_SECRET/artifact.bin",
    "file://CANARY_JC_SECRET/share/artifact.bin",
    "http://CANARY_JC_SECRET.invalid/artifact",
    "https://CANARY_JC_SECRET.invalid/artifact",
])
def test_arbitrary_local_unc_and_device_paths_are_rejected(path_canary: str) -> None:
    resolver, _ = _resolver()
    caught = _error_without_external_io(lambda: resolver.resolve_content(
        path_canary,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=1024,
    ))
    assert caught.code == "ARTIFACT_REFERENCE_TYPE"
    assert "CANARY_JC_SECRET" not in str(caught)


def test_pathlike_symlink_or_junction_reference_is_not_coerced() -> None:
    class PoisonPath:
        calls = 0

        def __fspath__(self) -> str:
            self.calls += 1
            raise AssertionError("resolver attempted filesystem coercion")

    resolver, _ = _resolver()
    poison = PoisonPath()
    assert _error_code(lambda: resolver.resolve_content(
        poison,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=1024,
    )) == "ARTIFACT_REFERENCE_TYPE"
    assert poison.calls == 0


def test_unknown_near_digest_is_exact_miss_without_fuzzy_or_external_search() -> None:
    resolver, content_ref = _resolver()
    unknown_ref = ContentRefV4(
        kind=content_ref.kind,
        digest=_one_nibble_digest_change(content_ref.digest),
    )
    assert _error_code(lambda: resolver.resolve_content(
        unknown_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=1024,
    )) == "ARTIFACT_NOT_FOUND"


def test_typed_content_ref_path_canary_is_rejected_without_echo_or_io() -> None:
    resolver, content_ref = _resolver()
    path_canary = r"\\CANARY_JC_SECRET\share\artifact.bin"
    typed_ref = ContentRefV4(kind=path_canary, digest=content_ref.digest)
    caught = _error_without_external_io(lambda: resolver.resolve_content(
        typed_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=1024,
    ))
    assert caught.code == "ARTIFACT_ID_GRAMMAR"
    assert "CANARY_JC_SECRET" not in str(caught)


@pytest.mark.parametrize(
    ("field", "expected_code"),
    (
        ("artifact_id", "ARTIFACT_ID_GRAMMAR"),
        ("kind", "ARTIFACT_ID_GRAMMAR"),
        ("scope", "ARTIFACT_ID_GRAMMAR"),
        ("media_type", "ARTIFACT_MEDIA_TYPE"),
        ("content_ref_kind", "ARTIFACT_ID_GRAMMAR"),
    ),
)
def test_typed_handle_path_fields_are_rejected_without_echo_or_io(
    field: str, expected_code: str,
) -> None:
    content = b"0123456789"
    resolver, content_ref = _resolver(content)
    path_canary = r"\\CANARY_JC_SECRET\share\artifact.bin"
    handle_ref = content_ref
    handle_kwargs: dict[str, str] = {}
    if field == "content_ref_kind":
        handle_ref = ContentRefV4(kind=path_canary, digest=content_ref.digest)
    elif field == "kind":
        handle_kwargs["artifact_kind"] = path_canary
    else:
        handle_kwargs[field] = path_canary
    handle = _handle(
        handle_ref,
        size_bytes=len(content),
        max_bytes=len(content),
        **handle_kwargs,
    )
    caught = _error_without_external_io(lambda: resolver.resolve_handle(
        handle,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        offset=0,
        length=1,
    ))
    assert caught.code == expected_code
    assert "CANARY_JC_SECRET" not in str(caught)


def test_metadata_and_size_fail_before_content_digest_access() -> None:
    resolver, content_ref = _resolver()
    calls = (
        ("ARTIFACT_KIND_MISMATCH", {"expected_artifact_kind": "rule-pack"}),
        ("ARTIFACT_MEDIA_TYPE_MISMATCH", {"expected_media_type": "text/plain"}),
        ("ARTIFACT_SCOPE_MISMATCH", {"expected_scope": "other-run"}),
        ("ARTIFACT_TOO_LARGE", {"max_bytes": 4}),
    )
    baseline = {
        "expected_artifact_kind": "source-bundle",
        "expected_media_type": "application/json",
        "expected_scope": "formal-run",
        "max_bytes": 1024,
    }
    with patch.object(DigestV4, "from_bytes", side_effect=AssertionError("content read")):
        for expected_code, changed in calls:
            kwargs = {**baseline, **changed}
            assert _error_code(
                lambda kwargs=kwargs: resolver.resolve_content(content_ref, **kwargs)
            ) == expected_code


def test_registration_checks_bound_and_digest_before_mutating_registry() -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=4)
    oversized = b"12345"
    valid_ref = _ref(b"1234")
    with patch.object(DigestV4, "from_bytes", side_effect=AssertionError("hashed oversize")):
        assert _error_code(lambda: resolver.register_bytes(
            artifact_id="artifact-1",
            content_ref=valid_ref,
            artifact_kind="source-bundle",
            media_type="application/json",
            scope="formal-run",
            content=oversized,
        )) == "ARTIFACT_TOO_LARGE"
    assert _error_code(lambda: resolver.resolve_content(
        valid_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=4,
    )) == "ARTIFACT_NOT_FOUND"


def test_public_single_bit_mutation_and_stored_corruption_are_rejected() -> None:
    content = b"0123456789"
    resolver, content_ref = _resolver(content)
    mutated = bytes((content[0] ^ 0x01,)) + content[1:]
    assert _error_code(lambda: resolver.register_bytes(
        artifact_id="artifact-mutated",
        content_ref=content_ref,
        artifact_kind="source-bundle",
        media_type="application/json",
        scope="formal-run",
        content=mutated,
    )) == "ARTIFACT_DIGEST_MISMATCH"
    assert _call_with_zero_external_io(lambda: resolver.resolve_content(
        content_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=1024,
    )) == content

    record = resolver._by_id["artifact-1"]
    object.__setattr__(record, "content", mutated)
    assert _error_code(lambda: resolver.resolve_content(
        content_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=1024,
    )) == "ARTIFACT_DIGEST_MISMATCH"


def test_handle_declared_size_mismatch_is_rejected() -> None:
    content = b"0123456789"
    clean_resolver, clean_ref = _resolver(content)

    handle = _handle(clean_ref, size_bytes=len(content) + 1, max_bytes=len(content) + 1)
    assert _error_code(lambda: clean_resolver.resolve_handle(
        handle,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        offset=0,
        length=1,
    )) == "ARTIFACT_SIZE_MISMATCH"


def test_handle_scope_media_kind_and_range_are_exact_before_read() -> None:
    content = b"0123456789"
    resolver, content_ref = _resolver(content)
    handle = _handle(content_ref, size_bytes=len(content), max_bytes=len(content))
    invalid = (
        ("ARTIFACT_KIND_MISMATCH", {"expected_artifact_kind": "rule-pack"}),
        ("ARTIFACT_MEDIA_TYPE_MISMATCH", {"expected_media_type": "text/plain"}),
        ("ARTIFACT_SCOPE_MISMATCH", {"expected_scope": "other-run"}),
        ("ARTIFACT_RANGE", {"offset": len(content), "length": 1}),
    )
    baseline = {
        "expected_artifact_kind": "source-bundle",
        "expected_media_type": "application/json",
        "expected_scope": "formal-run",
        "offset": 2,
        "length": 4,
    }
    with patch.object(DigestV4, "from_bytes", side_effect=AssertionError("content read")):
        for expected_code, changed in invalid:
            kwargs = {**baseline, **changed}
            assert _error_code(
                lambda kwargs=kwargs: resolver.resolve_handle(handle, **kwargs)
            ) == expected_code
    assert _call_with_zero_external_io(
        lambda: resolver.resolve_handle(handle, **baseline)
    ) == b"2345"


@pytest.mark.parametrize(
    ("field", "changed_value", "expected_code"),
    (
        ("kind", "rule-pack", "ARTIFACT_KIND_MISMATCH"),
        ("media_type", "text/plain", "ARTIFACT_MEDIA_TYPE_MISMATCH"),
        ("scope", "other-run", "ARTIFACT_SCOPE_MISMATCH"),
        ("artifact_id", "artifact-2", "ARTIFACT_ID_MISMATCH"),
    ),
)
def test_handle_fields_cannot_disagree_with_stored_record(
    field: str, changed_value: str, expected_code: str,
) -> None:
    content = b"0123456789"
    resolver, content_ref = _resolver(content)
    handle_kwargs = {
        "artifact_id": "artifact-1",
        "artifact_kind": "source-bundle",
        "media_type": "application/json",
        "scope": "formal-run",
    }
    expected = {
        "expected_artifact_kind": "source-bundle",
        "expected_media_type": "application/json",
        "expected_scope": "formal-run",
    }
    handle_key = "artifact_kind" if field == "kind" else field
    handle_kwargs[handle_key] = changed_value
    if field == "kind":
        expected["expected_artifact_kind"] = changed_value
    elif field == "media_type":
        expected["expected_media_type"] = changed_value
    elif field == "scope":
        expected["expected_scope"] = changed_value
    handle = _handle(
        content_ref,
        size_bytes=len(content),
        max_bytes=len(content),
        **handle_kwargs,
    )
    assert _error_code(lambda: resolver.resolve_handle(
        handle,
        **expected,
        offset=0,
        length=1,
    )) == expected_code


def test_handle_content_ref_cannot_select_a_different_stored_record() -> None:
    first = b"first-record"
    second = b"second-record"
    resolver, _ = _resolver(first)
    second_ref = _ref(second)
    resolver.register_bytes(
        artifact_id="artifact-2",
        content_ref=second_ref,
        artifact_kind="source-bundle",
        media_type="application/json",
        scope="formal-run",
        content=second,
    )
    handle = _handle(
        second_ref,
        artifact_id="artifact-1",
        size_bytes=len(second),
        max_bytes=len(second),
    )
    assert _error_code(lambda: resolver.resolve_handle(
        handle,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        offset=0,
        length=1,
    )) == "ARTIFACT_ID_MISMATCH"


@pytest.mark.parametrize(
    ("offset", "length", "expected_code"),
    (
        (-1, 1, "ARTIFACT_BOUNDS"),
        (True, 1, "ARTIFACT_BOUNDS"),
        (1.0, 1, "ARTIFACT_BOUNDS"),
        (0, 0, "ARTIFACT_RANGE"),
        (0, -1, "ARTIFACT_RANGE"),
        (0, True, "ARTIFACT_RANGE"),
        (0, 1.0, "ARTIFACT_RANGE"),
    ),
)
def test_handle_range_parameters_reject_negative_bool_and_float(
    offset: object, length: object, expected_code: str,
) -> None:
    content = b"0123456789"
    resolver, content_ref = _resolver(content)
    handle = _handle(content_ref, size_bytes=len(content), max_bytes=len(content))
    assert _error_code(lambda: resolver.resolve_handle(
        handle,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        offset=offset,
        length=length,
    )) == expected_code


@pytest.mark.parametrize("invalid_max_bytes", (True, 1.0, -1, 11))
def test_handle_max_bytes_rejects_forged_bool_float_and_invalid_bounds(
    invalid_max_bytes: object,
) -> None:
    content = b"0123456789"
    resolver, content_ref = _resolver(content)
    handle = _handle(content_ref, size_bytes=len(content), max_bytes=len(content))
    object.__setattr__(handle, "max_bytes", invalid_max_bytes)
    assert _error_code(lambda: resolver.resolve_handle(
        handle,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        offset=0,
        length=1,
    )) == "ARTIFACT_BOUNDS"


def test_handle_max_bytes_exact_boundary_passes_and_one_less_rejects() -> None:
    content = b"0123456789"
    resolver, content_ref = _resolver(content)
    exact = _handle(content_ref, size_bytes=len(content), max_bytes=6)
    assert _call_with_zero_external_io(lambda: resolver.resolve_handle(
        exact,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        offset=2,
        length=4,
    )) == b"2345"
    narrow = _handle(content_ref, size_bytes=len(content), max_bytes=5)
    assert _error_code(lambda: resolver.resolve_handle(
        narrow,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        offset=2,
        length=4,
    )) == "ARTIFACT_RANGE"


def test_resolve_handle_page_length_policy_exact_and_limit_plus_one() -> None:
    default_page = DEFAULT_RESOURCE_LIMITS_V4["artifact_page_bytes"]
    hard_page = HARD_MAX_RESOURCE_LIMITS_V4["artifact_page_bytes"]
    page_content = (bytes(range(256)) * ((hard_page + 256) // 256))[:hard_page + 1]
    page_ref = _ref(page_content)
    default_resolver = ArtifactResolverV4(max_artifact_bytes=len(page_content))
    hard_resolver = ArtifactResolverV4(
        max_artifact_bytes=len(page_content), artifact_page_bytes=hard_page
    )
    for page_resolver in (default_resolver, hard_resolver):
        page_resolver.register_bytes(
            artifact_id="page-artifact",
            content_ref=page_ref,
            artifact_kind="source-bundle",
            media_type="application/json",
            scope="formal-run",
            content=page_content,
        )
    page_handle = _handle(
        page_ref,
        artifact_id="page-artifact",
        size_bytes=len(page_content),
        max_bytes=len(page_content),
    )
    for page_resolver, page_limit in (
        (default_resolver, default_page),
        (hard_resolver, hard_page),
    ):
        resolved = _call_with_zero_external_io(lambda: page_resolver.resolve_handle(
            page_handle,
            expected_artifact_kind="source-bundle",
            expected_media_type="application/json",
            expected_scope="formal-run",
            offset=1,
            length=page_limit,
        ))
        assert resolved == page_content[1:1 + page_limit]
        assert _error_code(lambda: page_resolver.resolve_handle(
            page_handle,
            expected_artifact_kind="source-bundle",
            expected_media_type="application/json",
            expected_scope="formal-run",
            offset=1,
            length=page_limit + 1,
        )) == "ARTIFACT_PAGE_LIMIT"
    assert _error_code(lambda: ArtifactResolverV4(
        max_artifact_bytes=hard_page,
        artifact_page_bytes=hard_page + 1,
    )) == "ARTIFACT_PAGE_LIMIT"


@pytest.mark.parametrize(
    ("changed", "expected_code"),
    (
        ({"artifact_id": "artifact-2"}, "ARTIFACT_REFERENCE_COLLISION"),
        ({"artifact_kind": "rule-pack"}, "ARTIFACT_METADATA_COLLISION"),
        ({"media_type": "text/plain"}, "ARTIFACT_METADATA_COLLISION"),
        ({"scope": "other-run"}, "ARTIFACT_METADATA_COLLISION"),
    ),
)
def test_same_ref_identity_or_metadata_rebinding_preserves_original(
    changed: dict[str, str], expected_code: str,
) -> None:
    content = b"immutable-record"
    resolver, content_ref = _resolver(content)
    registration = {
        "artifact_id": "artifact-1",
        "artifact_kind": "source-bundle",
        "media_type": "application/json",
        "scope": "formal-run",
    }
    registration.update(changed)
    assert _error_code(lambda: resolver.register_bytes(
        content_ref=content_ref,
        content=content,
        **registration,
    )) == expected_code
    assert _call_with_zero_external_io(lambda: resolver.resolve_content(
        content_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=1024,
    )) == content


def test_process_local_colliding_writer_smoke_never_overwrites_the_winner() -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=1024)

    def register(content: bytes) -> tuple[str, bytes]:
        try:
            resolver.register_bytes(
                artifact_id="shared-id",
                content_ref=_ref(content),
                artifact_kind="source-bundle",
                media_type="application/json",
                scope="formal-run",
                content=content,
            )
            return "stored", content
        except ContractV4Error as exc:
            return exc.code, content

    def race() -> list[tuple[str, bytes]]:
        with ThreadPoolExecutor(max_workers=2) as workers:
            return list(workers.map(register, (b"first", b"second")))

    outcomes = _call_with_zero_external_io(race)
    assert sorted(code for code, _ in outcomes) == ["ARTIFACT_ID_COLLISION", "stored"]
    winner = next(content for code, content in outcomes if code == "stored")
    assert _call_with_zero_external_io(
        lambda: resolver.resolve_content(
            _ref(winner),
            expected_artifact_kind="source-bundle",
            expected_media_type="application/json",
            expected_scope="formal-run",
            max_bytes=1024,
        )
    ) == winner


def _case_artifact(identifier: str, content: bytes) -> CaseArtifactV4:
    return CaseArtifactV4(
        identifier, ContentRefV4("case-json", DigestV4.from_bytes(content)),
        "case-json", "application/json", "case-input", b64encode(content).decode("ascii"),
    )


def _complete_case_bundle() -> CaseInputBundleV4:
    from tests.contract.test_case_input_bundle import bundle as incomplete_bundle

    value = incomplete_bundle()
    evidence = _case_artifact("evidence", b"{}")
    request = value.request.to_dict()
    request["evidence_manifest_ref"] = evidence.content_ref.to_dict()
    body = {
        "schema_version": value.schema_version,
        "bundle_id": value.bundle_id,
        "request": request,
        "artifacts": [value.artifacts[0].to_dict(), evidence.to_dict()],
    }
    return CaseInputBundleV4.from_dict({**body, "bundle_digest": str(digest_value(body))})


def test_case_overlay_does_not_grow_global_records() -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=1_048_576)
    initial = len(resolver._by_ref)
    for index in range(100):
        item = _case_artifact("same-id", f'{{"case":{index}}}'.encode())
        with resolver.overlay((item,)):
            assert resolver.resolve_content(
                item.content_ref, expected_artifact_kind=item.artifact_kind,
                expected_media_type=item.media_type, expected_scope=item.scope,
                max_bytes=100,
            ) == item.content_bytes()
    assert len(resolver._by_ref) == initial
    assert not resolver.contains(item.content_ref)


def test_parallel_case_overlays_with_same_id_are_isolated() -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=1_048_576)

    def resolve(content: bytes) -> bytes:
        item = _case_artifact("shared-id", content)
        with resolver.overlay((item,)):
            return resolver.resolve_content(
                item.content_ref, expected_artifact_kind=item.artifact_kind,
                expected_media_type=item.media_type, expected_scope=item.scope,
                max_bytes=100,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert set(pool.map(resolve, (b'{"case":1}', b'{"case":2}'))) == {
            b'{"case":1}', b'{"case":2}'
        }


def test_case_overlay_cleans_up_and_blocks_pack_collision() -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=1_048_576)
    item = _case_artifact("case", b"{}")
    with pytest.raises(RuntimeError):
        with resolver.overlay((item,)):
            raise RuntimeError("boom")
    assert not resolver.contains(item.content_ref)
    resolver.register_bytes(
        artifact_id=item.artifact_id, content_ref=item.content_ref,
        artifact_kind=item.artifact_kind, media_type=item.media_type,
        scope=item.scope, content=item.content_bytes(),
    )
    with pytest.raises(ContractV4Error, match="ARTIFACT_NAMESPACE_COLLISION"):
        with resolver.overlay((item,)):
            pass


def test_case_bundle_closure_rejects_missing_and_orphan_artifacts() -> None:
    from tests.contract.test_case_input_bundle import bundle as incomplete_bundle

    resolver = ArtifactResolverV4(max_artifact_bytes=1_048_576)
    with pytest.raises(ContractV4Error, match="CASE_BUNDLE_INCOMPLETE"):
        resolver.validate_case_bundle(incomplete_bundle())
    complete = _complete_case_bundle()
    resolver.validate_case_bundle(complete)
    orphan = _case_artifact("orphan", b'{"orphan":true}')
    body = complete.digest_body()
    body["artifacts"].append(orphan.to_dict())
    with pytest.raises(ContractV4Error, match="CASE_BUNDLE_ORPHAN"):
        resolver.validate_case_bundle(CaseInputBundleV4.from_dict({
            **body, "bundle_digest": str(digest_value(body)),
        }))
