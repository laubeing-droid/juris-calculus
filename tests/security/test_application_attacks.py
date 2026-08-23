"""ApplicationV4 fail-closed attacks at the pack readiness boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler_core.canonical_serialization import parse_json_document
from compiler_core.contracts import CertificateKindV4, DecisionStatusV4, PackSignatureV4
from compiler_core.rule_packs import JSON_MEDIA_TYPE, PACK_SIGNATURE_KIND, RULE_PACK_SCOPE
from tests.contract.test_application import _application
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


def test_current_request_reverifies_and_rejects_a_revoked_cached_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ChainHarness()
    old_handle = harness.verify_pack()
    assert old_handle.verifier_issued is True
    raw = harness.resolver.resolve_content(
        harness.pack_ref,
        expected_artifact_kind=PACK_SIGNATURE_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=RULE_PACK_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    )
    pack_signature = PackSignatureV4.from_dict(parse_json_document(raw))
    harness.trust._revoked_subjects = frozenset((
        *harness.trust._revoked_subjects,
        pack_signature.signature.subject_digest,
    ))
    calls = 0
    original = harness.pack_verifier.verify

    def verify(pack_ref, *, now):
        nonlocal calls
        calls += 1
        return original(pack_ref, now=now)

    monkeypatch.setattr(harness.pack_verifier, "verify", verify)
    application, _, _ = _application(tmp_path, harness)

    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )

    assert old_handle.verifier_issued is False
    assert calls == 1
    assert envelope.result.decision_status is DecisionStatusV4.BLOCKED
    assert envelope.result.certificate_kind is CertificateKindV4.NONE
    assert envelope.certificate.kind is CertificateKindV4.NONE
    assert envelope.transport_outcome.error.stage == "pack"
    assert envelope.transport_outcome.error.code in {
        "TRUST_SIGNATURE_REVOKED",
        "TRUST_REPLAY",
    }
