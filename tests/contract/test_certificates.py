"""Contract tests for bundle-bound V4 certificate issuance and verification."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from compiler_core.audit_bundle import AuditArtifactV4, AuditBundleStoreV4
from compiler_core.canonical_serialization import DigestV4, digest_value, parse_json_document
from compiler_core.certificates import (
    CertificateContextV4,
    CertificateIssuerV4,
    CertificateV4Error,
    CertificateVerifierV4,
)
from compiler_core.contracts import (
    CertificateKindV4,
    CheckerReceiptV4,
    ClaimResultV4,
    ContentRefV4,
    ProofReceiptV4,
    RuleV4,
    SemanticResultV4,
    SolverReceiptV4,
)
from compiler_core.storage import V4TransactionStore
from tests.contract.test_audit_bundle import _fixture, _semantic_digest


def _formal_materials(materials, harness, checked_ref: ContentRefV4):
    solver_ref = materials.result.runtime_profile.backend_receipt_ref
    assert solver_ref is not None
    solver_record = harness.resolver._by_ref[solver_ref]
    solver = SolverReceiptV4.from_dict(parse_json_document(solver_record.content))
    checker_record = harness.resolver._by_ref[checked_ref]
    checker = CheckerReceiptV4.from_dict(parse_json_document(checker_record.content))

    rule_refs = tuple(
        reference for reference in checker.signature.evidence_refs if reference.kind == "rule-v4"
    )
    fact_refs = tuple(
        reference
        for reference in checker.signature.evidence_refs
        if reference.kind == "admitted-fact"
    )
    source_refs = tuple(
        reference
        for reference in checker.signature.evidence_refs
        if reference.kind == "source-snapshot"
    )
    promotion_refs = tuple(
        reference
        for reference in checker.signature.evidence_refs
        if reference.kind == "rule-promotion-receipt"
    )
    source_receipt_refs = tuple(
        reference
        for reference in checker.signature.evidence_refs
        if reference.kind == "source-authenticity-receipt"
    )
    fact_receipt_refs = tuple(
        reference
        for reference in checker.signature.evidence_refs
        if reference.kind == "fact-admission-receipt"
    )
    assert all(len(values) == 1 for values in (
        rule_refs,
        fact_refs,
        source_refs,
        promotion_refs,
        source_receipt_refs,
        fact_receipt_refs,
    ))
    rule_record = harness.resolver._by_ref[rule_refs[0]]
    rule_payload = parse_json_document(rule_record.content)
    rule = RuleV4.from_dict({**rule_payload, "rule_digest": str(rule_refs[0].digest)})
    assert rule.promotion_receipt_refs == promotion_refs

    claim_ref = ContentRefV4("claim-v4", DigestV4.from_bytes(b"w4-04-accepted-claim"))
    proof_body = {
        "receipt_id": "w4-04-proof",
        "run_identity_ref": harness.run_identity_ref.to_dict(),
        "subject_ref": claim_ref.to_dict(),
        "proof_kind": "independent-checker-confirmed-backend-proof",
        "proof_ref": solver.proof_ref.to_dict(),
        "checker_receipt_ref": checked_ref.to_dict(),
        "proof_build_digest": str(checker.checker_build_digest),
        "trusted_computing_base_refs": [
            solver.proof_ref.to_dict(), checked_ref.to_dict(),
        ],
        "status": "PASS",
        "issued_at": harness.now.to_dict(),
    }
    proof_signature = harness._sign_receipt(
        claim_ref.digest,
        digest_value(proof_body),
        (claim_ref, solver.proof_ref, checked_ref),
        harness.run_identity_ref,
        harness.now,
    )
    proof = ProofReceiptV4.from_dict({**proof_body, "signature": proof_signature.to_dict()})
    proof_raw = proof.canonical_bytes()
    proof_ref = ContentRefV4("proof-receipt-v4", DigestV4.from_bytes(proof_raw))
    proof_artifact = AuditArtifactV4(
        "proof-receipt-v4-" + proof_ref.digest.hex,
        proof_ref,
        "proof-receipt-v4",
        "application/json",
        "independent-checker",
        proof_raw,
    )

    claim = ClaimResultV4(
        "w4-04-accepted-claim",
        claim_ref,
        "accepted",
        "IN",
        (checker.argument_graph_ref,),
        fact_refs,
        rule_refs,
        source_refs,
        (proof_ref,),
        (checked_ref,),
    )
    translation_refs = tuple(
        item.content_ref
        for item in materials.translation_artifacts
        if item.artifact_kind == "translation-receipt"
    )
    receipt_refs = tuple(sorted((
        *source_receipt_refs,
        harness.run.evidence_manifest_ref,
        *fact_receipt_refs,
        *promotion_refs,
        *translation_refs,
        solver_ref,
        proof_ref,
        checked_ref,
    ), key=lambda item: (item.kind, item.digest.hex)))
    body = {
        "request_ref": harness.run.request_ref.to_dict(),
        "execution_status": "completed",
        "decision_status": "accepted_formal_result",
        "review_state": {
            "status": "not_required",
            "unresolved_item_refs": [],
            "responsible_role": None,
            "release_condition_refs": [],
            "review_receipt_ref": None,
        },
        "completeness_state": "complete",
        "interruption_state": None,
        "certificate_kind": "formal_verified",
        "runtime_profile": {
            **materials.result.runtime_profile.to_dict(),
            "formal_kernel": True,
        },
        "claims": [claim.to_dict()],
        "branches": [],
        "missing_facts": [],
        "admitted_fact_refs": [item.to_dict() for item in fact_refs],
        "rejected_fact_refs": [],
        "applicable_rule_refs": [item.to_dict() for item in rule_refs],
        "inapplicable_rule_refs": [],
        "argument_refs": [checker.argument_graph_ref.to_dict()],
        "attack_refs": [],
        "exception_resolution_refs": [],
        "permission_resolution_refs": [],
        "priority_resolution_refs": [],
        "temporal_result_refs": [],
        "numeric_result_refs": [],
        "decision_reason_codes": [],
        "taint_codes": [],
        "risk_codes": [],
        "receipt_refs": [item.to_dict() for item in receipt_refs],
        "run_identity_ref": harness.run_identity_ref.to_dict(),
    }
    result = SemanticResultV4.from_dict({
        **body, "result_digest": str(_semantic_digest(body)),
    })
    return replace(
        materials,
        result=result,
        checker_artifacts=tuple(sorted(
            (*materials.checker_artifacts, proof_artifact),
            key=lambda item: item.sort_key,
        )),
    )


def _formal_fixture(tmp_path: Path):
    harness, _, bundles, capability, materials, checked_ref = _fixture(tmp_path)
    materials = _formal_materials(materials, harness, checked_ref)
    issuer = CertificateIssuerV4(
        harness.trust,
        current_engine_build_digest=harness.run.engine_build_digest,
        signer=harness._sign_receipt,
    )
    return harness, bundles, capability, materials, issuer


def _context(bundles: AuditBundleStoreV4, materials):
    core = bundles._verify_core(
        bundles._core_files(materials), now=materials.request.decision_time
    )
    return bundles._certificate_context(core, now=materials.request.decision_time)


def test_bundle_bound_formal_certificate_is_issued_and_independently_verified(
    tmp_path: Path,
) -> None:
    harness, bundles, capability, materials, issuer = _formal_fixture(tmp_path)
    completed = bundles.write_run(
        capability,
        materials,
        now=harness.now,
        certificate_factory=issuer,
    )
    assert completed.certificate.kind is CertificateKindV4.FORMAL_VERIFIED
    assert completed.certificate.formal is not None
    assert completed.certificate.formal.bundle_core_digest == _context(
        bundles, materials
    ).bundle_core_digest
    assert completed.certificate.service_signature is not None
    assert bundles.verify_run(capability, now=harness.now) == completed


def test_internal_certificate_body_is_deterministic_across_service_signatures(
    tmp_path: Path,
) -> None:
    harness, bundles, _, materials, _ = _formal_fixture(tmp_path)
    trust = bundles._trust_material

    def issued(prefix: str, state_name: str):
        storage = V4TransactionStore.create(
            (tmp_path / state_name).resolve(), quota_bytes=256 * 1024 * 1024
        )
        store = AuditBundleStoreV4(
            storage,
            trust_material=trust,
            current_engine_build_digest=harness.run.engine_build_digest,
            checker_receipt_issuer="synthetic-service-issuer",
        )

        def signer(subject, payload, evidence, run_ref, now):
            return harness._signature(
                "service",
                subject_digest=subject,
                payload_digest=payload,
                evidence_refs=evidence,
                nonce=f"{prefix}-{subject.hex}",
                issued_at=now,
                run_identity_ref=run_ref,
            )

        certificate = store.write_run(
            store.capability_for(harness.run_identity_ref),
            materials,
            now=harness.now,
            certificate_factory=CertificateIssuerV4(
                harness.trust,
                current_engine_build_digest=harness.run.engine_build_digest,
                signer=signer,
            ),
        ).certificate
        return certificate

    first = issued("first", "deterministic-a")
    second = issued("second", "deterministic-b")
    assert first.formal == second.formal
    assert first.service_signature != second.service_signature


def test_none_result_is_the_unsigned_none_union(tmp_path: Path) -> None:
    _, _, bundles, capability, materials, _ = _fixture(tmp_path)
    completed = bundles.write_run(
        capability, materials, now=materials.request.decision_time
    )
    assert completed.certificate.kind is CertificateKindV4.NONE
    assert completed.certificate.formal is None
    assert completed.certificate.conflict is None
    assert completed.certificate.service_signature is None


def test_conflict_result_uses_the_signed_conflict_union(tmp_path: Path) -> None:
    harness, bundles, capability, materials, issuer = _formal_fixture(tmp_path)
    body = materials.result.to_dict()
    body["decision_status"] = "conflict_certificate"
    body["certificate_kind"] = "conflict_verified"
    body["review_state"] = {
        "status": "pending",
        "unresolved_item_refs": [materials.result.claims[0].claim_ref.to_dict()],
        "responsible_role": "legal_reviewer",
        "release_condition_refs": [ContentRefV4(
            "review-condition", DigestV4.from_bytes(b"resolve-conflict")
        ).to_dict()],
        "review_receipt_ref": None,
    }
    body["attack_refs"] = [ContentRefV4(
        "attack-v4", DigestV4.from_bytes(b"w4-04-conflict-attack")
    ).to_dict()]
    body.pop("result_digest")
    conflict = SemanticResultV4.from_dict({
        **body, "result_digest": str(_semantic_digest(body)),
    })
    completed = bundles.write_run(
        capability,
        replace(materials, result=conflict),
        now=harness.now,
        certificate_factory=issuer,
    )
    assert completed.certificate.kind is CertificateKindV4.CONFLICT_VERIFIED
    assert completed.certificate.formal is None
    assert completed.certificate.conflict is not None
    assert completed.certificate.conflict.attack_refs == conflict.attack_refs


def test_context_is_sealed_and_issuer_has_no_gate_map_api(tmp_path: Path) -> None:
    harness, bundles, _, materials, issuer = _formal_fixture(tmp_path)
    with pytest.raises(CertificateV4Error) as caught:
        CertificateContextV4(
            object(),
            harness.request,
            harness.run,
            materials.result,
            DigestV4.from_bytes(b"caller-core"),
            (),
            (),
            harness.now,
        )
    assert caught.value.code == "CERTIFICATE_CONTEXT_AUTHORITY"
    assert not hasattr(issuer, "issue")
    assert not hasattr(issuer, "issue_formal_certificate")
    forged = replace(
        _context(bundles, materials),
        bundle_core_digest=DigestV4.from_bytes(b"caller-replaced-core"),
    )
    with pytest.raises(CertificateV4Error) as replaced:
        issuer(forged)
    assert replaced.value.code == "CERTIFICATE_CONTEXT_AUTHORITY"
    with pytest.raises(CertificateV4Error) as mapping:
        issuer({"all_gates": "PASS", "bundle_digest": "sha256:" + "0" * 64})
    assert mapping.value.code == "CERTIFICATE_CONTEXT_AUTHORITY"


def test_unsigned_direct_constructor_is_not_an_issued_certificate(tmp_path: Path) -> None:
    harness, bundles, _, materials, issuer = _formal_fixture(tmp_path)
    context = _context(bundles, materials)
    unsigned, _, _ = issuer._verifier._recompute(context)
    verifier = CertificateVerifierV4(
        harness.trust,
        current_engine_build_digest=harness.run.engine_build_digest,
    )
    with pytest.raises(CertificateV4Error) as caught:
        verifier.verify(context, unsigned)
    assert caught.value.code == "CERTIFICATE_SIGNATURE_REQUIRED"
