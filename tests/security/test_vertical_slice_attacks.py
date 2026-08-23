"""End-to-end material, backend, checker, revocation, and bundle attacks."""

from __future__ import annotations

from base64 import b64decode, b64encode
from copy import deepcopy
from pathlib import Path

import pytest

from compiler_core.audit_bundle import AuditBundleV4Error
from compiler_core.backend_router import BackendV4Error
from compiler_core.canonical_serialization import parse_json_document
from compiler_core.contracts import CertificateKindV4, ContractV4Error, DecisionStatusV4, PackSignatureV4
from compiler_core.independent_checker import IndependentCheckerV4Error
from compiler_core.rule_packs import JSON_MEDIA_TYPE, PACK_SIGNATURE_KIND, RULE_PACK_SCOPE
from tests.contract.test_application import _application
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


@pytest.mark.parametrize("artifact_kind", ("source-snapshot", "rule-v4", "pack-signature"))
def test_fixture_artifact_byte_tamper_is_rejected_before_evaluation(
    artifact_kind: str,
) -> None:
    baseline = _ChainHarness().fixture
    fixture = deepcopy(baseline)
    row = next(item for item in fixture["artifacts"] if item["artifact_kind"] == artifact_kind)
    raw = b64decode(row["content_base64"], validate=True)
    row["content_base64"] = b64encode(bytes((raw[0] ^ 1,)) + raw[1:]).decode("ascii")

    with pytest.raises(ContractV4Error, match="^ARTIFACT_DIGEST_MISMATCH:"):
        _ChainHarness(fixture=fixture)


def test_fact_signature_tamper_never_certifies(tmp_path: Path) -> None:
    harness = _ChainHarness(tamper_fact_signature=True)
    application, _, _ = _application(tmp_path, harness)

    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )

    assert envelope.result.decision_status is DecisionStatusV4.BLOCKED
    assert envelope.result.certificate_kind is CertificateKindV4.NONE
    assert envelope.certificate.kind is CertificateKindV4.NONE


@pytest.mark.parametrize("boundary", ("backend", "checker"))
def test_backend_crash_and_checker_disagreement_have_no_formal_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    harness = _ChainHarness()
    application, _, router = _application(tmp_path, harness)

    def backend_fail(*_args, **_kwargs):
        raise BackendV4Error("BACKEND_CRASH", "injected provider crash")

    def checker_fail(*_args, **_kwargs):
        raise IndependentCheckerV4Error("CHECKER_DISAGREEMENT", "injected mismatch")

    if boundary == "backend":
        monkeypatch.setattr(router, "execute", backend_fail)
    else:
        monkeypatch.setattr(application._checker, "check", checker_fail)
    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )

    assert envelope.result.decision_status is DecisionStatusV4.ENGINE_ERROR
    assert envelope.result.certificate_kind is CertificateKindV4.NONE
    assert envelope.certificate.kind is CertificateKindV4.NONE
    assert envelope.transport_outcome.status == "error"


def test_current_revocation_invalidates_cached_pack_before_execution(tmp_path: Path) -> None:
    harness = _ChainHarness()
    harness.verify_pack()
    raw = harness.resolver.resolve_content(
        harness.pack_ref,
        expected_artifact_kind=PACK_SIGNATURE_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=RULE_PACK_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    )
    signature = PackSignatureV4.from_dict(parse_json_document(raw)).signature
    harness.trust._revoked_subjects = frozenset((
        *harness.trust._revoked_subjects,
        signature.subject_digest,
    ))
    application, _, _ = _application(tmp_path, harness)

    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )

    assert envelope.result.decision_status is DecisionStatusV4.BLOCKED
    assert envelope.result.certificate_kind is CertificateKindV4.NONE
    assert envelope.certificate.kind is CertificateKindV4.NONE
    assert envelope.transport_outcome.error.stage == "pack"


def test_completed_bundle_tamper_breaks_independent_verify(tmp_path: Path) -> None:
    harness = _ChainHarness()
    application, store, _ = _application(tmp_path, harness)
    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )
    capability = store.capability_for(harness.run_identity_ref)
    bundle = store._store.root / "audit-bundles" / capability.token
    result_path = bundle / "result.json"
    result_path.write_bytes(result_path.read_bytes() + b" ")

    with pytest.raises(AuditBundleV4Error):
        store.verify_run(capability, now=harness.now)
    assert envelope.certificate.kind is CertificateKindV4.FORMAL_VERIFIED
