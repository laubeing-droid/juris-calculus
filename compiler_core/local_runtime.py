"""Local keyless composition root: rule directories, local records, one client.

This module assembles the existing V4 formal spine for direct local use
without service keys, trust bundles, signed packs, or activation material.
Every admission that used to require an Ed25519 endorsement is admitted
through an explicit :class:`compiler_core.contracts.LocalRecordV4` instead:
a content-bound, keyless record that claims exactly what the local runtime
did — and never claims an external signer. Structure checks, semantic
gates, the sole ``ApplicationV4`` evaluation, the independent checker, the
incremental semantics, and the audit bundle are the existing production
machinery, unchanged.

Honesty boundary (SPLIT-LOCAL-3):

* ``LocalRecordV4`` says "recorded locally", not "approved externally";
* results carry ``execution_mode="local"`` and ``signature_status="not_used"``;
* no key material is ever generated, loaded, or implied.
"""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from compiler_core.application import (
    ApplicationV4,
    PROFILE_MAPPING_VERSION_V5,
    _v5_scenario_ref,
)
from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.audit_bundle import AuditTrustMaterialV4, AuditBundleStoreV4
from compiler_core.backend_router import BackendRouterV4, backend_profile_digest_v4
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.certificates import CertificateIssuerV4
from compiler_core.contracts import (
    DEFAULT_RESOURCE_LIMITS_V4,
    HARD_MAX_RESOURCE_LIMITS_V4,
    LOCAL_RECORD_ALGORITHM_V4,
    BusinessTaskV1,
    CanonicalLocatorV4,
    CanonicalTimeV4,
    CaseArtifactV4,
    CaseInputBundleV4,
    CaseRequestV4,
    ContentRefV4,
    ContractV4Error,
    DefeatPolicyV5,
    LocalRecordV4,
    RequestedOutputV4,
    ResourceLimitsV4,
    RunIdentityV4,
    SourceBundleV4,
    SourceSnapshotV4,
    TrustPolicyV4,
)
from compiler_core.fact_admission import (
    CASE_EVIDENCE_SCOPE,
    CASE_REQUEST_BINDING_KIND,
    CASE_REQUEST_KIND,
    CASE_REQUEST_SCOPE,
    EVIDENCE_CUSTODY_KIND,
    EVIDENCE_DOCUMENT_KIND,
    EVIDENCE_ITEM_KIND,
    EVIDENCE_MANIFEST_KIND,
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
    fact_attestation_evidence_refs,
)
from compiler_core.independent_checker import IndependentCheckerV4
from compiler_core.legal_ir import LegalIRCompilerV4
from compiler_core.production_runtime import _algorithm_profile_digest
from compiler_core.rule_packs import (
    BUILD_ATTESTATION_KIND,
    BUILD_ATTESTATION_SCOPE,
    ENGINEERING_APPROVAL_KIND,
    ENGINEERING_APPROVAL_SCOPE,
    JSON_MEDIA_TYPE,
    LEGAL_APPROVAL_KIND,
    PACK_BUILD_SUBJECT_KIND,
    PACK_CONFIG_KIND,
    PACK_COVERAGE_RECEIPT_KIND,
    PACK_MANIFEST_KIND,
    PACK_SIGNATURE_KIND,
    PACK_VERIFICATION_RECEIPT_KIND,
    RULE_ATTACK_KIND,
    RULE_AUTHORITY_KIND,
    RULE_CONCLUSION_KIND,
    RULE_DEFINED_TERM_KIND,
    RULE_EXCEPTION_KIND,
    RULE_INTERPRETATION_KIND,
    RULE_KIND,
    RULE_PERMISSION_KIND,
    RULE_PREMISE_KIND,
    RULE_PRIORITY_KIND,
    RULE_PROMOTION_RECEIPT_KIND,
    RULE_PROMOTION_SUBJECT_KIND,
    RULE_TEMPORAL_KIND,
    RULE_VARIABLE_KIND,
    RULE_PACK_SCOPE,
    RULE_COMPONENT_SCOPE,
    RulePackVerifierV4,
    RulePromotionReceiptV4,
    RuleV4,
    PackManifestV4,
    VerifiedRulePackV4,
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
from compiler_core.storage import V4TransactionStore
from compiler_core.trust import LocalRecordTrustV4
from compiler_core.version import __version__


LOCAL_POLICY_ID = "jc-local-record-policy/1.0"
LOCAL_PACK_SCHEMA = "jc/local-pack/1.0"
LOCAL_PACK_DESCRIPTOR = "jc-local-pack.json"
LOCAL_TRUST_VALID_FROM = CanonicalTimeV4("2026-01-01T00:00:00Z")
LOCAL_TRUST_VALID_TO = CanonicalTimeV4("2036-01-01T00:00:00Z")

# One distinct local issuer per trust role. Separation of duties is
# preserved because each role's records name a different issuer; no issuer
# corresponds to any external party — they name what this runtime did.
LOCAL_ISSUER_ROLES: dict[str, str] = {
    "source_attestor": "local-source-loader",
    "legal_reviewer": "local-legal-record",
    "engineering_reviewer": "local-engineering-record",
    "pack_releaser": "local-pack-assembler",
    "service_signer": "local-run-service",
    "build_attestor": "local-build-recorder",
}

_SOURCE_TIERS = ("official_first_party", "official_mirror", "third_party_verified")
_RULE_MODALITIES = ("OBLIGATION", "PERMISSION", "CONSTITUTIVE")


class LocalRuntimeError(RuntimeError):
    """Stable local-runtime error; code maps to the public error surface."""


def _now_utc() -> CanonicalTimeV4:
    return CanonicalTimeV4(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def _local_ref(kind: str, label: str) -> ContentRefV4:
    return ContentRefV4(kind, digest_value({"jc-local/1": label}))


def local_trust_policy() -> TrustPolicyV4:
    """The fixed local-record policy: content-stable across processes."""

    body = {
        "policy_id": LOCAL_POLICY_ID,
        "allowed_algorithms": [LOCAL_RECORD_ALGORITHM_V4],
        "trusted_key_ids": [],
        "revoked_key_ids": [],
        "allowed_issuers": sorted(LOCAL_ISSUER_ROLES.values()),
        "allowed_roles": ["source_attestor", "legal_reviewer", "engineering_reviewer",
                          "pack_releaser", "service_signer", "build_attestor"],
        "allowed_scopes": ["source-authenticity", "legal-approval", "engineering-approval",
                           "pack-release", "service-certificate", "build-attestation"],
        "allowed_artifact_kinds": ["source-snapshot", "legal-approval", "engineering-approval",
                                   "rule-pack", "service-certificate", "build-attestation"],
        "valid_from": LOCAL_TRUST_VALID_FROM.to_dict(),
        "valid_to": LOCAL_TRUST_VALID_TO.to_dict(),
        "authorization_policy_ref": _local_ref(
            "trust-authorization-policy", "local-authorization").to_dict(),
        "revocation_policy_ref": _local_ref(
            "trust-revocation-policy", "local-revocation").to_dict(),
        "replay_policy_ref": _local_ref("trust-replay-policy", "local-replay").to_dict(),
        "separation_of_duties_ref": _local_ref(
            "trust-separation-policy", "local-separation").to_dict(),
    }
    return TrustPolicyV4.from_dict({
        **body, "policy_digest": str(digest_value(body)),
    })


def local_trust() -> LocalRecordTrustV4:
    return LocalRecordTrustV4(policy=local_trust_policy())


@dataclass(frozen=True, slots=True)
class LocalBuildIdentityV4:
    """Content-derived identity of the installed local engine."""

    engine_api: str
    engine_source_commit: str
    engine_source_tree: str
    compiler_build_digest: DigestV4
    source_tree_digest: DigestV4
    schema_digest: DigestV4
    tool_spec_digest: DigestV4
    wheel_digest: DigestV4
    package_digest: DigestV4
    lock_digest: DigestV4


_PINNED_BUILD_MODULES = (
    "application.py", "argumentation.py", "artifact_store.py", "audit_bundle.py",
    "backend_router.py", "canonical_serialization.py", "certificates.py",
    "contracts.py", "domain_composition.py", "fact_admission.py", "incremental.py",
    "independent_checker.py", "legal_ir.py", "procedure.py", "query_semantics.py",
    "rule_packs.py", "source_service.py", "storage.py", "trust.py", "version.py",
)


def local_build_identity() -> LocalBuildIdentityV4:
    """Digest the installed formal modules into stable run-identity pins.

    The pins are content-addressed, so they are identical for every process
    of one installed distribution and old state roots stay readable.
    """

    from compiler_core import mcp as mcp_module

    root = Path(__file__).resolve().parent
    module_digests: dict[str, str] = {}
    for name in _PINNED_BUILD_MODULES:
        module_digests[name] = str(DigestV4.from_bytes((root / name).read_bytes()))
    source_tree = digest_value(module_digests)
    schema_digest = DigestV4.from_bytes(mcp_module.schema_bytes())
    return LocalBuildIdentityV4(
        engine_api=__version__,
        engine_source_commit=source_tree.hex,
        engine_source_tree=source_tree.hex,
        compiler_build_digest=digest_value({
            "engine_api": __version__, "source_tree": str(source_tree),
        }),
        source_tree_digest=source_tree,
        schema_digest=schema_digest,
        tool_spec_digest=mcp_module.tool_spec_digest(),
        wheel_digest=digest_value({"local-wheel": __version__}),
        package_digest=digest_value({"local-package": __version__}),
        lock_digest=digest_value({"local-lock": sorted(module_digests)}),
    )


class LocalRecordIssuerV4:
    """Issues the run's internal local records (receipts, proofs, handles)."""

    def __init__(self, policy: TrustPolicyV4) -> None:
        self._policy = policy

    def record(
        self,
        *,
        role: str,
        scope: str,
        kind: str,
        subject_digest: DigestV4,
        payload_digest: DigestV4,
        evidence_refs: tuple[ContentRefV4, ...],
        run_identity_ref: ContentRefV4 | None,
        now: CanonicalTimeV4,
        nonce: str | None = None,
    ) -> LocalRecordV4:
        issuer = LOCAL_ISSUER_ROLES.get(role)
        if issuer is None:
            raise LocalRuntimeError(f"unsupported local record role: {role!r}")
        return LocalRecordV4.from_dict({
            "algorithm": LOCAL_RECORD_ALGORITHM_V4,
            "issuer": issuer,
            "role": role,
            "scope": scope,
            "kind": kind,
            "schema_version": "jc/5.0",
            "subject_digest": str(subject_digest),
            "run_identity_ref": None if run_identity_ref is None else run_identity_ref.to_dict(),
            "status": "LOCAL-RECORDED",
            "issued_at": now.to_dict(),
            "expires_at": self._policy.valid_to.to_dict(),
            "nonce": nonce or f"local-{subject_digest.hex}-{payload_digest.hex}",
            "evidence_refs": [item.to_dict() for item in evidence_refs],
            "payload_digest": str(payload_digest),
            "policy_digest": str(self._policy.policy_digest),
            "revocation_ref": self._policy.revocation_policy_ref.to_dict(),
        })

    def __call__(
        self,
        subject_digest: DigestV4,
        payload_digest: DigestV4,
        evidence_refs: tuple[ContentRefV4, ...],
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> LocalRecordV4:
        return self.record(
            role="service_signer",
            scope="service-certificate",
            kind="service-certificate",
            subject_digest=subject_digest,
            payload_digest=payload_digest,
            evidence_refs=evidence_refs,
            run_identity_ref=run_identity_ref,
            now=now,
        )


def _read_authoring_document(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise LocalRuntimeError(f"cannot read local rule document: {path.name}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalRuntimeError(
            f"local rule document is not strict UTF-8 JSON: {path.name}"
        ) from exc
    if not isinstance(value, dict):
        raise LocalRuntimeError(f"local rule document must be a JSON object: {path.name}")
    return value


def _require_fields(document: dict[str, Any], required: tuple[str, ...], label: str) -> None:
    missing = [name for name in required if document.get(name) is None]
    if missing:
        raise LocalRuntimeError(f"{label} is missing field {missing[0]!r}")


def _time(document: dict[str, Any], field: str, label: str) -> CanonicalTimeV4:
    value = document.get(field)
    if value is None:
        raise LocalRuntimeError(f"{label} is missing field {field!r}")
    try:
        return CanonicalTimeV4.parse(value)
    except ContractV4Error as exc:
        raise LocalRuntimeError(f"{label}.{field} is not a canonical time") from exc


def _locator(document: dict[str, Any], label: str) -> CanonicalLocatorV4:
    raw = document.get("locator")
    if not isinstance(raw, dict):
        raise LocalRuntimeError(f"{label}.locator must be an object")
    try:
        return CanonicalLocatorV4(
            raw.get("kind", "uri"), raw.get("value", ""),
            raw.get("page"), raw.get("span_start"), raw.get("span_end"),
        )
    except ContractV4Error as exc:
        raise LocalRuntimeError(f"{label}.locator is invalid") from exc


class LocalRuleSourceLoaderV4:
    """Load authoring documents from local directories into canonical artifacts.

    Every accepted document becomes exactly the canonical V4 artifact it
    declares; nothing is rewritten into an approximate rule. Structural
    checks (parse, source anchor, complete components, identity, effective
    time) are re-derived by ``RulePackVerifierV4.verify`` afterwards. The
    number of rules is bounded only by the pack resource limits — there is
    no fixed six-rule profile.
    """

    def __init__(
        self,
        resolver: ArtifactResolverV4,
        policy: TrustPolicyV4,
        *,
        now: CanonicalTimeV4,
    ) -> None:
        self._resolver = resolver
        self._policy = policy
        self._now = now
        self._serial = 0

    def _store(
        self,
        reference: ContentRefV4,
        content: bytes,
        *,
        kind: str,
        scope: str,
        media_type: str = JSON_MEDIA_TYPE,
    ) -> ContentRefV4:
        self._serial += 1
        return self._resolver.register_bytes(
            artifact_id=f"local-{self._serial:05d}",
            content_ref=reference,
            artifact_kind=kind,
            media_type=media_type,
            scope=scope,
            content=content,
        )

    def _store_json(
        self,
        kind: str,
        payload: dict[str, object],
        *,
        scope: str,
    ) -> ContentRefV4:
        raw = canonical_bytes(payload)
        return self._store(
            ContentRefV4(kind, DigestV4.from_bytes(raw)), raw, kind=kind, scope=scope,
        )

    def _record(
        self,
        *,
        role: str,
        scope: str,
        kind: str,
        subject_digest: DigestV4,
        payload_digest: DigestV4,
        evidence_refs: tuple[ContentRefV4, ...],
    ) -> LocalRecordV4:
        issuer = LocalRecordIssuerV4(self._policy)
        return issuer.record(
            role=role, scope=scope, kind=kind,
            subject_digest=subject_digest, payload_digest=payload_digest,
            evidence_refs=evidence_refs, run_identity_ref=None, now=self._now,
        )

    def _load_source(self, document: dict[str, Any], label: str) -> SourceSnapshotV4:
        _require_fields(document, (
            "source_id", "jurisdiction", "authority_tier", "issuer", "title",
            "publication_time", "effective_from", "retrieved_at", "content",
        ), label)
        tier = document["authority_tier"]
        if tier not in _SOURCE_TIERS:
            raise LocalRuntimeError(
                f"{label}.authority_tier must be one of {_SOURCE_TIERS}; "
                "a local source must declare an honest authority tier"
            )
        locator = _locator(document, label)
        raw = str(document["content"]).encode("utf-8")
        normalized = normalize_source_bytes(raw)
        raw_ref = ContentRefV4(SOURCE_RAW_KIND, DigestV4.from_bytes(raw))
        normalized_ref = ContentRefV4(SOURCE_NORMALIZED_KIND, DigestV4.from_bytes(normalized))
        self._store(raw_ref, raw, kind=SOURCE_RAW_KIND, scope="source-content",
                    media_type="text/plain")
        self._store(normalized_ref, normalized, kind=SOURCE_NORMALIZED_KIND,
                    scope="source-content", media_type="text/plain")
        sections = document.get("structure_sections")
        if not isinstance(sections, list) or not sections or any(
            not isinstance(item, str) or not item for item in sections
        ):
            raise LocalRuntimeError(
                f"{label}.structure_sections must be a non-empty string array"
            )
        structure_ref = self._store_json(
            SOURCE_STRUCTURE_MAP_KIND,
            {"schema_version": "jc/source-structure/1.0", "sections": list(sections)},
            scope="source-provenance",
        )
        provenance_ref = self._store_json(
            SOURCE_PROVENANCE_KIND,
            {
                "schema_version": "jc/source-provenance/1.0",
                "method": str(document.get("provenance_method", "local-import")),
            },
            scope="source-provenance",
        )
        snapshot = SourceSnapshotV4(
            source_id=str(document["source_id"]),
            jurisdiction=str(document["jurisdiction"]),
            authority_tier=str(tier),
            issuer=str(document["issuer"]),
            title=str(document["title"]),
            publication_time=_time(document, "publication_time", label),
            effective_from=_time(document, "effective_from", label),
            effective_to=(
                None if document.get("effective_to") is None
                else _time(document, "effective_to", label)
            ),
            retrieved_at=_time(document, "retrieved_at", label),
            canonical_locator=locator,
            raw_digest=raw_ref.digest,
            normalization_profile=SOURCE_NORMALIZATION_PROFILE,
            normalized_digest=normalized_ref.digest,
            structure_map_ref=structure_ref,
            authenticity_receipt_ref=_local_ref(
                SOURCE_AUTHENTICITY_RECEIPT_KIND, f"{label}-pending"
            ),
            provenance_refs=(provenance_ref,),
            acquisition_method=str(document.get("acquisition_method", "local-file")),
            license_status=str(document.get("license_status", "local-import")),
            distribution_status=str(document.get("distribution_status", "local-import")),
        )
        evidence = (raw_ref, normalized_ref, structure_ref, provenance_ref)
        record = self._record(
            role="source_attestor",
            scope="source-authenticity",
            kind=SOURCE_SNAPSHOT_KIND,
            subject_digest=snapshot.raw_digest,
            payload_digest=source_authenticity_payload_digest(snapshot),
            evidence_refs=evidence,
        )
        record_ref = ContentRefV4(
            SOURCE_AUTHENTICITY_RECEIPT_KIND,
            DigestV4.from_bytes(record.canonical_bytes()),
        )
        self._store(record_ref, record.canonical_bytes(),
                    kind=SOURCE_AUTHENTICITY_RECEIPT_KIND, scope="source-authenticity")
        from dataclasses import replace

        snapshot = replace(snapshot, authenticity_receipt_ref=record_ref)
        snapshot_ref = source_snapshot_ref(snapshot)
        self._store(snapshot_ref, snapshot.canonical_bytes(),
                    kind=SOURCE_SNAPSHOT_KIND, scope="source-authenticity")
        return snapshot

    def _component(self, kind: str, rule_id: str, values: dict[str, object]) -> ContentRefV4:
        return self._store_json(
            kind,
            {"schema_version": f"jc/{kind}/1.0", "rule_id": rule_id, **values},
            scope=RULE_COMPONENT_SCOPE,
        )

    def _load_rule(
        self,
        document: dict[str, Any],
        sources: dict[str, tuple[ContentRefV4, SourceSnapshotV4]],
        label: str,
    ) -> tuple[ContentRefV4, ContentRefV4]:
        _require_fields(document, (
            "rule_id", "jurisdiction", "governing_law", "source_id", "modality",
            "premises", "conclusion", "effective_from",
        ), label)
        rule_id = str(document["rule_id"])
        source_entry = sources.get(str(document["source_id"]))
        if source_entry is None:
            raise LocalRuntimeError(
                f"{label}.source_id does not name a source of this pack"
            )
        source_ref, source = source_entry
        modality = str(document["modality"])
        if modality not in _RULE_MODALITIES:
            raise LocalRuntimeError(f"{label}.modality must be one of {_RULE_MODALITIES}")

        authority_ref = self._component(
            RULE_AUTHORITY_KIND, rule_id,
            {"tier": str(document.get("authority_tier", "local-import"))},
        )
        variable_ref = self._component(
            RULE_VARIABLE_KIND, rule_id,
            {"name": str(document.get("variable", "claim"))},
        )
        premises = document["premises"]
        if not isinstance(premises, list):
            raise LocalRuntimeError(f"{label}.premises must be an array")
        premise_refs = []
        for premise in premises:
            if not isinstance(premise, dict) or not premise.get("fact_key"):
                raise LocalRuntimeError(f"{label}.premises entries need a fact_key")
            premise_refs.append(self._component(RULE_PREMISE_KIND, rule_id, {
                "fact_key": str(premise["fact_key"]),
                "required": bool(premise.get("required", True)),
            }))
        conclusion = document["conclusion"]
        if not isinstance(conclusion, dict):
            raise LocalRuntimeError(f"{label}.conclusion must be an object")
        if conclusion.get("fact_key"):
            conclusion_ref = self._component(
                RULE_CONCLUSION_KIND, rule_id, {"fact_key": str(conclusion["fact_key"])},
            )
        elif conclusion.get("value") is not None:
            conclusion_ref = self._component(
                RULE_CONCLUSION_KIND, rule_id, {"value": conclusion["value"]},
            )
        else:
            raise LocalRuntimeError(f"{label}.conclusion needs either fact_key or value")
        interpretation = document.get("interpretation")
        interpretation_choice = (
            str(interpretation.get("choice", "literal"))
            if isinstance(interpretation, dict) else "literal"
        )
        interpretation_ref = self._component(
            RULE_INTERPRETATION_KIND, rule_id, {"choice": interpretation_choice},
        )
        terms = document.get("defined_terms")
        if terms is not None and not isinstance(terms, list):
            raise LocalRuntimeError(f"{label}.defined_terms must be an array")
        term_refs = []
        for term in (terms or []):
            if not isinstance(term, dict) or not term.get("term"):
                raise LocalRuntimeError(f"{label}.defined_terms entries need a term")
            term_refs.append(self._component(
                RULE_DEFINED_TERM_KIND, rule_id, {"term": str(term["term"])},
            ))
        exceptions = document.get("exceptions") or []
        exception_refs = []
        for item in exceptions:
            if not isinstance(item, dict) or not item.get("target") or not item.get("condition_fact_key"):
                raise LocalRuntimeError(
                    f"{label}.exceptions entries need target and condition_fact_key")
            exception_refs.append(self._component(RULE_EXCEPTION_KIND, rule_id, {
                "attacker": rule_id,
                "target": str(item["target"]),
                "attack_type": str(item.get("attack_type", "exception")),
                "target_aspect": str(item.get("target_aspect", "applicability")),
                "condition_fact_key": str(item["condition_fact_key"]),
            }))
        attacks = document.get("attacks") or []
        attack_refs = []
        for item in attacks:
            if not isinstance(item, dict) or not item.get("target"):
                raise LocalRuntimeError(f"{label}.attacks entries need a target")
            attack_refs.append(self._component(RULE_ATTACK_KIND, rule_id, {
                "attacker": rule_id,
                "target": str(item["target"]),
                "attack_type": str(item.get("attack_type", "rebut")),
                "target_aspect": str(item.get("target_aspect", "conclusion")),
                "condition_fact_key": (
                    str(item["condition_fact_key"]) if item.get("condition_fact_key") else None
                ),
            }))
        priorities = document.get("priorities") or []
        priority_refs = []
        for item in priorities:
            if not isinstance(item, dict) or not item.get("target") or not item.get("condition"):
                raise LocalRuntimeError(
                    f"{label}.priorities entries need target and condition")
            priority_refs.append(self._component(RULE_PRIORITY_KIND, rule_id, {
                "source": rule_id,
                "target": str(item["target"]),
                "condition": str(item["condition"]),
            }))
        temporal = document.get("temporal") or []
        temporal_refs = []
        for item in temporal:
            if not isinstance(item, dict) or not item.get("start") or not item.get("end"):
                raise LocalRuntimeError(f"{label}.temporal entries need start and end")
            temporal_refs.append(self._component(RULE_TEMPORAL_KIND, rule_id, {
                "start": item["start"],
                "end": item["end"],
                "target_rule_id": str(item.get("target_rule_id", rule_id)),
            }))
        permission_ref = None
        if document.get("permission") is not None:
            permission = document["permission"]
            if not isinstance(permission, dict) or not permission.get("permits"):
                raise LocalRuntimeError(f"{label}.permission needs permits")
            permission_ref = self._component(RULE_PERMISSION_KIND, rule_id, {
                "permission_id": str(permission.get(
                    "permission_id", f"{rule_id}.permission")),
                "permits": str(permission["permits"]),
                "relation_to": str(permission["relation_to"]),
                "relation_kind": str(permission.get("relation_kind", "exception")),
            })

        base: dict[str, object] = {
            "rule_id": rule_id,
            "jurisdiction": str(document["jurisdiction"]),
            "governing_law": str(document["governing_law"]),
            "authority_ref": authority_ref.to_dict(),
            "variable_declaration_refs": [variable_ref.to_dict()],
            "premise_refs": [item.to_dict() for item in premise_refs],
            "conclusion_ref": conclusion_ref.to_dict(),
            "modality": modality,
            "permission_ref": None if permission_ref is None else permission_ref.to_dict(),
            "exception_refs": [item.to_dict() for item in exception_refs],
            "priority_refs": [item.to_dict() for item in priority_refs],
            "attack_refs": [item.to_dict() for item in attack_refs],
            "temporal_constraint_refs": [item.to_dict() for item in temporal_refs],
            "numeric_constraint_refs": [],
            "source_snapshot_ref": source_ref.to_dict(),
            "source_locator": source.canonical_locator.to_dict(),
            "source_structure_ref": source.structure_map_ref.to_dict(),
            "interpretation_choice_refs": [interpretation_ref.to_dict()],
            "defined_term_refs": [item.to_dict() for item in term_refs],
            "promotion_receipt_refs": [],
            "effective_from": _time(document, "effective_from", label).to_dict(),
            "effective_to": (
                None if document.get("effective_to") is None
                else _time(document, "effective_to", label).to_dict()
            ),
        }
        draft = RuleV4.from_dict({**base, "rule_digest": str(digest_value(base))})
        subject_body = rule_promotion_subject_body(draft)
        subject_ref = rule_promotion_subject_ref(draft)
        self._store(subject_ref, canonical_bytes(subject_body),
                    kind=RULE_PROMOTION_SUBJECT_KIND, scope=RULE_PACK_SCOPE)
        replay_ref = self._policy.replay_policy_ref
        legal = self._record(
            role="legal_reviewer",
            scope=LEGAL_APPROVAL_SCOPE,
            kind=LEGAL_APPROVAL_KIND,
            subject_digest=subject_ref.digest,
            payload_digest=subject_ref.digest,
            evidence_refs=rule_review_evidence_refs(draft, subject_ref, replay_ref, "legal"),
        )
        legal_ref = ContentRefV4(LEGAL_APPROVAL_KIND, DigestV4.from_bytes(legal.canonical_bytes()))
        self._store(legal_ref, legal.canonical_bytes(), kind=LEGAL_APPROVAL_KIND,
                    scope=LEGAL_APPROVAL_SCOPE)
        engineering = self._record(
            role="engineering_reviewer",
            scope="engineering-approval",
            kind="engineering-approval",
            subject_digest=subject_ref.digest,
            payload_digest=subject_ref.digest,
            evidence_refs=rule_review_evidence_refs(
                draft, subject_ref, replay_ref, "engineering"),
        )
        engineering_ref = ContentRefV4(
            ENGINEERING_APPROVAL_KIND, DigestV4.from_bytes(engineering.canonical_bytes()),
        )
        self._store(engineering_ref, engineering.canonical_bytes(),
                    kind=ENGINEERING_APPROVAL_KIND, scope="engineering-approval")
        receipt_body = {
            "receipt_id": f"local-promotion-{rule_id}",
            "rule_subject_digest": str(subject_ref.digest),
            "legal_review_ref": legal_ref.to_dict(),
            "engineering_review_ref": engineering_ref.to_dict(),
            "status": "APPROVED",
            "issued_at": self._now.to_dict(),
        }
        service = self._record(
            role="service_signer",
            scope="service-certificate",
            kind="service-certificate",
            subject_digest=subject_ref.digest,
            payload_digest=digest_value(receipt_body),
            evidence_refs=promotion_receipt_evidence_refs(
                subject_ref, legal_ref, engineering_ref, replay_ref,
            ),
        )
        receipt = RulePromotionReceiptV4.from_dict({
            **receipt_body, "signature": service.to_dict(),
        })
        promotion_ref = ContentRefV4(
            RULE_PROMOTION_RECEIPT_KIND, DigestV4.from_bytes(receipt.canonical_bytes()),
        )
        self._store(promotion_ref, receipt.canonical_bytes(),
                    kind=RULE_PROMOTION_RECEIPT_KIND, scope=RULE_PACK_SCOPE)
        final_body = {**base, "promotion_receipt_refs": [promotion_ref.to_dict()]}
        rule = RuleV4.from_dict({
            **final_body, "rule_digest": str(digest_value(final_body)),
        })
        rule_ref = ContentRefV4(RULE_KIND, rule.rule_digest)
        self._store(rule_ref, canonical_bytes(rule.digest_body()), kind=RULE_KIND,
                    scope=RULE_PACK_SCOPE)
        return rule_ref, promotion_ref


@dataclass(frozen=True, slots=True)
class LoadedLocalPackV4:
    """One assembled local pack plus the refs case bundles must cite.

    ``pack_ref`` still needs ``RulePackVerifierV4.verify`` (the factory does
    it eagerly) before the pack is usable by the formal spine.
    """

    pack_ref: ContentRefV4
    sources: tuple[tuple[ContentRefV4, SourceSnapshotV4], ...]
    rule_claims: tuple[dict[str, str], ...]


def _authoring_documents(rule_root: Path) -> list[tuple[str, dict[str, Any]]]:
    """Collect (label, document) rows from one rule root."""

    if rule_root.is_file():
        documents = [(rule_root.name, _read_authoring_document(rule_root))]
    elif rule_root.is_dir():
        descriptor = rule_root / LOCAL_PACK_DESCRIPTOR
        if not descriptor.is_file():
            raise LocalRuntimeError(
                f"rule root {rule_root.name!r} has no {LOCAL_PACK_DESCRIPTOR}"
            )
        documents = [(descriptor.name, _read_authoring_document(descriptor))]
    else:
        raise LocalRuntimeError(f"rule root does not exist: {rule_root.name!r}")
    return documents


def build_local_pack(
    resolver: ArtifactResolverV4,
    policy: TrustPolicyV4,
    rule_roots: tuple[Path, ...],
    *,
    identity: LocalBuildIdentityV4,
    now: CanonicalTimeV4,
) -> LoadedLocalPackV4:
    """Assemble one verified local pack from one or more rule roots.

    All roots are merged into a single pack so a case request can cite one
    ``rule_pack_ref``. ``pack_id`` is content-derived: the same rules always
    produce the same pack, whatever the directories are called.
    """

    if not rule_roots:
        raise LocalRuntimeError("create_local_client requires at least one rule root")
    loader = LocalRuleSourceLoaderV4(resolver, policy, now=now)
    sources: dict[str, tuple[ContentRefV4, SourceSnapshotV4]] = {}
    source_refs: list[ContentRefV4] = []
    source_rows: list[SourceSnapshotV4] = []
    rules: list[tuple[ContentRefV4, ContentRefV4]] = []
    content_digest_inputs: list[str] = []
    for root in rule_roots:
        for label, document in _authoring_documents(root):
            if document.get("schema_version") != LOCAL_PACK_SCHEMA:
                raise LocalRuntimeError(
                    f"{label}: schema_version must be {LOCAL_PACK_SCHEMA}"
                )
            content_digest_inputs.append(canonical_bytes(document).decode("utf-8"))
            for index, source_document in enumerate(document.get("sources") or []):
                if not isinstance(source_document, dict):
                    raise LocalRuntimeError(f"{label}.sources[{index}] must be an object")
                snapshot = loader._load_source(source_document, f"{label}.sources[{index}]")
                if snapshot.source_id in sources:
                    raise LocalRuntimeError(
                        f"{label}: duplicate source_id {snapshot.source_id!r}"
                    )
                snapshot_ref = source_snapshot_ref(snapshot)
                sources[snapshot.source_id] = (snapshot_ref, snapshot)
                source_refs.append(snapshot_ref)
                source_rows.append(snapshot)
            for index, rule_document in enumerate(document.get("rules") or []):
                if not isinstance(rule_document, dict):
                    raise LocalRuntimeError(f"{label}.rules[{index}] must be an object")
                rules.append(loader._load_rule(rule_document, sources, f"{label}.rules[{index}]"))
    if not rules:
        raise LocalRuntimeError(
            "local rule roots contain no rules; JC will not invent legal capability"
        )
    rule_refs = tuple(sorted((ref for ref, _ in rules), key=lambda item: (item.kind, str(item.digest))))
    promotion_refs = tuple(sorted(
        (ref for _, ref in rules), key=lambda item: (item.kind, str(item.digest)),
    ))

    pack_id = f"local-{digest_value(sorted(content_digest_inputs)).hex[:24]}"
    # One domain config per (jurisdiction, governing_law); together the
    # configs must partition the exact rule set.
    config_groups: dict[tuple[str, str], list[ContentRefV4]] = {}
    for rule_ref in rule_refs:
        raw = resolver.resolve_content(
            rule_ref,
            expected_artifact_kind=RULE_KIND,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope=RULE_PACK_SCOPE,
            max_bytes=resolver.max_artifact_bytes,
        )
        rule = RuleV4.from_dict({
            **parse_json_document(raw), "rule_digest": str(rule_ref.digest),
        })
        key = (rule.jurisdiction, rule.governing_law)
        config_groups.setdefault(key, []).append(rule_ref)
    config_refs = []
    for (jurisdiction, governing_law), refs in sorted(config_groups.items()):
        ordered = tuple(sorted(refs, key=lambda item: (item.kind, str(item.digest))))
        config_refs.append(loader._store_json(PACK_CONFIG_KIND, {
            "schema_version": "jc/domain-config/1.0",
            "domain_id": f"{jurisdiction}:{governing_law}",
            "namespace": f"{pack_id}:{jurisdiction}:{governing_law}",
            "jurisdiction": jurisdiction,
            "governing_law": governing_law,
            "rule_refs": [item.to_dict() for item in ordered],
        }, scope=RULE_PACK_SCOPE))
    config_refs_tuple = tuple(sorted(config_refs, key=lambda item: (item.kind, str(item.digest))))

    coverage_ref = loader._store_json(PACK_COVERAGE_RECEIPT_KIND, {
        "schema_version": "jc/pack-coverage-receipt/1.0",
        "status": "PASS",
        "rule_refs": [item.to_dict() for item in rule_refs],
    }, scope=RULE_PACK_SCOPE)
    verification_ref = loader._store_json(PACK_VERIFICATION_RECEIPT_KIND, {
        "schema_version": "jc/pack-verification-receipt/1.0",
        "status": "PASS",
        "rule_refs": [item.to_dict() for item in rule_refs],
    }, scope=RULE_PACK_SCOPE)
    ordered_sources = tuple(sorted(source_refs, key=lambda item: (item.kind, str(item.digest))))
    values: dict[str, object] = {
        "pack_id": pack_id,
        "pack_version": "1.0.0",
        "engine_api": identity.engine_api,
        "rule_refs": [item.to_dict() for item in rule_refs],
        "source_refs": [item.to_dict() for item in ordered_sources],
        "config_refs": [item.to_dict() for item in config_refs_tuple],
        "receipt_refs": [item.to_dict() for item in promotion_refs],
        "compiler_build_digest": str(identity.compiler_build_digest),
        "source_tree_digest": str(identity.source_tree_digest),
        "schema_digest": str(identity.schema_digest),
        "trust_policy_ref": ContentRefV4(
            TRUST_POLICY_KIND, policy.canonical_digest(),
        ).to_dict(),
        "coverage_receipt_refs": [coverage_ref.to_dict()],
        "verification_receipt_refs": [verification_ref.to_dict()],
    }
    provisional = PackManifestV4.from_dict({
        **values, "manifest_digest": str(digest_value(values)),
    })
    build_body = build_subject_body(provisional)
    build_ref = build_subject_ref(provisional)
    loader._store(build_ref, canonical_bytes(build_body),
                  kind=PACK_BUILD_SUBJECT_KIND, scope=RULE_PACK_SCOPE)
    build_record_issuer = LocalRecordIssuerV4(policy)
    build_record = build_record_issuer.record(
        role="build_attestor",
        scope="build-attestation",
        kind=BUILD_ATTESTATION_KIND,
        subject_digest=build_ref.digest,
        payload_digest=build_ref.digest,
        evidence_refs=build_attestation_evidence_refs(provisional, build_ref),
        run_identity_ref=None,
        now=now,
    )
    build_ref_final = ContentRefV4(
        BUILD_ATTESTATION_KIND, DigestV4.from_bytes(build_record.canonical_bytes()),
    )
    loader._store(build_ref_final, build_record.canonical_bytes(),
                  kind=BUILD_ATTESTATION_KIND, scope="build-attestation")
    receipt_refs = tuple(sorted(
        (*promotion_refs, build_ref_final),
        key=lambda item: (item.kind, str(item.digest)),
    ))
    final_values = {**values, "receipt_refs": [item.to_dict() for item in receipt_refs]}
    manifest = PackManifestV4.from_dict({
        **final_values, "manifest_digest": str(digest_value(final_values)),
    })
    manifest_ref = pack_manifest_ref(manifest)
    loader._store(manifest_ref, canonical_bytes(manifest.digest_body()),
                  kind=PACK_MANIFEST_KIND, scope=RULE_PACK_SCOPE)
    release_record = build_record_issuer.record(
        role="pack_releaser",
        scope="pack-release",
        kind="rule-pack",
        subject_digest=manifest_ref.digest,
        payload_digest=digest_value({"manifest_ref": manifest_ref.to_dict()}),
        evidence_refs=pack_release_evidence_refs(manifest_ref, manifest, build_ref),
        run_identity_ref=None,
        now=now,
    )
    pack_raw = canonical_bytes({
        "manifest_ref": manifest_ref.to_dict(),
        "signature": release_record.to_dict(),
    })
    pack_ref = ContentRefV4(PACK_SIGNATURE_KIND, DigestV4.from_bytes(pack_raw))
    loader._store(pack_ref, pack_raw, kind=PACK_SIGNATURE_KIND, scope=RULE_PACK_SCOPE)

    rule_claims: list[dict[str, str]] = []
    for rule in _verified_rules_of(resolver, rule_refs):
        rule_claims.append({
            "rule_id": rule.rule_id,
            "claim": str(rule.conclusion_ref.digest),
            "jurisdiction": rule.jurisdiction,
            "governing_law": rule.governing_law,
            "effective_from": rule.effective_from.to_dict(),
            "effective_to": (
                None if rule.effective_to is None else rule.effective_to.to_dict()
            ),
        })
    return LoadedLocalPackV4(
        pack_ref=pack_ref,
        sources=tuple((ref, snapshot) for ref, snapshot in
                      sorted(sources.values(), key=lambda row: row[0].digest.hex)),
        rule_claims=tuple(rule_claims),
    )


def _verified_rules_of(
    resolver: ArtifactResolverV4, rule_refs: tuple[ContentRefV4, ...],
) -> list[RuleV4]:
    rules: list[RuleV4] = []
    for rule_ref in rule_refs:
        raw = resolver.resolve_content(
            rule_ref,
            expected_artifact_kind=RULE_KIND,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope=RULE_PACK_SCOPE,
            max_bytes=resolver.max_artifact_bytes,
        )
        rules.append(RuleV4.from_dict({
            **parse_json_document(raw), "rule_digest": str(rule_ref.digest),
        }))
    return rules


@dataclass(frozen=True, slots=True)
class LocalFactInput:
    """One locally reviewed fact for a case bundle.

    ``dispute_state``/``assumption_state`` keep the existing fact-state
    semantics: ``USER_ASSUMED`` facts drive the hypothetical branch and are
    never reported as proven; ``UNKNOWN``/``DISPUTED`` facts stay review-only.
    No state field here can become a verified claim by itself.
    """

    fact_key: str
    value: bool = True
    evidence_text: str = ""
    locator_label: str = ""
    admission_basis: str = "documentary_evidence_human_reviewed"
    dispute_state: str = "UNDISPUTED"
    assumption_state: str = "NONE"

    def __post_init__(self) -> None:
        if not self.fact_key:
            raise LocalRuntimeError("LocalFactInput.fact_key must not be empty")
        if self.dispute_state not in ("UNDISPUTED", "UNKNOWN", "DISPUTED", "USER_ASSUMED"):
            raise LocalRuntimeError("LocalFactInput.dispute_state is unknown")
        if self.assumption_state not in ("NONE", "USER_ASSUMED"):
            raise LocalRuntimeError("LocalFactInput.assumption_state is unknown")
        if self.assumption_state == "USER_ASSUMED" and self.dispute_state not in (
            "UNDISPUTED", "USER_ASSUMED",
        ):
            raise LocalRuntimeError(
                "LocalFactInput assumption and dispute states disagree"
            )


@dataclass(frozen=True, slots=True)
class LocalQueryInput:
    """One requested legal issue bound to one Dung profile."""

    query_id: str
    claim: str
    profile: str

    def __post_init__(self) -> None:
        for name in ("query_id", "claim", "profile"):
            if not getattr(self, name):
                raise LocalRuntimeError(f"LocalQueryInput.{name} must not be empty")


class LocalCaseInputsBuilderV4:
    """Build complete, self-contained local case bundles (serialization help).

    The returned :class:`CaseInputBundleV4` carries every case artifact, so
    the Harness only handles JC public types. Source bundles are registered
    once per distinct source in the client resolver because they belong to
    the loaded pack, not to one case.
    """

    def __init__(
        self,
        resolver: ArtifactResolverV4,
        policy: TrustPolicyV4,
        pack: LoadedLocalPackV4,
        identity: LocalBuildIdentityV4,
    ) -> None:
        self._resolver = resolver
        self._policy = policy
        self._pack = pack
        self._identity = identity
        self._record_issuer = LocalRecordIssuerV4(policy)
        self._serial = 0

    def source_bundle_ref(self, source_id: str | None = None) -> ContentRefV4:
        rows = self._pack.sources
        if source_id is None:
            if len(rows) != 1:
                raise LocalRuntimeError(
                    "this pack has multiple sources; pass source_id explicitly"
                )
            snapshot_ref, snapshot = rows[0]
        else:
            found = [row for row in rows if row[1].source_id == source_id]
            if not found:
                raise LocalRuntimeError(f"unknown source_id {source_id!r}")
            snapshot_ref, snapshot = found[0]
        bundle_body = {
            "bundle_id": f"local-source-path-{snapshot.source_id}",
            "root_source_ref": snapshot_ref.to_dict(),
            "terminal_source_ref": snapshot_ref.to_dict(),
            "snapshots": [snapshot.to_dict()],
            "version_edges": [],
        }
        bundle = SourceBundleV4.from_dict({
            **bundle_body, "bundle_digest": str(digest_value(bundle_body)),
        })
        reference = ContentRefV4(
            SOURCE_BUNDLE_KIND, DigestV4.from_bytes(canonical_bytes(bundle.digest_body())),
        )
        try:
            self._resolver.resolve_content(
                reference,
                expected_artifact_kind=SOURCE_BUNDLE_KIND,
                expected_media_type=JSON_MEDIA_TYPE,
                expected_scope="source-path",
                max_bytes=self._resolver.max_artifact_bytes,
            )
        except ContractV4Error:
            self._resolver.register_bytes(
                artifact_id=f"local-source-bundle-{reference.digest.hex[:24]}",
                content_ref=reference,
                artifact_kind=SOURCE_BUNDLE_KIND,
                media_type=JSON_MEDIA_TYPE,
                scope="source-path",
                content=canonical_bytes(bundle.digest_body()),
            )
        return reference

    def build_bundle(
        self,
        *,
        case_id: str,
        decision_time: str | CanonicalTimeV4,
        facts: tuple[LocalFactInput, ...] = (),
        queries: tuple[LocalQueryInput, ...] = (),
        source_id: str | None = None,
        request_id: str | None = None,
        allowed_attack_kinds: tuple[str, ...] = ("exception_attack",),
        query_refutations: tuple[Any, ...] = (),
        query_gates: tuple[Any, ...] = (),
        procedural_input: Any | None = None,
        incremental_parent: Any | None = None,
        composition_policy: Any | None = None,
        composition_choice: Any | None = None,
        composition_expression: Any | None = None,
        composition_operands: tuple[Any, ...] = (),
        business_tasks: tuple[Any, ...] = (),
        now: CanonicalTimeV4 | None = None,
    ) -> CaseInputBundleV4:
        if not case_id:
            raise LocalRuntimeError("case_id must not be empty")
        if not queries and not business_tasks:
            raise LocalRuntimeError(
                "a local case bundle needs at least one issue query or "
                "one typed jc-business-root/1 task"
            )
        business_tasks = tuple(
            task if isinstance(task, BusinessTaskV1) else BusinessTaskV1.from_dict(dict(task))
            for task in business_tasks
        )
        facts = tuple(
            fact if isinstance(fact, LocalFactInput)
            else LocalFactInput(**dict(fact))
            for fact in facts
        )
        queries = tuple(
            query if isinstance(query, LocalQueryInput)
            else LocalQueryInput(
                query_id=dict(query).get("query_id", dict(query).get("issue_id", "")),
                claim=dict(query)["claim"],
                profile=dict(query)["profile"],
            )
            for query in queries
        )
        bundle_now = self._record_issuer_now() if now is None else now
        decision = (
            decision_time if type(decision_time) is CanonicalTimeV4
            else CanonicalTimeV4.parse(decision_time)
        )
        artifact_rows: list[CaseArtifactV4] = []

        artifact_by_ref: dict[ContentRefV4, CaseArtifactV4] = {}

        def add(kind: str, scope: str, payload: dict[str, object],
                media_type: str = JSON_MEDIA_TYPE) -> ContentRefV4:
            raw = canonical_bytes(payload)
            reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
            if reference not in artifact_by_ref:
                artifact_by_ref[reference] = CaseArtifactV4(
                    f"local-{kind}-{reference.digest.hex[:24]}", reference, kind,
                    media_type, scope, b64encode(raw).decode("ascii"),
                )
            return reference

        def add_bytes(kind: str, scope: str, raw: bytes,
                      media_type: str) -> ContentRefV4:
            reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
            if reference not in artifact_by_ref:
                artifact_by_ref[reference] = CaseArtifactV4(
                    f"local-{kind}-{reference.digest.hex[:24]}", reference, kind,
                    media_type, scope, b64encode(raw).decode("ascii"),
                )
            return reference

        source_bundle_ref = self.source_bundle_ref(source_id)
        rule_pack_ref = self._pack.pack_ref
        request_id_value = request_id or f"local-{case_id}"
        placeholder_manifest = _local_ref(EVIDENCE_MANIFEST_KIND, f"{case_id}-manifest")
        placeholder_attestation = _local_ref(FACT_ATTESTATION_KIND, f"{case_id}-attest")
        seed = CaseRequestV4(
            request_id_value,
            "jc/5.0",
            _case_legal_context(self._pack),
            decision,
            source_bundle_ref,
            placeholder_manifest,
            (placeholder_attestation,),
            rule_pack_ref,
            (RequestedOutputV4("semantic_result", "json", "zh-CN"),),
            (),
        )
        binding = case_request_binding_ref(seed)

        manifest_rows = []
        candidate_refs: list[ContentRefV4] = []
        evidence_refs: list[ContentRefV4] = []
        attestation_refs: list[ContentRefV4] = []
        for index, fact in enumerate(facts):
            label = f"fact-{index}"
            proposition_ref = add(FACT_PROPOSITION_KIND, FACT_ADMISSION_SCOPE, {
                "schema_version": "jc/fact-proposition/1.0", "proposition": fact.fact_key,
            })
            value_ref = add(FACT_VALUE_KIND, FACT_ADMISSION_SCOPE, {
                "schema_version": "jc/fact-value/1.0",
                "value_kind": "boolean", "value": bool(fact.value),
            })
            document = (
                fact.evidence_text or f"local reviewed evidence for {fact.fact_key}"
            ).encode("utf-8")
            document_ref = add_bytes(
                EVIDENCE_DOCUMENT_KIND, CASE_EVIDENCE_SCOPE, document,
                "application/octet-stream",
            )
            custody_ref = add(EVIDENCE_CUSTODY_KIND, CASE_EVIDENCE_SCOPE, {
                "schema_version": "jc/evidence-custody/1.0",
                "custody": fact.locator_label or "local-case-file",
            })
            evidence = _evidence_item_v4(
                f"{label}-evidence", document_ref, custody_ref,
            )
            evidence_ref = add(EVIDENCE_ITEM_KIND, CASE_EVIDENCE_SCOPE, evidence.to_dict())
            candidate = _fact_candidate_v4(
                f"{label}-candidate", proposition_ref, value_ref, evidence_ref,
            )
            candidate_ref = add(FACT_CANDIDATE_KIND, FACT_ADMISSION_SCOPE, candidate.to_dict())
            candidate_refs.append(candidate_ref)
            evidence_refs.append(evidence_ref)
            manifest_rows.append(evidence)
        manifest_body = {
            "manifest_id": f"local-{case_id}-evidence-manifest",
            "request_ref": binding.to_dict(),
            "case_scope": case_id,
            "items": [row.to_dict() for row in manifest_rows],
            "fact_candidate_refs": [item.to_dict() for item in candidate_refs],
            "contradictions": [],
        }
        manifest_ref = ContentRefV4(EVIDENCE_MANIFEST_KIND, digest_value(manifest_body))
        artifact_by_ref[manifest_ref] = CaseArtifactV4(
            f"local-{EVIDENCE_MANIFEST_KIND}-{manifest_ref.digest.hex[:24]}",
            manifest_ref, EVIDENCE_MANIFEST_KIND, JSON_MEDIA_TYPE, CASE_EVIDENCE_SCOPE,
            b64encode(canonical_bytes(manifest_body)).decode("ascii"),
        )
        applicable_source = self._applicable_source(source_id)
        for index, fact in enumerate(facts):
            candidate_ref = candidate_refs[index]
            evidence_ref = evidence_refs[index]
            proposition_ref = _ref_of(
                digest_value({
                    "schema_version": "jc/fact-proposition/1.0",
                    "proposition": fact.fact_key,
                }),
                FACT_PROPOSITION_KIND,
            )
            value_ref = _ref_of(
                digest_value({
                    "schema_version": "jc/fact-value/1.0",
                    "value_kind": "boolean", "value": bool(fact.value),
                }),
                FACT_VALUE_KIND,
            )
            legal_evidence = fact_attestation_evidence_refs(
                request_binding_ref=binding,
                manifest_ref=manifest_ref,
                candidate_ref=candidate_ref,
                proposition_ref=proposition_ref,
                value_ref=value_ref,
                source_refs=(applicable_source,),
                evidence_refs=(evidence_ref,),
                replay_policy_ref=self._policy.replay_policy_ref,
            )
            attestation_body = {
                "attestation_id": (
                    f"local-{manifest_ref.digest.hex[:16]}-{index}-"
                    f"{bundle_now.wire}-attestation"
                ),
                "candidate_ref": candidate_ref.to_dict(),
                "request_ref": binding.to_dict(),
                "case_scope": case_id,
                "proposition_digest": str(proposition_ref.digest),
                "value_digest": str(value_ref.digest),
                "source_refs": [applicable_source.to_dict()],
                "evidence_refs": [evidence_ref.to_dict()],
                "interpretation_version": "local-v1",
                "admission_basis": fact.admission_basis,
                "issuer_role": "legal_reviewer",
                "issued_at": bundle_now.to_dict(),
                "expires_at": self._policy.valid_to.to_dict(),
                "dispute_state": fact.dispute_state,
                "assumption_state": fact.assumption_state,
                "nonce": (
                    f"local-{manifest_ref.digest.hex[:16]}-{index}-{bundle_now.wire}"
                ),
                "replay_policy_ref": self._policy.replay_policy_ref.to_dict(),
                "revocation_ref": None,
            }
            record = self._record_issuer.record(
                role="legal_reviewer",
                scope=LEGAL_APPROVAL_SCOPE,
                kind="legal-approval",
                subject_digest=candidate_ref.digest,
                payload_digest=digest_value(attestation_body),
                evidence_refs=legal_evidence,
                run_identity_ref=None,
                now=bundle_now,
                nonce=attestation_body["nonce"],
            )
            attestation_ref = add(FACT_ATTESTATION_KIND, LEGAL_APPROVAL_SCOPE, {
                **attestation_body, "signature": record.to_dict(),
            })
            attestation_refs.append(attestation_ref)

        claim_by_rule = {row["claim"]: row for row in self._pack.rule_claims}
        query_rows = []
        for query in queries:
            if query.claim not in claim_by_rule:
                raise LocalRuntimeError(
                    f"query {query.query_id!r} cites claim {query.claim!r} "
                    "that is not a conclusion of this pack"
                )
            query_rows.append(_query_request_v5(
                query.query_id, query.claim, query.profile, binding,
            ))
        defeat_policy = None
        if query_rows:
            defeat_policy = DefeatPolicyV5(
                policy_id="local-defeat-policy",
                policy_version="1",
                request_ref=binding.digest,
                allowed_kinds=tuple(allowed_attack_kinds),
                legal_evidence_ref=digest_value({"governance": "local-defeat-policy"}),
            )
        request = CaseRequestV4(
            request_id_value,
            "jc/5.0",
            _case_legal_context(self._pack),
            decision,
            source_bundle_ref,
            manifest_ref,
            tuple(attestation_refs),
            rule_pack_ref,
            (RequestedOutputV4("semantic_result", "json", "zh-CN"),),
            (),
            defeat_policy_v5=defeat_policy,
            profile_queries_v5=tuple(query_rows),
            composition_policy_v5=composition_policy,
            composition_choice_v5=composition_choice,
            composition_expression_v5=composition_expression,
            composition_operands_v5=tuple(composition_operands),
            incremental_parent_v5=incremental_parent,
            query_refutations_v5=tuple(query_refutations),
            query_gates_v5=tuple(query_gates),
            procedural_input_v5=procedural_input,
            business_tasks_v1=business_tasks,
        )
        bundle_body = {
            "schema_version": "jc/case-input-bundle/1.0",
            "bundle_id": f"local-{case_id}",
            "request": request.to_dict(),
            "artifacts": [
                item.to_dict() for item in sorted(
                    artifact_by_ref.values(),
                    key=lambda item: (item.artifact_kind, item.content_ref.digest.hex),
                )
            ],
        }
        return CaseInputBundleV4.from_dict({
            **bundle_body, "bundle_digest": str(digest_value(bundle_body)),
        })

    def _record_issuer_now(self) -> CanonicalTimeV4:
        return _now_utc()

    def _applicable_source(self, source_id: str | None) -> ContentRefV4:
        rows = self._pack.sources
        if source_id is None:
            if len(rows) != 1:
                raise LocalRuntimeError(
                    "this pack has multiple sources; pass source_id explicitly"
                )
            return rows[0][0]
        for ref, snapshot in rows:
            if snapshot.source_id == source_id:
                return ref
        raise LocalRuntimeError(f"unknown source_id {source_id!r}")


def _case_legal_context(pack: LoadedLocalPackV4):
    """The pack's single (jurisdiction, governing_law) context for a case."""

    contexts = {
        (row["jurisdiction"], row["governing_law"]) for row in pack.rule_claims
    }
    if len(contexts) != 1:
        raise LocalRuntimeError(
            "a local case bundle needs exactly one (jurisdiction, governing_law); "
            "split the pack or the case"
        )
    jurisdiction, governing_law = next(iter(contexts))
    from compiler_core.contracts import LegalContextV4

    return LegalContextV4(jurisdiction, governing_law)


def _evidence_item_v4(evidence_id, document_ref, custody_ref):
    from compiler_core.contracts import EvidenceItemV4

    return EvidenceItemV4(
        evidence_id,
        document_ref,
        (CanonicalLocatorV4("page", "local-case-file", 1, None, None),),
        (custody_ref,),
        "NONE",
        "REVIEWED",
    )


def _fact_candidate_v4(candidate_id, proposition_ref, value_ref, evidence_ref):
    from compiler_core.contracts import FactCandidateV4

    return FactCandidateV4(
        candidate_id,
        proposition_ref,
        "boolean",
        value_ref,
        (evidence_ref,),
        "lawyer",
        None,
    )


def _ref_of(digest: DigestV4, kind: str) -> ContentRefV4:
    return ContentRefV4(kind, digest)


def _query_request_v5(query_id: str, claim: str, profile: str, binding: ContentRefV4):
    from compiler_core.contracts import QueryRequestV5

    return QueryRequestV5(
        query_id=query_id,
        claim=claim,
        profile=profile,
        mapping_version=PROFILE_MAPPING_VERSION_V5,
        scenario_ref=_v5_scenario_ref(binding.digest, query_id),
    )


@dataclass(frozen=True, slots=True)
class LocalRuntimeHandleV4:
    """The local runtime materials a :class:`JCClient` instance carries."""

    policy: TrustPolicyV4
    trust: LocalRecordTrustV4
    identity: LocalBuildIdentityV4
    pack: LoadedLocalPackV4
    pack_verifier: RulePackVerifierV4
    builder: LocalCaseInputsBuilderV4
    backend_profile_digest: DigestV4
    runtime_config_digest: DigestV4
    storage_capability_ref: ContentRefV4


def _norm_rule_roots(rule_roots) -> tuple[Path, ...]:
    if rule_roots is None:
        return ()
    if isinstance(rule_roots, (str, Path)):
        rule_roots = (rule_roots,)
    roots = []
    for root in rule_roots:
        path = Path(root).expanduser()
        roots.append(path if path.is_absolute() else path.resolve())
    return tuple(roots)


def create_local_client(
    state_root,
    rule_roots=(),
    *,
    clock=None,
    quota_bytes: int | None = None,
):
    """Create the local keyless JC client over the existing formal spine.

    ``state_root`` is the local run-record directory; ``rule_roots`` are one
    or more local rule directories (or a single ``jc-local-pack.json`` file).
    No service key, trust bundle, signed pack, broker, probe, activation
    ledger, or generated key is required or created.
    """

    from contextlib import contextmanager
    from base64 import b64encode

    from compiler_core.audit_bundle import AuditBundleStoreV4
    from compiler_core.backend_router import BackendRouterV4
    from compiler_core.client import JCClient
    from compiler_core.contracts import (
        EvidenceManifestV4,
        MCPCapabilitiesOutputV4,
    )
    from compiler_core.independent_checker import IndependentCheckerV4
    from compiler_core.legal_ir import LegalIRCompilerV4
    from compiler_core.mcp import TOOL_SPECS
    from compiler_core.storage import V4TransactionStore

    root = Path(state_root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    roots = _norm_rule_roots(rule_roots)
    runtime_clock = clock if clock is not None else _now_utc
    policy = local_trust_policy()
    trust = LocalRecordTrustV4(policy=policy)
    identity = local_build_identity()
    solver_deadline = (
        HARD_MAX_RESOURCE_LIMITS_V4["solver_deadline_ms"] if os.name == "nt"
        else DEFAULT_RESOURCE_LIMITS_V4["solver_deadline_ms"]
    )
    backend_profile = backend_profile_digest_v4(solver_deadline_ms=solver_deadline)
    default_limits = None
    if os.name == "nt":
        from compiler_core.contracts import ResourceLimitsV4 as _RL

        default_limits = _RL.from_dict({
            **DEFAULT_RESOURCE_LIMITS_V4, "solver_deadline_ms": solver_deadline,
        })

    resolver = ArtifactResolverV4(max_artifact_bytes=4_194_304)
    source_service = SourceServiceV4(resolver, trust)
    pack_verifier = RulePackVerifierV4(
        resolver,
        source_service,
        trust,
        expected_engine_api=identity.engine_api,
        expected_compiler_build_digest=identity.compiler_build_digest,
        expected_source_tree_digest=identity.source_tree_digest,
        expected_schema_digest=identity.schema_digest,
    )
    if not roots:
        raise LocalRuntimeError(
            "create_local_client requires at least one rule root; JC does not "
            "ship a rule library and will not invent legal capability"
        )
    pack = build_local_pack(
        resolver, policy, tuple(roots), identity=identity, now=runtime_clock(),
    )
    pack_verifier.verify(pack.pack_ref, now=runtime_clock())

    storage_ref = _local_ref("storage-capability", f"local:{pack.pack_ref.digest.hex[:24]}")
    runtime_config_digest = digest_value({
        "jc-local-runtime/1": {
            "policy": str(policy.policy_digest),
            "pack": str(pack.pack_ref.digest),
            "build": str(identity.compiler_build_digest),
            "backend_profile": str(backend_profile),
        },
    })

    fact_service = FactAdmissionServiceV4(
        resolver,
        source_service,
        trust,
        receipt_issuer=LOCAL_ISSUER_ROLES["service_signer"],
        receipt_signer=LocalRecordIssuerV4(policy),
    )
    compiler = LegalIRCompilerV4(
        pack_verifier,
        receipt_issuer=LOCAL_ISSUER_ROLES["service_signer"],
        receipt_signer=LocalRecordIssuerV4(policy),
    )
    router = BackendRouterV4(compiler, fact_service, receipt_signer=LocalRecordIssuerV4(policy))
    checker = IndependentCheckerV4(
        resolver,
        trust,
        receipt_issuer=LOCAL_ISSUER_ROLES["service_signer"],
        receipt_signer=LocalRecordIssuerV4(policy),
    )
    quota = quota_bytes if quota_bytes is not None else 1_073_741_824
    namespace = root / "jc-v4-state"
    store = (
        V4TransactionStore.open(root, quota_bytes=quota)
        if namespace.is_dir()
        else V4TransactionStore.create(root, quota_bytes=quota)
    )
    audit_store = AuditBundleStoreV4(
        store,
        trust_material=AuditTrustMaterialV4(policy, (), "local", (), ()),
        current_engine_build_digest=identity.compiler_build_digest,
        checker_receipt_issuer=LOCAL_ISSUER_ROLES["service_signer"],
    )
    certificate_issuer = CertificateIssuerV4(
        trust,
        current_engine_build_digest=identity.compiler_build_digest,
        signer=LocalRecordIssuerV4(policy),
    )
    application = ApplicationV4(
        resolver,
        trust,
        source_service,
        fact_service,
        pack_verifier,
        compiler,
        router,
        checker,
        audit_store,
        certificate_issuer,
        receipt_signer=LocalRecordIssuerV4(policy),
        clock=runtime_clock,
        default_limits=default_limits,
    )

    @contextmanager
    def evaluation_context(bundle):
        resolver.validate_case_bundle(bundle)
        request = bundle.request
        manifest_artifact = next(
            item for item in bundle.artifacts
            if item.content_ref == request.evidence_manifest_ref
        )
        manifest = EvidenceManifestV4.from_dict({
            **parse_json_document(manifest_artifact.content_bytes()),
            "manifest_digest": str(request.evidence_manifest_ref.digest),
        })
        request_ref = ContentRefV4(CASE_REQUEST_KIND, request.canonical_digest())
        run = RunIdentityV4.build(
            request,
            request_ref,
            engine_version=identity.engine_api,
            engine_source_commit=identity.engine_source_commit,
            engine_source_tree=identity.engine_source_tree,
            engine_build_digest=identity.compiler_build_digest,
            wheel_digest=identity.wheel_digest,
            package_digest=identity.package_digest,
            schema_digest=identity.schema_digest,
            tool_spec_digest=identity.tool_spec_digest,
            lock_digest=identity.lock_digest,
            runtime_config_digest=runtime_config_digest,
            algorithm_profile_digest=_algorithm_profile_digest(),
            trust_policy_ref=ContentRefV4(TRUST_POLICY_KIND, policy.canonical_digest()),
            storage_capability_ref=storage_ref,
            backend_profile_digest=backend_profile,
        )
        run_ref = ContentRefV4(RUN_IDENTITY_KIND, run.canonical_digest())

        def artifact(artifact_id, reference, kind, scope, raw):
            return CaseArtifactV4(
                artifact_id, reference, kind, "application/json", scope,
                b64encode(raw).decode("ascii"),
            )

        transient = (
            *bundle.artifacts,
            artifact(
                f"request-{request_ref.digest.hex[:24]}", request_ref,
                CASE_REQUEST_KIND, CASE_REQUEST_SCOPE, request.canonical_bytes(),
            ),
            artifact(
                f"run-{run_ref.digest.hex[:24]}", run_ref,
                RUN_IDENTITY_KIND, RUN_IDENTITY_SCOPE, canonical_bytes(run.digest_body()),
            ),
        )
        with resolver.overlay(transient):
            yield request_ref, run_ref, manifest.case_scope

    capabilities = MCPCapabilitiesOutputV4(
        "jc/5.0",
        identity.engine_api,
        identity.source_tree_digest.hex,
        identity.compiler_build_digest,
        identity.wheel_digest,
        identity.package_digest,
        identity.lock_digest,
        identity.schema_digest,
        identity.tool_spec_digest,
        TOOL_SPECS,
        default_limits if default_limits is not None else ResourceLimitsV4(),
        pack.pack_ref,
        ContentRefV4(TRUST_POLICY_KIND, policy.canonical_digest()),
        storage_ref,
        True,
        True,
    )
    client = JCClient(
        application,
        audit_store,
        clock=runtime_clock,
        evaluation_context=evaluation_context,
        capabilities=capabilities,
        default_limits=default_limits,
    )
    handle = LocalRuntimeHandleV4(
        policy=policy,
        trust=trust,
        identity=identity,
        pack=pack,
        pack_verifier=pack_verifier,
        builder=LocalCaseInputsBuilderV4(resolver, policy, pack, identity),
        backend_profile_digest=backend_profile,
        runtime_config_digest=runtime_config_digest,
        storage_capability_ref=storage_ref,
    )
    client._local_runtime = handle  # noqa: SLF001 - composition root wiring
    return client


def local_handle_of(client):
    """Return the local runtime handle wired by :func:`create_local_client`."""

    handle = getattr(client, "_local_runtime", None)
    if handle is None:
        raise LocalRuntimeError(
            "this client was not created by create_local_client"
        )
    return handle


__all__ = (
    "LOCAL_ISSUER_ROLES",
    "LOCAL_PACK_DESCRIPTOR",
    "LOCAL_PACK_SCHEMA",
    "LOCAL_POLICY_ID",
    "LocalBuildIdentityV4",
    "LocalCaseInputsBuilderV4",
    "LocalFactInput",
    "LocalQueryInput",
    "LocalRecordIssuerV4",
    "LocalRecordTrustV4",
    "LocalRuleSourceLoaderV4",
    "LocalRuntimeError",
    "LocalRuntimeHandleV4",
    "LoadedLocalPackV4",
    "build_local_pack",
    "create_local_client",
    "local_build_identity",
    "local_handle_of",
    "local_trust",
    "local_trust_policy",
)
