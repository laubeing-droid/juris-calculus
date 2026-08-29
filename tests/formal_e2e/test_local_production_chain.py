from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from compiler_core.backend_router import backend_profile_digest_v4
from compiler_core.canonical_serialization import DigestV4, canonical_bytes, digest_value, parse_json_document
from compiler_core.contracts import (
    CanonicalLocatorV4, CaseArtifactV4, CaseInputBundleV4, CaseRequestV4,
    ContentRefV4, DecisionStatusV4, EvidenceItemV4, EvidenceManifestV4,
    FactAttestationV4, FactCandidateV4, LegalContextV4, MCPEvaluateInputV4,
    RequestedOutputV4, SignatureEnvelopeV4, SourceBundleV4, SourceSnapshotV4,
)
from compiler_core.fact_admission import (
    CASE_EVIDENCE_SCOPE, EVIDENCE_CUSTODY_KIND, EVIDENCE_DOCUMENT_KIND,
    EVIDENCE_ITEM_KIND, EVIDENCE_MANIFEST_KIND, FACT_ADMISSION_SCOPE,
    FACT_ATTESTATION_KIND, FACT_CANDIDATE_KIND, FACT_PROPOSITION_KIND,
    FACT_VALUE_KIND, case_request_binding_ref, fact_attestation_evidence_refs,
)
from compiler_core.mcp import tool_spec_digest
from compiler_core.production_pack import current_utc_time, load_production_pack
from compiler_core.production_runtime import _algorithm_profile_digest, create_client
from compiler_core.rule_packs import LEGAL_APPROVAL_SCOPE
from compiler_core.source_service import SOURCE_BUNDLE_KIND, SOURCE_SNAPSHOT_KIND
from tests.conftest import ProductionMaterial


FACTS = {
    13: "pipl.art13.lawful_basis_present",
    14: "pipl.art14.consent_is_basis",
    15: "pipl.art15.processing_based_on_consent",
    16: "pipl.art16.consent_refused_or_withdrawn",
    17: "pipl.art17.before_processing",
    18: "pipl.art18.notice_exception_applies",
}
CASE_SCOPE = "local-production-case"


def runtime_config(path: Path, state_root: Path, material: ProductionMaterial) -> Path:
    document = {
        "schema_version": "jc/production-runtime/1.0",
        "pack_path": str(material.pack_path),
        "trust_path": str(material.trust_path),
        "service_key_path": str(material.service_key_path),
        "state_root": str(state_root.resolve()), "quota_bytes": 268435456,
        "engine_source_commit": "a" * 40,
        "wheel_digest": str(DigestV4.from_bytes(b"w10-wheel")),
        "package_digest": str(DigestV4.from_bytes(b"w10-package")),
        "lock_digest": str(DigestV4.from_bytes(b"w10-lock")),
        "tool_spec_digest": str(tool_spec_digest()),
        "algorithm_profile_digest": str(_algorithm_profile_digest()),
        "backend_profile_digest": str(backend_profile_digest_v4(solver_deadline_ms=2500)),
        "storage_capability_ref": ContentRefV4(
            "storage-capability", DigestV4.from_bytes(b"w10-storage")
        ).to_dict(),
    }
    path.write_bytes(canonical_bytes(document))
    return path


def _legal_key(material: ProductionMaterial) -> Ed25519PrivateKey:
    root = parse_json_document(material.identity_path.read_bytes())
    master = b64decode(root["private_seed_base64"], validate=True)
    seed = HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=b"jc-v4-local-production-v1",
        info=b"juris-calculus/local-production/legal",
    ).derive(master)
    return Ed25519PrivateKey.from_private_bytes(seed)


def _case_artifact(
    serial: int, reference: ContentRefV4, raw: bytes, *, scope: str,
    media_type: str = "application/json",
) -> CaseArtifactV4:
    return CaseArtifactV4(
        f"case-{serial:03d}", reference, reference.kind, media_type, scope,
        b64encode(raw).decode("ascii"),
    )


def production_bundle(
    article: int = 13,
    *,
    fact_key: str | None = None,
    dispute_state: str = "UNDISPUTED",
    assumption_state: str = "NONE",
    label: str = "case",
    material: ProductionMaterial | None = None,
) -> CaseInputBundleV4:
    if material is None:
        raise TypeError("production_bundle requires the production_material fixture")
    loaded = load_production_pack(
        material.pack_path, material.trust_path, material.service_key_path,
    )
    now = current_utc_time()
    fact_key = fact_key or FACTS[article]
    variant = f"{label}-{article}-{dispute_state.lower()}-{assumption_state.lower()}-{fact_key}"
    source_ref = loaded.verified_pack.manifest.source_refs[0]
    source_raw = loaded.resolver.resolve_content(
        source_ref, expected_artifact_kind=SOURCE_SNAPSHOT_KIND,
        expected_media_type="application/json", expected_scope="source-authenticity",
        max_bytes=1_048_576,
    )
    source = SourceSnapshotV4.from_dict(parse_json_document(source_raw))
    source_body = {
        "bundle_id": f"pipl-{article}-source", "root_source_ref": source_ref.to_dict(),
        "terminal_source_ref": source_ref.to_dict(), "snapshots": [source.to_dict()],
        "version_edges": [],
    }
    source_bundle = SourceBundleV4.from_dict({
        **source_body, "bundle_digest": str(digest_value(source_body)),
    })
    source_bundle_ref = ContentRefV4(SOURCE_BUNDLE_KIND, source_bundle.canonical_digest())
    artifacts: list[CaseArtifactV4] = [
        _case_artifact(1, source_bundle_ref, canonical_bytes(source_bundle.digest_body()), scope="source-path")
    ]

    def add_json(kind: str, value: dict[str, object], scope: str) -> ContentRefV4:
        raw = canonical_bytes(value)
        ref = ContentRefV4(kind, DigestV4.from_bytes(raw))
        artifacts.append(_case_artifact(len(artifacts) + 1, ref, raw, scope=scope))
        return ref

    proposition_ref = add_json(
        FACT_PROPOSITION_KIND,
        {"schema_version": "jc/fact-proposition/1.0", "proposition": fact_key},
        FACT_ADMISSION_SCOPE,
    )
    value_ref = add_json(
        FACT_VALUE_KIND,
        {"schema_version": "jc/fact-value/1.0", "value_kind": "boolean", "value": True},
        FACT_ADMISSION_SCOPE,
    )
    document = f"non-personal local PIPL article {article} evidence".encode("ascii")
    document_ref = ContentRefV4(EVIDENCE_DOCUMENT_KIND, DigestV4.from_bytes(document))
    artifacts.append(_case_artifact(
        len(artifacts) + 1, document_ref, document,
        scope=CASE_EVIDENCE_SCOPE, media_type="application/octet-stream",
    ))
    custody_ref = add_json(
        EVIDENCE_CUSTODY_KIND,
        {"schema_version": "jc/evidence-custody/1.0", "custody": "local-owner-reviewed"},
        CASE_EVIDENCE_SCOPE,
    )
    evidence = EvidenceItemV4(
        f"pipl-{article}-evidence", document_ref,
        (CanonicalLocatorV4("page", f"pipl-{article}.txt", 1, 0, len(document)),),
        (custody_ref,), "NONE", "REVIEWED",
    )
    evidence_ref = ContentRefV4(EVIDENCE_ITEM_KIND, evidence.canonical_digest())
    artifacts.append(_case_artifact(
        len(artifacts) + 1, evidence_ref, evidence.canonical_bytes(), scope=CASE_EVIDENCE_SCOPE,
    ))
    candidate = FactCandidateV4(
        f"pipl-{variant}-candidate", proposition_ref, "boolean", value_ref,
        (evidence_ref,), "lawyer", None,
    )
    candidate_ref = ContentRefV4(FACT_CANDIDATE_KIND, candidate.canonical_digest())
    artifacts.append(_case_artifact(
        len(artifacts) + 1, candidate_ref, candidate.canonical_bytes(), scope=FACT_ADMISSION_SCOPE,
    ))
    rule_ref = next(
        ref for ref, rule in zip(
            loaded.verified_pack.manifest.rule_refs, loaded.verified_pack.rules, strict=True
        ) if rule.rule_id == f"PIPL-ART-{article:03d}"
    )
    placeholder = ContentRefV4("placeholder", DigestV4.from_bytes(b"placeholder"))
    seed_request = CaseRequestV4(
        f"pipl-{variant}-request", "jc/4.0",
        LegalContextV4("CN", "中华人民共和国个人信息保护法"), now,
        source_bundle_ref, placeholder, (placeholder,), loaded.pack_ref,
        (RequestedOutputV4("semantic_result", "json", "zh-CN"),), (rule_ref,),
    )
    request_binding = case_request_binding_ref(seed_request)
    binding_body = {
        "schema_version": "jc/case-request-binding/1.0",
        "request_id": seed_request.request_id,
        "request_schema_version": seed_request.schema_version,
        "legal_context": seed_request.legal_context.to_dict(),
        "decision_time": seed_request.decision_time.to_dict(),
        "source_bundle_ref": seed_request.source_bundle_ref.to_dict(),
        "rule_pack_ref": seed_request.rule_pack_ref.to_dict(),
        "requested_outputs": [item.to_dict() for item in seed_request.requested_outputs],
        "proposal_refs": [item.to_dict() for item in seed_request.proposal_refs],
    }
    assert DigestV4.from_bytes(canonical_bytes(binding_body)) == request_binding.digest
    manifest_body = {
        "manifest_id": f"pipl-{variant}-manifest", "request_ref": request_binding.to_dict(),
        "case_scope": CASE_SCOPE, "items": [evidence.to_dict()],
        "fact_candidate_refs": [candidate_ref.to_dict()], "contradictions": [],
    }
    manifest = EvidenceManifestV4.from_dict({
        **manifest_body, "manifest_digest": str(digest_value(manifest_body)),
    })
    manifest_ref = ContentRefV4(EVIDENCE_MANIFEST_KIND, manifest.canonical_digest())
    artifacts.append(_case_artifact(
        len(artifacts) + 1, manifest_ref, canonical_bytes(manifest.digest_body()),
        scope=CASE_EVIDENCE_SCOPE,
    ))
    legal_evidence = fact_attestation_evidence_refs(
        request_binding_ref=request_binding, manifest_ref=manifest_ref,
        candidate_ref=candidate_ref, proposition_ref=proposition_ref, value_ref=value_ref,
        source_refs=(source_ref,), evidence_refs=(evidence_ref,),
        replay_policy_ref=loaded.policy.replay_policy_ref,
    )
    attestation_body = {
        "attestation_id": f"pipl-{variant}-attestation", "candidate_ref": candidate_ref.to_dict(),
        "request_ref": request_binding.to_dict(), "case_scope": CASE_SCOPE,
        "proposition_digest": str(proposition_ref.digest), "value_digest": str(value_ref.digest),
        "source_refs": [source_ref.to_dict()], "evidence_refs": [evidence_ref.to_dict()],
        "interpretation_version": "local-production-v1",
        "admission_basis": "documentary_evidence_human_reviewed",
        "issuer_role": "legal_reviewer", "issued_at": now.to_dict(),
        "expires_at": loaded.policy.valid_to.to_dict(), "dispute_state": dispute_state,
        "assumption_state": assumption_state, "nonce": f"pipl-{variant}-legal-fact",
        "replay_policy_ref": loaded.policy.replay_policy_ref.to_dict(), "revocation_ref": None,
    }
    signature_body = {
        "algorithm": "Ed25519", "key_id": "local-production-legal-key",
        "issuer": "local-production-legal-issuer", "role": "legal_reviewer",
        "scope": "legal-approval", "kind": "legal-approval", "schema_version": "jc/4.0",
        "subject_digest": str(candidate_ref.digest), "run_identity_ref": None,
        "status": "APPROVED", "issued_at": now.to_dict(),
        "expires_at": loaded.policy.valid_to.to_dict(), "nonce": f"pipl-{variant}-legal-fact",
        "evidence_refs": [item.to_dict() for item in legal_evidence],
        "payload_digest": str(digest_value(attestation_body)),
        "policy_digest": str(loaded.policy.policy_digest),
        "revocation_ref": loaded.policy.revocation_policy_ref.to_dict(),
    }
    signature = SignatureEnvelopeV4.from_dict({
        **signature_body,
        "signature": b64encode(_legal_key(material).sign(canonical_bytes(signature_body))).decode("ascii"),
    })
    attestation = FactAttestationV4.from_dict({
        **attestation_body, "signature": signature.to_dict(),
    })
    attestation_ref = ContentRefV4(FACT_ATTESTATION_KIND, attestation.canonical_digest())
    artifacts.append(_case_artifact(
        len(artifacts) + 1, attestation_ref, attestation.canonical_bytes(),
        scope=LEGAL_APPROVAL_SCOPE,
    ))
    request = replace(
        seed_request, evidence_manifest_ref=manifest_ref,
        fact_attestation_refs=(attestation_ref,),
    )
    body = {
        "schema_version": "jc/case-input-bundle/1.0",
        "bundle_id": f"pipl-{variant}-bundle", "request": request.to_dict(),
        "artifacts": [item.to_dict() for item in artifacts],
    }
    return CaseInputBundleV4.from_dict({
        **body, "bundle_digest": str(digest_value(body)),
    })


@pytest.fixture()
def bundle_factory(production_material: ProductionMaterial):
    def build(article: int = 13, **options: object) -> CaseInputBundleV4:
        return production_bundle(article, material=production_material, **options)

    return build


@pytest.mark.parametrize("article", range(13, 19))
def test_six_article_real_production_chain_and_handles(
    article: int, tmp_path: Path, monkeypatch, bundle_factory,
    production_material: ProductionMaterial,
) -> None:
    config = runtime_config(tmp_path / "runtime.json", tmp_path / "state", production_material)
    monkeypatch.setenv("JC_PRODUCTION_CONFIG", str(config))
    client = create_client()
    output = client.evaluate_for_mcp(MCPEvaluateInputV4(bundle_factory(article)))
    assert output.result.decision_status is DecisionStatusV4.ACCEPTED_FORMAL_RESULT, (
        output.result.decision_reason_codes,
        output.result.interruption_state,
    )
    assert output.certificate_handle.kind == "audit-certificate-binding"
    verified = client.verify_run(output.run_handle)
    assert verified.verification.status == "VERIFIED"
    page = client.read_artifact(
        output.certificate_handle, offset=0, length=output.certificate_handle.size_bytes
    )
    assert page.eof is True
    assert DigestV4.from_bytes(b64decode(page.content_base64, validate=True)) == output.certificate_handle.content_ref.digest
    replay = client.verify_for_mcp(output.run_handle, offline_replay=True).replay
    assert replay is not None and replay.status == "MATCH" and replay.semantic_equal is True


@pytest.mark.parametrize(
    ("options", "expected"),
    (
        ({"fact_key": "pipl.unrelated.fact"}, DecisionStatusV4.MISSING_REQUIRED_FACT),
        ({"dispute_state": "DISPUTED"}, DecisionStatusV4.REVIEW_ONLY_RESULT),
        (
            {"assumption_state": "USER_ASSUMED"},
            DecisionStatusV4.HYPOTHETICAL_RESULT,
        ),
    ),
)
def test_real_production_nonformal_state_matrix(
    options: dict[str, str], expected: DecisionStatusV4,
    tmp_path: Path, monkeypatch, bundle_factory,
    production_material: ProductionMaterial,
) -> None:
    config = runtime_config(tmp_path / "runtime.json", tmp_path / "state", production_material)
    monkeypatch.setenv("JC_PRODUCTION_CONFIG", str(config))
    output = create_client().evaluate_for_mcp(
        MCPEvaluateInputV4(bundle_factory(15, **options))
    )
    assert output.result.decision_status is expected
    assert output.result.certificate_kind.value == "none"
