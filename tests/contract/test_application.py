"""Contract tests for the sole ApplicationV4 formal spine."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import compiler_core.application as application_module
from compiler_core.application import ApplicationV4
from compiler_core.audit_bundle import AuditBundleStoreV4, AuditTrustMaterialV4
from compiler_core.backend_router import BackendRouterV4, BackendV4Error
from compiler_core.canonical_serialization import DigestV4, digest_value, parse_json_document
from compiler_core.certificates import CertificateIssuerV4
from compiler_core.contracts import (
    CaseRequestV4,
    CertificateKindV4,
    ContentRefV4,
    DecisionStatusV4,
    EvidenceManifestV4,
    ExecutionStatusV4,
    FactAttestationV4,
    LegalContextV4,
    RunIdentityV4,
)
from compiler_core.fact_admission import (
    CASE_EVIDENCE_SCOPE,
    CASE_REQUEST_KIND,
    CASE_REQUEST_SCOPE,
    EVIDENCE_MANIFEST_KIND,
    RUN_IDENTITY_KIND,
    RUN_IDENTITY_SCOPE,
    case_request_binding_ref,
)
from compiler_core.independent_checker import IndependentCheckerV4
from compiler_core.legal_ir import LegalIRCompilerV4
from compiler_core.storage import V4TransactionStore
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


def _application(tmp_path: Path, harness: _ChainHarness):
    tmp_path.mkdir(parents=True, exist_ok=True)
    compiler = LegalIRCompilerV4(
        harness.pack_verifier,
        receipt_issuer="synthetic-service-issuer",
        receipt_signer=harness._sign_receipt,
    )
    router = BackendRouterV4(
        compiler,
        harness.fact_service,
        receipt_signer=harness._sign_receipt,
    )
    checker = IndependentCheckerV4(
        harness.resolver,
        harness.trust,
        receipt_issuer="synthetic-service-issuer",
        receipt_signer=harness._sign_receipt,
    )
    trust_material = AuditTrustMaterialV4(
        harness.policy,
        tuple(key for _, key in sorted(harness.trust._keys.items())),
        harness.trust.target_environment,
        tuple(sorted(harness.trust._revoked_subjects, key=str)),
        tuple(sorted(harness.trust._revoked_nonces)),
    )
    store = AuditBundleStoreV4(
        V4TransactionStore.create(
            (tmp_path / "state").resolve(),
            quota_bytes=256 * 1024 * 1024,
        ),
        trust_material=trust_material,
        current_engine_build_digest=harness.run.engine_build_digest,
        checker_receipt_issuer="synthetic-service-issuer",
    )
    issuer = CertificateIssuerV4(
        harness.trust,
        current_engine_build_digest=harness.run.engine_build_digest,
        signer=harness._sign_receipt,
    )
    application = ApplicationV4(
        harness.resolver,
        harness.trust,
        harness.source_service,
        harness.fact_service,
        harness.pack_verifier,
        compiler,
        router,
        checker,
        store,
        issuer,
        receipt_signer=harness._sign_receipt,
        clock=lambda: harness.now,
    )
    return application, store, router


def _register_request_and_run(
    harness: _ChainHarness,
    *,
    attestation_refs: tuple[ContentRefV4, ...],
    proposal_refs: tuple[ContentRefV4, ...] = (),
    legal_context: LegalContextV4 | None = None,
) -> tuple[CaseRequestV4, ContentRefV4, RunIdentityV4, ContentRefV4]:
    seed = replace(
        harness.request,
        fact_attestation_refs=attestation_refs,
        proposal_refs=proposal_refs,
        legal_context=legal_context or harness.request.legal_context,
    )
    manifest_record = harness.resolver._by_ref[harness.request.evidence_manifest_ref]
    manifest_body = parse_json_document(manifest_record.content)
    manifest = EvidenceManifestV4.from_dict({
        **manifest_body,
        "manifest_digest": str(harness.request.evidence_manifest_ref.digest),
    })
    binding = case_request_binding_ref(seed)
    if manifest.request_ref != binding:
        changed_body = manifest.digest_body()
        changed_body["request_ref"] = binding.to_dict()
        manifest = EvidenceManifestV4.from_dict({
            **changed_body,
            "manifest_digest": str(digest_value(changed_body)),
        })
        manifest_ref = harness._digest_contract(
            EVIDENCE_MANIFEST_KIND,
            CASE_EVIDENCE_SCOPE,
            manifest,
        )
        seed = replace(seed, evidence_manifest_ref=manifest_ref)
    request_ref = harness._contract(CASE_REQUEST_KIND, CASE_REQUEST_SCOPE, seed)
    original = harness.run
    run = RunIdentityV4.build(
        seed,
        request_ref,
        engine_version=original.engine_version,
        engine_source_commit=original.engine_source_commit,
        engine_source_tree=original.engine_source_tree,
        engine_build_digest=original.engine_build_digest,
        wheel_digest=original.wheel_digest,
        package_digest=original.package_digest,
        schema_digest=original.schema_digest,
        tool_spec_digest=original.tool_spec_digest,
        lock_digest=original.lock_digest,
        runtime_config_digest=original.runtime_config_digest,
        algorithm_profile_digest=original.algorithm_profile_digest,
        trust_policy_ref=original.trust_policy_ref,
        storage_capability_ref=original.storage_capability_ref,
        backend_profile_digest=original.backend_profile_digest,
    )
    run_ref = harness._digest_contract(RUN_IDENTITY_KIND, RUN_IDENTITY_SCOPE, run)
    return seed, request_ref, run, run_ref


def _nonformal_attestation(
    harness: _ChainHarness,
    *,
    dispute_state: str,
    assumption_state: str,
    label: str,
) -> ContentRefV4:
    body = harness.attestation.signature_body()
    body.update({
        "attestation_id": f"application-{label}",
        "dispute_state": dispute_state,
        "assumption_state": assumption_state,
        "nonce": f"application-{label}",
    })
    signature = harness._signature(
        "legal",
        subject_digest=harness.candidate_ref.digest,
        payload_digest=digest_value(body),
        evidence_refs=harness.attestation.signature.evidence_refs,
        nonce=body["nonce"],
        issued_at=harness.attestation.issued_at,
        run_identity_ref=None,
    )
    attestation = FactAttestationV4.from_dict({**body, "signature": signature.to_dict()})
    return harness._contract(
        "fact-attestation",
        "legal-approval",
        attestation,
    )


def _rule_ref(harness: _ChainHarness, rule_id: str) -> ContentRefV4:
    pack = harness.verify_pack()
    return next(
        reference
        for reference, rule in zip(pack.manifest.rule_refs, pack.rules, strict=True)
        if rule.rule_id == rule_id
    )


@pytest.mark.parametrize(
    ("dispute_state", "assumption_state", "expected"),
    (
        ("DISPUTED", "NONE", DecisionStatusV4.REVIEW_ONLY_RESULT),
        ("UNDISPUTED", "USER_ASSUMED", DecisionStatusV4.HYPOTHETICAL_RESULT),
    ),
)
def test_nonformal_fact_states_never_receive_a_certificate(
    tmp_path: Path,
    dispute_state: str,
    assumption_state: str,
    expected: DecisionStatusV4,
) -> None:
    harness = _ChainHarness()
    attestation_ref = _nonformal_attestation(
        harness,
        dispute_state=dispute_state,
        assumption_state=assumption_state,
        label=expected.value,
    )
    _, request_ref, _, run_ref = _register_request_and_run(
        harness,
        attestation_refs=(attestation_ref,),
    )
    application, _, _ = _application(tmp_path, harness)

    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)

    assert envelope.result.decision_status is expected
    assert envelope.result.certificate_kind is CertificateKindV4.NONE
    assert envelope.certificate.kind is CertificateKindV4.NONE
    assert envelope.transport_outcome.status == "success"


def test_missing_and_unknown_are_distinct_typed_results(tmp_path: Path) -> None:
    missing_harness = _ChainHarness()
    missing_rule = _rule_ref(missing_harness, "synthetic-missing-disputed")
    _, request_ref, _, run_ref = _register_request_and_run(
        missing_harness,
        attestation_refs=(),
        proposal_refs=(missing_rule,),
    )
    application, _, _ = _application(tmp_path / "missing", missing_harness)
    missing = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)
    assert missing.result.decision_status is DecisionStatusV4.MISSING_REQUIRED_FACT
    assert missing.result.missing_facts
    assert missing.certificate.kind is CertificateKindV4.NONE

    unknown_harness = _ChainHarness()
    _, request_ref, _, run_ref = _register_request_and_run(
        unknown_harness,
        attestation_refs=(),
    )
    application, _, _ = _application(tmp_path / "unknown", unknown_harness)
    unknown = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)
    assert unknown.result.decision_status is DecisionStatusV4.UNKNOWN
    assert unknown.result.decision_reason_codes == ("no_applicable_rule",)
    assert unknown.certificate.kind is CertificateKindV4.NONE


def test_backend_fault_is_engine_error_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ChainHarness()
    application, _, router = _application(tmp_path, harness)

    def fail(*_args, **_kwargs):
        raise BackendV4Error("BACKEND_TEST_FAULT", "synthetic stage fault")

    monkeypatch.setattr(router, "execute", fail)
    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )

    assert envelope.result.execution_status is ExecutionStatusV4.ENGINE_ERROR
    assert envelope.result.decision_status is DecisionStatusV4.ENGINE_ERROR
    assert envelope.result.certificate_kind is CertificateKindV4.NONE
    assert envelope.transport_outcome.status == "error"
    assert envelope.transport_outcome.error.code == "BACKEND_TEST_FAULT"


def test_checked_conflict_uses_conflict_certificate_not_formal_certificate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ChainHarness()
    application, _, _ = _application(tmp_path, harness)

    def conflict(_execution, checked):
        return application_module._ArgumentOutcome(
            "disputed",
            (),
            (checked.receipt.argument_graph_ref,),
            (ContentRefV4("attack-v4", DigestV4.from_bytes(b"synthetic-conflict")),),
            (),
            (),
        )

    monkeypatch.setattr(application, "_argument_outcome", conflict)
    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )

    assert envelope.result.decision_status is DecisionStatusV4.CONFLICT_CERTIFICATE
    assert envelope.result.certificate_kind is CertificateKindV4.CONFLICT_VERIFIED
    assert envelope.certificate.kind is CertificateKindV4.CONFLICT_VERIFIED
    assert envelope.certificate.conflict is not None


def test_application_module_has_no_v3_compatibility_surface() -> None:
    assert application_module.__all__ == ["ApplicationV4", "ApplicationV4Error"]
    assert not hasattr(application_module, "evaluate_case")
    assert not hasattr(application_module, "run_id_for_case")


def test_signed_domain_config_has_no_global_fallback(tmp_path: Path) -> None:
    harness = _ChainHarness()
    _, request_ref, _, run_ref = _register_request_and_run(
        harness,
        attestation_refs=(),
        legal_context=LegalContextV4("TEST", "not-the-signed-law"),
    )
    application, _, _ = _application(tmp_path, harness)

    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)

    assert envelope.result.decision_status is DecisionStatusV4.BLOCKED
    assert envelope.result.certificate_kind is CertificateKindV4.NONE
    assert envelope.transport_outcome.error.code == "APPLICATION_DOMAIN_CONFIG"
    assert envelope.transport_outcome.error.stage == "pack"
