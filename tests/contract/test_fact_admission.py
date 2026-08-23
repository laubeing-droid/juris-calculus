from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import DigestV4, canonical_bytes, digest_value
from compiler_core.contracts import (
    CanonicalLocatorV4,
    CanonicalTimeV4,
    CaseRequestV4,
    ContentRefV4,
    ContradictionRefV4,
    ContractV4Error,
    EvidenceItemV4,
    EvidenceManifestV4,
    FactAdmissionReceiptV4,
    FactAttestationV4,
    FactCandidateV4,
    LegalContextV4,
    RequestedOutputV4,
    RunIdentityV4,
    SignatureEnvelopeV4,
    SourceBundleV4,
    SourceSnapshotV4,
    TrustPolicyV4,
)
from compiler_core.fact_admission import (
    ADMITTED_FACT_KIND,
    CASE_EVIDENCE_SCOPE,
    CASE_REQUEST_BINDING_KIND,
    CASE_REQUEST_KIND,
    CASE_REQUEST_SCOPE,
    EVIDENCE_CUSTODY_KIND,
    EVIDENCE_DOCUMENT_KIND,
    EVIDENCE_ITEM_KIND,
    EVIDENCE_MANIFEST_KIND,
    FACT_ADMISSION_RECEIPT_KIND,
    FACT_ADMISSION_SCOPE,
    FACT_ATTESTATION_KIND,
    FACT_CANDIDATE_KIND,
    FACT_PROPOSITION_KIND,
    FACT_VALUE_KIND,
    LEGAL_APPROVAL_SCOPE,
    RUN_IDENTITY_KIND,
    RUN_IDENTITY_SCOPE,
    TRUST_POLICY_KIND,
    FactAdmissionServiceV4,
    case_request_binding_ref,
    evidence_item_ref,
    fact_attestation_evidence_refs,
)
from compiler_core.source_service import (
    SOURCE_AUTHENTICITY_RECEIPT_KIND,
    SOURCE_BUNDLE_KIND,
    SOURCE_NORMALIZATION_PROFILE,
    SOURCE_NORMALIZED_KIND,
    SOURCE_PROVENANCE_KIND,
    SOURCE_RAW_KIND,
    SOURCE_SNAPSHOT_KIND,
    SOURCE_STRUCTURE_MAP_KIND,
    SourceServiceV4,
    normalize_source_bytes,
    source_authenticity_payload_digest,
    source_snapshot_ref,
)
from compiler_core.trust import TrustKeyV4, TrustVerifierV4


ROOT = Path(__file__).resolve().parents[2]
P09 = json.loads(
    (ROOT / "tests/fixtures/theory_absorption/p09_fact_admission.json").read_text(
        encoding="utf-8"
    )
)
NOW = CanonicalTimeV4("2026-08-22T12:00:00Z")
LEGAL_ISSUED = CanonicalTimeV4("2026-08-22T10:00:00Z")
SIGNATURE_EXPIRY = CanonicalTimeV4("2027-08-22T00:00:00Z")

SOURCE_PRIVATE = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("11" * 32))
LEGAL_PRIVATE = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("22" * 32))
SERVICE_PRIVATE = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("33" * 32))


def _digest(label: str) -> DigestV4:
    return DigestV4.from_bytes(label.encode())


def _ref(kind: str, label: str) -> ContentRefV4:
    return ContentRefV4(kind, _digest(label))


def _public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _policy() -> TrustPolicyV4:
    body = {
        "policy_id": "w2-02-test-policy",
        "allowed_algorithms": ["Ed25519"],
        "trusted_key_ids": ["source-key", "legal-key", "service-key"],
        "revoked_key_ids": [],
        "allowed_issuers": ["source-authority", "legal-harness", "fact-service"],
        "allowed_roles": ["source_attestor", "legal_reviewer", "service_signer"],
        "allowed_scopes": ["source-authenticity", "legal-approval", "service-certificate"],
        "allowed_artifact_kinds": [SOURCE_SNAPSHOT_KIND, "legal-approval", "service-certificate"],
        "valid_from": {"wire": "2026-01-01T00:00:00Z"},
        "valid_to": {"wire": "2028-01-01T00:00:00Z"},
        "authorization_policy_ref": _ref("policy", "authorization").to_dict(),
        "revocation_policy_ref": _ref("policy", "revocation").to_dict(),
        "replay_policy_ref": _ref("policy", "replay").to_dict(),
        "separation_of_duties_ref": _ref("policy", "separation").to_dict(),
    }
    return TrustPolicyV4.from_dict({**body, "policy_digest": str(digest_value(body))})


def _signature(
    private_key: Ed25519PrivateKey,
    *,
    key_id: str,
    issuer: str,
    role: str,
    scope: str,
    kind: str,
    subject_digest: DigestV4,
    payload_digest: DigestV4,
    evidence_refs: tuple[ContentRefV4, ...],
    policy: TrustPolicyV4,
    nonce: str,
    issued_at: CanonicalTimeV4,
    expires_at: CanonicalTimeV4,
    run_identity_ref: ContentRefV4 | None,
    tamper: bool = False,
) -> SignatureEnvelopeV4:
    body = {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "issuer": issuer,
        "role": role,
        "scope": scope,
        "kind": kind,
        "schema_version": "jc/4.0",
        "subject_digest": str(subject_digest),
        "run_identity_ref": None if run_identity_ref is None else run_identity_ref.to_dict(),
        "status": "APPROVED",
        "issued_at": issued_at.to_dict(),
        "expires_at": expires_at.to_dict(),
        "nonce": nonce,
        "evidence_refs": [item.to_dict() for item in evidence_refs],
        "payload_digest": str(payload_digest),
        "policy_digest": str(policy.policy_digest),
        "revocation_ref": policy.revocation_policy_ref.to_dict(),
    }
    signed = private_key.sign(canonical_bytes(body))
    if tamper:
        signed = bytes([signed[0] ^ 1, *signed[1:]])
    return SignatureEnvelopeV4.from_dict(
        {**body, "signature": b64encode(signed).decode("ascii")}
    )


@dataclass(frozen=True)
class _Stage:
    request_ref: ContentRefV4
    candidate_ref: ContentRefV4
    attestation_ref: ContentRefV4
    run_identity_ref: ContentRefV4
    case_scope: str
    candidate: FactCandidateV4
    evidence_item: EvidenceItemV4


class _Harness:
    def __init__(self) -> None:
        self.resolver = ArtifactResolverV4(max_artifact_bytes=262_144)
        self.policy = _policy()
        keys = (
            TrustKeyV4(
                "source-key", "source-authority", "source-principal",
                ("source_attestor",), ("source-authenticity",),
                (SOURCE_SNAPSHOT_KIND,), _public_bytes(SOURCE_PRIVATE), False,
            ),
            TrustKeyV4(
                "legal-key", "legal-harness", "legal-principal",
                ("legal_reviewer",), ("legal-approval",),
                ("legal-approval",), _public_bytes(LEGAL_PRIVATE), False,
            ),
            TrustKeyV4(
                "service-key", "fact-service", "service-principal",
                ("service_signer",), ("service-certificate",),
                ("service-certificate",), _public_bytes(SERVICE_PRIVATE), False,
            ),
        )
        self.trust = TrustVerifierV4(
            policy=self.policy, keys=keys, target_environment="test"
        )
        self.source_service = SourceServiceV4(self.resolver, self.trust)
        self._registered: set[ContentRefV4] = set()
        self._serial = 0
        self.source_ref, self.bundle_ref = self._stage_source()
        self.service = FactAdmissionServiceV4(
            self.resolver,
            self.source_service,
            self.trust,
            receipt_issuer="fact-service",
            receipt_signer=self._sign_receipt,
        )

    def _register(
        self,
        reference: ContentRefV4,
        content: bytes,
        *,
        kind: str,
        media_type: str,
        scope: str,
    ) -> ContentRefV4:
        if reference in self._registered:
            return reference
        self._serial += 1
        self.resolver.register_bytes(
            artifact_id=f"w2-fact-{self._serial}",
            content_ref=reference,
            artifact_kind=kind,
            media_type=media_type,
            scope=scope,
            content=content,
        )
        self._registered.add(reference)
        return reference

    def _json(self, kind: str, scope: str, payload: dict[str, object]) -> ContentRefV4:
        raw = canonical_bytes(payload)
        reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
        return self._register(
            reference, raw, kind=kind, media_type="application/json", scope=scope
        )

    def _contract(self, kind: str, scope: str, value: object) -> ContentRefV4:
        raw = value.canonical_bytes()
        reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
        return self._register(
            reference, raw, kind=kind, media_type="application/json", scope=scope
        )

    def _digest_body_contract(self, kind: str, scope: str, value: object) -> ContentRefV4:
        raw = canonical_bytes(value.digest_body())
        reference = ContentRefV4(kind, value.canonical_digest())
        return self._register(
            reference, raw, kind=kind, media_type="application/json", scope=scope
        )

    def _stage_source(self) -> tuple[ContentRefV4, ContentRefV4]:
        raw = "第八十五条 人民法院应当调查取证。".encode()
        normalized = normalize_source_bytes(raw)
        raw_ref = self._register(
            ContentRefV4(SOURCE_RAW_KIND, DigestV4.from_bytes(raw)), raw,
            kind=SOURCE_RAW_KIND, media_type="text/plain", scope="source-content",
        )
        normalized_ref = self._register(
            ContentRefV4(SOURCE_NORMALIZED_KIND, DigestV4.from_bytes(normalized)), normalized,
            kind=SOURCE_NORMALIZED_KIND, media_type="text/plain", scope="source-content",
        )
        structure_ref = self._json(
            SOURCE_STRUCTURE_MAP_KIND, "source-provenance",
            {"source_id": "cpl-2021", "kind": "structure-map"},
        )
        provenance_ref = self._json(
            SOURCE_PROVENANCE_KIND, "source-provenance",
            {"source_id": "cpl-2021", "method": "official-download"},
        )
        placeholder = _ref(SOURCE_AUTHENTICITY_RECEIPT_KIND, "source-placeholder")
        snapshot = SourceSnapshotV4(
            "cpl-2021", "CN", "official_first_party", "standing_committee",
            "civil-procedure-law", CanonicalTimeV4("2020-12-24T00:00:00Z"),
            CanonicalTimeV4("2021-01-01T00:00:00Z"), None,
            CanonicalTimeV4("2026-08-01T00:00:00Z"),
            CanonicalLocatorV4("uri", "authority.example/cpl-2021", None, None, None),
            raw_ref.digest, SOURCE_NORMALIZATION_PROFILE, normalized_ref.digest,
            structure_ref, placeholder, (provenance_ref,), "official-download",
            "verified", "permitted",
        )
        source_signature = _signature(
            SOURCE_PRIVATE,
            key_id="source-key", issuer="source-authority", role="source_attestor",
            scope="source-authenticity", kind=SOURCE_SNAPSHOT_KIND,
            subject_digest=snapshot.raw_digest,
            payload_digest=source_authenticity_payload_digest(snapshot),
            evidence_refs=(raw_ref, normalized_ref, structure_ref, provenance_ref),
            policy=self.policy, nonce="source-nonce", issued_at=LEGAL_ISSUED,
            expires_at=SIGNATURE_EXPIRY, run_identity_ref=None,
        )
        receipt_ref = self._contract(
            SOURCE_AUTHENTICITY_RECEIPT_KIND, "source-authenticity", source_signature
        )
        snapshot = replace(snapshot, authenticity_receipt_ref=receipt_ref)
        snapshot_ref = self._contract(
            SOURCE_SNAPSHOT_KIND, "source-authenticity", snapshot
        )
        bundle_body = {
            "bundle_id": "cpl-bundle",
            "root_source_ref": snapshot_ref.to_dict(),
            "terminal_source_ref": snapshot_ref.to_dict(),
            "snapshots": [snapshot.to_dict()],
            "version_edges": [],
        }
        bundle = SourceBundleV4.from_dict(
            {**bundle_body, "bundle_digest": str(digest_value(bundle_body))}
        )
        return snapshot_ref, self._digest_body_contract(
            SOURCE_BUNDLE_KIND, "source-path", bundle
        )

    def _sign_receipt(
        self,
        subject_digest: DigestV4,
        payload_digest: DigestV4,
        evidence_refs: tuple[ContentRefV4, ...],
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> SignatureEnvelopeV4:
        return _signature(
            SERVICE_PRIVATE,
            key_id="service-key", issuer="fact-service", role="service_signer",
            scope="service-certificate", kind="service-certificate",
            subject_digest=subject_digest, payload_digest=payload_digest,
            evidence_refs=evidence_refs, policy=self.policy,
            nonce=f"receipt-{subject_digest.hex}", issued_at=now,
            expires_at=SIGNATURE_EXPIRY, run_identity_ref=run_identity_ref,
        )

    def stage(
        self,
        *,
        request_id: str = "request-1",
        case_scope: str = "case-1",
        candidate_id: str = "candidate-1",
        attestation_id: str = "attestation-1",
        proposition: str = "payment_was_made",
        value_kind: str = "boolean",
        value_artifact_kind: str | None = None,
        attestation_source_refs: tuple[ContentRefV4, ...] | None = None,
        attestation_evidence_refs: tuple[ContentRefV4, ...] | None = None,
        proposition_digest: DigestV4 | None = None,
        value_digest: DigestV4 | None = None,
        dispute_state: str = "UNDISPUTED",
        assumption_state: str = "NONE",
        review_state: str = "REVIEWED",
        contradiction: bool = False,
        expires_at: CanonicalTimeV4 = SIGNATURE_EXPIRY,
        revocation_ref: ContentRefV4 | None = None,
        tamper_signature: bool = False,
        manifest_request_ref: ContentRefV4 | None = None,
        reuse: _Stage | None = None,
    ) -> _Stage:
        if reuse is None:
            proposition_ref = self._json(
                FACT_PROPOSITION_KIND, FACT_ADMISSION_SCOPE,
                {"schema_version": "jc/fact-proposition/1.0", "proposition": proposition},
            )
            value_ref = self._json(
                FACT_VALUE_KIND, FACT_ADMISSION_SCOPE,
                {
                    "schema_version": "jc/fact-value/1.0",
                    "value_kind": value_artifact_kind or value_kind,
                    "value": True,
                },
            )
            document = f"evidence:{request_id}".encode()
            document_ref = self._register(
                ContentRefV4(EVIDENCE_DOCUMENT_KIND, DigestV4.from_bytes(document)),
                document, kind=EVIDENCE_DOCUMENT_KIND,
                media_type="application/octet-stream", scope=CASE_EVIDENCE_SCOPE,
            )
            custody_ref = self._json(
                EVIDENCE_CUSTODY_KIND, CASE_EVIDENCE_SCOPE,
                {"request_id": request_id, "custody": "filed-by-party"},
            )
            item = EvidenceItemV4(
                f"evidence-{request_id}", document_ref,
                (CanonicalLocatorV4("page", "judgment.pdf", 1, 0, 8),),
                (custody_ref,), "NONE", review_state,
            )
            evidence_ref = self._contract(
                EVIDENCE_ITEM_KIND, CASE_EVIDENCE_SCOPE, item
            )
            candidate = FactCandidateV4(
                candidate_id, proposition_ref, value_kind, value_ref,
                (evidence_ref,), "lawyer", None,
            )
            candidate_ref = self._contract(
                FACT_CANDIDATE_KIND, FACT_ADMISSION_SCOPE, candidate
            )
        else:
            candidate = reuse.candidate
            candidate_ref = reuse.candidate_ref
            item = reuse.evidence_item
            evidence_ref = evidence_item_ref(item)

        placeholder_manifest = _ref(EVIDENCE_MANIFEST_KIND, f"manifest-{request_id}")
        placeholder_attestation = _ref(FACT_ATTESTATION_KIND, f"attestation-{request_id}")
        seed_request = CaseRequestV4(
            request_id, "jc/4.0", LegalContextV4("CN", "PRC"),
            CanonicalTimeV4("2026-08-22T00:00:00Z"), self.bundle_ref,
            placeholder_manifest, (placeholder_attestation,), _ref("rule-pack", "rules"),
            (RequestedOutputV4("semantic_result", "json", "zh-CN"),), (),
        )
        request_binding = case_request_binding_ref(seed_request)
        contradiction_values = (
            ContradictionRefV4(
                evidence_ref, _ref(EVIDENCE_ITEM_KIND, "opposing-evidence"),
                "conflict", "unresolved",
            ),
        ) if contradiction else ()
        manifest_body = {
            "manifest_id": f"manifest-{request_id}",
            "request_ref": (manifest_request_ref or request_binding).to_dict(),
            "case_scope": case_scope,
            "items": [item.to_dict()],
            "fact_candidate_refs": [candidate_ref.to_dict()],
            "contradictions": [entry.to_dict() for entry in contradiction_values],
        }
        manifest = EvidenceManifestV4.from_dict(
            {**manifest_body, "manifest_digest": str(digest_value(manifest_body))}
        )
        manifest_ref = self._digest_body_contract(
            EVIDENCE_MANIFEST_KIND, CASE_EVIDENCE_SCOPE, manifest
        )
        declared_sources = attestation_source_refs or (self.source_ref,)
        declared_evidence = attestation_evidence_refs or candidate.evidence_refs
        legal_evidence = fact_attestation_evidence_refs(
            request_binding_ref=request_binding,
            manifest_ref=manifest_ref,
            candidate_ref=candidate_ref,
            proposition_ref=candidate.proposition_ref,
            value_ref=candidate.value_ref,
            source_refs=declared_sources,
            evidence_refs=declared_evidence,
            replay_policy_ref=self.policy.replay_policy_ref,
        )
        nonce = f"legal-{request_id}-{attestation_id}"
        attestation_body = {
            "attestation_id": attestation_id,
            "candidate_ref": candidate_ref.to_dict(),
            "request_ref": request_binding.to_dict(),
            "case_scope": case_scope,
            "proposition_digest": str(proposition_digest or candidate.proposition_ref.digest),
            "value_digest": str(value_digest or candidate.value_ref.digest),
            "source_refs": [item_ref.to_dict() for item_ref in declared_sources],
            "evidence_refs": [item_ref.to_dict() for item_ref in declared_evidence],
            "interpretation_version": "interp-2026-01",
            "admission_basis": "documentary_evidence_human_reviewed",
            "issuer_role": "legal_reviewer",
            "issued_at": LEGAL_ISSUED.to_dict(),
            "expires_at": expires_at.to_dict(),
            "dispute_state": dispute_state,
            "assumption_state": assumption_state,
            "nonce": nonce,
            "replay_policy_ref": self.policy.replay_policy_ref.to_dict(),
            "revocation_ref": None if revocation_ref is None else revocation_ref.to_dict(),
        }
        legal_signature = _signature(
            LEGAL_PRIVATE,
            key_id="legal-key", issuer="legal-harness", role="legal_reviewer",
            scope="legal-approval", kind="legal-approval",
            subject_digest=candidate_ref.digest,
            payload_digest=digest_value(attestation_body), evidence_refs=legal_evidence,
            policy=self.policy, nonce=nonce, issued_at=LEGAL_ISSUED,
            expires_at=expires_at, run_identity_ref=None, tamper=tamper_signature,
        )
        attestation = FactAttestationV4.from_dict(
            {**attestation_body, "signature": legal_signature.to_dict()}
        )
        attestation_ref = self._contract(
            FACT_ATTESTATION_KIND, LEGAL_APPROVAL_SCOPE, attestation
        )
        request = replace(
            seed_request,
            evidence_manifest_ref=manifest_ref,
            fact_attestation_refs=(attestation_ref,),
        )
        assert case_request_binding_ref(request) == request_binding
        request_ref = self._contract(CASE_REQUEST_KIND, CASE_REQUEST_SCOPE, request)
        trust_policy_ref = ContentRefV4(
            TRUST_POLICY_KIND, self.policy.canonical_digest()
        )
        run_body = {
            "request_ref": request_ref.to_dict(),
            "source_bundle_ref": self.bundle_ref.to_dict(),
            "evidence_manifest_ref": manifest_ref.to_dict(),
            "fact_attestation_refs": [attestation_ref.to_dict()],
            "rule_pack_ref": request.rule_pack_ref.to_dict(),
            "engine_version": "4.0.0",
            "engine_source_commit": "a" * 40,
            "engine_source_tree": "b" * 40,
            "engine_build_digest": str(_digest("engine-build")),
            "wheel_digest": str(_digest("wheel")),
            "package_digest": str(_digest("package")),
            "schema_digest": str(_digest("schema")),
            "tool_spec_digest": str(_digest("tool-spec")),
            "lock_digest": str(_digest("lock")),
            "runtime_config_digest": str(_digest("runtime")),
            "algorithm_profile_digest": str(_digest("algorithm")),
            "trust_policy_ref": trust_policy_ref.to_dict(),
            "storage_capability_ref": _ref("storage-capability", "storage").to_dict(),
            "backend_profile_digest": str(
                digest_value({"backend_profile": "fact-admission"})
            ),
        }
        run = RunIdentityV4.from_dict(
            {**run_body, "run_digest": str(digest_value(run_body))}
        )
        run_ref = self._digest_body_contract(RUN_IDENTITY_KIND, RUN_IDENTITY_SCOPE, run)
        return _Stage(
            request_ref, candidate_ref, attestation_ref, run_ref,
            case_scope, candidate, item,
        )

    def admit(self, stage: _Stage, **overrides: object) -> ContentRefV4:
        return self.service.admit(
            stage.request_ref,
            stage.candidate_ref,
            stage.attestation_ref,
            case_scope=overrides.get("case_scope", stage.case_scope),
            run_identity_ref=overrides.get("run_identity_ref", stage.run_identity_ref),
            now=NOW,
        )

    def receipt(self, reference: ContentRefV4) -> FactAdmissionReceiptV4:
        raw = self.resolver.resolve_content(
            reference,
            expected_artifact_kind=FACT_ADMISSION_RECEIPT_KIND,
            expected_media_type="application/json",
            expected_scope=FACT_ADMISSION_SCOPE,
            max_bytes=262_144,
        )
        return FactAdmissionReceiptV4.from_dict(json.loads(raw))


def _error_code(call: Callable[[], object]) -> str:
    with pytest.raises(ContractV4Error) as caught:
        call()
    return caught.value.code


def test_frozen_p09_positive_admits_resolvable_outputs() -> None:
    assert P09["cases"][0]["id"] == "p09-positive-01"
    harness = _Harness()
    stage = harness.stage()
    receipt_ref = harness.admit(stage)
    receipt = harness.receipt(receipt_ref)
    fact_ref = harness.service.verify_receipt(
        receipt_ref,
        request_ref=stage.request_ref,
        case_scope=stage.case_scope,
        run_identity_ref=stage.run_identity_ref,
        now=NOW,
    )
    assert (receipt.status, receipt.fact_ref, fact_ref) == ("ADMITTED", fact_ref, fact_ref)
    assert fact_ref.kind == ADMITTED_FACT_KIND
    assert len({
        receipt.source_gate_receipt_ref.kind,
        receipt.interpretation_gate_receipt_ref.kind,
        receipt.fact_gate_receipt_ref.kind,
    }) == 3


def test_same_scope_retry_is_idempotent() -> None:
    harness = _Harness()
    stage = harness.stage()
    assert harness.admit(stage) == harness.admit(stage)


def test_failed_receipt_signing_does_not_poison_same_scope_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    stage = harness.stage()
    signer = harness.service._receipt_signer

    def fail_signing(*_args: object) -> SignatureEnvelopeV4:
        raise RuntimeError("injected signer outage")

    monkeypatch.setattr(harness.service, "_receipt_signer", fail_signing)
    with pytest.raises(RuntimeError, match="injected signer outage"):
        harness.admit(stage)
    monkeypatch.setattr(harness.service, "_receipt_signer", signer)
    assert harness.admit(stage).kind == FACT_ADMISSION_RECEIPT_KIND


def test_source_and_fact_services_cannot_mix_trust_domains() -> None:
    fact_domain = _Harness()
    source_domain = _Harness()
    assert _error_code(
        lambda: FactAdmissionServiceV4(
            fact_domain.resolver,
            source_domain.source_service,
            fact_domain.trust,
            receipt_issuer="fact-service",
            receipt_signer=fact_domain._sign_receipt,
        )
    ) == "FACT_INPUT_TYPE"


def test_receipt_cannot_outlive_legal_attestation() -> None:
    harness = _Harness()
    stage = harness.stage(expires_at=CanonicalTimeV4("2027-01-01T00:00:00Z"))
    assert _error_code(lambda: harness.admit(stage)) == "FACT_RECEIPT_ENVELOPE"


@pytest.mark.parametrize(
    "extra",
    ({"status": "PASS"}, {"receipt": _ref(FACT_ADMISSION_RECEIPT_KIND, "caller")}),
    ids=("caller-pass", "caller-receipt"),
)
def test_caller_cannot_supply_pass_or_receipt(extra: dict[str, object]) -> None:
    harness = _Harness()
    stage = harness.stage()
    with pytest.raises(TypeError):
        harness.service.admit(
            stage.request_ref,
            stage.candidate_ref,
            stage.attestation_ref,
            case_scope=stage.case_scope,
            run_identity_ref=stage.run_identity_ref,
            now=NOW,
            **extra,
        )


@pytest.mark.parametrize(
    ("field", "expected"),
    (("source", "FACT_ATTESTATION_BINDING"),
     ("evidence", "FACT_ATTESTATION_BINDING"),
     ("proposition", "FACT_ATTESTATION_BINDING"),
     ("value", "FACT_ATTESTATION_BINDING"),
     ("value-kind", "FACT_VALUE_KIND_MISMATCH")),
    ids=("source", "evidence", "proposition", "value", "value-kind"),
)
def test_exact_fact_material_mismatches_fail(field: str, expected: str) -> None:
    harness = _Harness()
    kwargs: dict[str, object] = {}
    if field == "source":
        kwargs["attestation_source_refs"] = (_ref(SOURCE_SNAPSHOT_KIND, "wrong-source"),)
    elif field == "evidence":
        kwargs["attestation_evidence_refs"] = (_ref(EVIDENCE_ITEM_KIND, "wrong-evidence"),)
    elif field == "proposition":
        kwargs["proposition_digest"] = _digest("wrong-proposition")
    elif field == "value":
        kwargs["value_digest"] = _digest("wrong-value")
    else:
        kwargs["value_artifact_kind"] = "string"
    stage = harness.stage(**kwargs)
    assert _error_code(lambda: harness.admit(stage)) == expected


@pytest.mark.parametrize(
    ("dispute_state", "assumption_state"),
    (("UNKNOWN", "NONE"), ("DISPUTED", "NONE"), ("UNDISPUTED", "USER_ASSUMED")),
    ids=("unknown", "disputed", "user-assumed"),
)
def test_nonformal_fact_states_never_admit(
    dispute_state: str, assumption_state: str
) -> None:
    assert P09["cases"][2]["id"] == "p09-missing-01"
    harness = _Harness()
    stage = harness.stage(
        dispute_state=dispute_state, assumption_state=assumption_state
    )
    assert _error_code(lambda: harness.admit(stage)) == "FACT_NOT_FORMAL"


@pytest.mark.parametrize("condition", ("unreviewed", "contradiction"))
def test_unreviewed_or_contradicted_evidence_never_admits(condition: str) -> None:
    harness = _Harness()
    stage = harness.stage(
        review_state="PENDING" if condition == "unreviewed" else "REVIEWED",
        contradiction=condition == "contradiction",
    )
    expected = (
        "FACT_EVIDENCE_NOT_VERIFIED"
        if condition == "unreviewed"
        else "FACT_EVIDENCE_CONTRADICTION"
    )
    assert _error_code(lambda: harness.admit(stage)) == expected


@pytest.mark.parametrize(
    ("condition", "expected"),
    (
        ("expired", "FACT_ATTESTATION_EXPIRED"),
        ("revoked", "FACT_ATTESTATION_REVOKED"),
        ("crypto", "TRUST_SIGNATURE_INVALID"),
    ),
    ids=("expired", "revoked", "forged-crypto"),
)
def test_expired_revoked_or_forged_attestation_fails(
    condition: str, expected: str
) -> None:
    harness = _Harness()
    kwargs: dict[str, object] = {}
    if condition == "expired":
        kwargs["expires_at"] = CanonicalTimeV4("2026-08-22T11:00:00Z")
    elif condition == "revoked":
        kwargs["revocation_ref"] = _ref("revocation", "revoked-attestation")
    else:
        kwargs["tamper_signature"] = True
    stage = harness.stage(**kwargs)
    assert _error_code(lambda: harness.admit(stage)) == expected


@pytest.mark.parametrize(
    ("context", "expected"),
    (
        ("request", "FACT_REQUEST_BINDING"),
        ("case", "FACT_SCOPE_MISMATCH"),
        ("run", "FACT_RUN_BINDING"),
    ),
    ids=("request-projection", "case-scope", "run-identity"),
)
def test_request_case_and_run_bindings_are_exact(context: str, expected: str) -> None:
    harness = _Harness()
    if context == "request":
        stage = harness.stage(
            manifest_request_ref=_ref(CASE_REQUEST_BINDING_KIND, "other-request")
        )
        call = lambda: harness.admit(stage)
    else:
        stage = harness.stage()
        if context == "case":
            call = lambda: harness.admit(stage, case_scope="case-2")
        else:
            other = harness.stage(
                request_id="request-2",
                candidate_id="candidate-2",
                attestation_id="attestation-2",
            )
            call = lambda: harness.admit(stage, run_identity_ref=other.run_identity_ref)
    assert _error_code(call) == expected


@pytest.mark.parametrize("context", ("request", "case", "run"))
def test_receipt_cannot_cross_request_case_or_run(context: str) -> None:
    harness = _Harness()
    stage = harness.stage()
    receipt_ref = harness.admit(stage)
    request_ref = stage.request_ref
    case_scope = stage.case_scope
    run_identity_ref = stage.run_identity_ref
    if context == "request":
        request_ref = _ref(CASE_REQUEST_KIND, "other-request")
    elif context == "case":
        case_scope = "case-2"
    else:
        run_identity_ref = _ref(RUN_IDENTITY_KIND, "other-run")
    assert _error_code(
        lambda: harness.service.verify_receipt(
            receipt_ref,
            request_ref=request_ref,
            case_scope=case_scope,
            run_identity_ref=run_identity_ref,
            now=NOW,
        )
    ) == "FACT_RECEIPT_SCOPE"


def test_handmade_receipt_cannot_verify() -> None:
    harness = _Harness()
    stage = harness.stage()
    receipt = harness.receipt(harness.admit(stage))
    receipt_body = receipt.signature_body()
    forged_signature = _signature(
        LEGAL_PRIVATE,
        key_id="service-key",
        issuer="fact-service",
        role="service_signer",
        scope="service-certificate",
        kind="service-certificate",
        subject_digest=receipt.subject_digest,
        payload_digest=digest_value(receipt_body),
        evidence_refs=receipt.signature.evidence_refs,
        policy=harness.policy,
        nonce="handmade-receipt",
        issued_at=receipt.issued_at,
        expires_at=SIGNATURE_EXPIRY,
        run_identity_ref=stage.run_identity_ref,
    )
    forged = FactAdmissionReceiptV4.from_dict(
        {**receipt_body, "signature": forged_signature.to_dict()}
    )
    forged_ref = harness._contract(
        FACT_ADMISSION_RECEIPT_KIND, FACT_ADMISSION_SCOPE, forged
    )
    assert _error_code(
        lambda: harness.service.verify_receipt(
            forged_ref,
            request_ref=stage.request_ref,
            case_scope=stage.case_scope,
            run_identity_ref=stage.run_identity_ref,
            now=NOW,
        )
    ) == "TRUST_SIGNATURE_INVALID"


@pytest.mark.parametrize("identity", ("candidate", "attestation"))
def test_candidate_or_attestation_id_cannot_be_overwritten(identity: str) -> None:
    harness = _Harness()
    first = harness.stage()
    harness.admit(first)
    if identity == "candidate":
        second = harness.stage(
            request_id="request-2",
            candidate_id=first.candidate.candidate_id,
            attestation_id="attestation-2",
            proposition="payment_was_not_made",
        )
        expected = "FACT_CANDIDATE_ID_COLLISION"
    else:
        second = harness.stage(
            request_id="request-2",
            attestation_id="attestation-1",
            reuse=first,
        )
        expected = "FACT_ATTESTATION_ID_COLLISION"
    assert _error_code(lambda: harness.admit(second)) == expected
