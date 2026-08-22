"""版本化规则包manifest、文件hash和正式准入验证。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from functools import wraps
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
import weakref

import yaml

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
    ContractV4Error,
    PackManifestV4,
    PackSignatureV4,
    RulePromotionReceiptV4,
    RuleV4,
    SignatureEnvelopeV4,
    SourceSnapshotV4,
    require_engine_match,
)
from compiler_core.source_service import (
    SOURCE_AUTHENTICITY_RECEIPT_KIND,
    SOURCE_SNAPSHOT_KIND,
    SourceServiceV4,
    source_authenticity_payload_digest,
)
from compiler_core.trust import TrustVerifierV4
from compiler_core.types import DataQuality, normalize_rule_admission


PACK_SCHEMA_VERSION = "1.0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_MODALITIES = {"OBLIGATION", "PROHIBITION", "PERMISSION", "CONSTITUTIVE", "UNKNOWN", ""}
_TEXT_HASH_SUFFIXES = {".json", ".yaml", ".yml"}

RULE_KIND = "rule-v4"
RULE_PROMOTION_SUBJECT_KIND = "rule-promotion-subject"
LEGAL_APPROVAL_KIND = "legal-approval"
ENGINEERING_APPROVAL_KIND = "engineering-approval"
RULE_PROMOTION_RECEIPT_KIND = "rule-promotion-receipt"
PACK_MANIFEST_KIND = "pack-manifest"
PACK_BUILD_SUBJECT_KIND = "pack-build-subject"
BUILD_ATTESTATION_KIND = "build-attestation"
PACK_SIGNATURE_KIND = "pack-signature"
PACK_CONFIG_KIND = "domain-config"
PACK_COVERAGE_RECEIPT_KIND = "pack-coverage-receipt"
PACK_VERIFICATION_RECEIPT_KIND = "pack-verification-receipt"
TRUST_POLICY_KIND = "trust-policy"

RULE_PACK_SCOPE = "rule-pack"
RULE_COMPONENT_SCOPE = "rule-component"
LEGAL_APPROVAL_SCOPE = "legal-approval"
ENGINEERING_APPROVAL_SCOPE = "engineering-approval"
BUILD_ATTESTATION_SCOPE = "build-attestation"
JSON_MEDIA_TYPE = "application/json"

RULE_AUTHORITY_KIND = "rule-authority"
RULE_VARIABLE_KIND = "rule-variable-declaration"
RULE_PREMISE_KIND = "rule-premise"
RULE_CONCLUSION_KIND = "rule-conclusion"
RULE_PERMISSION_KIND = "rule-permission"
RULE_EXCEPTION_KIND = "rule-exception"
RULE_PRIORITY_KIND = "rule-priority"
RULE_ATTACK_KIND = "rule-attack"
RULE_TEMPORAL_KIND = "rule-temporal-constraint"
RULE_NUMERIC_KIND = "rule-numeric-constraint"
RULE_INTERPRETATION_KIND = "rule-interpretation"
RULE_DEFINED_TERM_KIND = "rule-defined-term"

_V4_MODALITIES = frozenset({"OBLIGATION", "PROHIBITION", "PERMISSION", "CONSTITUTIVE"})
class RulePackError(ValueError):
    """规则包结构或选择错误；code供CLI稳定映射。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _v4_fail(code: str, detail: str) -> None:
    raise ContractV4Error(code, detail)


def _sorted_refs(references: tuple[ContentRefV4, ...]) -> tuple[ContentRefV4, ...]:
    if any(type(reference) is not ContentRefV4 for reference in references):
        _v4_fail("PACK_REFERENCE_TYPE", "pack evidence must contain ContentRefV4 values")
    if len(set(references)) != len(references):
        _v4_fail("PACK_DUPLICATE_REFERENCE", "pack evidence references must not repeat")
    return tuple(sorted(references, key=lambda item: (item.kind, str(item.digest))))


def _exact_sorted_refs(
    references: tuple[ContentRefV4, ...],
    *,
    field: str,
    allow_empty: bool = False,
) -> tuple[ContentRefV4, ...]:
    if type(references) is not tuple or any(type(item) is not ContentRefV4 for item in references):
        _v4_fail("PACK_REFERENCE_TYPE", f"{field} must contain exact ContentRefV4 values")
    if not references and not allow_empty:
        _v4_fail("PACK_EMPTY", f"{field} must not be empty")
    ordered = _sorted_refs(references)
    if references != ordered:
        _v4_fail("PACK_REFERENCE_ORDER", f"{field} must be sorted by kind and digest")
    return references


def rule_promotion_subject_body(rule: RuleV4) -> dict[str, object]:
    if type(rule) is not RuleV4:
        _v4_fail("PACK_INPUT_TYPE", "rule promotion subject requires RuleV4")
    body = rule.to_dict()
    del body["rule_digest"]
    del body["promotion_receipt_refs"]
    return body


def rule_promotion_subject_ref(rule: RuleV4) -> ContentRefV4:
    body = rule_promotion_subject_body(rule)
    reference = ContentRefV4(RULE_PROMOTION_SUBJECT_KIND, digest_value(body))
    if reference.digest != rule.promotion_subject_digest():
        _v4_fail("PACK_PROMOTION_SUBJECT", "rule promotion subject digest is inconsistent")
    return reference


def rule_review_evidence_refs(
    rule: RuleV4,
    subject_ref: ContentRefV4,
    replay_policy_ref: ContentRefV4,
    review_kind: str,
) -> tuple[ContentRefV4, ...]:
    if type(rule) is not RuleV4 or subject_ref != rule_promotion_subject_ref(rule):
        _v4_fail("PACK_PROMOTION_SUBJECT", "review does not bind the rule promotion subject")
    if type(replay_policy_ref) is not ContentRefV4:
        _v4_fail("PACK_REFERENCE_TYPE", "review replay policy must be ContentRefV4")
    if review_kind == "legal":
        references = (
            subject_ref,
            rule.authority_ref,
            rule.source_snapshot_ref,
            rule.source_structure_ref,
            *rule.interpretation_choice_refs,
            *rule.defined_term_refs,
            replay_policy_ref,
        )
    elif review_kind == "engineering":
        references = (
            subject_ref,
            *rule.variable_declaration_refs,
            *rule.premise_refs,
            rule.conclusion_ref,
            *((rule.permission_ref,) if rule.permission_ref is not None else ()),
            *rule.exception_refs,
            *rule.priority_refs,
            *rule.attack_refs,
            *rule.temporal_constraint_refs,
            *rule.numeric_constraint_refs,
            replay_policy_ref,
        )
    else:
        _v4_fail("PACK_REVIEW_KIND", "review_kind must be legal or engineering")
    return _sorted_refs(references)


def promotion_receipt_evidence_refs(
    subject_ref: ContentRefV4,
    legal_review_ref: ContentRefV4,
    engineering_review_ref: ContentRefV4,
    replay_policy_ref: ContentRefV4,
) -> tuple[ContentRefV4, ...]:
    return _sorted_refs((
        subject_ref,
        legal_review_ref,
        engineering_review_ref,
        replay_policy_ref,
    ))


def _promotion_refs(manifest: PackManifestV4) -> tuple[ContentRefV4, ...]:
    return tuple(
        reference
        for reference in manifest.receipt_refs
        if reference.kind == RULE_PROMOTION_RECEIPT_KIND
    )


def build_subject_body(manifest: PackManifestV4) -> dict[str, object]:
    if type(manifest) is not PackManifestV4:
        _v4_fail("PACK_INPUT_TYPE", "build subject requires PackManifestV4")
    return {
        "schema_version": "jc/pack-build-subject/1.0",
        "pack_id": manifest.pack_id,
        "pack_version": manifest.pack_version,
        "engine_api": manifest.engine_api,
        "compiler_build_digest": str(manifest.compiler_build_digest),
        "source_tree_digest": str(manifest.source_tree_digest),
        "schema_digest": str(manifest.schema_digest),
        "rule_refs": [reference.to_dict() for reference in manifest.rule_refs],
        "source_refs": [reference.to_dict() for reference in manifest.source_refs],
        "config_refs": [reference.to_dict() for reference in manifest.config_refs],
        "promotion_receipt_refs": [
            reference.to_dict() for reference in _promotion_refs(manifest)
        ],
        "trust_policy_ref": manifest.trust_policy_ref.to_dict(),
        "coverage_receipt_refs": [
            reference.to_dict() for reference in manifest.coverage_receipt_refs
        ],
        "verification_receipt_refs": [
            reference.to_dict() for reference in manifest.verification_receipt_refs
        ],
    }


def build_subject_ref(manifest: PackManifestV4) -> ContentRefV4:
    return ContentRefV4(PACK_BUILD_SUBJECT_KIND, digest_value(build_subject_body(manifest)))


def build_attestation_evidence_refs(
    manifest: PackManifestV4,
    subject_ref: ContentRefV4,
) -> tuple[ContentRefV4, ...]:
    if subject_ref != build_subject_ref(manifest):
        _v4_fail("PACK_BUILD_SUBJECT", "build attestation uses another build subject")
    return _sorted_refs((
        subject_ref,
        *manifest.rule_refs,
        *manifest.source_refs,
        *manifest.config_refs,
        *_promotion_refs(manifest),
        manifest.trust_policy_ref,
        *manifest.coverage_receipt_refs,
        *manifest.verification_receipt_refs,
    ))


def pack_manifest_ref(manifest: PackManifestV4) -> ContentRefV4:
    if type(manifest) is not PackManifestV4:
        _v4_fail("PACK_INPUT_TYPE", "pack manifest reference requires PackManifestV4")
    return ContentRefV4(PACK_MANIFEST_KIND, manifest.canonical_digest())


def pack_release_evidence_refs(
    manifest_ref: ContentRefV4,
    manifest: PackManifestV4,
    subject_ref: ContentRefV4,
) -> tuple[ContentRefV4, ...]:
    if manifest_ref != pack_manifest_ref(manifest) or subject_ref != build_subject_ref(manifest):
        _v4_fail("PACK_RELEASE_BINDING", "pack release uses another manifest or build subject")
    return _sorted_refs((
        manifest_ref,
        subject_ref,
        *manifest.rule_refs,
        *manifest.source_refs,
        *manifest.config_refs,
        *manifest.receipt_refs,
        manifest.trust_policy_ref,
        *manifest.coverage_receipt_refs,
        *manifest.verification_receipt_refs,
    ))


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class VerifiedRulePackV4:
    """Immutable in-process handle issued only after full signed-pack verification."""

    pack_ref: ContentRefV4
    manifest_ref: ContentRefV4
    build_attestation_ref: ContentRefV4
    manifest: PackManifestV4
    rules: tuple[RuleV4, ...]
    domain_bindings: tuple[tuple[str, str, tuple[ContentRefV4, ...]], ...]

    def __new__(cls, *args: object, **kwargs: object) -> VerifiedRulePackV4:
        raise TypeError("VerifiedRulePackV4 is issued only by RulePackVerifierV4.verify")

    @property
    def status(self) -> str:
        _v4_fail("PACK_HANDLE_NOT_ISSUED", "verified pack handle was not issued by its verifier")

    @property
    def verifier_issued(self) -> bool:
        return False


class RulePackVerifierV4:
    """Derive one active V4 pack only from resolved bytes and scoped signatures."""

    def __init__(
        self,
        resolver: ArtifactResolverV4,
        source_service: SourceServiceV4,
        trust: TrustVerifierV4,
        *,
        expected_engine_api: str,
        expected_compiler_build_digest: DigestV4,
        expected_source_tree_digest: DigestV4,
        expected_schema_digest: DigestV4,
    ) -> None:
        if (
            type(resolver) is not ArtifactResolverV4
            or type(source_service) is not SourceServiceV4
            or type(trust) is not TrustVerifierV4
            or source_service._resolver is not resolver
            or source_service._trust is not trust
            or type(expected_engine_api) is not str
            or type(expected_compiler_build_digest) is not DigestV4
            or type(expected_source_tree_digest) is not DigestV4
            or type(expected_schema_digest) is not DigestV4
        ):
            _v4_fail("PACK_INPUT_TYPE", "pack verifier dependencies or identities are invalid")
        require_engine_match(expected_engine_api)
        self._resolver = resolver
        self._source_service = source_service
        self._trust = trust
        self._expected_engine_api = expected_engine_api
        self._expected_compiler_build_digest = expected_compiler_build_digest
        self._expected_source_tree_digest = expected_source_tree_digest
        self._expected_schema_digest = expected_schema_digest
        self._signature_principals: dict[tuple[object, ...], str] = {}
        self._verified: dict[ContentRefV4, VerifiedRulePackV4] = {}

    def _trust_state(self) -> tuple[object, ...]:
        return (
            self._trust.target_environment,
            self._trust.policy.canonical_bytes(),
            tuple(
                (
                    key_id,
                    key.issuer,
                    key.principal_id,
                    key.roles,
                    key.scopes,
                    key.artifact_kinds,
                    key.public_key,
                    key.production_allowed,
                )
                for key_id, key in sorted(self._trust._keys.items())
            ),
            tuple(sorted(str(digest) for digest in self._trust._revoked_subjects)),
            tuple(sorted(self._trust._revoked_nonces)),
        )

    def _resolve_json(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
    ) -> dict[str, object]:
        if type(reference) is not ContentRefV4 or reference.kind != kind:
            _v4_fail("PACK_REF_KIND", f"expected {kind} content reference")
        raw = self._resolver.resolve_content(
            reference,
            expected_artifact_kind=kind,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope=scope,
            max_bytes=self._resolver.max_artifact_bytes,
        )
        try:
            document = parse_json_document(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ContractV4Error("PACK_JSON_UTF8", f"{kind} must be valid UTF-8") from exc
        if type(document) is not dict:
            _v4_fail("PACK_JSON_TYPE", f"{kind} must be a JSON object")
        if raw != canonical_bytes(document):
            _v4_fail("PACK_NONCANONICAL_JSON", f"{kind} must use canonical JSON bytes")
        return document

    def _resolve_contract(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
        contract: type,
    ) -> object:
        document = self._resolve_json(reference, kind=kind, scope=scope)
        value = contract.from_dict(document)
        if canonical_bytes(document) != value.canonical_bytes():
            _v4_fail("PACK_NONCANONICAL_JSON", f"{kind} contract bytes are not canonical")
        return value

    def _resolve_self_digest_contract(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        contract: type,
        digest_field: str,
    ) -> object:
        body = self._resolve_json(reference, kind=kind, scope=RULE_PACK_SCOPE)
        if digest_field in body:
            _v4_fail("PACK_DIGEST_BODY", f"{kind} must store its canonical digest body")
        value = contract.from_dict({**body, digest_field: str(reference.digest)})
        if value.canonical_digest() != reference.digest or value.digest_body() != body:
            _v4_fail("PACK_SELF_DIGEST", f"{kind} self digest does not match its reference")
        return value

    def _resolve_component(self, reference: ContentRefV4, *, kind: str) -> None:
        self._resolve_json(reference, kind=kind, scope=RULE_COMPONENT_SCOPE)

    def _ensure_cached_signature_active(
        self,
        envelope: SignatureEnvelopeV4,
        *,
        now: CanonicalTimeV4,
        principal: str,
        separation: tuple[str, ...],
    ) -> None:
        policy = self._trust.policy
        if (
            now < policy.valid_from
            or (policy.valid_to is not None and not now < policy.valid_to)
            or now < envelope.issued_at
            or envelope.expires_at is None
            or not now < envelope.expires_at
        ):
            _v4_fail("PACK_SIGNATURE_INACTIVE", "cached signature is not active")
        if principal in separation:
            _v4_fail("TRUST_SEPARATION_OF_DUTIES", "cached signer violates separation of duties")

    def _verify_signature(
        self,
        reference: ContentRefV4,
        envelope: SignatureEnvelopeV4,
        *,
        expected_subject: DigestV4,
        expected_payload: DigestV4,
        role: str,
        scope: str,
        artifact_kind: str,
        status: str,
        now: CanonicalTimeV4,
        separation: tuple[str, ...],
    ) -> str:
        key = (
            reference,
            DigestV4.from_bytes(envelope.canonical_bytes()),
            self._trust_state(),
            expected_subject,
            expected_payload,
            role,
            scope,
            artifact_kind,
            status,
        )
        cached = self._signature_principals.get(key)
        if cached is not None:
            self._ensure_cached_signature_active(
                envelope,
                now=now,
                principal=cached,
                separation=separation,
            )
            return cached
        principal = self._trust.verify(
            envelope,
            expected_subject_digest=expected_subject,
            expected_payload_digest=expected_payload,
            required_role=role,
            required_scope=scope,
            required_artifact_kind=artifact_kind,
            expected_status=status,
            now=now,
            separation_from_principals=separation,
        )
        self._signature_principals[key] = principal
        return principal

    @staticmethod
    def _signature_without_run(envelope: SignatureEnvelopeV4, *, detail: str) -> None:
        if envelope.run_identity_ref is not None:
            _v4_fail("PACK_SIGNATURE_RUN", f"{detail} must precede a run identity")

    def _resolve_source(
        self,
        reference: ContentRefV4,
        *,
        now: CanonicalTimeV4,
    ) -> tuple[SourceSnapshotV4, str]:
        self._source_service.admit_snapshot(reference, now=now)
        value = self._resolve_contract(
            reference,
            kind=SOURCE_SNAPSHOT_KIND,
            scope="source-authenticity",
            contract=SourceSnapshotV4,
        )
        if type(value) is not SourceSnapshotV4:
            _v4_fail("PACK_SOURCE_TYPE", "source reference is not SourceSnapshotV4")
        envelope_value = self._resolve_contract(
            value.authenticity_receipt_ref,
            kind=SOURCE_AUTHENTICITY_RECEIPT_KIND,
            scope="source-authenticity",
            contract=SignatureEnvelopeV4,
        )
        if type(envelope_value) is not SignatureEnvelopeV4:
            _v4_fail("PACK_SOURCE_TYPE", "source receipt is not a signature envelope")
        envelope = envelope_value
        current_trust = TrustVerifierV4(
            policy=self._trust.policy,
            keys=tuple(key for _, key in sorted(self._trust._keys.items())),
            target_environment=self._trust.target_environment,
            revoked_subject_digests=tuple(
                sorted(self._trust._revoked_subjects, key=str)
            ),
            revoked_nonces=tuple(sorted(self._trust._revoked_nonces)),
        )
        principal = current_trust.verify(
            envelope,
            expected_subject_digest=value.raw_digest,
            expected_payload_digest=source_authenticity_payload_digest(value),
            required_role="source_attestor",
            required_scope="source-authenticity",
            required_artifact_kind=SOURCE_SNAPSHOT_KIND,
            expected_status="APPROVED",
            now=now,
            separation_from_principals=(),
        )
        return value, principal

    def _validate_rule_components(self, rule: RuleV4, source: SourceSnapshotV4) -> None:
        if rule.modality not in _V4_MODALITIES:
            _v4_fail("PACK_RULE_MODALITY", "formal rule has an unsupported modality")
        if (rule.modality == "PERMISSION") != (rule.permission_ref is not None):
            _v4_fail("PACK_RULE_PERMISSION", "permission modality and permission_ref disagree")
        if (
            rule.jurisdiction != source.jurisdiction
            or rule.source_locator != source.canonical_locator
            or rule.source_structure_ref != source.structure_map_ref
        ):
            _v4_fail("PACK_RULE_SOURCE", "rule does not bind its verified source snapshot")
        if rule.effective_from < source.effective_from or (
            source.effective_to is not None
            and (rule.effective_to is None or source.effective_to < rule.effective_to)
        ):
            _v4_fail("PACK_RULE_TIME", "rule validity exceeds its source validity")
        fields = (
            (rule.authority_ref, RULE_AUTHORITY_KIND),
            *((reference, RULE_VARIABLE_KIND) for reference in rule.variable_declaration_refs),
            *((reference, RULE_PREMISE_KIND) for reference in rule.premise_refs),
            (rule.conclusion_ref, RULE_CONCLUSION_KIND),
            *(
                ((rule.permission_ref, RULE_PERMISSION_KIND),)
                if rule.permission_ref is not None
                else ()
            ),
            *((reference, RULE_EXCEPTION_KIND) for reference in rule.exception_refs),
            *((reference, RULE_PRIORITY_KIND) for reference in rule.priority_refs),
            *((reference, RULE_ATTACK_KIND) for reference in rule.attack_refs),
            *((reference, RULE_TEMPORAL_KIND) for reference in rule.temporal_constraint_refs),
            *((reference, RULE_NUMERIC_KIND) for reference in rule.numeric_constraint_refs),
            *((reference, RULE_INTERPRETATION_KIND) for reference in rule.interpretation_choice_refs),
            *((reference, RULE_DEFINED_TERM_KIND) for reference in rule.defined_term_refs),
        )
        for reference, kind in fields:
            self._resolve_component(reference, kind=kind)
        for name, references in (
            ("variable_declaration_refs", rule.variable_declaration_refs),
            ("premise_refs", rule.premise_refs),
            ("exception_refs", rule.exception_refs),
            ("priority_refs", rule.priority_refs),
            ("attack_refs", rule.attack_refs),
            ("temporal_constraint_refs", rule.temporal_constraint_refs),
            ("numeric_constraint_refs", rule.numeric_constraint_refs),
            ("interpretation_choice_refs", rule.interpretation_choice_refs),
            ("defined_term_refs", rule.defined_term_refs),
        ):
            if len(set(references)) != len(references):
                _v4_fail("PACK_DUPLICATE_REFERENCE", f"RuleV4.{name} contains duplicates")

    def _verify_promotion(
        self,
        rule: RuleV4,
        receipt_ref: ContentRefV4,
        *,
        now: CanonicalTimeV4,
    ) -> tuple[RulePromotionReceiptV4, tuple[str, str, str]]:
        subject_ref = rule_promotion_subject_ref(rule)
        subject = self._resolver.resolve_content(
            subject_ref,
            expected_artifact_kind=RULE_PROMOTION_SUBJECT_KIND,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope=RULE_PACK_SCOPE,
            max_bytes=self._resolver.max_artifact_bytes,
        )
        if subject != canonical_bytes(rule_promotion_subject_body(rule)):
            _v4_fail("PACK_PROMOTION_SUBJECT", "stored promotion subject differs from RuleV4")
        receipt_value = self._resolve_contract(
            receipt_ref,
            kind=RULE_PROMOTION_RECEIPT_KIND,
            scope=RULE_PACK_SCOPE,
            contract=RulePromotionReceiptV4,
        )
        if type(receipt_value) is not RulePromotionReceiptV4:
            _v4_fail("PACK_PROMOTION_TYPE", "promotion receipt has the wrong contract type")
        receipt = receipt_value
        if (
            receipt.rule_subject_digest != subject_ref.digest
            or receipt.status != "APPROVED"
            or receipt.signature.issued_at != receipt.issued_at
        ):
            _v4_fail("PACK_PROMOTION_BINDING", "promotion receipt does not approve this rule")
        legal_value = self._resolve_contract(
            receipt.legal_review_ref,
            kind=LEGAL_APPROVAL_KIND,
            scope=LEGAL_APPROVAL_SCOPE,
            contract=SignatureEnvelopeV4,
        )
        engineering_value = self._resolve_contract(
            receipt.engineering_review_ref,
            kind=ENGINEERING_APPROVAL_KIND,
            scope=ENGINEERING_APPROVAL_SCOPE,
            contract=SignatureEnvelopeV4,
        )
        if type(legal_value) is not SignatureEnvelopeV4 or type(engineering_value) is not SignatureEnvelopeV4:
            _v4_fail("PACK_REVIEW_TYPE", "promotion reviews must be signature envelopes")
        legal = legal_value
        engineering = engineering_value
        for envelope, detail in ((legal, "legal review"), (engineering, "engineering review")):
            self._signature_without_run(envelope, detail=detail)
        replay_ref = self._trust.policy.replay_policy_ref
        legal_evidence = rule_review_evidence_refs(rule, subject_ref, replay_ref, "legal")
        engineering_evidence = rule_review_evidence_refs(
            rule, subject_ref, replay_ref, "engineering"
        )
        if legal.evidence_refs != legal_evidence or engineering.evidence_refs != engineering_evidence:
            _v4_fail("PACK_REVIEW_EVIDENCE", "rule review evidence is incomplete or reordered")
        legal_principal = self._verify_signature(
            receipt.legal_review_ref,
            legal,
            expected_subject=subject_ref.digest,
            expected_payload=subject_ref.digest,
            role="legal_reviewer",
            scope=LEGAL_APPROVAL_SCOPE,
            artifact_kind=LEGAL_APPROVAL_KIND,
            status="APPROVED",
            now=now,
            separation=(),
        )
        engineering_principal = self._verify_signature(
            receipt.engineering_review_ref,
            engineering,
            expected_subject=subject_ref.digest,
            expected_payload=subject_ref.digest,
            role="engineering_reviewer",
            scope=ENGINEERING_APPROVAL_SCOPE,
            artifact_kind=ENGINEERING_APPROVAL_KIND,
            status="APPROVED",
            now=now,
            separation=(legal_principal,),
        )
        service_evidence = promotion_receipt_evidence_refs(
            subject_ref,
            receipt.legal_review_ref,
            receipt.engineering_review_ref,
            replay_ref,
        )
        self._signature_without_run(receipt.signature, detail="promotion receipt")
        if receipt.signature.evidence_refs != service_evidence:
            _v4_fail("PACK_PROMOTION_EVIDENCE", "promotion receipt evidence is incomplete")
        if (
            receipt.issued_at < legal.issued_at
            or receipt.issued_at < engineering.issued_at
            or receipt.signature.expires_at is None
            or legal.expires_at is None
            or engineering.expires_at is None
            or legal.expires_at < receipt.signature.expires_at
            or engineering.expires_at < receipt.signature.expires_at
        ):
            _v4_fail("PACK_PROMOTION_TIME", "promotion receipt outlives or predates a review")
        service_principal = self._verify_signature(
            receipt_ref,
            receipt.signature,
            expected_subject=subject_ref.digest,
            expected_payload=digest_value(receipt.signature_body()),
            role="service_signer",
            scope="service-certificate",
            artifact_kind="service-certificate",
            status="APPROVED",
            now=now,
            separation=(legal_principal, engineering_principal),
        )
        return receipt, (legal_principal, engineering_principal, service_principal)

    def _validate_config(
        self,
        reference: ContentRefV4,
    ) -> tuple[str, str, str, str, tuple[ContentRefV4, ...]]:
        document = self._resolve_json(reference, kind=PACK_CONFIG_KIND, scope=RULE_PACK_SCOPE)
        if set(document) != {
            "schema_version", "domain_id", "namespace", "jurisdiction",
            "governing_law", "rule_refs",
        }:
            _v4_fail("PACK_CONFIG_FIELDS", "domain config has missing or unknown fields")
        if document.get("schema_version") != "jc/domain-config/1.0":
            _v4_fail("PACK_CONFIG_SCHEMA", "domain config schema is unsupported")
        strings = tuple(document.get(field) for field in (
            "domain_id", "namespace", "jurisdiction", "governing_law",
        ))
        if any(type(value) is not str or not value for value in strings):
            _v4_fail("PACK_CONFIG_TYPE", "domain config identity fields must be non-empty strings")
        raw_refs = document.get("rule_refs")
        if type(raw_refs) is not list:
            _v4_fail("PACK_CONFIG_TYPE", "domain config rule_refs must be an array")
        refs = tuple(ContentRefV4.from_dict(item) for item in raw_refs)
        _exact_sorted_refs(refs, field="domain-config.rule_refs")
        return strings[0], strings[1], strings[2], strings[3], refs

    def _validate_gate_receipt(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        schema_version: str,
        rule_refs: tuple[ContentRefV4, ...],
    ) -> None:
        document = self._resolve_json(reference, kind=kind, scope=RULE_PACK_SCOPE)
        if (
            set(document) != {"schema_version", "status", "rule_refs"}
            or document.get("schema_version") != schema_version
            or document.get("status") != "PASS"
        ):
            _v4_fail("PACK_GATE_RECEIPT", f"{kind} is not an exact PASS receipt")
        raw_refs = document.get("rule_refs")
        if type(raw_refs) is not list:
            _v4_fail("PACK_GATE_RECEIPT", f"{kind}.rule_refs must be an array")
        observed = tuple(ContentRefV4.from_dict(item) for item in raw_refs)
        if observed != rule_refs:
            _v4_fail("PACK_GATE_RECEIPT", f"{kind} does not cover the exact rule set")

    def verify(
        self,
        pack_ref: ContentRefV4,
        *,
        now: CanonicalTimeV4,
    ) -> VerifiedRulePackV4:
        """Verify one final PackSignatureV4 reference; caller status is never accepted."""

        if (
            type(pack_ref) is not ContentRefV4
            or pack_ref.kind != PACK_SIGNATURE_KIND
            or type(now) is not CanonicalTimeV4
        ):
            _v4_fail("PACK_INPUT_TYPE", "verify requires a pack-signature ref and canonical time")
        signature_value = self._resolve_contract(
            pack_ref,
            kind=PACK_SIGNATURE_KIND,
            scope=RULE_PACK_SCOPE,
            contract=PackSignatureV4,
        )
        if type(signature_value) is not PackSignatureV4:
            _v4_fail("PACK_SIGNATURE_TYPE", "pack ref does not resolve PackSignatureV4")
        pack_signature = signature_value
        manifest_value = self._resolve_self_digest_contract(
            pack_signature.manifest_ref,
            kind=PACK_MANIFEST_KIND,
            contract=PackManifestV4,
            digest_field="manifest_digest",
        )
        if type(manifest_value) is not PackManifestV4:
            _v4_fail("PACK_MANIFEST_TYPE", "pack signature does not resolve PackManifestV4")
        manifest = manifest_value
        for name, references in (
            ("rule_refs", manifest.rule_refs),
            ("source_refs", manifest.source_refs),
            ("config_refs", manifest.config_refs),
            ("receipt_refs", manifest.receipt_refs),
            ("coverage_receipt_refs", manifest.coverage_receipt_refs),
            ("verification_receipt_refs", manifest.verification_receipt_refs),
        ):
            _exact_sorted_refs(references, field=f"PackManifestV4.{name}")
        if manifest.engine_api != self._expected_engine_api:
            _v4_fail("PACK_ENGINE_API", "pack engine_api does not match this verifier")
        if (
            manifest.compiler_build_digest != self._expected_compiler_build_digest
            or manifest.source_tree_digest != self._expected_source_tree_digest
            or manifest.schema_digest != self._expected_schema_digest
        ):
            _v4_fail("PACK_BUILD_IDENTITY", "pack build, source tree, or schema identity is wrong")
        expected_policy_ref = ContentRefV4(
            TRUST_POLICY_KIND,
            self._trust.policy.canonical_digest(),
        )
        if manifest.trust_policy_ref != expected_policy_ref:
            _v4_fail("PACK_TRUST_POLICY", "pack does not bind the active trust policy")

        source_rows = {
            reference: self._resolve_source(reference, now=now)
            for reference in manifest.source_refs
        }
        source_by_ref = {reference: row[0] for reference, row in source_rows.items()}
        source_principals = {row[1] for row in source_rows.values()}
        rules: list[RuleV4] = []
        by_rule_ref: dict[ContentRefV4, RuleV4] = {}
        for reference in manifest.rule_refs:
            value = self._resolve_self_digest_contract(
                reference,
                kind=RULE_KIND,
                contract=RuleV4,
                digest_field="rule_digest",
            )
            if type(value) is not RuleV4:
                _v4_fail("PACK_RULE_TYPE", "rule ref does not resolve RuleV4")
            rule = value
            source = source_by_ref.get(rule.source_snapshot_ref)
            if source is None:
                _v4_fail("PACK_SOURCE_BINDING", "rule source is outside manifest.source_refs")
            self._validate_rule_components(rule, source)
            rules.append(rule)
            by_rule_ref[reference] = rule
        if len({rule.rule_id for rule in rules}) != len(rules):
            _v4_fail("PACK_RULE_ID_COLLISION", "rule_id must be unique in a pack")
        used_sources = {rule.source_snapshot_ref for rule in rules}
        if used_sources != set(manifest.source_refs):
            _v4_fail("PACK_SOURCE_BINDING", "manifest has missing or orphan source refs")

        config_rows = tuple(self._validate_config(reference) for reference in manifest.config_refs)
        identities = {(row[0], row[1]) for row in config_rows}
        if len(identities) != len(config_rows):
            _v4_fail("PACK_CONFIG_COLLISION", "domain_id and namespace must be unique")
        config_rule_refs = tuple(reference for row in config_rows for reference in row[4])
        if (
            len(config_rule_refs) != len(set(config_rule_refs))
            or set(config_rule_refs) != set(manifest.rule_refs)
        ):
            _v4_fail("PACK_CONFIG_BINDING", "domain configs must partition the exact rule set")
        for _, _, jurisdiction, governing_law, references in config_rows:
            if any(
                by_rule_ref[reference].jurisdiction != jurisdiction
                or by_rule_ref[reference].governing_law != governing_law
                for reference in references
            ):
                _v4_fail("PACK_CONFIG_BINDING", "domain config identity differs from a rule")

        for reference in manifest.coverage_receipt_refs:
            self._validate_gate_receipt(
                reference,
                kind=PACK_COVERAGE_RECEIPT_KIND,
                schema_version="jc/pack-coverage-receipt/1.0",
                rule_refs=manifest.rule_refs,
            )
        for reference in manifest.verification_receipt_refs:
            self._validate_gate_receipt(
                reference,
                kind=PACK_VERIFICATION_RECEIPT_KIND,
                schema_version="jc/pack-verification-receipt/1.0",
                rule_refs=manifest.rule_refs,
            )

        expected_promotions = tuple(
            sorted(
                (reference for rule in rules for reference in rule.promotion_receipt_refs),
                key=lambda item: (item.kind, str(item.digest)),
            )
        )
        if any(len(rule.promotion_receipt_refs) != 1 for rule in rules):
            _v4_fail("PACK_PROMOTION_REQUIRED", "each formal RuleV4 requires one promotion receipt")
        if len(set(expected_promotions)) != len(expected_promotions):
            _v4_fail("PACK_PROMOTION_REPLAY", "one promotion receipt cannot activate multiple rules")
        actual_promotions = _promotion_refs(manifest)
        build_refs = tuple(
            reference for reference in manifest.receipt_refs
            if reference.kind == BUILD_ATTESTATION_KIND
        )
        if (
            actual_promotions != expected_promotions
            or len(build_refs) != 1
            or len(manifest.receipt_refs) != len(actual_promotions) + 1
        ):
            _v4_fail("PACK_RECEIPT_BINDING", "manifest receipts do not close promotions and build")
        promotion_principals: list[str] = []
        promotion_principals_by_role: tuple[list[str], list[str], list[str]] = ([], [], [])
        promotion_receipts: list[RulePromotionReceiptV4] = []
        for rule in rules:
            receipt_ref = rule.promotion_receipt_refs[0]
            receipt, principals = self._verify_promotion(rule, receipt_ref, now=now)
            promotion_receipts.append(receipt)
            promotion_principals.extend(principals)
            for role_principals, principal in zip(promotion_principals_by_role, principals):
                role_principals.append(principal)
        legal_principals, engineering_principals, service_principals = (
            set(principals) for principals in promotion_principals_by_role
        )
        seen_principals: set[str] = set()
        for role_principals in (
            source_principals,
            legal_principals,
            engineering_principals,
            service_principals,
        ):
            if seen_principals & role_principals:
                _v4_fail(
                    "TRUST_SEPARATION_OF_DUTIES",
                    "source, legal, engineering, and service roles must be globally disjoint",
                )
            seen_principals.update(role_principals)

        build_ref = build_refs[0]
        build_value = self._resolve_contract(
            build_ref,
            kind=BUILD_ATTESTATION_KIND,
            scope=BUILD_ATTESTATION_SCOPE,
            contract=SignatureEnvelopeV4,
        )
        if type(build_value) is not SignatureEnvelopeV4:
            _v4_fail("PACK_BUILD_TYPE", "build attestation must be a signature envelope")
        build = build_value
        build_subject = build_subject_ref(manifest)
        stored_build_subject = self._resolver.resolve_content(
            build_subject,
            expected_artifact_kind=PACK_BUILD_SUBJECT_KIND,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope=RULE_PACK_SCOPE,
            max_bytes=self._resolver.max_artifact_bytes,
        )
        if stored_build_subject != canonical_bytes(build_subject_body(manifest)):
            _v4_fail("PACK_BUILD_SUBJECT", "stored build subject differs from manifest outputs")
        self._signature_without_run(build, detail="build attestation")
        if build.evidence_refs != build_attestation_evidence_refs(manifest, build_subject):
            _v4_fail("PACK_BUILD_EVIDENCE", "build attestation evidence is incomplete")
        if any(build.issued_at < receipt.issued_at for receipt in promotion_receipts):
            _v4_fail("PACK_BUILD_TIME", "build attestation predates a promotion receipt")
        distinct_promoters = tuple(dict.fromkeys((
            *sorted(source_principals),
            *promotion_principals,
        )))
        build_principal = self._verify_signature(
            build_ref,
            build,
            expected_subject=build_subject.digest,
            expected_payload=build_subject.digest,
            role="build_attestor",
            scope=BUILD_ATTESTATION_SCOPE,
            artifact_kind=BUILD_ATTESTATION_KIND,
            status="APPROVED",
            now=now,
            separation=distinct_promoters,
        )

        self._signature_without_run(pack_signature.signature, detail="pack release")
        expected_release_evidence = pack_release_evidence_refs(
            pack_signature.manifest_ref,
            manifest,
            build_subject,
        )
        if pack_signature.signature.evidence_refs != expected_release_evidence:
            _v4_fail("PACK_RELEASE_EVIDENCE", "pack release evidence is incomplete")
        if (
            pack_signature.signature.issued_at < build.issued_at
            or pack_signature.signature.expires_at is None
            or build.expires_at is None
            or build.expires_at < pack_signature.signature.expires_at
            or any(
                receipt.signature.expires_at is None
                or receipt.signature.expires_at < pack_signature.signature.expires_at
                for receipt in promotion_receipts
            )
        ):
            _v4_fail("PACK_RELEASE_TIME", "pack release outlives or predates its approvals")
        self._verify_signature(
            pack_ref,
            pack_signature.signature,
            expected_subject=pack_signature.manifest_ref.digest,
            expected_payload=digest_value(pack_signature.signature_body()),
            role="pack_releaser",
            scope="pack-release",
            artifact_kind="rule-pack",
            status="APPROVED",
            now=now,
            separation=(*distinct_promoters, build_principal),
        )
        candidate = object.__new__(VerifiedRulePackV4)
        object.__setattr__(candidate, "pack_ref", pack_ref)
        object.__setattr__(candidate, "manifest_ref", pack_signature.manifest_ref)
        object.__setattr__(candidate, "build_attestation_ref", build_ref)
        object.__setattr__(candidate, "manifest", manifest)
        object.__setattr__(candidate, "rules", tuple(rules))
        object.__setattr__(
            candidate,
            "domain_bindings",
            tuple((row[0], row[1], row[4]) for row in config_rows),
        )
        existing = self._verified.get(pack_ref)
        if existing is not None:
            if existing != candidate:
                _v4_fail("PACK_IDENTITY_COLLISION", "pack ref changed verified materials")
            return existing
        self._verified[pack_ref] = candidate
        return candidate


def _bind_verified_handle_issuance() -> None:
    issued: dict[
        int,
        tuple[
            weakref.ReferenceType[VerifiedRulePackV4],
            weakref.ReferenceType[RulePackVerifierV4],
            tuple[object, ...],
        ],
    ] = {}
    verify_impl = RulePackVerifierV4.verify

    @wraps(verify_impl)
    def verify(
        self: RulePackVerifierV4,
        pack_ref: ContentRefV4,
        *,
        now: CanonicalTimeV4,
    ) -> VerifiedRulePackV4:
        handle = verify_impl(self, pack_ref, now=now)
        identity = id(handle)
        issued[identity] = (
            weakref.ref(
                handle,
                lambda _reference, key=identity: issued.pop(key, None),
            ),
            weakref.ref(self),
            self._trust_state(),
        )
        return handle

    def verifier_issued(handle: VerifiedRulePackV4) -> bool:
        entry = issued.get(id(handle))
        if entry is None:
            return False
        handle_ref, verifier_ref, trust_state = entry
        verifier = verifier_ref()
        return (
            handle_ref() is handle
            and verifier is not None
            and verifier._trust_state() == trust_state
        )

    def status(handle: VerifiedRulePackV4) -> str:
        if not verifier_issued(handle):
            _v4_fail(
                "PACK_HANDLE_NOT_ISSUED",
                "verified pack handle was not issued by its verifier",
            )
        return "VERIFIED_ACTIVE"

    RulePackVerifierV4.verify = verify
    VerifiedRulePackV4.verifier_issued = property(verifier_issued)
    VerifiedRulePackV4.status = property(status)


_bind_verified_handle_issuance()
del _bind_verified_handle_issuance


@dataclass(frozen=True)
class PackVerification:
    """一次manifest完整性与正式可用性验证结果。"""

    pack_id: str
    version: str
    jurisdiction: str
    kind: str
    integrity_valid: bool
    reasoning_ready: bool
    content_digest: str
    inventory: dict[str, int]
    verified_rule_ids: tuple[str, ...] = ()
    candidate_rule_ids: tuple[str, ...] = ()
    rejected_rule_ids: tuple[str, ...] = ()
    issues: tuple[dict[str, str], ...] = ()
    config_files: tuple[tuple[str, str], ...] = ()
    governing_law: str = ""
    review_only: bool = False
    distribution_channel: str = ""
    build_attestation: str = ""
    effective_from: str = ""
    effective_to: str = ""
    declared_status: str = ""
    development_override: bool = False
    override_path_hash: str = ""

    def to_dict(self, *, include_candidates: bool = True) -> dict[str, Any]:
        """返回确定性机器结果；list命令可省略大候选列表。"""

        payload = {
            "pack_id": self.pack_id,
            "version": self.version,
            "jurisdiction": self.jurisdiction,
            "kind": self.kind,
            "integrity_valid": self.integrity_valid,
            "reasoning_ready": self.reasoning_ready,
            "content_digest": self.content_digest,
            "inventory": dict(self.inventory),
            "verified_rule_ids": tuple(self.verified_rule_ids),
            "candidate_rule_count": len(self.candidate_rule_ids),
            "rejected_rule_count": len(self.rejected_rule_ids),
            "issues": [dict(issue) for issue in self.issues],
            "governing_law": self.governing_law,
            "review_only": self.review_only,
            "distribution_channel": self.distribution_channel,
            "build_attestation": self.build_attestation,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "declared_status": self.declared_status,
            "development_override": self.development_override,
            "override_path_hash": self.override_path_hash,
            "config_files": list(self.config_files),
        }
        if include_candidates:
            payload["candidate_rule_ids"] = list(self.candidate_rule_ids)
        return payload


@dataclass(frozen=True)
class LoadedRulePack:
    """通过完整门禁后可交给application和离线缓存的规则包材料。"""

    descriptor: Any
    rules: tuple[Any, ...]
    source_manifest: Any
    verification: PackVerification
    manifest_path: Path
    config_root: Path
    config_files: tuple[Path, ...]
    resource_paths: tuple[Path, ...]
    _issuer: object = field(repr=False, compare=False)

    @property
    def registry_issued(self) -> bool:
        """仅registry加载器可签发可求值handle。"""

        return self._issuer is _REGISTRY_HANDLE_ISSUER


@dataclass(frozen=True)
class LoadedCorpusPack:
    """通过manifest完整性门禁、但不具备正式推理资格的语料材料。"""

    verification: PackVerification
    manifest: Mapping[str, Any]
    manifest_path: Path
    rule_paths: tuple[Path, ...]
    source_paths: tuple[Path, ...]
    config_root: Path


_REGISTRY_HANDLE_ISSUER = object()


class RulePackRegistry:
    """扫描单一configs根下的pack manifests并拒绝重复pack ID。"""

    def __init__(self, config_root: Path, *, development_override: bool = False) -> None:
        self.config_root = Path(config_root).resolve()
        self.development_override = development_override
        self.override_path_hash = (
            hashlib.sha256(str(self.config_root).encode("utf-8")).hexdigest()
            if development_override
            else ""
        )
        # Pack由manifest内容摘要绑定；同一registry内可安全复用只读加载结果，不复用案件状态或recorder。
        self._reasoning_cache: dict[str, LoadedRulePack] = {}

    def manifests(self) -> dict[str, Path]:
        """返回pack ID到manifest路径的稳定映射。"""

        discovered: dict[str, Path] = {}
        for path in sorted((self.config_root / "packs").glob("*/manifest.yaml")):
            document = _load_yaml_mapping(path)
            pack_id = str(document.get("pack_id", "")).strip()
            if not pack_id:
                raise RulePackError("MISSING_PACK_ID", f"manifest has no pack_id: {path.name}")
            if pack_id in discovered:
                raise RulePackError("DUPLICATE_PACK_ID", pack_id)
            discovered[pack_id] = path
        return discovered

    def verify(self, pack_id: str) -> PackVerification:
        """验证一个已注册pack；缺失可选pack不得回退其他法域。"""

        manifests = self.manifests()
        if pack_id not in manifests:
            raise RulePackError("PACK_NOT_INSTALLED", pack_id)
        return verify_pack_manifest(
            manifests[pack_id],
            self.config_root,
            development_override=self.development_override,
            override_path_hash=self.override_path_hash,
        )

    def list_installed(self) -> tuple[dict[str, Any], ...]:
        """只读manifest摘要，不把list命令伪装成完整hash验证。"""

        summaries: list[dict[str, Any]] = []
        for pack_id, path in sorted(self.manifests().items()):
            document = _load_yaml_mapping(path)
            summaries.append({
                "pack_id": pack_id,
                "version": str(document.get("version", "")),
                "jurisdiction": str(document.get("jurisdiction", "")),
                "kind": str(document.get("kind", "")),
                "declared_status": str(document.get("status", "")),
                "content_digest": str(document.get("content_digest", "")),
                "inventory": dict(document.get("inventory", {})),
                "verification_status": "not_run",
                "development_override": self.development_override,
                "override_path_hash": self.override_path_hash,
            })
        return tuple(summaries)

    def verify_all(self) -> tuple[PackVerification, ...]:
        """按pack ID排序验证全部已安装manifest。"""

        return tuple(self.verify(pack_id) for pack_id in sorted(self.manifests()))

    def load_reasoning_pack(self, pack_id: str) -> LoadedRulePack:
        """加载已验证且非空的official pack；candidate pack不得进入application。"""

        if pack_id in self._reasoning_cache:
            return self._reasoning_cache[pack_id]

        verification = self.verify(pack_id)
        development_loadable = bool(
            verification.development_override
            and verification.integrity_valid
            and verification.kind == "official"
            and verification.declared_status == "active"
            and verification.governing_law
            and verification.verified_rule_ids
        )
        if not verification.reasoning_ready and not development_loadable:
            raise RulePackError("PACK_NOT_REASONING_READY", pack_id)
        manifest_path = self.manifests()[pack_id]
        document = _load_yaml_mapping(manifest_path)
        from compiler_core.contracts import RulePackDescriptor
        from compiler_core.evaluator import load_rules_from_yaml
        from compiler_core.source_manifest import SourceManifest

        rules: list[Any] = []
        resources: list[Path] = [manifest_path]
        for entry in document["rule_files"]:
            path = self.config_root / entry["path"]
            rules.extend(load_rules_from_yaml(str(path)))
            resources.append(path)
        source_manifest = SourceManifest()
        for entry in document["source_files"]:
            path = self.config_root / entry["path"]
            source_manifest.load(str(path))
            resources.append(path)
        config_file_paths: list[Path] = []
        config_file_names: list[str] = []
        for entry in document["config_files"]:
            path = _validated_resource_path(self.config_root, entry, [])
            if path is None:
                raise RulePackError("PACK_PATH_VERIFICATION_ERROR", entry["path"])
            resources.append(path)
            config_file_paths.append(path)
            config_file_names.append(path.relative_to(self.config_root).as_posix())
        rule_ids = tuple(rule.id for rule in rules)
        id_set = set(rule_ids)
        verified_ids = tuple(id for id in verification.verified_rule_ids if id in id_set)
        candidate_ids = tuple(id for id in verification.candidate_rule_ids if id in id_set)
        rejected_ids = tuple(id for id in verification.rejected_rule_ids if id in id_set)
        descriptor = RulePackDescriptor(
            pack_id=verification.pack_id,
            version=verification.version,
            content_digest=verification.content_digest,
            verified_rule_ids=verified_ids,
            candidate_rule_ids=tuple(sorted(candidate_ids)),
            rejected_rule_ids=tuple(sorted(rejected_ids)),
            jurisdiction=verification.jurisdiction,
            governing_law=verification.governing_law,
            kind=verification.kind,
            review_only=verification.review_only,
            distribution_channel=verification.distribution_channel,
            development_override=verification.development_override,
            build_attestation=verification.build_attestation,
            effective_from=verification.effective_from,
            effective_to=verification.effective_to,
            config_files=tuple(config_file_names),
        )
        loaded = LoadedRulePack(
            descriptor=descriptor,
            rules=tuple(rules),
            source_manifest=source_manifest,
            verification=verification,
            manifest_path=manifest_path,
            config_root=self.config_root,
            resource_paths=tuple(resources),
            config_files=tuple(config_file_paths),
            _issuer=_REGISTRY_HANDLE_ISSUER,
        )
        self._reasoning_cache[pack_id] = loaded
        return loaded

    def load_corpus_pack(self, pack_id: str) -> LoadedCorpusPack:
        """加载完整性有效的语料pack，且不把candidate晋升为reasoning-ready。"""

        verification = self.verify(pack_id)
        if not verification.integrity_valid:
            raise RulePackError("PACK_INTEGRITY_INVALID", pack_id)
        manifest_path = self.manifests()[pack_id]
        document = _load_yaml_mapping(manifest_path)
        rule_paths = tuple(
            (self.config_root / str(entry["path"])).resolve()
            for entry in document.get("rule_files", ())
        )
        source_paths = tuple(
            (self.config_root / str(entry["path"])).resolve()
            for entry in document.get("source_files", ())
        )
        for path in (*rule_paths, *source_paths):
            try:
                path.relative_to(self.config_root)
            except ValueError as exc:
                raise RulePackError("PACK_PATH_ESCAPE", path.name) from exc
        return LoadedCorpusPack(
            verification=verification,
            manifest=document,
            manifest_path=manifest_path,
            rule_paths=rule_paths,
            source_paths=source_paths,
            config_root=self.config_root,
        )


def verify_pack_manifest(
    manifest_path: Path,
    config_root: Path,
    *,
    development_override: bool = False,
    override_path_hash: str = "",
) -> PackVerification:
    """校验manifest、文件hash、ID唯一性、计数及正式来源准入。"""

    document = _load_yaml_mapping(manifest_path)
    issues: list[dict[str, str]] = []
    required = {
        "schema_version", "pack_id", "version", "kind", "jurisdiction", "governing_law",
        "effective_from", "effective_to", "rule_files", "source_files", "inventory",
        "config_files", "content_digest", "build_commit",
    }
    for field in sorted(required - set(document)):
        _issue(issues, "MISSING_MANIFEST_FIELD", field)
    if document.get("schema_version") != PACK_SCHEMA_VERSION:
        _issue(issues, "UNSUPPORTED_PACK_SCHEMA", str(document.get("schema_version", "")))
    _validate_date(document.get("effective_from"), "effective_from", issues, allow_empty=False)
    _validate_date(document.get("effective_to"), "effective_to", issues, allow_empty=True)
    _validate_effective_range(document, issues)
    if not _SHA256_RE.fullmatch(str(document.get("content_digest", ""))):
        _issue(issues, "INVALID_CONTENT_DIGEST", "content_digest must be SHA-256")

    config_root = Path(config_root).resolve()
    rules: list[dict[str, Any]] = []
    source_entries: dict[str, dict[str, Any]] = {}
    config_files: list[tuple[str, str]] = []
    for entry in _file_entries(document.get("rule_files"), "rule_files", issues):
        path = _validated_resource_path(config_root, entry, issues)
        if path is None:
            continue
        _verify_file_hash(path, entry, issues)
        loaded = _load_yaml_mapping(path)
        file_rules = loaded.get("rules", [])
        if not isinstance(file_rules, list):
            _issue(issues, "INVALID_RULE_ARRAY", entry["path"])
            continue
        meta = loaded.get("_meta", {})
        if isinstance(meta, Mapping) and "total" in meta and meta["total"] != len(file_rules):
            _issue(issues, "META_TOTAL_MISMATCH", entry["path"])
        rules.extend(dict(rule) for rule in file_rules if isinstance(rule, Mapping))
    for entry in _file_entries(document.get("source_files"), "source_files", issues):
        path = _validated_resource_path(config_root, entry, issues)
        if path is None:
            continue
        _verify_file_hash(path, entry, issues)
        loaded = _load_yaml_mapping(path)
        for source in loaded.get("sources", []) if isinstance(loaded.get("sources", []), list) else []:
            if not isinstance(source, Mapping):
                continue
            source_id = str(source.get("source_id", ""))
            if source_id in source_entries:
                _issue(issues, "DUPLICATE_SOURCE_ID", source_id)
            source_entries[source_id] = dict(source)
    for entry in _file_entries(document.get("config_files"), "config_files", issues):
        path = _validated_resource_path(config_root, entry, issues)
        if path is not None:
            _verify_file_hash(path, entry, issues)
            try:
                relative = path.relative_to(config_root).as_posix()
            except ValueError:
                relative = path.name
            config_files.append((relative, entry["sha256"]))

    ids = [str(rule.get("id", "")) for rule in rules]
    for rule_id in sorted(rule_id for rule_id, count in Counter(ids).items() if count > 1):
        _issue(issues, "DUPLICATE_RULE_ID", rule_id)
    if any(not rule_id for rule_id in ids):
        _issue(issues, "EMPTY_RULE_ID", "one or more rules have no id")

    governing_law = str(document.get("governing_law", ""))
    distribution_channel = str(document.get("distribution_channel", ""))
    manifest_development = bool(document.get("development_override", False))
    effective_development = bool(development_override or manifest_development)
    build_attestation = str(document.get("build_attestation", ""))
    effective_from = str(document.get("effective_from", ""))
    effective_to = str(document.get("effective_to", ""))
    status = str(document.get("status", ""))
    review_only = (
        status != "active"
        or distribution_channel == "review"
        or bool(document.get("review_only"))
        or effective_development
    )
    eligible_ids: list[str] = []
    candidate_ids: list[str] = []
    rejected_ids: list[str] = []
    official = document.get("kind") == "official"
    relation_validity = _validate_rule_relations(rules, issues) if official else {}
    for rule in rules:
        rule_id = str(rule.get("id", ""))
        if not rule_id:
            _issue(issues, "EMPTY_RULE_ID", "one or more rules have no id")
            continue
        if not official:
            candidate_ids.append(rule_id)
            continue
        if not relation_validity.get(rule_id, False):
            rejected_ids.append(rule_id)
            continue
        if _official_rule_eligible(rule, source_entries, issues):
            eligible_ids.append(rule_id)
        else:
            candidate_ids.append(rule_id)
    if official and not governing_law:
        _issue(issues, "MISSING_GOVERNING_LAW", "governing_law is required for official packs")
    if official and not build_attestation:
        _issue(issues, "MISSING_BUILD_ATTESTATION", "build attestation is required for official packs")
    elif official and not _SHA256_RE.fullmatch(build_attestation):
        _issue(issues, "INVALID_BUILD_ATTESTATION", "build attestation must be SHA-256")
    inventory = {
        "corpus_total": len(rules),
        "reasoning_eligible_total": len(eligible_ids),
        "candidate_only_total": len(candidate_ids) + len(rejected_ids),
    }
    expected_inventory = document.get("inventory")
    if expected_inventory != inventory:
        _issue(issues, "INVENTORY_MISMATCH", json.dumps(inventory, sort_keys=True))
    calculated_digest = manifest_content_digest(document)
    if document.get("content_digest") != calculated_digest:
        _issue(issues, "MANIFEST_DIGEST_MISMATCH", calculated_digest)

    blocker_codes = {
        issue["code"]
        for issue in issues
        if issue["code"] != "MISSING_BUILD_ATTESTATION"
    }
    if official and not eligible_ids:
        _issue(issues, "EMPTY_OFFICIAL_PACK", "no reasoning-eligible rules")
    integrity_valid = not blocker_codes
    reasoning_ready = bool(
        integrity_valid
        and official
        and not review_only
        and governing_law
        and build_attestation
        and eligible_ids
        and status == "active"
    )
    verified_rule_ids = tuple(sorted(
        eligible_ids if official else {str(rule.get("id", "")) for rule in rules}
    ))
    return PackVerification(
        pack_id=str(document.get("pack_id", "")),
        version=str(document.get("version", "")),
        jurisdiction=str(document.get("jurisdiction", "")),
        kind=str(document.get("kind", "")),
        governing_law=governing_law,
        integrity_valid=integrity_valid,
        reasoning_ready=reasoning_ready,
        content_digest=str(document.get("content_digest", "")),
        inventory=inventory,
        verified_rule_ids=verified_rule_ids,
        candidate_rule_ids=tuple(sorted(candidate_ids)),
        rejected_rule_ids=tuple(sorted(rejected_ids)),
        issues=tuple(sorted(issues, key=lambda item: (item["code"], item["detail"]))),
        review_only=review_only,
        distribution_channel=distribution_channel,
        build_attestation=build_attestation,
        effective_from=effective_from,
        effective_to=effective_to,
        declared_status=status,
        development_override=effective_development,
        override_path_hash=override_path_hash,
        config_files=tuple(config_files),
    )


def manifest_content_digest(document: Mapping[str, Any]) -> str:
    """计算排除content_digest自身的规范manifest摘要。"""

    projection = {key: value for key, value in document.items() if key != "content_digest"}
    encoded = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    """计算文件SHA-256；文本资源规范化CRLF，避免跨平台规则包漂移。"""

    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        if path.suffix.lower() in _TEXT_HASH_SUFFIXES:
            for line in stream:
                digest.update(line.replace(b"\r\n", b"\n"))
        else:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _official_rule_eligible(
    raw_rule: Mapping[str, Any],
    source_entries: Mapping[str, Mapping[str, Any]],
    issues: list[dict[str, str]],
) -> bool:
    """执行official规则的来源、质量、日期和modality准入。"""

    rule = normalize_rule_admission(raw_rule)
    rule_id = str(rule.get("id", ""))
    anchor = str(rule.get("source_anchor", ""))
    source = source_entries.get(anchor)
    source_verified = bool(
        source
        and source.get("verified") is True
        and _SHA256_RE.fullmatch(str(source.get("content_hash", "")))
    )
    quality = str(rule.get("data_quality", DataQuality.CLEAN.value))
    modality = str(rule.get("norm_modality", ""))
    dates_valid = _rule_dates_valid(rule, rule_id, issues)
    modality_valid = modality in _ALLOWED_MODALITIES
    if not modality_valid:
        _issue(issues, "INVALID_RULE_MODALITY", rule_id)
    return bool(anchor and source_verified and quality != DataQuality.CANDIDATE_ONLY.value and dates_valid and modality_valid)


def _rule_dates_valid(rule: Mapping[str, Any], rule_id: str, issues: list[dict[str, str]]) -> bool:
    """验证规则可选生效/失效日期，不补造缺失日期。"""

    valid = True
    for field in ("valid_from", "valid_to"):
        value = rule.get(field)
        if not value:
            continue
        try:
            date.fromisoformat(str(value))
        except ValueError:
            _issue(issues, "INVALID_RULE_DATE", f"{rule_id}:{field}")
            valid = False
    return valid


def _validate_rule_relations(
    rules: Iterable[Mapping[str, Any]],
    issues: list[dict[str, str]],
) -> dict[str, bool]:
    """验证official exception与priority引用，防止悬空覆盖关系进入索引。"""

    material = tuple(rules)
    rule_ids = {str(rule.get("id", "")) for rule in material}
    claim_ids = {str(rule.get("head_claim", "")) for rule in material}
    validity: dict[str, bool] = {}
    for rule in material:
        rule_id = str(rule.get("id", ""))
        valid = True
        exceptions = rule.get("exception_chain", [])
        priorities = rule.get("priority_over", [])
        if not isinstance(exceptions, list) or not isinstance(priorities, list):
            _issue(issues, "INVALID_RULE_RELATION", rule_id)
            validity[rule_id] = False
            continue
        for target in exceptions:
            if str(target) not in rule_ids:
                _issue(issues, "UNKNOWN_EXCEPTION_TARGET", f"{rule_id}:{target}")
                valid = False
        for target in priorities:
            if str(target) not in rule_ids | claim_ids:
                _issue(issues, "UNKNOWN_PRIORITY_TARGET", f"{rule_id}:{target}")
                valid = False
        validity[rule_id] = valid
    return validity


def _file_entries(value: Any, label: str, issues: list[dict[str, str]]) -> tuple[dict[str, str], ...]:
    """严格解析manifest文件项。"""

    if not isinstance(value, list):
        _issue(issues, "INVALID_FILE_LIST", label)
        return ()
    entries: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
            _issue(issues, "INVALID_FILE_ENTRY", label)
            continue
        entries.append({"path": str(item["path"]), "sha256": str(item["sha256"])})
    return tuple(entries)


def _validated_resource_path(
    config_root: Path,
    entry: Mapping[str, str],
    issues: list[dict[str, str]],
) -> Path | None:
    """拒绝绝对路径和越出configs根的manifest引用。"""

    relative = Path(entry["path"])
    if relative.is_absolute() or ".." in relative.parts:
        _issue(issues, "UNSAFE_RESOURCE_PATH", entry["path"])
        return None
    path = (config_root / relative).resolve()
    if config_root not in path.parents:
        _issue(issues, "UNSAFE_RESOURCE_PATH", entry["path"])
        return None
    if not path.is_file():
        _issue(issues, "RESOURCE_NOT_FOUND", entry["path"])
        return None
    return path


def _verify_file_hash(path: Path, entry: Mapping[str, str], issues: list[dict[str, str]]) -> None:
    """精确比较manifest文件hash。"""

    if not _SHA256_RE.fullmatch(entry["sha256"]):
        _issue(issues, "INVALID_FILE_HASH", entry["path"])
    elif sha256_file(path) != entry["sha256"]:
        _issue(issues, "FILE_HASH_MISMATCH", entry["path"])


def _validate_date(value: Any, field: str, issues: list[dict[str, str]], *, allow_empty: bool) -> None:
    """验证manifest ISO日期。"""

    if allow_empty and value in (None, ""):
        return
    try:
        date.fromisoformat(str(value))
    except ValueError:
        _issue(issues, "INVALID_MANIFEST_DATE", field)


def _validate_effective_range(document: Mapping[str, Any], issues: list[dict[str, str]]) -> None:
    """拒绝结束日期早于开始日期。"""

    start = document.get("effective_from")
    end = document.get("effective_to")
    if not start or not end:
        return
    try:
        if date.fromisoformat(str(end)) < date.fromisoformat(str(start)):
            _issue(issues, "INVALID_EFFECTIVE_RANGE", "effective_to precedes effective_from")
    except ValueError:
        return


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """读取UTF-8 YAML并要求顶层对象。"""

    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RulePackError("MANIFEST_READ_ERROR", type(exc).__name__) from exc
    if not isinstance(value, Mapping):
        raise RulePackError("INVALID_YAML_DOCUMENT", Path(path).name)
    return dict(value)


def _issue(issues: list[dict[str, str]], code: str, detail: str) -> None:
    """追加不含机器路径和异常repr的确定性问题。"""

    issues.append({"code": code, "detail": str(detail)})
