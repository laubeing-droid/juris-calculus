#!/usr/bin/env python3
"""Build the deterministic test-only signed V4 pack fixture."""

from __future__ import annotations

import argparse
from base64 import b64decode, b64encode
from dataclasses import replace
from pathlib import Path
import sys
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    CanonicalLocatorV4,
    CanonicalTimeV4,
    ContentRefV4,
    PackManifestV4,
    RulePromotionReceiptV4,
    RuleV4,
    SignatureEnvelopeV4,
    SourceSnapshotV4,
    TrustPolicyV4,
)
from compiler_core.rule_packs import (
    BUILD_ATTESTATION_KIND,
    BUILD_ATTESTATION_SCOPE,
    ENGINEERING_APPROVAL_KIND,
    ENGINEERING_APPROVAL_SCOPE,
    JSON_MEDIA_TYPE,
    LEGAL_APPROVAL_KIND,
    LEGAL_APPROVAL_SCOPE,
    PACK_BUILD_SUBJECT_KIND,
    PACK_CONFIG_KIND,
    PACK_COVERAGE_RECEIPT_KIND,
    PACK_MANIFEST_KIND,
    PACK_SIGNATURE_KIND,
    PACK_VERIFICATION_RECEIPT_KIND,
    RULE_AUTHORITY_KIND,
    RULE_COMPONENT_SCOPE,
    RULE_CONCLUSION_KIND,
    RULE_DEFINED_TERM_KIND,
    RULE_EXCEPTION_KIND,
    RULE_INTERPRETATION_KIND,
    RULE_KIND,
    RULE_PACK_SCOPE,
    RULE_PERMISSION_KIND,
    RULE_PREMISE_KIND,
    RULE_PRIORITY_KIND,
    RULE_PROMOTION_RECEIPT_KIND,
    RULE_PROMOTION_SUBJECT_KIND,
    RULE_TEMPORAL_KIND,
    RULE_VARIABLE_KIND,
    TRUST_POLICY_KIND,
    build_attestation_evidence_refs,
    build_subject_body,
    build_subject_ref,
    pack_manifest_ref,
    pack_release_evidence_refs,
    promotion_receipt_evidence_refs,
    rule_promotion_subject_body,
    rule_promotion_subject_ref,
    rule_review_evidence_refs,
)
from compiler_core.source_service import (
    SOURCE_AUTHENTICITY_RECEIPT_KIND,
    SOURCE_NORMALIZATION_PROFILE,
    SOURCE_NORMALIZED_KIND,
    SOURCE_PROVENANCE_KIND,
    SOURCE_RAW_KIND,
    SOURCE_SNAPSHOT_KIND,
    SOURCE_STRUCTURE_MAP_KIND,
    normalize_source_bytes,
    source_authenticity_payload_digest,
    source_snapshot_ref,
)


FIXTURE_PATH = ROOT / "tests/fixtures/packs/synthetic/signed-pack.json"
TRUST_CONTEXT_PATH = ROOT / "tests/fixtures/keys/v4-synthetic-trust.json"
TEST_MASTER_KEY_PATH = ROOT / "tests/fixtures/keys/v4-test-ed25519.json"
_TRUSTED_CONTEXT = parse_json_document(TRUST_CONTEXT_PATH.read_bytes())
if not isinstance(_TRUSTED_CONTEXT, dict):
    raise ValueError("synthetic trusted context must be an object")
VERIFY_AT = CanonicalTimeV4.from_dict(_TRUSTED_CONTEXT["verification_time"])
ISSUED_AT = CanonicalTimeV4("2026-08-22T11:00:00Z")
EXPIRES_AT = CanonicalTimeV4("2028-01-01T00:00:00Z")
_RUNTIME_IDENTITY = _TRUSTED_CONTEXT["runtime_identity"]
ENGINE_API = _RUNTIME_IDENTITY["engine_api"]
COMPILER_BUILD = DigestV4(_RUNTIME_IDENTITY["compiler_build_digest"])
SOURCE_TREE = DigestV4(_RUNTIME_IDENTITY["source_tree_digest"])
SCHEMA_DIGEST = DigestV4(_RUNTIME_IDENTITY["schema_digest"])

_PROFILES = {
    "source": ("source_attestor", "source-authenticity", SOURCE_SNAPSHOT_KIND),
    "legal": ("legal_reviewer", LEGAL_APPROVAL_SCOPE, LEGAL_APPROVAL_KIND),
    "engineering": (
        "engineering_reviewer",
        ENGINEERING_APPROVAL_SCOPE,
        ENGINEERING_APPROVAL_KIND,
    ),
    "service": ("service_signer", "service-certificate", "service-certificate"),
    "build": ("build_attestor", BUILD_ATTESTATION_SCOPE, BUILD_ATTESTATION_KIND),
    "release": ("pack_releaser", "pack-release", "rule-pack"),
}


def _ref(kind: str, label: str) -> ContentRefV4:
    return ContentRefV4(kind, DigestV4.from_bytes(label.encode("utf-8")))


class _SyntheticPackBuilder:
    def __init__(
        self,
        *,
        issued_at_by_signer: dict[str, CanonicalTimeV4] | None = None,
    ) -> None:
        self.resolver = ArtifactResolverV4(max_artifact_bytes=262_144)
        self.issued_at_by_signer = dict(issued_at_by_signer or {})
        master_fixture = parse_json_document(TEST_MASTER_KEY_PATH.read_bytes())
        if not isinstance(master_fixture, dict) or master_fixture.get("scope") != "test-only":
            raise ValueError("synthetic builder requires the approved test-only master key")
        master_seed = b64decode(master_fixture["private_key_base64"], validate=True)
        self.private_keys = {
            name: Ed25519PrivateKey.from_private_bytes(
                HKDF(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=b"jc-v4-synthetic-test-only-v1",
                    info=f"juris-calculus/{name}".encode("ascii"),
                ).derive(master_seed)
            )
            for name in _PROFILES
        }
        self.policy = TrustPolicyV4.from_dict(_TRUSTED_CONTEXT["trust_policy"])
        trusted_keys = {
            row["key_id"]: row for row in _TRUSTED_CONTEXT["trust_keys"]
        }
        for name, private_key in self.private_keys.items():
            row = trusted_keys.get(f"synthetic-{name}-key")
            public_key = private_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
            if row is None or b64decode(row["public_key_base64"], validate=True) != public_key:
                raise ValueError(f"synthetic private key does not match trusted key: {name}")
        self.artifacts: dict[ContentRefV4, dict[str, Any]] = {}
        self._serial = 0

    def _store(
        self,
        reference: ContentRefV4,
        content: bytes,
        *,
        scope: str = RULE_PACK_SCOPE,
        artifact_kind: str | None = None,
        media_type: str = JSON_MEDIA_TYPE,
    ) -> ContentRefV4:
        kind = reference.kind if artifact_kind is None else artifact_kind
        existing = self.artifacts.get(reference)
        if existing is not None:
            if (
                existing["artifact_kind"] != kind
                or existing["media_type"] != media_type
                or existing["scope"] != scope
                or existing["content"] != content
            ):
                raise ValueError(f"synthetic artifact collision: {reference}")
            return reference
        self._serial += 1
        artifact_id = f"synthetic-{self._serial:04d}"
        self.resolver.register_bytes(
            artifact_id=artifact_id,
            content_ref=reference,
            artifact_kind=kind,
            media_type=media_type,
            scope=scope,
            content=content,
        )
        self.artifacts[reference] = {
            "artifact_id": artifact_id,
            "content_ref": reference.to_dict(),
            "artifact_kind": kind,
            "media_type": media_type,
            "scope": scope,
            "content": content,
        }
        return reference

    def _json(
        self,
        kind: str,
        value: dict[str, object],
        *,
        scope: str = RULE_PACK_SCOPE,
    ) -> ContentRefV4:
        raw = canonical_bytes(value)
        reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
        return self._store(reference, raw, scope=scope, artifact_kind=kind)

    def _sign(
        self,
        signer: str,
        *,
        subject_digest: DigestV4,
        payload_digest: DigestV4,
        evidence_refs: tuple[ContentRefV4, ...],
        nonce: str,
    ) -> SignatureEnvelopeV4:
        role, scope, kind = _PROFILES[signer]
        body = {
            "algorithm": "Ed25519",
            "key_id": f"synthetic-{signer}-key",
            "issuer": f"synthetic-{signer}-issuer",
            "role": role,
            "scope": scope,
            "kind": kind,
            "schema_version": "jc/4.0",
            "subject_digest": str(subject_digest),
            "run_identity_ref": None,
            "status": "APPROVED",
            "issued_at": self.issued_at_by_signer.get(signer, ISSUED_AT).to_dict(),
            "expires_at": EXPIRES_AT.to_dict(),
            "nonce": nonce,
            "evidence_refs": [item.to_dict() for item in evidence_refs],
            "payload_digest": str(payload_digest),
            "policy_digest": str(self.policy.policy_digest),
            "revocation_ref": self.policy.revocation_policy_ref.to_dict(),
        }
        signature = self.private_keys[signer].sign(canonical_bytes(body))
        return SignatureEnvelopeV4.from_dict({
            **body,
            "signature": b64encode(signature).decode("ascii"),
        })

    def _source(self) -> tuple[ContentRefV4, SourceSnapshotV4]:
        raw = "虚拟测试法第一条：仅用于自动化测试，不构成法律依据。".encode("utf-8")
        normalized = normalize_source_bytes(raw)
        raw_ref = ContentRefV4(SOURCE_RAW_KIND, DigestV4.from_bytes(raw))
        normalized_ref = ContentRefV4(
            SOURCE_NORMALIZED_KIND, DigestV4.from_bytes(normalized)
        )
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
        structure_ref = self._json(
            SOURCE_STRUCTURE_MAP_KIND,
            {"schema_version": "jc/source-structure/1.0", "sections": ["article-1"]},
            scope="source-provenance",
        )
        provenance_ref = self._json(
            SOURCE_PROVENANCE_KIND,
            {"schema_version": "jc/source-provenance/1.0", "method": "synthetic"},
            scope="source-provenance",
        )
        snapshot = SourceSnapshotV4(
            source_id="synthetic-test-law-article-1",
            jurisdiction="TEST",
            authority_tier="synthetic_test_only",
            issuer="synthetic-test-authority",
            title="synthetic-test-law",
            publication_time=CanonicalTimeV4("2021-12-24T00:00:00Z"),
            effective_from=CanonicalTimeV4("2022-01-01T00:00:00Z"),
            effective_to=None,
            retrieved_at=CanonicalTimeV4("2026-08-01T00:00:00Z"),
            canonical_locator=CanonicalLocatorV4(
                "uri", "test.invalid/synthetic-law/article-1", None, None, None
            ),
            raw_digest=raw_ref.digest,
            normalization_profile=SOURCE_NORMALIZATION_PROFILE,
            normalized_digest=normalized_ref.digest,
            structure_map_ref=structure_ref,
            authenticity_receipt_ref=_ref(
                SOURCE_AUTHENTICITY_RECEIPT_KIND, "synthetic-source-placeholder"
            ),
            provenance_refs=(provenance_ref,),
            acquisition_method="synthetic-test-fixture",
            license_status="test-only",
            distribution_status="test-only",
        )
        signature = self._sign(
            "source",
            subject_digest=snapshot.raw_digest,
            payload_digest=source_authenticity_payload_digest(snapshot),
            evidence_refs=(raw_ref, normalized_ref, structure_ref, provenance_ref),
            nonce="synthetic-source",
        )
        signature_ref = ContentRefV4(
            SOURCE_AUTHENTICITY_RECEIPT_KIND,
            DigestV4.from_bytes(signature.canonical_bytes()),
        )
        self._store(
            signature_ref,
            signature.canonical_bytes(),
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

    def _component(
        self,
        kind: str,
        rule_id: str,
        **values: object,
    ) -> ContentRefV4:
        return self._json(
            kind,
            {"schema_version": f"jc/{kind}/1.0", "rule_id": rule_id, **values},
            scope=RULE_COMPONENT_SCOPE,
        )

    def _rule(
        self,
        rule_id: str,
        source_ref: ContentRefV4,
        source: SourceSnapshotV4,
        *,
        features: tuple[str, ...],
        candidate: bool = False,
    ) -> tuple[ContentRefV4, ContentRefV4 | None]:
        authority_ref = self._component(RULE_AUTHORITY_KIND, rule_id, tier="synthetic")
        variable_ref = self._component(RULE_VARIABLE_KIND, rule_id, name="claim")
        premise_refs = [self._component(
            RULE_PREMISE_KIND,
            rule_id,
            fact_key=f"{rule_id}.required-fact",
            required=True,
        )]
        conclusion_ref = self._component(RULE_CONCLUSION_KIND, rule_id, value="applies")
        interpretation_ref = self._component(
            RULE_INTERPRETATION_KIND, rule_id, choice="literal"
        )
        term_ref = self._component(RULE_DEFINED_TERM_KIND, rule_id, term="claim")
        exception_refs = (
            (self._component(
                RULE_EXCEPTION_KIND,
                rule_id,
                attacker=rule_id,
                target="synthetic-positive",
                attack_type="exception",
                target_aspect="applicability",
                condition_fact_key=f"{rule_id}.exception-fact",
            ),)
            if "exception" in features
            else ()
        )
        priority_refs = (
            (self._component(
                RULE_PRIORITY_KIND,
                rule_id,
                source=rule_id,
                target="synthetic-positive",
                condition=f"{rule_id}.priority-condition",
            ),)
            if "priority" in features
            else ()
        )
        permission_ref = (
            self._component(
                RULE_PERMISSION_KIND,
                rule_id,
                permission_id=f"{rule_id}.permission",
                permits=f"{rule_id}.required-fact",
                relation_to="synthetic-positive",
                relation_kind="exception",
            )
            if "permission" in features
            else None
        )
        temporal_refs = (
            (
                self._component(
                    RULE_TEMPORAL_KIND,
                    rule_id,
                    start="2022-01-01T00:00:00Z",
                    end="2027-01-01T00:00:00Z",
                    target_rule_id=rule_id,
                ),
            )
            if "temporal" in features
            else ()
        )
        base = {
            "rule_id": rule_id,
            "jurisdiction": "TEST",
            "governing_law": "synthetic-test-law",
            "authority_ref": authority_ref.to_dict(),
            "variable_declaration_refs": [variable_ref.to_dict()],
            "premise_refs": [item.to_dict() for item in premise_refs],
            "conclusion_ref": conclusion_ref.to_dict(),
            "modality": "PERMISSION" if permission_ref is not None else "OBLIGATION",
            "permission_ref": permission_ref.to_dict() if permission_ref is not None else None,
            "exception_refs": [item.to_dict() for item in exception_refs],
            "priority_refs": [item.to_dict() for item in priority_refs],
            "attack_refs": [],
            "temporal_constraint_refs": [item.to_dict() for item in temporal_refs],
            "numeric_constraint_refs": [],
            "source_snapshot_ref": source_ref.to_dict(),
            "source_locator": source.canonical_locator.to_dict(),
            "source_structure_ref": source.structure_map_ref.to_dict(),
            "interpretation_choice_refs": [interpretation_ref.to_dict()],
            "defined_term_refs": [term_ref.to_dict()],
            "promotion_receipt_refs": [],
            "effective_from": {"wire": "2022-01-01T00:00:00Z"},
            "effective_to": (
                {"wire": "2027-01-01T00:00:00Z"} if "temporal" in features else None
            ),
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
            legal = self._sign(
                "legal",
                subject_digest=subject_ref.digest,
                payload_digest=subject_ref.digest,
                evidence_refs=rule_review_evidence_refs(
                    draft, subject_ref, self.policy.replay_policy_ref, "legal"
                ),
                nonce=f"synthetic-legal-{rule_id}",
            )
            legal_ref = ContentRefV4(
                LEGAL_APPROVAL_KIND, DigestV4.from_bytes(legal.canonical_bytes())
            )
            self._store(
                legal_ref,
                legal.canonical_bytes(),
                scope=LEGAL_APPROVAL_SCOPE,
                artifact_kind=LEGAL_APPROVAL_KIND,
            )
            engineering = self._sign(
                "engineering",
                subject_digest=subject_ref.digest,
                payload_digest=subject_ref.digest,
                evidence_refs=rule_review_evidence_refs(
                    draft, subject_ref, self.policy.replay_policy_ref, "engineering"
                ),
                nonce=f"synthetic-engineering-{rule_id}",
            )
            engineering_ref = ContentRefV4(
                ENGINEERING_APPROVAL_KIND,
                DigestV4.from_bytes(engineering.canonical_bytes()),
            )
            self._store(
                engineering_ref,
                engineering.canonical_bytes(),
                scope=ENGINEERING_APPROVAL_SCOPE,
                artifact_kind=ENGINEERING_APPROVAL_KIND,
            )
            receipt_body = {
                "receipt_id": f"synthetic-promotion-{rule_id}",
                "rule_subject_digest": str(subject_ref.digest),
                "legal_review_ref": legal_ref.to_dict(),
                "engineering_review_ref": engineering_ref.to_dict(),
                "status": "APPROVED",
                "issued_at": ISSUED_AT.to_dict(),
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
                nonce=f"synthetic-service-{rule_id}",
            )
            receipt = RulePromotionReceiptV4.from_dict({
                **receipt_body,
                "signature": service.to_dict(),
            })
            promotion_ref = ContentRefV4(
                RULE_PROMOTION_RECEIPT_KIND,
                DigestV4.from_bytes(receipt.canonical_bytes()),
            )
            self._store(promotion_ref, receipt.canonical_bytes())
            final_body = {**base, "promotion_receipt_refs": [promotion_ref.to_dict()]}
            rule = RuleV4.from_dict({
                **final_body,
                "rule_digest": str(digest_value(final_body)),
            })
        rule_ref = ContentRefV4(RULE_KIND, rule.rule_digest)
        self._store(rule_ref, canonical_bytes(rule.digest_body()), artifact_kind=RULE_KIND)
        return rule_ref, promotion_ref

    def _pack(
        self,
        pack_id: str,
        source_ref: ContentRefV4,
        rule_refs: tuple[ContentRefV4, ...],
        promotion_refs: tuple[ContentRefV4, ...],
    ) -> ContentRefV4:
        rule_refs = tuple(sorted(rule_refs, key=lambda item: (item.kind, str(item.digest))))
        promotion_refs = tuple(
            sorted(promotion_refs, key=lambda item: (item.kind, str(item.digest)))
        )
        config_ref = self._json(PACK_CONFIG_KIND, {
            "schema_version": "jc/domain-config/1.0",
            "domain_id": pack_id,
            "namespace": pack_id,
            "jurisdiction": "TEST",
            "governing_law": "synthetic-test-law",
            "rule_refs": [item.to_dict() for item in rule_refs],
        })
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
        values: dict[str, object] = {
            "pack_id": pack_id,
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
                TRUST_POLICY_KIND, self.policy.canonical_digest()
            ).to_dict(),
            "coverage_receipt_refs": [coverage_ref.to_dict()],
            "verification_receipt_refs": [verification_ref.to_dict()],
        }
        provisional = PackManifestV4.from_dict({
            **values,
            "manifest_digest": str(digest_value(values)),
        })
        build_body = build_subject_body(provisional)
        build_ref = build_subject_ref(provisional)
        self._store(
            build_ref,
            canonical_bytes(build_body),
            artifact_kind=PACK_BUILD_SUBJECT_KIND,
        )
        build = self._sign(
            "build",
            subject_digest=build_ref.digest,
            payload_digest=build_ref.digest,
            evidence_refs=build_attestation_evidence_refs(provisional, build_ref),
            nonce=f"synthetic-build-{pack_id}",
        )
        build_attestation_ref = ContentRefV4(
            BUILD_ATTESTATION_KIND,
            DigestV4.from_bytes(build.canonical_bytes()),
        )
        self._store(
            build_attestation_ref,
            build.canonical_bytes(),
            scope=BUILD_ATTESTATION_SCOPE,
            artifact_kind=BUILD_ATTESTATION_KIND,
        )
        receipt_refs = tuple(
            sorted(
                (*promotion_refs, build_attestation_ref),
                key=lambda item: (item.kind, str(item.digest)),
            )
        )
        final_values = {
            **values,
            "receipt_refs": [item.to_dict() for item in receipt_refs],
        }
        manifest = PackManifestV4.from_dict({
            **final_values,
            "manifest_digest": str(digest_value(final_values)),
        })
        manifest_ref = pack_manifest_ref(manifest)
        self._store(
            manifest_ref,
            canonical_bytes(manifest.digest_body()),
            artifact_kind=PACK_MANIFEST_KIND,
        )
        release = self._sign(
            "release",
            subject_digest=manifest_ref.digest,
            payload_digest=digest_value({"manifest_ref": manifest_ref.to_dict()}),
            evidence_refs=pack_release_evidence_refs(manifest_ref, manifest, build_ref),
            nonce=f"synthetic-release-{pack_id}",
        )
        pack_raw = canonical_bytes({
            "manifest_ref": manifest_ref.to_dict(),
            "signature": release.to_dict(),
        })
        pack_ref = ContentRefV4(PACK_SIGNATURE_KIND, DigestV4.from_bytes(pack_raw))
        self._store(pack_ref, pack_raw, artifact_kind=PACK_SIGNATURE_KIND)
        return pack_ref

    def build(self) -> dict[str, object]:
        source_ref, source = self._source()
        feature_rows = (
            ("synthetic-positive", ("positive",)),
            ("synthetic-exception-priority", ("exception", "priority")),
            ("synthetic-permission-temporal", ("permission", "temporal")),
            ("synthetic-missing-disputed", ("missing", "disputed")),
        )
        formal_rules: list[ContentRefV4] = []
        promotions: list[ContentRefV4] = []
        for rule_id, features in feature_rows:
            rule_ref, promotion_ref = self._rule(
                rule_id, source_ref, source, features=features
            )
            formal_rules.append(rule_ref)
            if promotion_ref is None:
                raise AssertionError("formal synthetic rule lacks promotion receipt")
            promotions.append(promotion_ref)
        pack_ref = self._pack(
            "synthetic-formal-test",
            source_ref,
            tuple(formal_rules),
            tuple(promotions),
        )
        candidate_rule_ref, candidate_promotion = self._rule(
            "synthetic-candidate",
            source_ref,
            source,
            features=("positive",),
            candidate=True,
        )
        if candidate_promotion is not None:
            raise AssertionError("candidate synthetic rule gained a promotion receipt")
        candidate_pack_ref = self._pack(
            "synthetic-candidate-test",
            source_ref,
            (candidate_rule_ref,),
            (),
        )
        artifacts = []
        for reference, row in sorted(
            self.artifacts.items(), key=lambda item: (item[0].kind, str(item[0].digest))
        ):
            artifacts.append({
                "artifact_id": row["artifact_id"],
                "content_ref": reference.to_dict(),
                "artifact_kind": row["artifact_kind"],
                "media_type": row["media_type"],
                "scope": row["scope"],
                "content_base64": b64encode(row["content"]).decode("ascii"),
            })
        missing_rule_id = "synthetic-missing-disputed"
        return {
            "schema_version": "jc/synthetic-signed-pack-fixture/1.0",
            "scope": "test-only",
            "production_allowed": False,
            "pack_ref": pack_ref.to_dict(),
            "candidate_pack_ref": candidate_pack_ref.to_dict(),
            "formal_rule_ids": [row[0] for row in feature_rows],
            "feature_rules": {feature: rule_id for rule_id, features in feature_rows for feature in features},
            "case_vectors": [
                {
                    "case_id": "missing-required-fact",
                    "rule_id": missing_rule_id,
                    "fact_key": f"{missing_rule_id}.required-fact",
                    "input_fact_state": "ABSENT",
                    "expected_admission": "BLOCKED",
                },
                {
                    "case_id": "disputed-required-fact",
                    "rule_id": missing_rule_id,
                    "fact_key": f"{missing_rule_id}.required-fact",
                    "input_fact_state": "DISPUTED",
                    "expected_admission": "BLOCKED",
                },
            ],
            "artifacts": artifacts,
        }


def build_fixture_bytes() -> bytes:
    return canonical_bytes(_SyntheticPackBuilder().build())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=FIXTURE_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = build_fixture_bytes()
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != expected:
            print(f"synthetic fixture drifted: {args.output}", file=sys.stderr)
            return 1
        print(f"synthetic fixture OK: {len(expected)} bytes")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(expected)
    print(f"synthetic fixture written: {args.output} ({len(expected)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
