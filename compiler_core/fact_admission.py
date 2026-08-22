"""Evidence-bound V4 fact admission with internally issued signed receipts."""

from __future__ import annotations

from typing import Callable

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    CanonicalTimeV4,
    CaseRequestV4,
    ContentRefV4,
    ContractV4Error,
    EvidenceItemV4,
    EvidenceManifestV4,
    FactAdmissionReceiptV4,
    FactAttestationV4,
    FactCandidateV4,
    RunIdentityV4,
    SignatureEnvelopeV4,
    SourceBundleV4,
)
from compiler_core.source_service import (
    SOURCE_BUNDLE_KIND,
    SOURCE_SNAPSHOT_KIND,
    SourceServiceV4,
    source_snapshot_ref,
)
from compiler_core.trust import TrustVerifierV4


CASE_REQUEST_KIND = "case-request"
CASE_REQUEST_SCOPE = "request"
CASE_REQUEST_BINDING_KIND = "case-request-binding"
EVIDENCE_MANIFEST_KIND = "evidence-manifest"
EVIDENCE_ITEM_KIND = "evidence-item"
EVIDENCE_DOCUMENT_KIND = "evidence-document"
EVIDENCE_CUSTODY_KIND = "evidence-custody"
CASE_EVIDENCE_SCOPE = "case-evidence"
FACT_PROPOSITION_KIND = "fact-proposition"
FACT_VALUE_KIND = "fact-value"
FACT_CANDIDATE_KIND = "fact-candidate"
FACT_ATTESTATION_KIND = "fact-attestation"
FACT_ADMISSION_SCOPE = "fact-admission"
LEGAL_APPROVAL_SCOPE = "legal-approval"
SOURCE_GATE_RECEIPT_KIND = "source-gate-receipt"
INTERPRETATION_GATE_RECEIPT_KIND = "interpretation-gate-receipt"
FACT_GATE_RECEIPT_KIND = "fact-gate-receipt"
ADMITTED_FACT_KIND = "admitted-fact"
FACT_ADMISSION_RECEIPT_KIND = "fact-admission-receipt"
RUN_IDENTITY_KIND = "run-identity"
RUN_IDENTITY_SCOPE = "run"
TRUST_POLICY_KIND = "trust-policy"

_ADMISSION_BASES = frozenset({
    "documentary_evidence_human_reviewed",
    "judicial_notice",
    "admitted_by_opponent",
    "presumption_of_law",
})
_CANDIDATE_PRODUCERS = frozenset({"agent", "extraction", "lawyer", "system"})
_VERIFIED_EVIDENCE_STATES = frozenset({"REVIEWED", "VERIFIED"})
_SAFE_REDACTION_STATES = frozenset({"NONE", "REDACTED_VERIFIED"})
_FORMAL_DISPUTE_STATE = "UNDISPUTED"
_NONFORMAL_DISPUTE_STATES = frozenset({"UNKNOWN", "DISPUTED", "USER_ASSUMED"})
_FORMAL_ASSUMPTION_STATE = "NONE"

ReceiptSignerV4 = Callable[
    [
        DigestV4,
        DigestV4,
        tuple[ContentRefV4, ...],
        ContentRefV4,
        CanonicalTimeV4,
    ],
    SignatureEnvelopeV4,
]


def _fail(code: str, detail: str) -> None:
    raise ContractV4Error(code, detail)


def _sorted_refs(references: tuple[ContentRefV4, ...]) -> tuple[ContentRefV4, ...]:
    if any(type(reference) is not ContentRefV4 for reference in references):
        _fail("FACT_REFERENCE_TYPE", "evidence references must be exact ContentRefV4 values")
    if len(set(references)) != len(references):
        _fail("FACT_DUPLICATE_REFERENCE", "fact evidence references must not repeat")
    return tuple(sorted(references, key=lambda item: (item.kind, str(item.digest))))


def _request_binding_body(request: CaseRequestV4) -> dict[str, object]:
    return {
        "schema_version": "jc/case-request-binding/1.0",
        "request_id": request.request_id,
        "request_schema_version": request.schema_version,
        "legal_context": request.legal_context.to_dict(),
        "decision_time": request.decision_time.to_dict(),
        "source_bundle_ref": request.source_bundle_ref.to_dict(),
        "rule_pack_ref": request.rule_pack_ref.to_dict(),
        "requested_outputs": [item.to_dict() for item in request.requested_outputs],
        "proposal_refs": [item.to_dict() for item in request.proposal_refs],
    }


def case_request_binding_ref(request: CaseRequestV4) -> ContentRefV4:
    """Return the acyclic identity projection used by request-owned inputs."""

    if type(request) is not CaseRequestV4:
        _fail("FACT_INPUT_TYPE", "request must be CaseRequestV4")
    return ContentRefV4(
        CASE_REQUEST_BINDING_KIND,
        DigestV4.from_bytes(canonical_bytes(_request_binding_body(request))),
    )


def evidence_item_ref(item: EvidenceItemV4) -> ContentRefV4:
    if type(item) is not EvidenceItemV4:
        _fail("FACT_INPUT_TYPE", "evidence item must be EvidenceItemV4")
    return ContentRefV4(EVIDENCE_ITEM_KIND, DigestV4.from_bytes(item.canonical_bytes()))


def fact_attestation_evidence_refs(
    *,
    request_binding_ref: ContentRefV4,
    manifest_ref: ContentRefV4,
    candidate_ref: ContentRefV4,
    proposition_ref: ContentRefV4,
    value_ref: ContentRefV4,
    source_refs: tuple[ContentRefV4, ...],
    evidence_refs: tuple[ContentRefV4, ...],
    replay_policy_ref: ContentRefV4,
) -> tuple[ContentRefV4, ...]:
    return _sorted_refs((
        request_binding_ref,
        manifest_ref,
        candidate_ref,
        proposition_ref,
        value_ref,
        *source_refs,
        *evidence_refs,
        replay_policy_ref,
    ))


class FactAdmissionServiceV4:
    """Admit one canonical fact only after all three derived gates pass."""

    def __init__(
        self,
        resolver: ArtifactResolverV4,
        source_service: SourceServiceV4,
        trust: TrustVerifierV4,
        *,
        receipt_issuer: str,
        receipt_signer: ReceiptSignerV4,
    ) -> None:
        if (
            type(resolver) is not ArtifactResolverV4
            or type(source_service) is not SourceServiceV4
            or type(trust) is not TrustVerifierV4
            or source_service._resolver is not resolver
            or source_service._trust is not trust
            or type(receipt_issuer) is not str
            or not receipt_issuer
            or not callable(receipt_signer)
        ):
            _fail("FACT_INPUT_TYPE", "fact service dependencies are invalid")
        self._resolver = resolver
        self._source_service = source_service
        self._trust = trust
        self._receipt_issuer = receipt_issuer
        self._receipt_signer = receipt_signer
        self._admissions: dict[
            tuple[ContentRefV4, str, ContentRefV4, ContentRefV4, ContentRefV4],
            ContentRefV4,
        ] = {}
        self._receipt_contexts: dict[
            ContentRefV4,
            tuple[ContentRefV4, str, ContentRefV4, ContentRefV4],
        ] = {}
        self._candidate_ids: dict[str, ContentRefV4] = {}
        self._attestation_ids: dict[str, ContentRefV4] = {}
        self._legal_contexts: dict[
            tuple[ContentRefV4, str, ContentRefV4, ContentRefV4, ContentRefV4],
            tuple[
                EvidenceManifestV4,
                FactCandidateV4,
                FactAttestationV4,
                tuple[ContentRefV4, ...],
                str,
            ],
        ] = {}

    def _resolve_contract(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
        contract: type,
    ) -> object:
        if type(reference) is not ContentRefV4 or reference.kind != kind:
            _fail("FACT_REF_KIND", f"expected {kind} content reference")
        raw = self._resolver.resolve_content(
            reference,
            expected_artifact_kind=kind,
            expected_media_type="application/json",
            expected_scope=scope,
            max_bytes=self._resolver.max_artifact_bytes,
        )
        try:
            document = parse_json_document(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ContractV4Error("FACT_JSON_UTF8", f"{kind} must be valid UTF-8") from exc
        if type(document) is not dict:
            _fail("FACT_JSON_TYPE", f"{kind} must be a JSON object")
        value = contract.from_dict(document)
        if raw != value.canonical_bytes():
            _fail("FACT_NONCANONICAL_JSON", f"{kind} must use canonical V4 bytes")
        return value

    def _resolve_json(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
        media_type: str = "application/json",
    ) -> dict[str, object]:
        if type(reference) is not ContentRefV4 or reference.kind != kind:
            _fail("FACT_REF_KIND", f"expected {kind} content reference")
        raw = self._resolver.resolve_content(
            reference,
            expected_artifact_kind=kind,
            expected_media_type=media_type,
            expected_scope=scope,
            max_bytes=self._resolver.max_artifact_bytes,
        )
        try:
            document = parse_json_document(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ContractV4Error("FACT_JSON_UTF8", f"{kind} must be valid UTF-8") from exc
        if type(document) is not dict:
            _fail("FACT_JSON_TYPE", f"{kind} must be a JSON object")
        if raw != canonical_bytes(document):
            _fail("FACT_NONCANONICAL_JSON", f"{kind} must use canonical JSON bytes")
        return document

    def _resolve_self_digest_contract(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
        contract: type,
        digest_field: str,
    ) -> object:
        """Resolve canonical digest-body bytes and restore the non-recursive digest."""

        if type(reference) is not ContentRefV4 or reference.kind != kind:
            _fail("FACT_REF_KIND", f"expected {kind} content reference")
        raw = self._resolver.resolve_content(
            reference,
            expected_artifact_kind=kind,
            expected_media_type="application/json",
            expected_scope=scope,
            max_bytes=self._resolver.max_artifact_bytes,
        )
        try:
            body = parse_json_document(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ContractV4Error("FACT_JSON_UTF8", f"{kind} must be valid UTF-8") from exc
        if type(body) is not dict or digest_field in body or raw != canonical_bytes(body):
            _fail("FACT_DIGEST_BODY", f"{kind} must store its canonical digest body")
        value = contract.from_dict({**body, digest_field: str(reference.digest)})
        if value.canonical_digest() != reference.digest or value.digest_body() != body:
            _fail("FACT_SELF_DIGEST", f"{kind} self digest does not match its reference")
        return value

    def _register_json(self, *, kind: str, payload: dict[str, object]) -> ContentRefV4:
        raw = canonical_bytes(payload)
        reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
        return self._resolver.register_bytes(
            artifact_id=f"{kind}-{reference.digest.hex}",
            content_ref=reference,
            artifact_kind=kind,
            media_type="application/json",
            scope=FACT_ADMISSION_SCOPE,
            content=raw,
        )

    def _bind_request_projection(self, request: CaseRequestV4) -> ContentRefV4:
        payload = _request_binding_body(request)
        reference = case_request_binding_ref(request)
        self._resolver.register_bytes(
            artifact_id=f"{CASE_REQUEST_BINDING_KIND}-{reference.digest.hex}",
            content_ref=reference,
            artifact_kind=CASE_REQUEST_BINDING_KIND,
            media_type="application/json",
            scope=FACT_ADMISSION_SCOPE,
            content=canonical_bytes(payload),
        )
        return reference

    def _validate_run_identity(
        self,
        run_identity_ref: ContentRefV4,
        *,
        request_ref: ContentRefV4,
        request: CaseRequestV4,
    ) -> RunIdentityV4:
        value = self._resolve_self_digest_contract(
            run_identity_ref,
            kind=RUN_IDENTITY_KIND,
            scope=RUN_IDENTITY_SCOPE,
            contract=RunIdentityV4,
            digest_field="run_digest",
        )
        if type(value) is not RunIdentityV4:
            _fail("FACT_CONTRACT_TYPE", "resolved run identity has the wrong type")
        expected_policy_ref = ContentRefV4(
            TRUST_POLICY_KIND,
            self._trust.policy.canonical_digest(),
        )
        if (
            value.request_ref != request_ref
            or value.source_bundle_ref != request.source_bundle_ref
            or value.evidence_manifest_ref != request.evidence_manifest_ref
            or value.fact_attestation_refs != request.fact_attestation_refs
            or value.rule_pack_ref != request.rule_pack_ref
            or value.trust_policy_ref != expected_policy_ref
        ):
            _fail("FACT_RUN_BINDING", "run identity does not bind the canonical request inputs")
        return value

    @staticmethod
    def _wire_ref(value: object, field: str) -> ContentRefV4:
        if type(value) is not dict:
            _fail("FACT_ARTIFACT_SHAPE", f"{field} must be a content reference")
        return ContentRefV4.from_dict(value)

    @staticmethod
    def _wire_refs(value: object, field: str) -> tuple[ContentRefV4, ...]:
        if type(value) is not list:
            _fail("FACT_ARTIFACT_SHAPE", f"{field} must be an array")
        return tuple(FactAdmissionServiceV4._wire_ref(item, field) for item in value)

    def _validate_materials(
        self,
        request_ref: ContentRefV4,
        request: CaseRequestV4,
        request_binding: ContentRefV4,
        candidate_ref: ContentRefV4,
        attestation_ref: ContentRefV4,
        *,
        case_scope: str,
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> tuple[
        EvidenceManifestV4,
        FactCandidateV4,
        FactAttestationV4,
        tuple[ContentRefV4, ...],
        str,
    ]:
        manifest_value = self._resolve_self_digest_contract(
            request.evidence_manifest_ref,
            kind=EVIDENCE_MANIFEST_KIND,
            scope=CASE_EVIDENCE_SCOPE,
            contract=EvidenceManifestV4,
            digest_field="manifest_digest",
        )
        candidate_value = self._resolve_contract(
            candidate_ref,
            kind=FACT_CANDIDATE_KIND,
            scope=FACT_ADMISSION_SCOPE,
            contract=FactCandidateV4,
        )
        attestation_value = self._resolve_contract(
            attestation_ref,
            kind=FACT_ATTESTATION_KIND,
            scope=LEGAL_APPROVAL_SCOPE,
            contract=FactAttestationV4,
        )
        if (
            type(manifest_value) is not EvidenceManifestV4
            or type(candidate_value) is not FactCandidateV4
            or type(attestation_value) is not FactAttestationV4
        ):
            _fail("FACT_CONTRACT_TYPE", "resolved fact inputs have the wrong contract type")
        manifest = manifest_value
        candidate = candidate_value
        attestation = attestation_value

        if manifest.request_ref != request_binding or attestation.request_ref != request_binding:
            _fail("FACT_REQUEST_BINDING", "manifest or attestation binds another request projection")
        if manifest.case_scope != case_scope or attestation.case_scope != case_scope:
            _fail("FACT_SCOPE_MISMATCH", "fact inputs bind another case scope")
        if attestation_ref not in request.fact_attestation_refs:
            _fail("FACT_REQUEST_MEMBERSHIP", "attestation is not declared by the request")
        if len(set(manifest.fact_candidate_refs)) != len(manifest.fact_candidate_refs):
            _fail("FACT_DUPLICATE_REFERENCE", "manifest candidate refs must not repeat")
        if manifest.fact_candidate_refs.count(candidate_ref) != 1:
            _fail("FACT_MANIFEST_CANDIDATE", "manifest does not bind the exact candidate")
        if candidate.producer_kind not in _CANDIDATE_PRODUCERS:
            _fail("FACT_PRODUCER", "candidate producer cannot confer formal trust")
        if candidate.proposal_ref is not None and candidate.proposal_ref not in request.proposal_refs:
            _fail("FACT_PROPOSAL_BINDING", "candidate proposal is not declared by the request")
        prior_candidate = self._candidate_ids.get(candidate.candidate_id)
        if prior_candidate is not None and prior_candidate != candidate_ref:
            _fail("FACT_CANDIDATE_ID_COLLISION", "candidate_id cannot bind different bytes")
        prior_attestation = self._attestation_ids.get(attestation.attestation_id)
        if prior_attestation is not None and prior_attestation != attestation_ref:
            _fail("FACT_ATTESTATION_ID_COLLISION", "attestation_id cannot bind different bytes")

        proposition = self._resolve_json(
            candidate.proposition_ref,
            kind=FACT_PROPOSITION_KIND,
            scope=FACT_ADMISSION_SCOPE,
        )
        value = self._resolve_json(
            candidate.value_ref,
            kind=FACT_VALUE_KIND,
            scope=FACT_ADMISSION_SCOPE,
        )
        if set(proposition) != {"schema_version", "proposition"} or (
            proposition.get("schema_version") != "jc/fact-proposition/1.0"
            or type(proposition.get("proposition")) is not str
            or not proposition["proposition"]
        ):
            _fail("FACT_PROPOSITION_SHAPE", "proposition artifact has the wrong canonical shape")
        if set(value) != {"schema_version", "value_kind", "value"} or (
            value.get("schema_version") != "jc/fact-value/1.0"
            or value.get("value_kind") != candidate.value_kind
        ):
            _fail("FACT_VALUE_KIND_MISMATCH", "value artifact does not bind candidate value_kind")

        item_by_ref: dict[ContentRefV4, EvidenceItemV4] = {}
        evidence_ids: set[str] = set()
        for item in manifest.items:
            reference = evidence_item_ref(item)
            if reference in item_by_ref or item.evidence_id in evidence_ids:
                _fail("FACT_EVIDENCE_ID_COLLISION", "manifest evidence identity repeats")
            item_by_ref[reference] = item
            evidence_ids.add(item.evidence_id)
        if not candidate.evidence_refs or len(set(candidate.evidence_refs)) != len(candidate.evidence_refs):
            _fail("FACT_EVIDENCE_REQUIRED", "candidate requires unique evidence refs")
        for reference in candidate.evidence_refs:
            item = item_by_ref.get(reference)
            if item is None:
                _fail("FACT_EVIDENCE_MISMATCH", "candidate evidence is absent from manifest")
            resolved_item = self._resolve_contract(
                reference,
                kind=EVIDENCE_ITEM_KIND,
                scope=CASE_EVIDENCE_SCOPE,
                contract=EvidenceItemV4,
            )
            if resolved_item != item:
                _fail("FACT_EVIDENCE_MISMATCH", "manifest evidence differs from resolved bytes")
            if (
                item.review_state not in _VERIFIED_EVIDENCE_STATES
                or item.redaction_state not in _SAFE_REDACTION_STATES
                or not item.locators
                or not item.custody_provenance
            ):
                _fail("FACT_EVIDENCE_NOT_VERIFIED", "evidence is not reviewed and provenance-bound")
            self._resolver.resolve_content(
                item.document_ref,
                expected_artifact_kind=EVIDENCE_DOCUMENT_KIND,
                expected_media_type="application/octet-stream",
                expected_scope=CASE_EVIDENCE_SCOPE,
                max_bytes=self._resolver.max_artifact_bytes,
            )
            for custody_ref in item.custody_provenance:
                self._resolver.resolve_content(
                    custody_ref,
                    expected_artifact_kind=EVIDENCE_CUSTODY_KIND,
                    expected_media_type="application/json",
                    expected_scope=CASE_EVIDENCE_SCOPE,
                    max_bytes=self._resolver.max_artifact_bytes,
                )
        selected_evidence = set(candidate.evidence_refs)
        if any(
            contradiction.left_ref in selected_evidence
            or contradiction.right_ref in selected_evidence
            for contradiction in manifest.contradictions
        ):
            _fail("FACT_EVIDENCE_CONTRADICTION", "selected evidence has an unresolved contradiction")

        bundle_value = self._resolve_self_digest_contract(
            request.source_bundle_ref,
            kind=SOURCE_BUNDLE_KIND,
            scope="source-path",
            contract=SourceBundleV4,
            digest_field="bundle_digest",
        )
        if type(bundle_value) is not SourceBundleV4:
            _fail("FACT_CONTRACT_TYPE", "resolved source bundle has the wrong type")
        for snapshot in bundle_value.snapshots:
            self._source_service.admit_snapshot(source_snapshot_ref(snapshot), now=now)
        applicable_source = self._source_service.resolve_applicable(
            request.source_bundle_ref,
            decision_time=request.decision_time,
        )
        source_refs = (applicable_source,)

        if (
            attestation.candidate_ref != candidate_ref
            or attestation.proposition_digest != candidate.proposition_ref.digest
            or attestation.value_digest != candidate.value_ref.digest
            or attestation.source_refs != source_refs
            or attestation.evidence_refs != candidate.evidence_refs
        ):
            _fail("FACT_ATTESTATION_BINDING", "attestation does not bind exact fact materials")
        if attestation.admission_basis not in _ADMISSION_BASES:
            _fail("FACT_ADMISSION_BASIS", "attestation admission basis is not authorized")
        if attestation.issuer_role != "legal_reviewer":
            _fail("FACT_ISSUER_ROLE", "fact attestation requires legal_reviewer")
        if attestation.dispute_state != _FORMAL_DISPUTE_STATE:
            if attestation.dispute_state in _NONFORMAL_DISPUTE_STATES:
                _fail("FACT_NOT_FORMAL", "UNKNOWN/DISPUTED/USER_ASSUMED cannot become premise")
            _fail("FACT_DISPUTE_STATE", "unknown dispute state")
        if attestation.assumption_state != _FORMAL_ASSUMPTION_STATE:
            _fail("FACT_NOT_FORMAL", "USER_ASSUMED facts cannot become premise")
        if attestation.revocation_ref is not None:
            _fail("FACT_ATTESTATION_REVOKED", "revoked attestation cannot admit a fact")
        if now < attestation.issued_at:
            _fail("FACT_ATTESTATION_NOT_YET_VALID", "attestation is not yet valid")
        if attestation.expires_at is None or not now < attestation.expires_at:
            _fail("FACT_ATTESTATION_EXPIRED", "attestation is expired or has no expiry")
        if attestation.replay_policy_ref != self._trust.policy.replay_policy_ref:
            _fail("FACT_REPLAY_POLICY", "attestation does not bind the active replay policy")
        if (
            attestation.signature.nonce != attestation.nonce
            or attestation.signature.issued_at != attestation.issued_at
            or attestation.signature.expires_at != attestation.expires_at
            or attestation.signature.run_identity_ref is not None
        ):
            _fail(
                "FACT_ATTESTATION_ENVELOPE",
                "legal attestation must precede and cannot hash-bind the full run identity",
            )
        expected_legal_evidence = fact_attestation_evidence_refs(
            request_binding_ref=request_binding,
            manifest_ref=request.evidence_manifest_ref,
            candidate_ref=candidate_ref,
            proposition_ref=candidate.proposition_ref,
            value_ref=candidate.value_ref,
            source_refs=source_refs,
            evidence_refs=candidate.evidence_refs,
            replay_policy_ref=attestation.replay_policy_ref,
        )
        if attestation.signature.evidence_refs != expected_legal_evidence:
            _fail("FACT_SIGNATURE_EVIDENCE", "legal signature evidence is incomplete or reordered")
        legal_key = (
            request_ref,
            case_scope,
            run_identity_ref,
            candidate_ref,
            attestation_ref,
        )
        cached = self._legal_contexts.get(legal_key)
        expected_context = (manifest, candidate, attestation, source_refs)
        if cached is not None:
            if cached[:4] != expected_context:
                _fail("FACT_LEGAL_CONTEXT", "cached legal context differs from canonical inputs")
        verification_trust = (
            self._trust._fresh_without_replay()
            if cached is not None
            else self._trust
        )
        legal_principal = verification_trust.verify(
            attestation.signature,
            expected_subject_digest=candidate_ref.digest,
            expected_payload_digest=digest_value(attestation.signature_body()),
            required_role="legal_reviewer",
            required_scope="legal-approval",
            required_artifact_kind="legal-approval",
            expected_status="APPROVED",
            now=now,
            separation_from_principals=(),
        )
        if cached is not None:
            if cached[4] != legal_principal:
                _fail("FACT_LEGAL_CONTEXT", "cached legal signer identity changed")
            return *expected_context, legal_principal
        result = (*expected_context, legal_principal)
        self._legal_contexts[legal_key] = result
        return result

    @staticmethod
    def _receipt_evidence_refs(
        *,
        request_ref: ContentRefV4,
        request_binding_ref: ContentRefV4,
        manifest_ref: ContentRefV4,
        candidate_ref: ContentRefV4,
        attestation_ref: ContentRefV4,
        fact_ref: ContentRefV4,
        source_gate_ref: ContentRefV4,
        interpretation_gate_ref: ContentRefV4,
        fact_gate_ref: ContentRefV4,
        source_refs: tuple[ContentRefV4, ...],
        evidence_refs: tuple[ContentRefV4, ...],
        replay_policy_ref: ContentRefV4,
    ) -> tuple[ContentRefV4, ...]:
        return _sorted_refs((
            request_ref,
            request_binding_ref,
            manifest_ref,
            candidate_ref,
            attestation_ref,
            fact_ref,
            source_gate_ref,
            interpretation_gate_ref,
            fact_gate_ref,
            *source_refs,
            *evidence_refs,
            replay_policy_ref,
        ))

    def admit(
        self,
        request_ref: ContentRefV4,
        candidate_ref: ContentRefV4,
        attestation_ref: ContentRefV4,
        *,
        case_scope: str,
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> ContentRefV4:
        """Derive all gates and issue a signed receipt; caller outcomes are not accepted."""

        if (
            type(request_ref) is not ContentRefV4
            or type(candidate_ref) is not ContentRefV4
            or type(attestation_ref) is not ContentRefV4
            or type(case_scope) is not str
            or not case_scope
            or type(run_identity_ref) is not ContentRefV4
            or run_identity_ref.kind != RUN_IDENTITY_KIND
            or type(now) is not CanonicalTimeV4
        ):
            _fail("FACT_INPUT_TYPE", "fact admission context is invalid")
        key = (request_ref, case_scope, run_identity_ref, candidate_ref, attestation_ref)
        existing = self._admissions.get(key)
        if existing is not None:
            self.verify_receipt(
                existing,
                request_ref=request_ref,
                case_scope=case_scope,
                run_identity_ref=run_identity_ref,
                now=now,
            )
            return existing

        request_value = self._resolve_contract(
            request_ref,
            kind=CASE_REQUEST_KIND,
            scope=CASE_REQUEST_SCOPE,
            contract=CaseRequestV4,
        )
        if type(request_value) is not CaseRequestV4:
            _fail("FACT_CONTRACT_TYPE", "resolved request has the wrong type")
        request = request_value
        request_binding = self._bind_request_projection(request)
        self._validate_run_identity(
            run_identity_ref,
            request_ref=request_ref,
            request=request,
        )
        manifest, candidate, attestation, source_refs, legal_principal = (
            self._validate_materials(
                request_ref,
                request,
                request_binding,
                candidate_ref,
                attestation_ref,
                case_scope=case_scope,
                run_identity_ref=run_identity_ref,
                now=now,
            )
        )
        common = {
            "schema_version": "jc/fact-gate/1.0",
            "status": "PASS",
            "request_ref": request_ref.to_dict(),
            "request_binding_ref": request_binding.to_dict(),
            "case_scope": case_scope,
            "run_identity_ref": run_identity_ref.to_dict(),
            "candidate_ref": candidate_ref.to_dict(),
        }
        source_gate_ref = self._register_json(
            kind=SOURCE_GATE_RECEIPT_KIND,
            payload={
                **common,
                "gate": "source",
                "source_bundle_ref": request.source_bundle_ref.to_dict(),
                "source_refs": [reference.to_dict() for reference in source_refs],
            },
        )
        interpretation_gate_ref = self._register_json(
            kind=INTERPRETATION_GATE_RECEIPT_KIND,
            payload={
                **common,
                "gate": "interpretation",
                "proposition_ref": candidate.proposition_ref.to_dict(),
                "value_kind": candidate.value_kind,
                "value_ref": candidate.value_ref.to_dict(),
                "interpretation_version": attestation.interpretation_version,
            },
        )
        fact_gate_ref = self._register_json(
            kind=FACT_GATE_RECEIPT_KIND,
            payload={
                **common,
                "gate": "fact",
                "manifest_ref": request.evidence_manifest_ref.to_dict(),
                "attestation_ref": attestation_ref.to_dict(),
                "evidence_refs": [reference.to_dict() for reference in candidate.evidence_refs],
            },
        )
        fact_payload = {
            "schema_version": "jc/admitted-fact/1.0",
            "status": "ADMITTED",
            "request_ref": request_ref.to_dict(),
            "request_binding_ref": request_binding.to_dict(),
            "case_scope": case_scope,
            "run_identity_ref": run_identity_ref.to_dict(),
            "manifest_ref": request.evidence_manifest_ref.to_dict(),
            "candidate_ref": candidate_ref.to_dict(),
            "proposition_ref": candidate.proposition_ref.to_dict(),
            "value_kind": candidate.value_kind,
            "value_ref": candidate.value_ref.to_dict(),
            "source_refs": [reference.to_dict() for reference in source_refs],
            "evidence_refs": [reference.to_dict() for reference in candidate.evidence_refs],
            "attestation_ref": attestation_ref.to_dict(),
        }
        fact_ref = self._register_json(kind=ADMITTED_FACT_KIND, payload=fact_payload)
        receipt_body = {
            "receipt_id": f"fact-admission-{fact_ref.digest.hex}",
            "request_ref": request_ref.to_dict(),
            "case_scope": case_scope,
            "run_identity_ref": run_identity_ref.to_dict(),
            "subject_digest": str(fact_ref.digest),
            "status": "ADMITTED",
            "source_gate_receipt_ref": source_gate_ref.to_dict(),
            "interpretation_gate_receipt_ref": interpretation_gate_ref.to_dict(),
            "fact_gate_receipt_ref": fact_gate_ref.to_dict(),
            "attestation_ref": attestation_ref.to_dict(),
            "fact_ref": fact_ref.to_dict(),
            "issued_at": now.to_dict(),
            "issuer": self._receipt_issuer,
        }
        receipt_evidence = self._receipt_evidence_refs(
            request_ref=request_ref,
            request_binding_ref=request_binding,
            manifest_ref=request.evidence_manifest_ref,
            candidate_ref=candidate_ref,
            attestation_ref=attestation_ref,
            fact_ref=fact_ref,
            source_gate_ref=source_gate_ref,
            interpretation_gate_ref=interpretation_gate_ref,
            fact_gate_ref=fact_gate_ref,
            source_refs=source_refs,
            evidence_refs=candidate.evidence_refs,
            replay_policy_ref=self._trust.policy.replay_policy_ref,
        )
        signature = self._receipt_signer(
            fact_ref.digest,
            digest_value(receipt_body),
            receipt_evidence,
            run_identity_ref,
            now,
        )
        if type(signature) is not SignatureEnvelopeV4:
            _fail("FACT_RECEIPT_SIGNATURE", "receipt signer returned the wrong contract")
        if (
            signature.issuer != self._receipt_issuer
            or signature.run_identity_ref != run_identity_ref
            or signature.issued_at != now
            or signature.expires_at is None
            or attestation.expires_at is None
            or attestation.expires_at < signature.expires_at
            or signature.evidence_refs != receipt_evidence
        ):
            _fail("FACT_RECEIPT_ENVELOPE", "receipt signature does not bind generated context")
        self._trust.verify(
            signature,
            expected_subject_digest=fact_ref.digest,
            expected_payload_digest=digest_value(receipt_body),
            required_role="service_signer",
            required_scope="service-certificate",
            required_artifact_kind="service-certificate",
            expected_status="APPROVED",
            now=now,
            separation_from_principals=(legal_principal,),
        )
        receipt = FactAdmissionReceiptV4.from_dict({**receipt_body, "signature": signature.to_dict()})
        receipt_ref = self._register_json(
            kind=FACT_ADMISSION_RECEIPT_KIND,
            payload=receipt.to_dict(),
        )
        self._candidate_ids[candidate.candidate_id] = candidate_ref
        self._attestation_ids[attestation.attestation_id] = attestation_ref
        self._admissions[key] = receipt_ref
        self._receipt_contexts[receipt_ref] = (
            request_ref,
            case_scope,
            run_identity_ref,
            fact_ref,
        )
        return receipt_ref

    def verify_receipt(
        self,
        receipt_ref: ContentRefV4,
        *,
        request_ref: ContentRefV4,
        case_scope: str,
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> ContentRefV4:
        """Verify exact generated artifacts and the service certificate on a receipt."""

        if (
            type(receipt_ref) is not ContentRefV4
            or type(request_ref) is not ContentRefV4
            or request_ref.kind != CASE_REQUEST_KIND
            or type(case_scope) is not str
            or not case_scope
            or type(run_identity_ref) is not ContentRefV4
            or run_identity_ref.kind != RUN_IDENTITY_KIND
            or type(now) is not CanonicalTimeV4
        ):
            _fail("FACT_INPUT_TYPE", "receipt verification context is invalid")
        receipt_value = self._resolve_contract(
            receipt_ref,
            kind=FACT_ADMISSION_RECEIPT_KIND,
            scope=FACT_ADMISSION_SCOPE,
            contract=FactAdmissionReceiptV4,
        )
        if type(receipt_value) is not FactAdmissionReceiptV4:
            _fail("FACT_CONTRACT_TYPE", "resolved receipt has the wrong type")
        receipt = receipt_value
        if (
            receipt.request_ref != request_ref
            or receipt.case_scope != case_scope
            or receipt.run_identity_ref != run_identity_ref
        ):
            _fail("FACT_RECEIPT_SCOPE", "receipt is reused across request, case, or run")
        if (
            receipt.status != "ADMITTED"
            or receipt.issuer != self._receipt_issuer
            or receipt.fact_ref.kind != ADMITTED_FACT_KIND
            or receipt.subject_digest != receipt.fact_ref.digest
            or receipt.receipt_id != f"fact-admission-{receipt.fact_ref.digest.hex}"
        ):
            _fail("FACT_RECEIPT_BINDING", "receipt identity or status is not service-derived")
        fact = self._resolve_json(
            receipt.fact_ref,
            kind=ADMITTED_FACT_KIND,
            scope=FACT_ADMISSION_SCOPE,
        )
        if set(fact) != {
            "schema_version", "status", "request_ref", "request_binding_ref",
            "case_scope", "run_identity_ref", "manifest_ref", "candidate_ref",
            "proposition_ref", "value_kind", "value_ref", "source_refs",
            "evidence_refs", "attestation_ref",
        } or fact.get("schema_version") != "jc/admitted-fact/1.0" or fact.get("status") != "ADMITTED":
            _fail("FACT_ARTIFACT_SHAPE", "admitted fact has the wrong canonical shape")
        if (
            self._wire_ref(fact.get("request_ref"), "request_ref") != request_ref
            or fact.get("case_scope") != case_scope
            or self._wire_ref(fact.get("run_identity_ref"), "run_identity_ref")
            != run_identity_ref
            or self._wire_ref(fact.get("attestation_ref"), "attestation_ref")
            != receipt.attestation_ref
        ):
            _fail("FACT_RECEIPT_BINDING", "admitted fact context differs from receipt")
        request_binding = self._wire_ref(fact.get("request_binding_ref"), "request_binding_ref")
        manifest_ref = self._wire_ref(fact.get("manifest_ref"), "manifest_ref")
        candidate_ref = self._wire_ref(fact.get("candidate_ref"), "candidate_ref")
        source_refs = self._wire_refs(fact.get("source_refs"), "source_refs")
        evidence_refs = self._wire_refs(fact.get("evidence_refs"), "evidence_refs")
        request_value = self._resolve_contract(
            request_ref,
            kind=CASE_REQUEST_KIND,
            scope=CASE_REQUEST_SCOPE,
            contract=CaseRequestV4,
        )
        if type(request_value) is not CaseRequestV4:
            _fail("FACT_CONTRACT_TYPE", "resolved request has the wrong type")
        request = request_value
        if self._bind_request_projection(request) != request_binding:
            _fail("FACT_REQUEST_BINDING", "receipt uses another request projection")
        self._validate_run_identity(
            run_identity_ref,
            request_ref=request_ref,
            request=request,
        )
        manifest, candidate, attestation, verified_sources, legal_principal = (
            self._validate_materials(
                request_ref,
                request,
                request_binding,
                candidate_ref,
                receipt.attestation_ref,
                case_scope=case_scope,
                run_identity_ref=run_identity_ref,
                now=now,
            )
        )
        expected_fact = {
            "schema_version": "jc/admitted-fact/1.0",
            "status": "ADMITTED",
            "request_ref": request_ref.to_dict(),
            "request_binding_ref": request_binding.to_dict(),
            "case_scope": case_scope,
            "run_identity_ref": run_identity_ref.to_dict(),
            "manifest_ref": request.evidence_manifest_ref.to_dict(),
            "candidate_ref": candidate_ref.to_dict(),
            "proposition_ref": candidate.proposition_ref.to_dict(),
            "value_kind": candidate.value_kind,
            "value_ref": candidate.value_ref.to_dict(),
            "source_refs": [reference.to_dict() for reference in verified_sources],
            "evidence_refs": [reference.to_dict() for reference in candidate.evidence_refs],
            "attestation_ref": receipt.attestation_ref.to_dict(),
        }
        if fact != expected_fact or manifest_ref != request.evidence_manifest_ref:
            _fail("FACT_RECEIPT_BINDING", "admitted fact differs from verified materials")
        if source_refs != verified_sources or evidence_refs != candidate.evidence_refs:
            _fail("FACT_RECEIPT_BINDING", "admitted fact source or evidence refs differ")
        observed_gates: dict[str, dict[str, object]] = {}
        gate_expectations = (
            (receipt.source_gate_receipt_ref, SOURCE_GATE_RECEIPT_KIND, "source"),
            (
                receipt.interpretation_gate_receipt_ref,
                INTERPRETATION_GATE_RECEIPT_KIND,
                "interpretation",
            ),
            (receipt.fact_gate_receipt_ref, FACT_GATE_RECEIPT_KIND, "fact"),
        )
        for gate_ref, kind, gate_name in gate_expectations:
            gate = self._resolve_json(gate_ref, kind=kind, scope=FACT_ADMISSION_SCOPE)
            observed_gates[gate_name] = gate
            if (
                gate.get("schema_version") != "jc/fact-gate/1.0"
                or gate.get("gate") != gate_name
                or gate.get("status") != "PASS"
                or self._wire_ref(gate.get("request_ref"), "request_ref") != request_ref
                or self._wire_ref(gate.get("request_binding_ref"), "request_binding_ref")
                != request_binding
                or gate.get("case_scope") != case_scope
                or self._wire_ref(gate.get("run_identity_ref"), "run_identity_ref")
                != run_identity_ref
                or self._wire_ref(gate.get("candidate_ref"), "candidate_ref")
                != candidate_ref
            ):
                _fail("FACT_GATE_BINDING", f"{gate_name} gate is not exact PASS evidence")
        common = {
            "schema_version": "jc/fact-gate/1.0",
            "status": "PASS",
            "request_ref": request_ref.to_dict(),
            "request_binding_ref": request_binding.to_dict(),
            "case_scope": case_scope,
            "run_identity_ref": run_identity_ref.to_dict(),
            "candidate_ref": candidate_ref.to_dict(),
        }
        expected_gates = {
            "source": {
                **common,
                "gate": "source",
                "source_bundle_ref": request.source_bundle_ref.to_dict(),
                "source_refs": [reference.to_dict() for reference in verified_sources],
            },
            "interpretation": {
                **common,
                "gate": "interpretation",
                "proposition_ref": candidate.proposition_ref.to_dict(),
                "value_kind": candidate.value_kind,
                "value_ref": candidate.value_ref.to_dict(),
                "interpretation_version": attestation.interpretation_version,
            },
            "fact": {
                **common,
                "gate": "fact",
                "manifest_ref": request.evidence_manifest_ref.to_dict(),
                "attestation_ref": receipt.attestation_ref.to_dict(),
                "evidence_refs": [
                    reference.to_dict() for reference in candidate.evidence_refs
                ],
            },
        }
        if observed_gates != expected_gates:
            _fail("FACT_GATE_BINDING", "one or more gate artifacts differ from verified inputs")
        expected_evidence = self._receipt_evidence_refs(
            request_ref=request_ref,
            request_binding_ref=request_binding,
            manifest_ref=manifest_ref,
            candidate_ref=candidate_ref,
            attestation_ref=receipt.attestation_ref,
            fact_ref=receipt.fact_ref,
            source_gate_ref=receipt.source_gate_receipt_ref,
            interpretation_gate_ref=receipt.interpretation_gate_receipt_ref,
            fact_gate_ref=receipt.fact_gate_receipt_ref,
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            replay_policy_ref=self._trust.policy.replay_policy_ref,
        )
        if (
            receipt.signature.issuer != self._receipt_issuer
            or receipt.signature.run_identity_ref != run_identity_ref
            or receipt.signature.issued_at != receipt.issued_at
            or receipt.signature.evidence_refs != expected_evidence
        ):
            _fail("FACT_RECEIPT_ENVELOPE", "receipt signature evidence or context differs")
        if now < receipt.signature.issued_at or (
            receipt.signature.expires_at is None or not now < receipt.signature.expires_at
        ):
            _fail("FACT_RECEIPT_EXPIRED", "receipt signature is not active")
        if attestation.expires_at is None or attestation.expires_at < receipt.signature.expires_at:
            _fail("FACT_RECEIPT_EXPIRY", "receipt outlives its legal attestation")
        if receipt.issued_at < attestation.issued_at:
            _fail("FACT_RECEIPT_TIME", "receipt predates its legal attestation")
        cached = self._receipt_contexts.get(receipt_ref)
        expected_context = (request_ref, case_scope, run_identity_ref, receipt.fact_ref)
        if cached is not None:
            if cached != expected_context:
                _fail("FACT_RECEIPT_SCOPE", "cached receipt context differs")
        verification_trust = (
            self._trust._fresh_without_replay()
            if cached is not None
            else self._trust
        )
        verification_trust.verify(
            receipt.signature,
            expected_subject_digest=receipt.fact_ref.digest,
            expected_payload_digest=digest_value(receipt.signature_body()),
            required_role="service_signer",
            required_scope="service-certificate",
            required_artifact_kind="service-certificate",
            expected_status="APPROVED",
            now=now,
            separation_from_principals=(legal_principal,),
        )
        if cached is not None:
            return receipt.fact_ref
        self._receipt_contexts[receipt_ref] = expected_context
        return receipt.fact_ref
