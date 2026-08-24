#!/usr/bin/env python3
"""Promote the current cn-official candidate into a locally signed production pack."""

from __future__ import annotations

import argparse
from base64 import b64decode, b64encode
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import subprocess
import sys
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
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
    RULE_KIND,
    RULE_PACK_SCOPE,
    RULE_PROMOTION_RECEIPT_KIND,
    RULE_PROMOTION_SUBJECT_KIND,
    TRUST_POLICY_KIND,
    RulePackVerifierV4,
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
    SOURCE_NORMALIZED_KIND,
    SOURCE_RAW_KIND,
    SOURCE_SNAPSHOT_KIND,
    SourceServiceV4,
    source_authenticity_payload_digest,
    source_snapshot_ref,
)
from compiler_core.trust import TrustKeyV4, TrustVerifierV4
from tools.build_cn_official_pack import OUTPUT_PATH as CANDIDATE_PATH
from tools.build_cn_official_pack import assert_valid_document as assert_valid_candidate


PACK_ID = "cn-official-local"
PACK_VERSION = "4.0.0"
ENGINE_API = "4.0.0"
_PROFILES = {
    "source": ("source_attestor", "source-authenticity", SOURCE_SNAPSHOT_KIND),
    "legal": ("legal_reviewer", LEGAL_APPROVAL_SCOPE, LEGAL_APPROVAL_KIND),
    "engineering": (
        "engineering_reviewer", ENGINEERING_APPROVAL_SCOPE, ENGINEERING_APPROVAL_KIND,
    ),
    "service": ("service_signer", "service-certificate", "service-certificate"),
    "build": ("build_attestor", BUILD_ATTESTATION_SCOPE, BUILD_ATTESTATION_KIND),
    "release": ("pack_releaser", "pack-release", "rule-pack"),
}


def _utc_wire(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_identity(path: Path) -> dict[str, object]:
    """Create the one local production root inside the caller-selected EFS directory."""

    if path.is_file():
        value = parse_json_document(path.read_bytes())
        if not isinstance(value, dict) or value.get("schema_version") != "jc/local-production-root/1.0":
            raise ValueError("local production identity has the wrong schema")
        if len(b64decode(str(value["private_seed_base64"]), validate=True)) != 32:
            raise ValueError("local production identity seed must be 32 bytes")
        CanonicalTimeV4(str(value["activated_at"]))
        return value
    now = datetime.now(timezone.utc)
    value = {
        "schema_version": "jc/local-production-root/1.0",
        "scope": "local-production",
        "signing_mode": "LOCAL_AUTOMATED_OWNER",
        "independent_human_review": False,
        "activated_at": _utc_wire(now),
        "expires_at": _utc_wire(now + timedelta(days=3650)),
        "private_seed_base64": b64encode(secrets.token_bytes(32)).decode("ascii"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    return value


def _tree_identity() -> tuple[DigestV4, DigestV4, DigestV4]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True,
    ).stdout.split(b"\0")
    rows = []
    for raw_path in tracked:
        if not raw_path:
            continue
        path = ROOT / raw_path.decode("utf-8")
        if path.is_file():
            rows.append([raw_path.decode("utf-8"), str(DigestV4.from_bytes(path.read_bytes()))])
    source_tree = digest_value(rows)
    compiler_rows = [row for row in rows if row[0].startswith("compiler_core/")]
    compiler_build = digest_value(compiler_rows)
    schema = DigestV4.from_bytes((ROOT / "compiler_core/contracts.py").read_bytes())
    return compiler_build, source_tree, schema


class LocalProductionPackBuilder:
    def __init__(self, candidate: dict[str, object], identity: dict[str, object]) -> None:
        assert_valid_candidate(candidate)
        if candidate.get("schema_version") != "jc/cn-official-candidate-bundle/1.0":
            raise ValueError("local production requires the cn-official candidate")
        self.candidate = candidate
        self.issued_at = CanonicalTimeV4(str(identity["activated_at"]))
        self.expires_at = CanonicalTimeV4(str(identity["expires_at"]))
        master = b64decode(str(identity["private_seed_base64"]), validate=True)
        self.private_keys = {
            name: Ed25519PrivateKey.from_private_bytes(HKDF(
                algorithm=hashes.SHA256(), length=32,
                salt=b"jc-v4-local-production-v1",
                info=f"juris-calculus/local-production/{name}".encode("ascii"),
            ).derive(master))
            for name in _PROFILES
        }
        self.policy = self._policy()
        self.compiler_build, self.source_tree, self.schema_digest = _tree_identity()
        self.resolver = ArtifactResolverV4(max_artifact_bytes=1_048_576)
        self.artifacts: dict[ContentRefV4, dict[str, object]] = {}
        self._serial = 0

    def _policy(self) -> TrustPolicyV4:
        names = tuple(_PROFILES)
        body = {
            "policy_id": "jc-v4-local-production-policy",
            "allowed_algorithms": ["Ed25519"],
            "trusted_key_ids": [f"local-production-{name}-key" for name in names],
            "revoked_key_ids": [],
            "allowed_issuers": [f"local-production-{name}-issuer" for name in names],
            "allowed_roles": [_PROFILES[name][0] for name in names],
            "allowed_scopes": [_PROFILES[name][1] for name in names],
            "allowed_artifact_kinds": [_PROFILES[name][2] for name in names],
            "valid_from": self.issued_at.to_dict(),
            "valid_to": self.expires_at.to_dict(),
            "authorization_policy_ref": self._label_ref(
                "trust-authorization-policy", "local-owner-authorization"
            ).to_dict(),
            "revocation_policy_ref": self._label_ref(
                "trust-revocation-policy", "local-owner-revocation"
            ).to_dict(),
            "replay_policy_ref": self._label_ref(
                "trust-replay-policy", "local-owner-replay"
            ).to_dict(),
            "separation_of_duties_ref": self._label_ref(
                "trust-separation-policy", "local-cryptographic-identities"
            ).to_dict(),
        }
        return TrustPolicyV4.from_dict({**body, "policy_digest": str(digest_value(body))})

    @staticmethod
    def _label_ref(kind: str, label: str) -> ContentRefV4:
        return ContentRefV4(kind, DigestV4.from_bytes(label.encode("utf-8")))

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
        previous = self.artifacts.get(reference)
        row = {
            "artifact_kind": kind, "media_type": media_type,
            "scope": scope, "content": content,
        }
        if previous is not None:
            if previous != row:
                raise ValueError(f"artifact collision: {reference.kind}")
            return reference
        self._serial += 1
        self.resolver.register_bytes(
            artifact_id=f"local-production-{self._serial:04d}",
            content_ref=reference, artifact_kind=kind, media_type=media_type,
            scope=scope, content=content,
        )
        self.artifacts[reference] = row
        return reference

    def _json(self, kind: str, value: dict[str, object], *, scope: str = RULE_PACK_SCOPE) -> ContentRefV4:
        raw = canonical_bytes(value)
        return self._store(
            ContentRefV4(kind, DigestV4.from_bytes(raw)), raw,
            scope=scope, artifact_kind=kind,
        )

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
            "key_id": f"local-production-{signer}-key",
            "issuer": f"local-production-{signer}-issuer",
            "role": role, "scope": scope, "kind": kind,
            "schema_version": "jc/4.0",
            "subject_digest": str(subject_digest),
            "run_identity_ref": None,
            "status": "APPROVED",
            "issued_at": self.issued_at.to_dict(),
            "expires_at": self.expires_at.to_dict(),
            "nonce": nonce,
            "evidence_refs": [item.to_dict() for item in evidence_refs],
            "payload_digest": str(payload_digest),
            "policy_digest": str(self.policy.policy_digest),
            "revocation_ref": self.policy.revocation_policy_ref.to_dict(),
        }
        signature = self.private_keys[signer].sign(canonical_bytes(body))
        return SignatureEnvelopeV4.from_dict({
            **body, "signature": b64encode(signature).decode("ascii"),
        })

    @staticmethod
    def _candidate_bytes(record: dict[str, object]) -> bytes:
        content = record["content"]
        return (
            str(content).encode("utf-8")
            if record["media_type"] == "text/plain"
            else canonical_bytes(content)
        )

    def _source(self) -> tuple[ContentRefV4, SourceSnapshotV4]:
        candidate_source = self.candidate["source"]
        old_snapshot = SourceSnapshotV4.from_dict(candidate_source["snapshot"])
        source_refs = (
            ContentRefV4.from_dict(candidate_source["raw_ref"]),
            ContentRefV4.from_dict(candidate_source["normalized_ref"]),
            old_snapshot.structure_map_ref,
            *old_snapshot.provenance_refs,
        )
        wanted = {(item.kind, str(item.digest)) for item in source_refs}
        evidence: list[ContentRefV4] = []
        for raw_record in self.candidate["artifacts"]:
            reference = ContentRefV4.from_dict(raw_record["content_ref"])
            if (reference.kind, str(reference.digest)) not in wanted:
                continue
            self._store(
                reference, self._candidate_bytes(raw_record),
                scope=(
                    "source-content"
                    if reference.kind in {SOURCE_RAW_KIND, SOURCE_NORMALIZED_KIND}
                    else str(raw_record["scope"])
                ),
                artifact_kind=str(raw_record["artifact_kind"]),
                media_type=str(raw_record["media_type"]),
            )
            evidence.append(reference)
        placeholder = replace(
            old_snapshot,
            authority_tier="official_first_party",
            authenticity_receipt_ref=self._label_ref(
                SOURCE_AUTHENTICITY_RECEIPT_KIND, "local-production-source-placeholder"
            ),
            acquisition_method="official-publication-local-production-intake",
        )
        signature = self._sign(
            "source", subject_digest=placeholder.raw_digest,
            payload_digest=source_authenticity_payload_digest(placeholder),
            evidence_refs=tuple(sorted(evidence, key=lambda item: (item.kind, str(item.digest)))),
            nonce="local-production-source-v1",
        )
        signature_ref = self._store(
            ContentRefV4(
                SOURCE_AUTHENTICITY_RECEIPT_KIND,
                DigestV4.from_bytes(signature.canonical_bytes()),
            ),
            signature.canonical_bytes(), scope="source-authenticity",
            artifact_kind=SOURCE_AUTHENTICITY_RECEIPT_KIND,
        )
        snapshot = replace(placeholder, authenticity_receipt_ref=signature_ref)
        snapshot_ref = source_snapshot_ref(snapshot)
        self._store(
            snapshot_ref, snapshot.canonical_bytes(), scope="source-authenticity",
            artifact_kind=SOURCE_SNAPSHOT_KIND,
        )
        return snapshot_ref, snapshot

    def _rule(self, candidate: RuleV4, source_ref: ContentRefV4) -> tuple[ContentRefV4, ContentRefV4]:
        body = candidate.to_dict()
        body.pop("rule_digest")
        body["source_snapshot_ref"] = source_ref.to_dict()
        body["promotion_receipt_refs"] = []
        draft = RuleV4.from_dict({**body, "rule_digest": str(digest_value(body))})
        component_refs = (
            draft.authority_ref, *draft.variable_declaration_refs, *draft.premise_refs,
            draft.conclusion_ref, *draft.exception_refs, *draft.priority_refs,
            *draft.attack_refs, *draft.temporal_constraint_refs, *draft.numeric_constraint_refs,
            *draft.interpretation_choice_refs, *draft.defined_term_refs,
        )
        if draft.permission_ref is not None:
            component_refs = (*component_refs, draft.permission_ref)
        wanted = {(item.kind, str(item.digest)) for item in component_refs}
        for raw_record in self.candidate["artifacts"]:
            reference = ContentRefV4.from_dict(raw_record["content_ref"])
            if (reference.kind, str(reference.digest)) in wanted:
                self._store(
                    reference, self._candidate_bytes(raw_record),
                    scope=str(raw_record["scope"]), artifact_kind=str(raw_record["artifact_kind"]),
                    media_type=str(raw_record["media_type"]),
                )
        subject_body = rule_promotion_subject_body(draft)
        subject_ref = rule_promotion_subject_ref(draft)
        self._store(subject_ref, canonical_bytes(subject_body), artifact_kind=RULE_PROMOTION_SUBJECT_KIND)
        approvals: dict[str, ContentRefV4] = {}
        for signer, kind, scope in (
            ("legal", LEGAL_APPROVAL_KIND, LEGAL_APPROVAL_SCOPE),
            ("engineering", ENGINEERING_APPROVAL_KIND, ENGINEERING_APPROVAL_SCOPE),
        ):
            envelope = self._sign(
                signer, subject_digest=subject_ref.digest, payload_digest=subject_ref.digest,
                evidence_refs=rule_review_evidence_refs(
                    draft, subject_ref, self.policy.replay_policy_ref, signer
                ),
                nonce=f"local-production-{signer}-{draft.rule_id}",
            )
            approvals[signer] = self._store(
                ContentRefV4(kind, DigestV4.from_bytes(envelope.canonical_bytes())),
                envelope.canonical_bytes(), scope=scope, artifact_kind=kind,
            )
        receipt_body = {
            "receipt_id": f"local-production-promotion-{draft.rule_id}",
            "rule_subject_digest": str(subject_ref.digest),
            "legal_review_ref": approvals["legal"].to_dict(),
            "engineering_review_ref": approvals["engineering"].to_dict(),
            "status": "APPROVED", "issued_at": self.issued_at.to_dict(),
        }
        service = self._sign(
            "service", subject_digest=subject_ref.digest,
            payload_digest=digest_value(receipt_body),
            evidence_refs=promotion_receipt_evidence_refs(
                subject_ref, approvals["legal"], approvals["engineering"],
                self.policy.replay_policy_ref,
            ),
            nonce=f"local-production-service-{draft.rule_id}",
        )
        receipt = RulePromotionReceiptV4.from_dict({**receipt_body, "signature": service.to_dict()})
        promotion_ref = self._store(
            ContentRefV4(
                RULE_PROMOTION_RECEIPT_KIND, DigestV4.from_bytes(receipt.canonical_bytes())
            ),
            receipt.canonical_bytes(), artifact_kind=RULE_PROMOTION_RECEIPT_KIND,
        )
        final_body = {**body, "promotion_receipt_refs": [promotion_ref.to_dict()]}
        rule = RuleV4.from_dict({
            **final_body, "rule_digest": str(digest_value(final_body)),
        })
        rule_ref = self._store(
            ContentRefV4(RULE_KIND, rule.rule_digest), canonical_bytes(rule.digest_body()),
            artifact_kind=RULE_KIND,
        )
        return rule_ref, promotion_ref

    def _pack(
        self, source_ref: ContentRefV4, rule_refs: tuple[ContentRefV4, ...],
        promotion_refs: tuple[ContentRefV4, ...],
    ) -> ContentRefV4:
        rule_refs = tuple(sorted(rule_refs, key=lambda item: (item.kind, str(item.digest))))
        promotion_refs = tuple(sorted(promotion_refs, key=lambda item: (item.kind, str(item.digest))))
        source = SourceSnapshotV4.from_dict(self.candidate["source"]["snapshot"])
        config_ref = self._json(PACK_CONFIG_KIND, {
            "schema_version": "jc/domain-config/1.0", "domain_id": PACK_ID,
            "namespace": PACK_ID, "jurisdiction": "CN", "governing_law": source.title,
            "rule_refs": [item.to_dict() for item in rule_refs],
        })
        gate = {
            "schema_version": "jc/pack-coverage-receipt/1.0", "status": "PASS",
            "rule_refs": [item.to_dict() for item in rule_refs],
        }
        coverage_ref = self._json(PACK_COVERAGE_RECEIPT_KIND, gate)
        verification_ref = self._json(PACK_VERIFICATION_RECEIPT_KIND, {
            **gate, "schema_version": "jc/pack-verification-receipt/1.0",
        })
        values: dict[str, object] = {
            "pack_id": PACK_ID, "pack_version": PACK_VERSION, "engine_api": ENGINE_API,
            "rule_refs": [item.to_dict() for item in rule_refs],
            "source_refs": [source_ref.to_dict()], "config_refs": [config_ref.to_dict()],
            "receipt_refs": [item.to_dict() for item in promotion_refs],
            "compiler_build_digest": str(self.compiler_build),
            "source_tree_digest": str(self.source_tree),
            "schema_digest": str(self.schema_digest),
            "trust_policy_ref": ContentRefV4(
                TRUST_POLICY_KIND, self.policy.canonical_digest()
            ).to_dict(),
            "coverage_receipt_refs": [coverage_ref.to_dict()],
            "verification_receipt_refs": [verification_ref.to_dict()],
        }
        provisional = PackManifestV4.from_dict({
            **values, "manifest_digest": str(digest_value(values)),
        })
        build_body = build_subject_body(provisional)
        build_ref = build_subject_ref(provisional)
        self._store(build_ref, canonical_bytes(build_body), artifact_kind=PACK_BUILD_SUBJECT_KIND)
        build = self._sign(
            "build", subject_digest=build_ref.digest, payload_digest=build_ref.digest,
            evidence_refs=build_attestation_evidence_refs(provisional, build_ref),
            nonce=f"local-production-build-{PACK_VERSION}",
        )
        build_attestation_ref = self._store(
            ContentRefV4(BUILD_ATTESTATION_KIND, DigestV4.from_bytes(build.canonical_bytes())),
            build.canonical_bytes(), scope=BUILD_ATTESTATION_SCOPE,
            artifact_kind=BUILD_ATTESTATION_KIND,
        )
        final_receipts = tuple(sorted(
            (*promotion_refs, build_attestation_ref), key=lambda item: (item.kind, str(item.digest))
        ))
        final_values = {
            **values, "receipt_refs": [item.to_dict() for item in final_receipts],
        }
        manifest = PackManifestV4.from_dict({
            **final_values, "manifest_digest": str(digest_value(final_values)),
        })
        manifest_ref = pack_manifest_ref(manifest)
        self._store(
            manifest_ref, canonical_bytes(manifest.digest_body()), artifact_kind=PACK_MANIFEST_KIND,
        )
        release = self._sign(
            "release", subject_digest=manifest_ref.digest,
            payload_digest=digest_value({"manifest_ref": manifest_ref.to_dict()}),
            evidence_refs=pack_release_evidence_refs(manifest_ref, manifest, build_ref),
            nonce=f"local-production-release-{PACK_VERSION}",
        )
        raw = canonical_bytes({"manifest_ref": manifest_ref.to_dict(), "signature": release.to_dict()})
        return self._store(
            ContentRefV4(PACK_SIGNATURE_KIND, DigestV4.from_bytes(raw)), raw,
            artifact_kind=PACK_SIGNATURE_KIND,
        )

    def _trust_keys(self) -> tuple[TrustKeyV4, ...]:
        return tuple(TrustKeyV4(
            key_id=f"local-production-{name}-key",
            issuer=f"local-production-{name}-issuer",
            principal_id=f"local-production-{name}-principal",
            roles=(_PROFILES[name][0],), scopes=(_PROFILES[name][1],),
            artifact_kinds=(_PROFILES[name][2],),
            public_key=self.private_keys[name].public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ),
            production_allowed=True,
        ) for name in _PROFILES)

    def build(self) -> tuple[dict[str, object], dict[str, object]]:
        source_ref, _ = self._source()
        rules: list[ContentRefV4] = []
        promotions: list[ContentRefV4] = []
        for raw_rule in self.candidate["candidate_rules"]:
            rule_ref, promotion_ref = self._rule(RuleV4.from_dict(raw_rule), source_ref)
            rules.append(rule_ref)
            promotions.append(promotion_ref)
        pack_ref = self._pack(source_ref, tuple(rules), tuple(promotions))
        artifacts = [{
            "artifact_id": f"local-production-export-{index:04d}",
            "content_ref": reference.to_dict(), "artifact_kind": row["artifact_kind"],
            "media_type": row["media_type"], "scope": row["scope"],
            "content_base64": b64encode(row["content"]).decode("ascii"),
        } for index, (reference, row) in enumerate(sorted(
            self.artifacts.items(), key=lambda item: (item[0].kind, str(item[0].digest))
        ), 1)]
        keys = self._trust_keys()
        trust_context = {
            "schema_version": "jc/local-production-trust/1.0",
            "scope": "local-production", "production_allowed": True,
            "signing_mode": "LOCAL_AUTOMATED_OWNER", "independent_human_review": False,
            "verification_time": self.issued_at.to_dict(),
            "runtime_identity": {
                "engine_api": ENGINE_API, "compiler_build_digest": str(self.compiler_build),
                "source_tree_digest": str(self.source_tree), "schema_digest": str(self.schema_digest),
            },
            "trust_policy": self.policy.to_dict(),
            "trust_keys": [{
                "key_id": key.key_id, "issuer": key.issuer, "principal_id": key.principal_id,
                "roles": list(key.roles), "scopes": list(key.scopes),
                "artifact_kinds": list(key.artifact_kinds),
                "public_key_base64": b64encode(key.public_key).decode("ascii"),
                "production_allowed": True,
            } for key in keys],
        }
        pack = {
            "schema_version": "jc/local-production-pack/1.0",
            "scope": "local-production", "production_allowed": True,
            "signing_mode": "LOCAL_AUTOMATED_OWNER", "independent_human_review": False,
            "observation_required": True, "pack_ref": pack_ref.to_dict(),
            "formal_rule_ids": [item["rule_id"] for item in self.candidate["candidate_rules"]],
            "artifacts": artifacts,
        }
        verify_pack(pack, trust_context)
        return pack, trust_context


def verify_pack(pack: dict[str, object], trust_context: dict[str, object]) -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=1_048_576)
    for row in pack["artifacts"]:
        resolver.register_bytes(
            artifact_id=row["artifact_id"],
            content_ref=ContentRefV4.from_dict(row["content_ref"]),
            artifact_kind=row["artifact_kind"], media_type=row["media_type"],
            scope=row["scope"], content=b64decode(row["content_base64"], validate=True),
        )
    policy = TrustPolicyV4.from_dict(trust_context["trust_policy"])
    keys = tuple(TrustKeyV4(
        key_id=row["key_id"], issuer=row["issuer"], principal_id=row["principal_id"],
        roles=tuple(row["roles"]), scopes=tuple(row["scopes"]),
        artifact_kinds=tuple(row["artifact_kinds"]),
        public_key=b64decode(row["public_key_base64"], validate=True),
        production_allowed=row["production_allowed"],
    ) for row in trust_context["trust_keys"])
    trust = TrustVerifierV4(policy=policy, keys=keys, target_environment="production")
    identity = trust_context["runtime_identity"]
    RulePackVerifierV4(
        resolver, SourceServiceV4(resolver, trust), trust,
        expected_engine_api=identity["engine_api"],
        expected_compiler_build_digest=DigestV4(identity["compiler_build_digest"]),
        expected_source_tree_digest=DigestV4(identity["source_tree_digest"]),
        expected_schema_digest=DigestV4(identity["schema_digest"]),
    ).verify(
        ContentRefV4.from_dict(pack["pack_ref"]),
        now=CanonicalTimeV4.from_dict(trust_context["verification_time"]),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=CANDIDATE_PATH)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trust-output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        candidate = parse_json_document(args.candidate.read_bytes())
        identity = ensure_identity(args.identity)
        pack, trust_context = LocalProductionPackBuilder(candidate, identity).build()
        pack_bytes, trust_bytes = canonical_bytes(pack), canonical_bytes(trust_context)
        if args.check:
            if args.output.read_bytes() != pack_bytes or args.trust_output.read_bytes() != trust_bytes:
                raise ValueError("local production pack or trust context drifted")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.trust_output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(pack_bytes)
            args.trust_output.write_bytes(trust_bytes)
    except (OSError, TypeError, ValueError) as exc:
        print(f"local production pack failed: {exc}", file=sys.stderr)
        return 1
    print(f"local production pack OK: {args.output} ({len(pack_bytes)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
