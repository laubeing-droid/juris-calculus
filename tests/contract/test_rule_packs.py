from __future__ import annotations

from base64 import b64encode
from dataclasses import replace
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import DigestV4, canonical_bytes, digest_value
from compiler_core.contracts import (
    CanonicalLocatorV4,
    CanonicalTimeV4,
    ContentRefV4,
    ContractV4Error,
    PackManifestV4,
    PackSignatureV4,
    RulePromotionReceiptV4,
    RuleV4,
    SignatureEnvelopeV4,
    SourceSnapshotV4,
    TrustPolicyV4,
)
from compiler_core.rule_packs import (
    BUILD_ATTESTATION_KIND,
    ENGINEERING_APPROVAL_KIND,
    LEGAL_APPROVAL_KIND,
    PACK_BUILD_SUBJECT_KIND,
    PACK_CONFIG_KIND,
    PACK_COVERAGE_RECEIPT_KIND,
    PACK_MANIFEST_KIND,
    PACK_SIGNATURE_KIND,
    PACK_VERIFICATION_RECEIPT_KIND,
    RULE_KIND,
    RULE_AUTHORITY_KIND,
    RULE_COMPONENT_SCOPE,
    RULE_CONCLUSION_KIND,
    RULE_DEFINED_TERM_KIND,
    RULE_INTERPRETATION_KIND,
    RULE_PACK_SCOPE,
    RULE_PERMISSION_KIND,
    RULE_PREMISE_KIND,
    RULE_PROMOTION_RECEIPT_KIND,
    RULE_PROMOTION_SUBJECT_KIND,
    RULE_VARIABLE_KIND,
    RulePackVerifierV4,
    VerifiedRulePackV4,
    build_attestation_evidence_refs,
    build_subject_body,
    build_subject_ref,
    pack_release_evidence_refs,
    promotion_receipt_evidence_refs,
    rule_review_evidence_refs,
    rule_promotion_subject_body,
    rule_promotion_subject_ref,
)
from compiler_core.source_service import (
    SOURCE_AUTHENTICITY_RECEIPT_KIND,
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


NOW = CanonicalTimeV4("2026-08-22T12:00:00Z")
ISSUED = CanonicalTimeV4("2026-08-22T11:00:00Z")
EXPIRES = CanonicalTimeV4("2027-01-01T00:00:00Z")
ENGINE_API = "4.0.0"
COMPILER_BUILD = DigestV4.from_bytes(b"compiler-build")
SOURCE_TREE = DigestV4.from_bytes(b"source-tree")
SCHEMA_DIGEST = DigestV4.from_bytes(b"schema")


def _ref(kind: str, label: str) -> ContentRefV4:
    return ContentRefV4(kind, DigestV4.from_bytes(label.encode()))


def _error_code(call: Callable[[], object]) -> str:
    with pytest.raises(ContractV4Error) as caught:
        call()
    return caught.value.code


class _PackHarness:
    """Real Ed25519/resolved-byte graph for the W2-03 public verifier."""

    _profiles = {
        "source": ("source_attestor", "source-authenticity", SOURCE_SNAPSHOT_KIND),
        "legal": ("legal_reviewer", "legal-approval", LEGAL_APPROVAL_KIND),
        "engineering": (
            "engineering_reviewer",
            "engineering-approval",
            ENGINEERING_APPROVAL_KIND,
        ),
        "service": ("service_signer", "service-certificate", "service-certificate"),
        "build": ("build_attestor", "build-attestation", BUILD_ATTESTATION_KIND),
        "release": ("pack_releaser", "pack-release", "rule-pack"),
    }

    def __init__(
        self,
        *,
        same_review_principal: bool = False,
        same_source_and_legal_principal: bool = False,
        cross_rule_role_overlap: bool = False,
        revoked_nonces: tuple[str, ...] = (),
        target_environment: str = "test",
        expected_engine_api: str = ENGINE_API,
        expected_compiler_build_digest: DigestV4 = COMPILER_BUILD,
        expected_source_tree_digest: DigestV4 = SOURCE_TREE,
        expected_schema_digest: DigestV4 = SCHEMA_DIGEST,
    ) -> None:
        self.resolver = ArtifactResolverV4(max_artifact_bytes=262_144)
        self.private_keys = {
            name: Ed25519PrivateKey.from_private_bytes(bytes([index]) * 32)
            for index, name in enumerate(self._profiles, 1)
        }
        key_ids = tuple(f"w2-03-{name}-key" for name in self._profiles)
        issuers = tuple(f"w2-03-{name}-issuer" for name in self._profiles)
        policy_body = {
            "policy_id": "w2-03-test-policy",
            "allowed_algorithms": ["Ed25519"],
            "trusted_key_ids": list(key_ids),
            "revoked_key_ids": [],
            "allowed_issuers": list(issuers),
            "allowed_roles": [value[0] for value in self._profiles.values()],
            "allowed_scopes": [value[1] for value in self._profiles.values()],
            "allowed_artifact_kinds": [value[2] for value in self._profiles.values()],
            "valid_from": {"wire": "2026-01-01T00:00:00Z"},
            "valid_to": {"wire": "2028-01-01T00:00:00Z"},
            "authorization_policy_ref": _ref("trust-authorization-policy", "auth").to_dict(),
            "revocation_policy_ref": _ref("trust-revocation-policy", "revocation").to_dict(),
            "replay_policy_ref": _ref("trust-replay-policy", "replay").to_dict(),
            "separation_of_duties_ref": _ref("trust-separation-policy", "separation").to_dict(),
        }
        self.policy = TrustPolicyV4.from_dict({
            **policy_body,
            "policy_digest": str(digest_value(policy_body)),
        })
        keys = []
        for name, (role, scope, kind) in self._profiles.items():
            principal = (
                "w2-03-shared-reviewer"
                if same_review_principal and name in {"legal", "engineering"}
                else "w2-03-shared-source-legal"
                if same_source_and_legal_principal and name in {"source", "legal"}
                else f"w2-03-{name}-principal"
            )
            profiles = (
                (self._profiles["legal"], self._profiles["engineering"])
                if cross_rule_role_overlap and name in {"legal", "engineering"}
                else ((role, scope, kind),)
            )
            keys.append(TrustKeyV4(
                key_id=f"w2-03-{name}-key",
                issuer=f"w2-03-{name}-issuer",
                principal_id=principal,
                roles=tuple(profile[0] for profile in profiles),
                scopes=tuple(profile[1] for profile in profiles),
                artifact_kinds=tuple(profile[2] for profile in profiles),
                public_key=self.private_keys[name].public_key().public_bytes(
                    serialization.Encoding.Raw,
                    serialization.PublicFormat.Raw,
                ),
                production_allowed=False,
            ))
        self.trust = TrustVerifierV4(
            policy=self.policy,
            keys=tuple(keys),
            target_environment=target_environment,
            revoked_nonces=revoked_nonces,
        )
        self.source_service = SourceServiceV4(self.resolver, self.trust)
        self.verifier = RulePackVerifierV4(
            self.resolver,
            self.source_service,
            self.trust,
            expected_engine_api=expected_engine_api,
            expected_compiler_build_digest=expected_compiler_build_digest,
            expected_source_tree_digest=expected_source_tree_digest,
            expected_schema_digest=expected_schema_digest,
        )
        self.cross_rule_role_overlap = cross_rule_role_overlap
        self._serial = 0

    def _store(
        self,
        reference: ContentRefV4,
        content: bytes,
        *,
        scope: str = RULE_PACK_SCOPE,
        artifact_kind: str | None = None,
        media_type: str = "application/json",
    ) -> ContentRefV4:
        self._serial += 1
        return self.resolver.register_bytes(
            artifact_id=f"w2-03-{self._serial}",
            content_ref=reference,
            artifact_kind=reference.kind if artifact_kind is None else artifact_kind,
            media_type=media_type,
            scope=scope,
            content=content,
        )

    def _json(self, kind: str, value: dict[str, object]) -> ContentRefV4:
        raw = canonical_bytes(value)
        reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
        return self._store(reference, raw)

    def _sign(
        self,
        signer: str,
        *,
        subject_digest: DigestV4,
        payload_digest: DigestV4,
        evidence_refs: tuple[ContentRefV4, ...],
        nonce: str,
        issued_at: CanonicalTimeV4 = ISSUED,
        expires_at: CanonicalTimeV4 = EXPIRES,
        profile_override: tuple[str, str, str] | None = None,
        corrupt: bool = False,
    ) -> SignatureEnvelopeV4:
        role, scope, kind = profile_override or self._profiles[signer]
        body = {
            "algorithm": "Ed25519",
            "key_id": f"w2-03-{signer}-key",
            "issuer": f"w2-03-{signer}-issuer",
            "role": role,
            "scope": scope,
            "kind": kind,
            "schema_version": "jc/4.0",
            "subject_digest": str(subject_digest),
            "run_identity_ref": None,
            "status": "APPROVED",
            "issued_at": issued_at.to_dict(),
            "expires_at": expires_at.to_dict(),
            "nonce": nonce,
            "evidence_refs": [item.to_dict() for item in evidence_refs],
            "payload_digest": str(payload_digest),
            "policy_digest": str(self.policy.policy_digest),
            "revocation_ref": self.policy.revocation_policy_ref.to_dict(),
        }
        signature = self.private_keys[signer].sign(canonical_bytes(body))
        if corrupt:
            signature = bytes([signature[0] ^ 1, *signature[1:]])
        return SignatureEnvelopeV4.from_dict({
            **body,
            "signature": b64encode(signature).decode("ascii"),
        })

    def _stage_source(self, *, forged: bool = False) -> tuple[ContentRefV4, SourceSnapshotV4]:
        raw = "第八十五条 人民法院应当调查取证。".encode()
        normalized = normalize_source_bytes(raw)
        raw_ref = ContentRefV4(SOURCE_RAW_KIND, DigestV4.from_bytes(raw))
        normalized_ref = ContentRefV4(SOURCE_NORMALIZED_KIND, DigestV4.from_bytes(normalized))
        self._store(
            raw_ref,
            raw,
            scope="source-content",
            artifact_kind=SOURCE_RAW_KIND,
            media_type="text/plain",
        )
        self._store(
            normalized_ref,
            normalized,
            scope="source-content",
            artifact_kind=SOURCE_NORMALIZED_KIND,
            media_type="text/plain",
        )
        structure_raw = canonical_bytes({
            "schema_version": "jc/source-structure/1.0",
            "sections": ["article-85"],
        })
        structure_ref = ContentRefV4(
            SOURCE_STRUCTURE_MAP_KIND, DigestV4.from_bytes(structure_raw)
        )
        self._store(
            structure_ref,
            structure_raw,
            scope="source-provenance",
            artifact_kind=SOURCE_STRUCTURE_MAP_KIND,
        )
        provenance_raw = canonical_bytes({
            "schema_version": "jc/source-provenance/1.0",
            "method": "official-download",
        })
        provenance_ref = ContentRefV4(
            SOURCE_PROVENANCE_KIND, DigestV4.from_bytes(provenance_raw)
        )
        self._store(
            provenance_ref,
            provenance_raw,
            scope="source-provenance",
            artifact_kind=SOURCE_PROVENANCE_KIND,
        )
        placeholder = _ref(SOURCE_AUTHENTICITY_RECEIPT_KIND, "source-placeholder")
        snapshot = SourceSnapshotV4(
            source_id="cn-cpl-article-85",
            jurisdiction="CN",
            authority_tier="official_first_party",
            issuer="npc-standing-committee",
            title="civil-procedure-law",
            publication_time=CanonicalTimeV4("2021-12-24T00:00:00Z"),
            effective_from=CanonicalTimeV4("2022-01-01T00:00:00Z"),
            effective_to=None,
            retrieved_at=CanonicalTimeV4("2026-08-01T00:00:00Z"),
            canonical_locator=CanonicalLocatorV4(
                "uri", "authority.example/cpl/article-85", None, None, None
            ),
            raw_digest=raw_ref.digest,
            normalization_profile=SOURCE_NORMALIZATION_PROFILE,
            normalized_digest=normalized_ref.digest,
            structure_map_ref=structure_ref,
            authenticity_receipt_ref=placeholder,
            provenance_refs=(provenance_ref,),
            acquisition_method="official-download",
            license_status="verified",
            distribution_status="permitted",
        )
        source_signature = self._sign(
            "source",
            subject_digest=snapshot.raw_digest,
            payload_digest=source_authenticity_payload_digest(snapshot),
            evidence_refs=(raw_ref, normalized_ref, structure_ref, provenance_ref),
            nonce="source-nonce",
            corrupt=forged,
        )
        signature_raw = source_signature.canonical_bytes()
        signature_ref = ContentRefV4(
            SOURCE_AUTHENTICITY_RECEIPT_KIND,
            DigestV4.from_bytes(signature_raw),
        )
        self._store(
            signature_ref,
            signature_raw,
            scope="source-authenticity",
            artifact_kind=SOURCE_AUTHENTICITY_RECEIPT_KIND,
        )
        snapshot = replace(snapshot, authenticity_receipt_ref=signature_ref)
        snapshot_ref = source_snapshot_ref(snapshot)
        self._store(
            snapshot_ref,
            snapshot.canonical_bytes(),
            scope="source-authenticity",
            artifact_kind=SOURCE_SNAPSHOT_KIND,
        )
        return snapshot_ref, snapshot

    def _rule_material_ref(self, kind: str, label: str) -> ContentRefV4:
        raw = canonical_bytes({
            "schema_version": f"jc/{kind}/1.0",
            "id": label,
        })
        reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
        return self._store(reference, raw, scope=RULE_COMPONENT_SCOPE)

    def _stage_rule(
        self,
        index: int,
        source_ref: ContentRefV4,
        source: SourceSnapshotV4,
        *,
        candidate: bool,
        wrong_locator: bool,
        wrong_structure: bool,
        missing_review: bool,
        promotion_nonce: str,
        permission: bool,
    ) -> tuple[ContentRefV4, ContentRefV4 | None]:
        authority_ref = self._rule_material_ref(RULE_AUTHORITY_KIND, f"authority-{index}")
        variable_ref = self._rule_material_ref(RULE_VARIABLE_KIND, f"amount-{index}")
        premise_ref = self._rule_material_ref(RULE_PREMISE_KIND, f"premise-{index}")
        conclusion_ref = self._rule_material_ref(RULE_CONCLUSION_KIND, f"conclusion-{index}")
        interpretation_ref = self._rule_material_ref(
            RULE_INTERPRETATION_KIND, f"literal-{index}"
        )
        term_ref = self._rule_material_ref(RULE_DEFINED_TERM_KIND, f"payment-{index}")
        permission_ref = (
            self._rule_material_ref(RULE_PERMISSION_KIND, f"permission-{index}")
            if permission
            else None
        )
        base = {
            "rule_id": f"rule-{index}",
            "jurisdiction": "CN",
            "governing_law": "civil-procedure-law",
            "authority_ref": authority_ref.to_dict(),
            "variable_declaration_refs": [variable_ref.to_dict()],
            "premise_refs": [premise_ref.to_dict()],
            "conclusion_ref": conclusion_ref.to_dict(),
            "modality": "PERMISSION" if permission else "OBLIGATION",
            "permission_ref": permission_ref.to_dict() if permission_ref is not None else None,
            "exception_refs": [],
            "priority_refs": [],
            "attack_refs": [],
            "temporal_constraint_refs": [],
            "numeric_constraint_refs": [],
            "source_snapshot_ref": source_ref.to_dict(),
            "source_locator": (
                CanonicalLocatorV4("uri", "authority.example/wrong", None, None, None)
                if wrong_locator
                else source.canonical_locator
            ).to_dict(),
            "source_structure_ref": (
                _ref(SOURCE_STRUCTURE_MAP_KIND, "wrong-structure")
                if wrong_structure
                else source.structure_map_ref
            ).to_dict(),
            "interpretation_choice_refs": [interpretation_ref.to_dict()],
            "defined_term_refs": [term_ref.to_dict()],
            "promotion_receipt_refs": [],
            "effective_from": {"wire": "2022-01-01T00:00:00Z"},
            "effective_to": None,
        }
        draft = RuleV4.from_dict({**base, "rule_digest": str(digest_value(base))})
        if candidate:
            rule = draft
            promotion_ref = None
        else:
            subject_body = rule_promotion_subject_body(draft)
            subject_ref = rule_promotion_subject_ref(draft)
            self._store(
                subject_ref,
                canonical_bytes(subject_body),
                artifact_kind=RULE_PROMOTION_SUBJECT_KIND,
            )
            legal_evidence = rule_review_evidence_refs(
                draft,
                subject_ref,
                self.policy.replay_policy_ref,
                "legal",
            )
            legal_signer = (
                "engineering" if self.cross_rule_role_overlap and index == 2 else "legal"
            )
            legal = self._sign(
                legal_signer,
                subject_digest=subject_ref.digest,
                payload_digest=DigestV4.from_bytes(canonical_bytes(subject_body)),
                evidence_refs=legal_evidence,
                nonce=promotion_nonce,
                profile_override=self._profiles["legal"],
            )
            legal_ref = ContentRefV4(
                LEGAL_APPROVAL_KIND, DigestV4.from_bytes(legal.canonical_bytes())
            )
            self._store(
                legal_ref,
                legal.canonical_bytes(),
                scope="legal-approval",
                artifact_kind=LEGAL_APPROVAL_KIND,
            )
            if missing_review:
                engineering_ref = _ref(ENGINEERING_APPROVAL_KIND, "missing-engineering")
            else:
                engineering_signer = (
                    "legal" if self.cross_rule_role_overlap and index == 2 else "engineering"
                )
                engineering = self._sign(
                    engineering_signer,
                    subject_digest=subject_ref.digest,
                    payload_digest=DigestV4.from_bytes(canonical_bytes(subject_body)),
                    evidence_refs=rule_review_evidence_refs(
                        draft,
                        subject_ref,
                        self.policy.replay_policy_ref,
                        "engineering",
                    ),
                    nonce=f"engineering-{index}",
                    profile_override=self._profiles["engineering"],
                )
                engineering_ref = ContentRefV4(
                    ENGINEERING_APPROVAL_KIND,
                    DigestV4.from_bytes(engineering.canonical_bytes()),
                )
                self._store(
                    engineering_ref,
                    engineering.canonical_bytes(),
                    scope="engineering-approval",
                    artifact_kind=ENGINEERING_APPROVAL_KIND,
                )
            receipt_body = {
                "receipt_id": f"rule-promotion-{index}",
                "rule_subject_digest": str(subject_ref.digest),
                "legal_review_ref": legal_ref.to_dict(),
                "engineering_review_ref": engineering_ref.to_dict(),
                "status": "APPROVED",
                "issued_at": ISSUED.to_dict(),
            }
            service = self._sign(
                "service",
                subject_digest=subject_ref.digest,
                payload_digest=digest_value(receipt_body),
                evidence_refs=promotion_receipt_evidence_refs(
                    subject_ref,
                    legal_ref,
                    engineering_ref,
                    self.policy.replay_policy_ref,
                ),
                nonce=f"service-{index}",
            )
            receipt = RulePromotionReceiptV4.from_dict({
                **receipt_body,
                "signature": service.to_dict(),
            })
            promotion_raw = receipt.canonical_bytes()
            promotion_ref = ContentRefV4(
                RULE_PROMOTION_RECEIPT_KIND,
                DigestV4.from_bytes(promotion_raw),
            )
            self._store(promotion_ref, promotion_raw)
            final_body = {**base, "promotion_receipt_refs": [promotion_ref.to_dict()]}
            rule = RuleV4.from_dict({
                **final_body,
                "rule_digest": str(digest_value(final_body)),
            })
        rule_ref = ContentRefV4(RULE_KIND, rule.rule_digest)
        self._store(rule_ref, canonical_bytes(rule.digest_body()), artifact_kind=RULE_KIND)
        return rule_ref, promotion_ref

    def build(
        self,
        *,
        candidate: bool = False,
        empty_field: str | None = None,
        config_state: str = "valid",
        forged_source: bool = False,
        wrong_locator: bool = False,
        wrong_structure: bool = False,
        missing_review: bool = False,
        format_only_build: bool = False,
        release_fault: str | None = None,
        promotion_replay: bool = False,
        permission: bool = False,
    ) -> ContentRefV4:
        source_ref, source = self._stage_source(forged=forged_source)
        self.last_source_ref = source_ref
        rule_count = 2 if promotion_replay or self.cross_rule_role_overlap else 1
        rule_refs: list[ContentRefV4] = []
        promotion_refs: list[ContentRefV4] = []
        for index in range(1, rule_count + 1):
            rule_ref, promotion_ref = self._stage_rule(
                index,
                source_ref,
                source,
                candidate=candidate,
                wrong_locator=wrong_locator,
                wrong_structure=wrong_structure,
                missing_review=missing_review,
                promotion_nonce=("legal-replay" if promotion_replay else f"legal-{index}"),
                permission=permission,
            )
            rule_refs.append(rule_ref)
            if promotion_ref is not None:
                promotion_refs.append(promotion_ref)

        rule_refs = sorted(rule_refs, key=lambda item: (item.kind, str(item.digest)))
        promotion_refs = sorted(
            promotion_refs, key=lambda item: (item.kind, str(item.digest))
        )
        if config_state == "missing":
            config_ref = _ref(PACK_CONFIG_KIND, "missing-config")
        else:
            config_raw = canonical_bytes({
                "schema_version": (
                    "jc/domain-config/9.9"
                    if config_state == "unknown"
                    else "jc/domain-config/1.0"
                ),
                "domain_id": "cn-civil",
                "namespace": "cn",
                "jurisdiction": "CN",
                "governing_law": "civil-procedure-law",
                "rule_refs": (
                    "corrupt-not-an-array"
                    if config_state == "corrupt"
                    else [item.to_dict() for item in rule_refs]
                ),
            })
            config_ref = ContentRefV4(PACK_CONFIG_KIND, DigestV4.from_bytes(config_raw))
            self._store(config_ref, config_raw, artifact_kind=PACK_CONFIG_KIND)

        coverage_ref = self._json(PACK_COVERAGE_RECEIPT_KIND, {
            "schema_version": "jc/pack-coverage-receipt/1.0",
            "status": "PASS",
            "rule_refs": [item.to_dict() for item in rule_refs],
        })
        verification_ref = self._json(PACK_VERIFICATION_RECEIPT_KIND, {
            "schema_version": "jc/pack-verification-receipt/1.0",
            "status": "PASS",
            "rule_refs": [item.to_dict() for item in rule_refs],
        })
        manifest_values: dict[str, object] = {
            "pack_id": "cn-official-test",
            "pack_version": "1.0.0",
            "engine_api": ENGINE_API,
            "rule_refs": [item.to_dict() for item in rule_refs],
            "source_refs": [source_ref.to_dict()],
            "config_refs": [config_ref.to_dict()],
            "receipt_refs": [item.to_dict() for item in promotion_refs],
            "compiler_build_digest": str(COMPILER_BUILD),
            "source_tree_digest": str(SOURCE_TREE),
            "schema_digest": str(SCHEMA_DIGEST),
            "trust_policy_ref": ContentRefV4(
                "trust-policy", self.policy.policy_digest
            ).to_dict(),
            "coverage_receipt_refs": [coverage_ref.to_dict()],
            "verification_receipt_refs": [verification_ref.to_dict()],
        }
        if empty_field is not None:
            manifest_values[empty_field] = []
        provisional = PackManifestV4.from_dict({
            **manifest_values,
            "manifest_digest": str(digest_value(manifest_values)),
        })
        build_body = build_subject_body(provisional)
        build_ref = build_subject_ref(provisional)
        self._store(
            build_ref,
            canonical_bytes(build_body),
            artifact_kind=PACK_BUILD_SUBJECT_KIND,
        )
        build_evidence = build_attestation_evidence_refs(provisional, build_ref)
        build = self._sign(
            "build",
            subject_digest=build_ref.digest,
            payload_digest=DigestV4.from_bytes(canonical_bytes(build_body)),
            evidence_refs=(() if format_only_build else build_evidence),
            nonce="build-nonce",
        )
        build_attestation_ref = ContentRefV4(
            BUILD_ATTESTATION_KIND,
            DigestV4.from_bytes(build.canonical_bytes()),
        )
        self._store(
            build_attestation_ref,
            build.canonical_bytes(),
            scope="build-attestation",
            artifact_kind=BUILD_ATTESTATION_KIND,
        )
        final_receipt_refs = sorted(
            (*promotion_refs, build_attestation_ref),
            key=lambda item: (item.kind, str(item.digest)),
        )
        final_values = {
            **manifest_values,
            "receipt_refs": [item.to_dict() for item in final_receipt_refs],
        }
        if empty_field is not None:
            final_values[empty_field] = []
        manifest = PackManifestV4.from_dict({
            **final_values,
            "manifest_digest": str(digest_value(final_values)),
        })
        manifest_ref = ContentRefV4(PACK_MANIFEST_KIND, manifest.manifest_digest)
        self._store(
            manifest_ref,
            canonical_bytes(manifest.digest_body()),
            artifact_kind=PACK_MANIFEST_KIND,
        )
        release_evidence = pack_release_evidence_refs(manifest_ref, manifest, build_ref)
        profile_override = None
        expires = EXPIRES
        corrupt = False
        if release_fault == "wrong-scope":
            profile_override = self._profiles["build"]
        elif release_fault == "expired":
            expires = CanonicalTimeV4("2026-08-22T11:30:00Z")
        elif release_fault in {"forged", "signature-replacement"}:
            corrupt = True
        release = self._sign(
            "release",
            subject_digest=manifest_ref.digest,
            payload_digest=digest_value({"manifest_ref": manifest_ref.to_dict()}),
            evidence_refs=release_evidence,
            nonce="release-nonce",
            expires_at=expires,
            profile_override=profile_override,
            corrupt=corrupt,
        )
        pack_document = {
            "manifest_ref": manifest_ref.to_dict(),
            "signature": release.to_dict(),
        }
        if release_fault == "manifest-replacement":
            pack_document["manifest_ref"] = _ref(PACK_MANIFEST_KIND, "replacement").to_dict()
        elif release_fault == "unsigned":
            del pack_document["signature"]
        pack_raw = canonical_bytes(pack_document)
        pack_ref = ContentRefV4(PACK_SIGNATURE_KIND, DigestV4.from_bytes(pack_raw))
        self._store(pack_ref, pack_raw, artifact_kind=PACK_SIGNATURE_KIND)
        return pack_ref


def test_signed_pack_verifies_real_resolved_graph() -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    verified = harness.verifier.verify(pack_ref, now=NOW)
    assert type(verified).__name__ == "VerifiedRulePackV4"


def test_verified_handle_has_no_caller_constructor() -> None:
    with pytest.raises(TypeError, match="issued only"):
        VerifiedRulePackV4()

    harness = _PackHarness()
    pack_ref = harness.build()
    issued = harness.verifier.verify(pack_ref, now=NOW)
    forged = object.__new__(VerifiedRulePackV4)
    object.__setattr__(forged, "pack_ref", pack_ref)
    assert issued.verifier_issued
    assert not forged.verifier_issued
    assert _error_code(lambda: forged.status) == "PACK_HANDLE_NOT_ISSUED"


def test_permission_rule_verifies() -> None:
    harness = _PackHarness()
    verified = harness.verifier.verify(harness.build(permission=True), now=NOW)
    assert verified.rules[0].modality == "PERMISSION"


def test_same_pack_retry_is_idempotent() -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    first = harness.verifier.verify(pack_ref, now=NOW)
    second = harness.verifier.verify(pack_ref, now=CanonicalTimeV4("2026-08-22T12:01:00Z"))
    assert second == first


@pytest.mark.parametrize("config_state", ("missing", "corrupt", "unknown"))
def test_missing_or_corrupt_domain_config_blocks(config_state: str) -> None:
    harness = _PackHarness()
    pack_ref = harness.build(config_state=config_state)
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)).startswith(
        ("ARTIFACT_", "PACK_CONFIG_")
    )


@pytest.mark.parametrize(
    ("expected_field", "value"),
    (
        ("expected_engine_api", "4.1.0"),
        ("expected_compiler_build_digest", DigestV4.from_bytes(b"wrong-build")),
        ("expected_source_tree_digest", DigestV4.from_bytes(b"wrong-tree")),
        ("expected_schema_digest", DigestV4.from_bytes(b"wrong-schema")),
    ),
)
def test_runtime_identity_mismatch_blocks(expected_field: str, value: object) -> None:
    harness = _PackHarness(**{expected_field: value})
    pack_ref = harness.build()
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)).startswith("PACK_")
