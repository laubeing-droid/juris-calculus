"""Privacy and stable error-class boundaries for ApplicationV4 audit output."""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from compiler_core.application import ApplicationV4Error
from compiler_core.audit_bundle import AuditBundleV4Error
from compiler_core.backend_router import BackendV4Error
from compiler_core.canonical_serialization import canonical_bytes
from compiler_core.contracts import ContractV4Error
from compiler_core.storage import StorageV4Error
from tests.contract.test_application import _application
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


_PATH_CANARY = r"D:\private\client\case.txt"
_SECRET_CANARY = "SECRET_TOKEN_W4_06"
_PII_CANARY = "PII_身份证_350000190001010000"
_PRIVATE_DETAIL = f"{_PATH_CANARY} {_SECRET_CANARY} {_PII_CANARY}"


def _bundle_bytes(envelope, store, harness: _ChainHarness) -> bytes:
    capability = store.capability_for(harness.run_identity_ref)
    verified = store.verify_run(capability, now=harness.now)
    return b"\n".join((
        canonical_bytes(envelope.to_dict()),
        repr(capability).encode("utf-8"),
        *verified.files.values(),
    ))


def _assert_private(raw: bytes, *paths: Path) -> None:
    text = raw.decode("utf-8", errors="replace")
    for canary in (_PATH_CANARY, _SECRET_CANARY, _PII_CANARY):
        assert canary not in text
    for path in paths:
        assert str(path.resolve()) not in text
    assert "Traceback (most recent call last)" not in text


def _raise_private_os_error(error_number: int):
    def fail(*_args, **_kwargs):
        raise OSError(error_number, _PRIVATE_DETAIL)

    return fail


def test_capabilities_and_errors_never_leak_absolute_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ChainHarness()
    application, store, router = _application(tmp_path, harness)

    def fail(*_args, **_kwargs):
        raise BackendV4Error("BACKEND_PRIVATE_FAILURE", _PRIVATE_DETAIL)

    monkeypatch.setattr(router, "execute", fail)
    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )

    error = envelope.transport_outcome.error
    assert error.code == "BACKEND_PRIVATE_FAILURE"
    assert error.stage == "backend"
    assert error.retryable is False
    _assert_private(_bundle_bytes(envelope, store, harness), tmp_path)


@pytest.mark.parametrize(
    ("error_number", "expected_code"),
    (
        (errno.ENOSPC, "STORAGE_CAPACITY"),
        (errno.EACCES, "STORAGE_PERMISSION"),
    ),
)
def test_enospc_and_eacces_keep_retryable_storage_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
    expected_code: str,
) -> None:
    harness = _ChainHarness()
    application, store, _ = _application(tmp_path, harness)
    monkeypatch.setattr(store, "_write_file", _raise_private_os_error(error_number))

    with pytest.raises(ApplicationV4Error) as caught:
        application.evaluate(
            harness.request_ref,
            harness.run_identity_ref,
            case_scope=CASE_SCOPE,
        )

    failure = caught.value
    assert (failure.code, failure.stage, failure.retryable) == (
        expected_code,
        "audit",
        True,
    )
    assert len(failure.correlation_id) == 24
    assert failure.__cause__ is None
    _assert_private(str(failure).encode(), tmp_path)
    assert not list((tmp_path / "state").rglob("COMPLETE"))
    assert not list((tmp_path / "state").rglob("certificate.json"))


def test_generic_io_is_retryable_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ChainHarness()
    application, store, _ = _application(tmp_path, harness)
    monkeypatch.setattr(store, "_write_file", _raise_private_os_error(errno.EIO))

    with pytest.raises(ApplicationV4Error) as caught:
        application.evaluate(
            harness.request_ref,
            harness.run_identity_ref,
            case_scope=CASE_SCOPE,
        )

    assert (caught.value.code, caught.value.stage, caught.value.retryable) == (
        "STORAGE_IO",
        "audit",
        True,
    )
    assert caught.value.__cause__ is None
    _assert_private(str(caught.value).encode(), tmp_path)


@pytest.mark.parametrize("boundary", ("security", "engine"))
def test_security_and_engine_details_are_recursively_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    harness = _ChainHarness()
    application, store, router = _application(tmp_path, harness)
    if boundary == "security":
        def fail(*_args, **_kwargs):
            raise ContractV4Error("TRUST_SIGNATURE_INVALID", _PRIVATE_DETAIL)

        monkeypatch.setattr(harness.pack_verifier, "verify", fail)
        expected_stage = "pack"
    else:
        def fail(*_args, **_kwargs):
            raise BackendV4Error("BACKEND_ENGINE_FAILURE", _PRIVATE_DETAIL)

        monkeypatch.setattr(router, "execute", fail)
        expected_stage = "backend"

    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )

    error = envelope.transport_outcome.error
    assert error.stage == expected_stage
    assert error.retryable is False
    assert len(error.correlation_id) == 24
    _assert_private(_bundle_bytes(envelope, store, harness), tmp_path)


def test_audit_capability_boundary_redacts_storage_exception_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ChainHarness()
    _, store, _ = _application(tmp_path, harness)

    def fail() -> None:
        raise StorageV4Error("STORAGE_IO", _PRIVATE_DETAIL)

    monkeypatch.setattr(store, "_verify_audit_layout_locked", fail)
    with pytest.raises(AuditBundleV4Error) as caught:
        store.capability_for(harness.run_identity_ref)

    assert caught.value.code == "STORAGE_IO"
    assert caught.value.detail == "private audit storage operation failed"
    assert caught.value.__cause__ is None
    _assert_private(str(caught.value).encode(), tmp_path)
