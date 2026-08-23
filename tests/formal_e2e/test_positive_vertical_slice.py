"""Positive synthetic V4 kernel output, certificate, verify, and offline replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler_core.audit_bundle import ReplayExecutionV4
from compiler_core.canonical_serialization import digest_value, parse_json_document
from compiler_core.contracts import (
    CertificateKindV4,
    ContentRefV4,
    DecisionStatusV4,
    RunIdentityV4,
)
from compiler_core.fact_admission import (
    CASE_REQUEST_KIND,
    CASE_REQUEST_SCOPE,
    RUN_IDENTITY_KIND,
    RUN_IDENTITY_SCOPE,
)
from compiler_core.rule_packs import JSON_MEDIA_TYPE
from tests.contract.test_application import _application
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


def _evaluate(tmp_path: Path):
    harness = _ChainHarness()
    application, store, _ = _application(tmp_path, harness)
    request_raw = harness.resolver.resolve_content(
        harness.request_ref,
        expected_artifact_kind=CASE_REQUEST_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=CASE_REQUEST_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    )
    run_raw = harness.resolver.resolve_content(
        harness.run_identity_ref,
        expected_artifact_kind=RUN_IDENTITY_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=RUN_IDENTITY_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    )
    assert request_raw == harness.request.canonical_bytes()
    assert parse_json_document(run_raw) == harness.run.digest_body()
    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )
    capability = store.capability_for(harness.run_identity_ref)
    verified = store.verify_run(capability, now=harness.now)
    return harness, application, store, capability, envelope, verified


def test_signed_pack_produces_verified_result(tmp_path: Path) -> None:
    harness, _, _, _, envelope, verified = _evaluate(tmp_path)

    assert envelope.result.decision_status is DecisionStatusV4.ACCEPTED_FORMAL_RESULT
    assert envelope.result.certificate_kind is CertificateKindV4.FORMAL_VERIFIED
    assert envelope.result.run_identity_ref == harness.run_identity_ref
    assert envelope.result.claims[0].claim_id == "synthetic-positive"
    assert envelope.transport_outcome.status == "success"
    assert verified.result == envelope.result
    assert verified.verification.status == "VERIFIED"


def test_certificate_uses_verified_run_receipts(tmp_path: Path) -> None:
    harness, _, _, _, envelope, verified = _evaluate(tmp_path)
    formal = envelope.certificate.formal

    assert formal is not None
    assert formal.run_identity_ref == harness.run_identity_ref
    assert formal.request_ref == harness.request_ref
    assert formal.result_ref == ContentRefV4(
        "semantic-result", envelope.result.canonical_digest()
    )
    receipt_refs = set(envelope.result.receipt_refs)
    for group in (
        formal.source_receipt_refs,
        formal.evidence_receipt_refs,
        formal.fact_admission_receipt_refs,
        formal.rule_promotion_receipt_refs,
        formal.translation_receipt_refs,
        formal.solver_receipt_refs,
        formal.proof_receipt_refs,
        formal.checker_receipt_refs,
    ):
        assert group and set(group) <= receipt_refs
    assert verified.certificate == envelope.certificate
    assert envelope.certificate.service_signature is not None


def test_v4_bundle_verifies_and_replays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, application, store, capability, _, original = _evaluate(tmp_path)
    replay_harness = _ChainHarness()
    replay_application, replay_store, _ = _application(
        tmp_path / "offline-replay",
        replay_harness,
    )
    captured: list[tuple[object, object]] = []
    write_run = replay_store.write_run

    def capture(capability_value, materials, **kwargs):
        captured.append((materials, kwargs.get("certificate_factory")))
        return write_run(capability_value, materials, **kwargs)

    monkeypatch.setattr(replay_store, "write_run", capture)
    replay_body = replay_harness.run.digest_body()
    replay_body["engine_source_commit"] = "c" * 40
    replay_run = RunIdentityV4.from_dict({
        **replay_body,
        "run_digest": str(digest_value(replay_body)),
    })
    replay_run_ref = replay_harness._digest_contract(
        RUN_IDENTITY_KIND,
        RUN_IDENTITY_SCOPE,
        replay_run,
    )

    def execute(sealed):
        assert sealed.original_run_identity_ref == harness.run_identity_ref
        assert sealed.read("input.json") == original.files["input.json"]
        replay_application.evaluate(
            replay_harness.request_ref,
            replay_run_ref,
            case_scope=CASE_SCOPE,
        )
        materials, certificate_factory = captured[-1]
        assert materials.run_identity == replay_run
        return ReplayExecutionV4(materials, certificate_factory)

    replay = store.replay_run(
        capability,
        now=harness.now,
        executor=execute,
    )

    assert replay.replay_run_identity_ref == replay_run_ref
    assert replay.status == "MATCH", replay.differing_paths
    assert replay.semantic_equal is True
    assert replay.exact_equal is False
    assert store.verify_run(capability, now=harness.now) == original
