from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import replace
import json
from pathlib import Path
from typing import Callable

import pytest

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.backend_router import backend_profile_digest_v4
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    CanonicalLocatorV4,
    CanonicalTimeV4,
    CaseRequestV4,
    ContentRefV4,
    ContractV4Error,
    EvidenceItemV4,
    EvidenceManifestV4,
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
    RUN_IDENTITY_KIND,
    RUN_IDENTITY_SCOPE,
    FactAdmissionServiceV4,
    case_request_binding_ref,
    evidence_item_ref,
    fact_attestation_evidence_refs,
)
from compiler_core.rule_packs import (
    JSON_MEDIA_TYPE,
    LEGAL_APPROVAL_KIND,
    LEGAL_APPROVAL_SCOPE,
    PACK_SIGNATURE_KIND,
    RULE_COMPONENT_SCOPE,
    RULE_PREMISE_KIND,
    TRUST_POLICY_KIND,
    RulePackVerifierV4,
)
from compiler_core.source_service import (
    SOURCE_BUNDLE_KIND,
    SOURCE_RAW_KIND,
    SOURCE_SNAPSHOT_KIND,
    SourceServiceV4,
    source_snapshot_ref,
)
from compiler_core.trust import TrustKeyV4, TrustVerifierV4
from tools.build_synthetic_pack import _SyntheticPackBuilder


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests/fixtures/packs/synthetic/signed-pack.json"
TRUST_CONTEXT_PATH = ROOT / "tests/fixtures/keys/v4-synthetic-trust.json"

FACT_KEY = "synthetic-positive.required-fact"
CASE_SCOPE = "synthetic-case"
ISSUED_AT = CanonicalTimeV4("2026-08-22T11:00:00Z")
EXPIRES_AT = CanonicalTimeV4("2028-01-01T00:00:00Z")


def _document(path: Path) -> dict[str, object]:
    value = parse_json_document(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _digest(label: str) -> DigestV4:
    return DigestV4.from_bytes(label.encode("utf-8"))


def _ref(kind: str, label: str) -> ContentRefV4:
    return ContentRefV4(kind, _digest(label))


def _error_code(call: Callable[[], object]) -> str:
    with pytest.raises(ContractV4Error) as caught:
        call()
    return caught.value.code


def _keys(trusted: dict[str, object]) -> tuple[TrustKeyV4, ...]:
    return tuple(
        TrustKeyV4(
            key_id=row["key_id"],
            issuer=row["issuer"],
            principal_id=row["principal_id"],
            roles=tuple(row["roles"]),
            scopes=tuple(row["scopes"]),
            artifact_kinds=tuple(row["artifact_kinds"]),
            public_key=b64decode(row["public_key_base64"], validate=True),
            production_allowed=row["production_allowed"],
        )
        for row in trusted["trust_keys"]
    )


class _ChainHarness:
    def __init__(
        self,
        *,
        fixture: dict[str, object] | None = None,
        policy: TrustPolicyV4 | None = None,
        tamper_fact_signature: bool = False,
        backend_profile_digest: DigestV4 | None = None,
    ) -> None:
        self.fixture = _document(FIXTURE_PATH) if fixture is None else fixture
        self.trusted = _document(TRUST_CONTEXT_PATH)
        self.policy = policy or TrustPolicyV4.from_dict(self.trusted["trust_policy"])
        self.backend_profile_digest = (
            backend_profile_digest
            or backend_profile_digest_v4(solver_deadline_ms=2500)
        )
        self.now = CanonicalTimeV4.from_dict(self.trusted["verification_time"])
        self.resolver = ArtifactResolverV4(max_artifact_bytes=262_144)
        for row in self.fixture["artifacts"]:
            self.resolver.register_bytes(
                artifact_id=row["artifact_id"],
                content_ref=ContentRefV4.from_dict(row["content_ref"]),
                artifact_kind=row["artifact_kind"],
                media_type=row["media_type"],
                scope=row["scope"],
                content=b64decode(row["content_base64"], validate=True),
            )
        self.trust = TrustVerifierV4(
            policy=self.policy,
            keys=_keys(self.trusted),
            target_environment="test",
        )
        self.source_service = SourceServiceV4(self.resolver, self.trust)
        identity = self.trusted["runtime_identity"]
        self.pack_verifier = RulePackVerifierV4(
            self.resolver,
            self.source_service,
            self.trust,
            expected_engine_api=identity["engine_api"],
            expected_compiler_build_digest=DigestV4(
                identity["compiler_build_digest"]
            ),
            expected_source_tree_digest=DigestV4(identity["source_tree_digest"]),
            expected_schema_digest=DigestV4(identity["schema_digest"]),
        )
        self._private_keys = _SyntheticPackBuilder().private_keys
        self._serial = 0
        self.pack_ref = ContentRefV4.from_dict(self.fixture["pack_ref"])
        self.candidate_pack_ref = ContentRefV4.from_dict(
            self.fixture["candidate_pack_ref"]
        )
        self._tamper_fact_signature = tamper_fact_signature
        source_rows = [
            row
            for row in self.fixture["artifacts"]
            if row["artifact_kind"] == SOURCE_SNAPSHOT_KIND
        ]
        assert len(source_rows) == 1
        source_raw = b64decode(source_rows[0]["content_base64"], validate=True)
        source_value = parse_json_document(source_raw)
        assert isinstance(source_value, dict)
        self.source = SourceSnapshotV4.from_dict(source_value)
        self.source_ref = ContentRefV4.from_dict(source_rows[0]["content_ref"])
        assert source_snapshot_ref(self.source) == self.source_ref
        self._stage_fact_inputs()
        self.fact_service = FactAdmissionServiceV4(
            self.resolver,
            self.source_service,
            self.trust,
            receipt_issuer="synthetic-service-issuer",
            receipt_signer=self._sign_receipt,
        )

    def _register(
        self,
        reference: ContentRefV4,
        raw: bytes,
        *,
        kind: str,
        scope: str,
        media_type: str = JSON_MEDIA_TYPE,
    ) -> ContentRefV4:
        self._serial += 1
        return self.resolver.register_bytes(
            artifact_id=f"w2-06-chain-{self._serial}",
            content_ref=reference,
            artifact_kind=kind,
            media_type=media_type,
            scope=scope,
            content=raw,
        )

    def _json(self, kind: str, scope: str, value: dict[str, object]) -> ContentRefV4:
        raw = canonical_bytes(value)
        return self._register(
            ContentRefV4(kind, DigestV4.from_bytes(raw)),
            raw,
            kind=kind,
            scope=scope,
        )

    def _contract(self, kind: str, scope: str, value: object) -> ContentRefV4:
        raw = value.canonical_bytes()
        return self._register(
            ContentRefV4(kind, DigestV4.from_bytes(raw)),
            raw,
            kind=kind,
            scope=scope,
        )

    def _digest_contract(self, kind: str, scope: str, value: object) -> ContentRefV4:
        raw = canonical_bytes(value.digest_body())
        return self._register(
            ContentRefV4(kind, value.canonical_digest()),
            raw,
            kind=kind,
            scope=scope,
        )

    def _signature(
        self,
        signer: str,
        *,
        subject_digest: DigestV4,
        payload_digest: DigestV4,
        evidence_refs: tuple[ContentRefV4, ...],
        nonce: str,
        issued_at: CanonicalTimeV4,
        run_identity_ref: ContentRefV4 | None,
    ) -> SignatureEnvelopeV4:
        profiles = {
            "legal": ("legal_reviewer", "legal-approval", "legal-approval"),
            "service": (
                "service_signer",
                "service-certificate",
                "service-certificate",
            ),
        }
        role, scope, kind = profiles[signer]
        body = {
            "algorithm": "Ed25519",
            "key_id": f"synthetic-{signer}-key",
            "issuer": f"synthetic-{signer}-issuer",
            "role": role,
            "scope": scope,
            "kind": kind,
            "schema_version": "jc/4.0",
            "subject_digest": str(subject_digest),
            "run_identity_ref": (
                None if run_identity_ref is None else run_identity_ref.to_dict()
            ),
            "status": "APPROVED",
            "issued_at": issued_at.to_dict(),
            "expires_at": EXPIRES_AT.to_dict(),
            "nonce": nonce,
            "evidence_refs": [item.to_dict() for item in evidence_refs],
            "payload_digest": str(payload_digest),
            "policy_digest": str(self.policy.policy_digest),
            "revocation_ref": self.policy.revocation_policy_ref.to_dict(),
        }
        signature = self._private_keys[signer].sign(canonical_bytes(body))
        return SignatureEnvelopeV4.from_dict(
            {**body, "signature": b64encode(signature).decode("ascii")}
        )

    def _sign_receipt(
        self,
        subject_digest: DigestV4,
        payload_digest: DigestV4,
        evidence_refs: tuple[ContentRefV4, ...],
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> SignatureEnvelopeV4:
        return self._signature(
            "service",
            subject_digest=subject_digest,
            payload_digest=payload_digest,
            evidence_refs=evidence_refs,
            nonce=f"w2-06-service-{subject_digest.hex}",
            issued_at=now,
            run_identity_ref=run_identity_ref,
        )

    def _stage_fact_inputs(self) -> None:
        bundle_body = {
            "bundle_id": "synthetic-source-path",
            "root_source_ref": self.source_ref.to_dict(),
            "terminal_source_ref": self.source_ref.to_dict(),
            "snapshots": [self.source.to_dict()],
            "version_edges": [],
        }
        bundle = SourceBundleV4.from_dict(
            {**bundle_body, "bundle_digest": str(digest_value(bundle_body))}
        )
        self.source_bundle_ref = self._digest_contract(
            SOURCE_BUNDLE_KIND, "source-path", bundle
        )
        proposition_ref = self._json(
            FACT_PROPOSITION_KIND,
            FACT_ADMISSION_SCOPE,
            {"schema_version": "jc/fact-proposition/1.0", "proposition": FACT_KEY},
        )
        value_ref = self._json(
            FACT_VALUE_KIND,
            FACT_ADMISSION_SCOPE,
            {
                "schema_version": "jc/fact-value/1.0",
                "value_kind": "boolean",
                "value": True,
            },
        )
        document = b"synthetic reviewed evidence"
        document_ref = self._register(
            ContentRefV4(EVIDENCE_DOCUMENT_KIND, DigestV4.from_bytes(document)),
            document,
            kind=EVIDENCE_DOCUMENT_KIND,
            media_type="application/octet-stream",
            scope=CASE_EVIDENCE_SCOPE,
        )
        custody_ref = self._json(
            EVIDENCE_CUSTODY_KIND,
            CASE_EVIDENCE_SCOPE,
            {"schema_version": "jc/evidence-custody/1.0", "custody": "test-only"},
        )
        evidence = EvidenceItemV4(
            "synthetic-evidence",
            document_ref,
            (CanonicalLocatorV4("page", "synthetic-evidence.pdf", 1, 0, 10),),
            (custody_ref,),
            "NONE",
            "REVIEWED",
        )
        evidence_ref = self._contract(
            EVIDENCE_ITEM_KIND, CASE_EVIDENCE_SCOPE, evidence
        )
        assert evidence_ref == evidence_item_ref(evidence)
        candidate = FactCandidateV4(
            "synthetic-fact-candidate",
            proposition_ref,
            "boolean",
            value_ref,
            (evidence_ref,),
            "lawyer",
            None,
        )
        self.candidate_ref = self._contract(
            FACT_CANDIDATE_KIND, FACT_ADMISSION_SCOPE, candidate
        )
        placeholder_manifest = _ref(EVIDENCE_MANIFEST_KIND, "w2-06-manifest")
        placeholder_attestation = _ref(FACT_ATTESTATION_KIND, "w2-06-attestation")
        seed_request = CaseRequestV4(
            "w2-06-request",
            "jc/4.0",
            LegalContextV4("TEST", "synthetic-test-law"),
            self.now,
            self.source_bundle_ref,
            placeholder_manifest,
            (placeholder_attestation,),
            self.pack_ref,
            (RequestedOutputV4("semantic_result", "json", "zh-CN"),),
            (),
        )
        request_binding = case_request_binding_ref(seed_request)
        manifest_body = {
            "manifest_id": "w2-06-evidence-manifest",
            "request_ref": request_binding.to_dict(),
            "case_scope": CASE_SCOPE,
            "items": [evidence.to_dict()],
            "fact_candidate_refs": [self.candidate_ref.to_dict()],
            "contradictions": [],
        }
        manifest = EvidenceManifestV4.from_dict(
            {**manifest_body, "manifest_digest": str(digest_value(manifest_body))}
        )
        manifest_ref = self._digest_contract(
            EVIDENCE_MANIFEST_KIND, CASE_EVIDENCE_SCOPE, manifest
        )
        legal_evidence = fact_attestation_evidence_refs(
            request_binding_ref=request_binding,
            manifest_ref=manifest_ref,
            candidate_ref=self.candidate_ref,
            proposition_ref=proposition_ref,
            value_ref=value_ref,
            source_refs=(self.source_ref,),
            evidence_refs=(evidence_ref,),
            replay_policy_ref=self.policy.replay_policy_ref,
        )
        attestation_body = {
            "attestation_id": "w2-06-fact-attestation",
            "candidate_ref": self.candidate_ref.to_dict(),
            "request_ref": request_binding.to_dict(),
            "case_scope": CASE_SCOPE,
            "proposition_digest": str(proposition_ref.digest),
            "value_digest": str(value_ref.digest),
            "source_refs": [self.source_ref.to_dict()],
            "evidence_refs": [evidence_ref.to_dict()],
            "interpretation_version": "synthetic-v1",
            "admission_basis": "documentary_evidence_human_reviewed",
            "issuer_role": "legal_reviewer",
            "issued_at": ISSUED_AT.to_dict(),
            "expires_at": EXPIRES_AT.to_dict(),
            "dispute_state": "UNDISPUTED",
            "assumption_state": "NONE",
            "nonce": "w2-06-legal-fact",
            "replay_policy_ref": self.policy.replay_policy_ref.to_dict(),
            "revocation_ref": None,
        }
        legal_signature = self._signature(
            "legal",
            subject_digest=self.candidate_ref.digest,
            payload_digest=digest_value(attestation_body),
            evidence_refs=legal_evidence,
            nonce="w2-06-legal-fact",
            issued_at=ISSUED_AT,
            run_identity_ref=None,
        )
        if self._tamper_fact_signature:
            raw_signature = b64decode(legal_signature.signature, validate=True)
            legal_signature = replace(
                legal_signature,
                signature=b64encode(
                    bytes((raw_signature[0] ^ 1,)) + raw_signature[1:]
                ).decode("ascii"),
            )
        self.attestation = FactAttestationV4.from_dict(
            {**attestation_body, "signature": legal_signature.to_dict()}
        )
        self.attestation_ref = self._contract(
            FACT_ATTESTATION_KIND, LEGAL_APPROVAL_SCOPE, self.attestation
        )
        self.request = replace(
            seed_request,
            evidence_manifest_ref=manifest_ref,
            fact_attestation_refs=(self.attestation_ref,),
        )
        assert case_request_binding_ref(self.request) == request_binding
        self.request_ref = self._contract(
            CASE_REQUEST_KIND, CASE_REQUEST_SCOPE, self.request
        )
        identity = self.trusted["runtime_identity"]
        run_body = {
            "request_ref": self.request_ref.to_dict(),
            "source_bundle_ref": self.source_bundle_ref.to_dict(),
            "evidence_manifest_ref": manifest_ref.to_dict(),
            "fact_attestation_refs": [self.attestation_ref.to_dict()],
            "rule_pack_ref": self.pack_ref.to_dict(),
            "engine_version": identity["engine_api"],
            "engine_source_commit": "a" * 40,
            "engine_source_tree": "b" * 40,
            "engine_build_digest": identity["compiler_build_digest"],
            "wheel_digest": str(_digest("w2-06-wheel")),
            "package_digest": str(_digest("w2-06-package")),
            "schema_digest": identity["schema_digest"],
            "tool_spec_digest": str(_digest("w2-06-tool-spec")),
            "lock_digest": str(_digest("w2-06-lock")),
            "runtime_config_digest": str(_digest("w2-06-runtime")),
            "algorithm_profile_digest": str(_digest("w2-06-algorithm")),
            "trust_policy_ref": ContentRefV4(
                TRUST_POLICY_KIND, self.policy.canonical_digest()
            ).to_dict(),
            "storage_capability_ref": _ref(
                "storage-capability", "w2-06-storage"
            ).to_dict(),
            "backend_profile_digest": str(self.backend_profile_digest),
        }
        self.run = RunIdentityV4.from_dict(
            {**run_body, "run_digest": str(digest_value(run_body))}
        )
        self.run_identity_ref = self._digest_contract(
            RUN_IDENTITY_KIND, RUN_IDENTITY_SCOPE, self.run
        )

    def admit_fact(self) -> tuple[ContentRefV4, ContentRefV4]:
        receipt_ref = self.fact_service.admit(
            self.request_ref,
            self.candidate_ref,
            self.attestation_ref,
            case_scope=CASE_SCOPE,
            run_identity_ref=self.run_identity_ref,
            now=self.now,
        )
        fact_ref = self.fact_service.verify_receipt(
            receipt_ref,
            request_ref=self.request_ref,
            case_scope=CASE_SCOPE,
            run_identity_ref=self.run_identity_ref,
            now=self.now,
        )
        return receipt_ref, fact_ref

    def verify_pack(self, *, candidate: bool = False):
        return self.pack_verifier.verify(
            self.candidate_pack_ref if candidate else self.pack_ref,
            now=self.now,
        )


def test_source_trust_is_derived_from_resolved_bytes() -> None:
    harness = _ChainHarness()
    assert harness.source_service.admit_snapshot(
        harness.source_ref, now=harness.now
    ) == harness.source_ref
    assert harness.source_service.resolve_applicable(
        harness.source_bundle_ref, decision_time=harness.now
    ) == harness.source_ref


def test_applicability_consumes_verified_source_version_path() -> None:
    harness = _ChainHarness()
    harness.source_service.admit_snapshot(harness.source_ref, now=harness.now)
    assert harness.source_service.resolve_applicable(
        harness.source_bundle_ref, decision_time=harness.now
    ) == harness.source_ref


def test_source_path_is_bound_to_resolved_authority_root() -> None:
    harness = _ChainHarness()
    harness.source_service.admit_snapshot(harness.source_ref, now=harness.now)
    forged_body = {
        "bundle_id": "caller-rebound-root",
        "root_source_ref": _ref(SOURCE_SNAPSHOT_KIND, "caller-root").to_dict(),
        "terminal_source_ref": harness.source_ref.to_dict(),
        "snapshots": [harness.source.to_dict()],
        "version_edges": [],
    }
    forged = SourceBundleV4.from_dict(
        {**forged_body, "bundle_digest": str(digest_value(forged_body))}
    )
    forged_ref = harness._digest_contract(SOURCE_BUNDLE_KIND, "source-path", forged)
    assert _error_code(
        lambda: harness.source_service.resolve_applicable(
            forged_ref, decision_time=harness.now
        )
    ) == "SOURCE_PATH_ENDPOINT"


def test_fact_admission_consumes_verified_source_receipt() -> None:
    harness = _ChainHarness()
    receipt_ref, fact_ref = harness.admit_fact()
    assert receipt_ref.kind == FACT_ADMISSION_RECEIPT_KIND
    fact = parse_json_document(harness.resolver.resolve_content(
        fact_ref,
        expected_artifact_kind=ADMITTED_FACT_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=FACT_ADMISSION_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    ))
    assert isinstance(fact, dict)
    assert fact["source_refs"] == [harness.source_ref.to_dict()]
    assert fact["candidate_ref"] == harness.candidate_ref.to_dict()


def test_public_fact_cannot_self_issue_admission() -> None:
    harness = _ChainHarness()
    assert _error_code(
        lambda: harness.fact_service.admit(
            {"status": "PASS"},
            harness.candidate_ref,
            harness.attestation_ref,
            case_scope=CASE_SCOPE,
            run_identity_ref=harness.run_identity_ref,
            now=harness.now,
        )
    ) == "FACT_INPUT_TYPE"


def test_rule_activation_consumes_verified_promotion_and_pack() -> None:
    harness = _ChainHarness()
    _, fact_ref = harness.admit_fact()
    verified = harness.verify_pack()
    assert verified.status == "VERIFIED_ACTIVE" and verified.verifier_issued
    rule = next(item for item in verified.rules if item.rule_id == "synthetic-positive")
    assert harness.request.rule_pack_ref == harness.run.rule_pack_ref == verified.pack_ref
    assert rule.source_snapshot_ref == harness.source_ref
    premise = parse_json_document(harness.resolver.resolve_content(
        rule.premise_refs[0],
        expected_artifact_kind=RULE_PREMISE_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=RULE_COMPONENT_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    ))
    fact = parse_json_document(harness.resolver.resolve_content(
        fact_ref,
        expected_artifact_kind=ADMITTED_FACT_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=FACT_ADMISSION_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    ))
    proposition = parse_json_document(harness.resolver.resolve_content(
        ContentRefV4.from_dict(fact["proposition_ref"]),
        expected_artifact_kind=FACT_PROPOSITION_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=FACT_ADMISSION_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    ))
    assert premise["fact_key"] == proposition["proposition"] == FACT_KEY
