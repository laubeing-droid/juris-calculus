"""ApplicationV4 size, deadline, cancellation, and audit quota boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

import compiler_core.audit_bundle as audit_bundle_module
import compiler_core.contracts as contracts_module
from compiler_core.application import ApplicationV4Error
from compiler_core.backend_router import BackendV4Error
from compiler_core.canonical_serialization import DigestV4, canonical_bytes
from compiler_core.contracts import (
    CertificateKindV4,
    ContentRefV4,
    DecisionStatusV4,
    ExecutionStatusV4,
    ResourceLimitsV4,
)
from compiler_core.fact_admission import CASE_REQUEST_KIND, CASE_REQUEST_SCOPE
from compiler_core.rule_packs import JSON_MEDIA_TYPE
from tests.contract.test_application import _application
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


def _assert_no_committed_bundle(root: Path) -> None:
    assert not list(root.rglob("COMPLETE"))
    assert not list(root.rglob("certificate.json"))


@pytest.mark.parametrize(
    ("boundary", "expected_code"),
    (
        ("size", "ARTIFACT_TOO_LARGE"),
        ("depth", "JSON_DEPTH_LIMIT"),
    ),
)
def test_request_size_and_depth_limits_fail_before_bundle(
    tmp_path: Path,
    boundary: str,
    expected_code: str,
) -> None:
    harness = _ChainHarness()
    application, _, _ = _application(tmp_path, harness)
    request_ref = harness.request_ref
    limits = ResourceLimitsV4(max_request_bytes=64)
    if boundary == "depth":
        nested: object = "leaf"
        for _ in range(20):
            nested = [nested]
        body = {**harness.request.to_dict(), "unexpected_nested": nested}
        raw = canonical_bytes(body)
        request_ref = ContentRefV4(CASE_REQUEST_KIND, DigestV4.from_bytes(raw))
        harness.resolver.register_bytes(
            artifact_id="w4-06-deep-request",
            content_ref=request_ref,
            artifact_kind=CASE_REQUEST_KIND,
            media_type=JSON_MEDIA_TYPE,
            scope=CASE_REQUEST_SCOPE,
            content=raw,
        )
        limits = ResourceLimitsV4()

    with pytest.raises(ApplicationV4Error) as caught:
        application.evaluate(
            request_ref,
            harness.run_identity_ref,
            case_scope=CASE_SCOPE,
            limits=limits,
        )

    assert (caught.value.code, caught.value.stage, caught.value.retryable) == (
        expected_code,
        "resolver",
        False,
    )
    assert caught.value.__cause__ is None
    _assert_no_committed_bundle(tmp_path / "state")


def test_request_admission_deadline_fails_before_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ChainHarness()
    application, _, _ = _application(tmp_path, harness)
    ticks = iter((0, 2_000_000))
    monkeypatch.setattr(
        contracts_module.time,
        "monotonic_ns",
        lambda: next(ticks),
    )

    with pytest.raises(ApplicationV4Error) as caught:
        application.evaluate(
            harness.request_ref,
            harness.run_identity_ref,
            case_scope=CASE_SCOPE,
            limits=ResourceLimitsV4(admission_deadline_ms=1),
        )

    assert (caught.value.code, caught.value.stage, caught.value.retryable) == (
        "ADMISSION_DEADLINE",
        "resolver",
        True,
    )
    assert caught.value.__cause__ is None
    _assert_no_committed_bundle(tmp_path / "state")


def test_pre_backend_cancellation_is_typed_and_never_certified(tmp_path: Path) -> None:
    harness = _ChainHarness()
    application, _, _ = _application(tmp_path, harness)

    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
        cancel_check=lambda: True,
    )

    assert envelope.result.decision_status is DecisionStatusV4.BLOCKED
    assert envelope.result.execution_status is ExecutionStatusV4.CANCELLED
    assert envelope.result.certificate_kind is CertificateKindV4.NONE
    assert envelope.certificate.kind is CertificateKindV4.NONE
    assert envelope.transport_outcome.error.code == "APPLICATION_CANCELLED"
    assert envelope.transport_outcome.error.retryable is False


def test_solver_cancellation_is_forwarded_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ChainHarness()
    application, _, router = _application(tmp_path, harness)
    cancel_check = lambda: False
    limits = ResourceLimitsV4(solver_deadline_ms=37)

    def cancel(*_args, **kwargs):
        assert kwargs["limits"] is limits
        assert kwargs["cancel_check"] is cancel_check
        raise BackendV4Error("BACKEND_CANCELLED", "private provider detail")

    monkeypatch.setattr(router, "execute", cancel)
    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
        limits=limits,
        cancel_check=cancel_check,
    )

    assert envelope.result.execution_status is ExecutionStatusV4.CANCELLED
    assert envelope.result.decision_status is DecisionStatusV4.BLOCKED
    assert envelope.result.certificate_kind is CertificateKindV4.NONE
    assert envelope.transport_outcome.error.code == "BACKEND_CANCELLED"


def test_audit_quota_failure_is_retryable_and_uncommitted(tmp_path: Path) -> None:
    harness = _ChainHarness()
    application, store, _ = _application(tmp_path, harness)
    store._store.quota_bytes = 1

    with pytest.raises(ApplicationV4Error) as caught:
        application.evaluate(
            harness.request_ref,
            harness.run_identity_ref,
            case_scope=CASE_SCOPE,
        )

    assert (caught.value.code, caught.value.stage, caught.value.retryable) == (
        "AUDIT_QUOTA",
        "audit",
        True,
    )
    assert caught.value.__cause__ is None
    _assert_no_committed_bundle(tmp_path / "state")


def test_bundle_size_bound_fails_without_complete_or_certificate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ChainHarness()
    application, _, _ = _application(tmp_path, harness)
    monkeypatch.setattr(audit_bundle_module, "MAX_BUNDLE_BYTES_V4", 1)

    with pytest.raises(ApplicationV4Error) as caught:
        application.evaluate(
            harness.request_ref,
            harness.run_identity_ref,
            case_scope=CASE_SCOPE,
        )

    assert (caught.value.code, caught.value.stage, caught.value.retryable) == (
        "AUDIT_BUNDLE_TOO_LARGE",
        "audit",
        False,
    )
    assert caught.value.__cause__ is None
    _assert_no_committed_bundle(tmp_path / "state")
