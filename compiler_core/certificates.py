"""Bundle-bound V4 certificate issuance and verification.

The issuer is callable only with a context sealed by ``audit_bundle`` after the
bundle core and independent checker receipts have been verified.  Certificate
bodies are deterministic; only the outer service signature is operational.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from weakref import ReferenceType, ref

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    BackendInvocationV4,
    CanonicalTimeV4,
    CaseRequestV4,
    CertificateEnvelopeV4,
    CertificateKindV4,
    CheckerReceiptV4,
    CompletenessStateV4,
    ConflictCertificateV4,
    ContentRefV4,
    ContractV4Error,
    DecisionStatusV4,
    EvidenceManifestV4,
    ExecutionStatusV4,
    FactAdmissionReceiptV4,
    FormalCertificateV4,
    PackManifestV4,
    PackSignatureV4,
    ProofReceiptV4,
    RuleV4,
    RunIdentityV4,
    SemanticResultV4,
    SignatureEnvelopeV4,
    SolverReceiptV4,
    SourceBundleV4,
    TranslationReceiptV4,
)
from compiler_core.fact_admission import case_request_binding_ref
from compiler_core.rule_packs import RulePackVerifierV4
from compiler_core.source_service import SourceServiceV4
from compiler_core.trust import TrustVerifierV4


SERVICE_ROLE_V4 = "service_signer"
SERVICE_SCOPE_V4 = "service-certificate"
SERVICE_KIND_V4 = "service-certificate"

_CONTEXT_SEAL = object()
_CONTEXTS_LOCK = Lock()
_SEALED_CONTEXTS: dict[int, ReferenceType[CertificateContextV4]] = {}


class CertificateV4Error(RuntimeError):
    """Stable fail-closed certificate error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise CertificateV4Error(code, detail)


def _ref_key(reference: ContentRefV4) -> tuple[str, str]:
    return reference.kind, reference.digest.hex


def _sorted_refs(values: tuple[ContentRefV4, ...], label: str) -> tuple[ContentRefV4, ...]:
    if any(type(item) is not ContentRefV4 for item in values):
        _fail("CERTIFICATE_REFERENCE", f"{label} contains a non-V4 reference")
    if len(values) != len(set(values)):
        _fail("CERTIFICATE_RECEIPT_REPLAY", f"{label} contains duplicate references")
    return tuple(sorted(values, key=_ref_key))


@dataclass(frozen=True, slots=True)
class CertificateArtifactV4:
    """Immutable artifact view copied from an already verified bundle core."""

    content_ref: ContentRefV4
    artifact_kind: str
    media_type: str
    scope: str
    content: bytes

    def __post_init__(self) -> None:
        if (
            type(self.content_ref) is not ContentRefV4
            or type(self.artifact_kind) is not str
            or not self.artifact_kind
            or type(self.media_type) is not str
            or not self.media_type
            or type(self.scope) is not str
            or not self.scope
            or type(self.content) is not bytes
        ):
            _fail("CERTIFICATE_ARTIFACT", "certificate artifact view is malformed")
        if self.content_ref.kind != self.artifact_kind:
            _fail("CERTIFICATE_ARTIFACT_KIND", "artifact kind differs from its reference")
        if DigestV4.from_bytes(self.content) != self.content_ref.digest:
            _fail("CERTIFICATE_ARTIFACT_DIGEST", "artifact bytes differ from their reference")


@dataclass(frozen=True, slots=True, weakref_slot=True)
class CertificateContextV4:
    """Internal immutable context; construction is sealed to the audit writer."""

    _seal: object
    request: CaseRequestV4
    run_identity: RunIdentityV4
    result: SemanticResultV4
    bundle_core_digest: DigestV4
    artifacts: tuple[CertificateArtifactV4, ...]
    verified_checker_receipt_refs: tuple[ContentRefV4, ...]
    now: CanonicalTimeV4

    def __post_init__(self) -> None:
        if self._seal is not _CONTEXT_SEAL:
            _fail("CERTIFICATE_CONTEXT_AUTHORITY", "context was not sealed by audit verification")
        if (
            type(self.request) is not CaseRequestV4
            or type(self.run_identity) is not RunIdentityV4
            or type(self.result) is not SemanticResultV4
            or type(self.bundle_core_digest) is not DigestV4
            or type(self.artifacts) is not tuple
            or any(type(item) is not CertificateArtifactV4 for item in self.artifacts)
            or type(self.verified_checker_receipt_refs) is not tuple
            or type(self.now) is not CanonicalTimeV4
        ):
            _fail("CERTIFICATE_CONTEXT", "certificate context uses non-V4 values")
        references = tuple(item.content_ref for item in self.artifacts)
        if len(references) != len(set(references)):
            _fail("CERTIFICATE_ARTIFACT_COLLISION", "artifact references are not unique")
        if tuple(sorted(self.artifacts, key=lambda item: _ref_key(item.content_ref))) != self.artifacts:
            _fail("CERTIFICATE_ARTIFACT_ORDER", "artifact views are not canonical")
        _sorted_refs(self.verified_checker_receipt_refs, "checker receipt refs")

    @property
    def run_identity_ref(self) -> ContentRefV4:
        return ContentRefV4("run-identity", self.run_identity.canonical_digest())

    @property
    def request_ref(self) -> ContentRefV4:
        return self.run_identity.request_ref

    @property
    def result_ref(self) -> ContentRefV4:
        return ContentRefV4("semantic-result", self.result.canonical_digest())

    @property
    def artifact_refs(self) -> tuple[ContentRefV4, ...]:
        return tuple(item.content_ref for item in self.artifacts)


def _verified_certificate_context(
    *,
    request: CaseRequestV4,
    run_identity: RunIdentityV4,
    result: SemanticResultV4,
    bundle_core_digest: DigestV4,
    artifacts: tuple[CertificateArtifactV4, ...],
    verified_checker_receipt_refs: tuple[ContentRefV4, ...],
    now: CanonicalTimeV4,
) -> CertificateContextV4:
    """Create a context only after the audit core has independently verified it."""

    context = CertificateContextV4(
        _CONTEXT_SEAL,
        request,
        run_identity,
        result,
        bundle_core_digest,
        tuple(sorted(artifacts, key=lambda item: _ref_key(item.content_ref))),
        _sorted_refs(verified_checker_receipt_refs, "checker receipt refs"),
        now,
    )
    key = id(context)

    def discard(reference: ReferenceType[CertificateContextV4]) -> None:
        with _CONTEXTS_LOCK:
            if _SEALED_CONTEXTS.get(key) is reference:
                del _SEALED_CONTEXTS[key]

    reference = ref(context, discard)
    with _CONTEXTS_LOCK:
        _SEALED_CONTEXTS[key] = reference
    return context


class _Resolver:
    def __init__(self, artifacts: tuple[CertificateArtifactV4, ...]) -> None:
        self._by_ref = {item.content_ref: item for item in artifacts}

    def artifact(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str | None = None,
    ) -> CertificateArtifactV4:
        if type(reference) is not ContentRefV4 or reference.kind != kind:
            _fail("CERTIFICATE_REFERENCE_KIND", f"expected {kind}")
        artifact = self._by_ref.get(reference)
        if artifact is None:
            _fail("CERTIFICATE_RECEIPT_MISSING", f"sealed artifact is missing: {kind}")
        if artifact.artifact_kind != kind or (scope is not None and artifact.scope != scope):
            _fail("CERTIFICATE_ARTIFACT_SCOPE", f"sealed artifact scope differs: {kind}")
        return artifact

    def document(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str | None = None,
    ) -> dict[str, object]:
        artifact = self.artifact(reference, kind=kind, scope=scope)
        if artifact.media_type != "application/json":
            _fail("CERTIFICATE_ARTIFACT_MEDIA", f"{kind} is not canonical JSON")
        try:
            value = parse_json_document(artifact.content)
        except (TypeError, ValueError) as exc:
            raise CertificateV4Error("CERTIFICATE_ARTIFACT_JSON", f"{kind} is invalid") from exc
        if type(value) is not dict or canonical_bytes(value) != artifact.content:
            _fail("CERTIFICATE_ARTIFACT_JSON", f"{kind} is not canonical JSON")
        return value

    def contract(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        contract: type,
        scope: str | None = None,
        self_digest_field: str | None = None,
    ) -> object:
        value = self.document(reference, kind=kind, scope=scope)
        if self_digest_field is not None:
            if self_digest_field in value:
                _fail("CERTIFICATE_SELF_DIGEST", f"{kind} stores its recursive digest")
            value = {**value, self_digest_field: str(reference.digest)}
        try:
            decoded = contract.from_dict(value)
        except (ContractV4Error, TypeError, ValueError) as exc:
            raise CertificateV4Error(
                "CERTIFICATE_RECEIPT_CONTRACT", f"{kind} violates {contract.__name__}"
            ) from exc
        if self_digest_field is None and decoded.canonical_bytes() != canonical_bytes(value):
            _fail("CERTIFICATE_RECEIPT_CONTRACT", f"{kind} bytes differ after decoding")
        return decoded

    def refs(self, kind: str) -> tuple[ContentRefV4, ...]:
        return _sorted_refs(
            tuple(item.content_ref for item in self._by_ref.values() if item.artifact_kind == kind),
            f"{kind} refs",
        )


def _sealed_artifact_resolver(context: CertificateContextV4) -> ArtifactResolverV4:
    resolver = ArtifactResolverV4(
        max_artifact_bytes=max((len(item.content) for item in context.artifacts), default=1)
    )
    for index, item in enumerate(context.artifacts):
        resolver.register_bytes(
            artifact_id=f"certificate-sealed-{index:06d}",
            content_ref=item.content_ref,
            artifact_kind=item.artifact_kind,
            media_type=item.media_type,
            scope=item.scope,
            content=item.content,
        )
    return resolver


@dataclass(frozen=True, slots=True)
class _ReceiptChain:
    source: tuple[ContentRefV4, ...]
    evidence: tuple[ContentRefV4, ...]
    fact: tuple[ContentRefV4, ...]
    rule: tuple[ContentRefV4, ...]
    translation: tuple[ContentRefV4, ...]
    solver: tuple[ContentRefV4, ...]
    proof: tuple[ContentRefV4, ...]
    checker: tuple[ContentRefV4, ...]

    @property
    def all(self) -> tuple[ContentRefV4, ...]:
        return _sorted_refs(
            (
                *self.source,
                *self.evidence,
                *self.fact,
                *self.rule,
                *self.translation,
                *self.solver,
                *self.proof,
                *self.checker,
            ),
            "certificate receipt chain",
        )


def _unsigned_envelope(
    kind: CertificateKindV4,
    certificate: FormalCertificateV4 | ConflictCertificateV4,
) -> CertificateEnvelopeV4:
    return CertificateEnvelopeV4(
        kind,
        certificate if kind is CertificateKindV4.FORMAL_VERIFIED else None,
        certificate if kind is CertificateKindV4.CONFLICT_VERIFIED else None,
        None,
    )


class CertificateVerifierV4:
    """Recompute certificate gates from the sealed bundle context and current trust."""

    def __init__(
        self,
        trust: TrustVerifierV4,
        *,
        current_engine_build_digest: DigestV4,
    ) -> None:
        if type(trust) is not TrustVerifierV4 or type(current_engine_build_digest) is not DigestV4:
            _fail("CERTIFICATE_VERIFIER_CONFIG", "verifier requires exact trust and build identity")
        self._trust = trust
        self._current_engine_build_digest = current_engine_build_digest

    @staticmethod
    def _context(context: CertificateContextV4) -> CertificateContextV4:
        with _CONTEXTS_LOCK:
            registered = _SEALED_CONTEXTS.get(id(context))
            sealed = registered is not None and registered() is context
        if (
            type(context) is not CertificateContextV4
            or context._seal is not _CONTEXT_SEAL
            or not sealed
        ):
            _fail("CERTIFICATE_CONTEXT_AUTHORITY", "issuer requires an audit-sealed context")
        return context

    @staticmethod
    def _verify_service_receipt(
        trust: TrustVerifierV4,
        receipt: object,
        *,
        subject_digest: DigestV4,
        run_ref: ContentRefV4 | None,
        now: CanonicalTimeV4,
    ) -> None:
        signature = getattr(receipt, "signature", None)
        if type(signature) is not SignatureEnvelopeV4:
            _fail("CERTIFICATE_RECEIPT_SIGNATURE", "receipt has no V4 service signature")
        if signature.run_identity_ref != run_ref:
            _fail("CERTIFICATE_RECEIPT_RUN", "receipt signature binds the wrong run")
        try:
            trust.verify(
                signature,
                expected_subject_digest=subject_digest,
                expected_payload_digest=digest_value(receipt.signature_body()),
                required_role=SERVICE_ROLE_V4,
                required_scope=SERVICE_SCOPE_V4,
                required_artifact_kind=SERVICE_KIND_V4,
                expected_status="APPROVED",
                now=now,
                separation_from_principals=(),
            )
        except ContractV4Error as exc:
            raise CertificateV4Error(
                "CERTIFICATE_RECEIPT_SIGNATURE", f"receipt signature failed: {exc.code}"
            ) from exc

    def _chain(
        self,
        context: CertificateContextV4,
        resolver: _Resolver,
        trust: TrustVerifierV4,
    ) -> _ReceiptChain:
        run = context.run_identity
        result = context.result
        run_ref = ContentRefV4("run-identity", run.canonical_digest())

        pack_signature = resolver.contract(
            run.rule_pack_ref,
            kind="pack-signature",
            scope="rule-pack",
            contract=PackSignatureV4,
        )
        if type(pack_signature) is not PackSignatureV4:
            _fail("CERTIFICATE_PACK", "run does not bind a V4 pack signature")
        manifest = resolver.contract(
            pack_signature.manifest_ref,
            kind="pack-manifest",
            scope="rule-pack",
            contract=PackManifestV4,
            self_digest_field="manifest_digest",
        )
        if type(manifest) is not PackManifestV4:
            _fail("CERTIFICATE_PACK", "pack manifest has the wrong type")
        sealed_resolver = _sealed_artifact_resolver(context)
        try:
            verified_pack = RulePackVerifierV4(
                sealed_resolver,
                SourceServiceV4(sealed_resolver, trust),
                trust,
                expected_engine_api=manifest.engine_api,
                expected_compiler_build_digest=run.engine_build_digest,
                expected_source_tree_digest=manifest.source_tree_digest,
                expected_schema_digest=manifest.schema_digest,
            ).verify(run.rule_pack_ref, now=context.now)
        except ContractV4Error as exc:
            raise CertificateV4Error(
                "CERTIFICATE_PACK_VERIFY", f"sealed pack verification failed: {exc.code}"
            ) from exc
        if (
            verified_pack.manifest_ref != pack_signature.manifest_ref
            or verified_pack.manifest != manifest
            or manifest.compiler_build_digest != run.engine_build_digest
            or manifest.trust_policy_ref != run.trust_policy_ref
        ):
            _fail("CERTIFICATE_PACK", "verified pack differs from run, build, or trust")
        verified_rules = {
            ContentRefV4("rule-v4", rule.rule_digest): rule
            for rule in verified_pack.rules
        }

        source_bundle = resolver.contract(
            run.source_bundle_ref,
            kind="source-bundle",
            scope="source-path",
            contract=SourceBundleV4,
            self_digest_field="bundle_digest",
        )
        if type(source_bundle) is not SourceBundleV4 or not source_bundle.snapshots:
            _fail("CERTIFICATE_SOURCE", "formal result requires a sealed source bundle")
        snapshot_refs: list[ContentRefV4] = []
        source_receipts: list[ContentRefV4] = []
        for snapshot in source_bundle.snapshots:
            snapshot_ref = ContentRefV4("source-snapshot", snapshot.canonical_digest())
            snapshot_artifact = resolver.artifact(
                snapshot_ref, kind="source-snapshot", scope="source-authenticity"
            )
            if snapshot_artifact.content != snapshot.canonical_bytes():
                _fail("CERTIFICATE_SOURCE", "source bundle and snapshot bytes differ")
            resolver.artifact(
                snapshot.authenticity_receipt_ref,
                kind="source-authenticity-receipt",
                scope="source-authenticity",
            )
            snapshot_refs.append(snapshot_ref)
            source_receipts.append(snapshot.authenticity_receipt_ref)
        if not set(snapshot_refs) <= set(manifest.source_refs):
            _fail("CERTIFICATE_SOURCE", "run sources are outside the verified pack")

        evidence = resolver.contract(
            run.evidence_manifest_ref,
            kind="evidence-manifest",
            scope="case-evidence",
            contract=EvidenceManifestV4,
            self_digest_field="manifest_digest",
        )
        if (
            type(evidence) is not EvidenceManifestV4
            or evidence.request_ref != case_request_binding_ref(context.request)
            or not evidence.items
        ):
            _fail("CERTIFICATE_EVIDENCE", "evidence manifest lacks its request projection")

        fact_receipts: list[ContentRefV4] = []
        fact_by_ref: dict[ContentRefV4, tuple[ContentRefV4, FactAdmissionReceiptV4]] = {}
        for reference in resolver.refs("fact-admission-receipt"):
            receipt = resolver.contract(
                reference,
                kind="fact-admission-receipt",
                scope="fact-admission",
                contract=FactAdmissionReceiptV4,
            )
            if (
                type(receipt) is not FactAdmissionReceiptV4
                or receipt.fact_ref not in result.admitted_fact_refs
            ):
                _fail("CERTIFICATE_RECEIPT_EXTRA", "bundle contains an unclaimed fact receipt")
            if receipt.fact_ref in fact_by_ref:
                _fail("CERTIFICATE_RECEIPT_REPLAY", "fact has multiple admission receipts")
            fact_by_ref[receipt.fact_ref] = (reference, receipt)
        if set(fact_by_ref) != set(result.admitted_fact_refs) or not fact_by_ref:
            _fail("CERTIFICATE_FACT_RECEIPT", "admitted facts lack an exact receipt chain")
        for fact_ref in sorted(fact_by_ref, key=_ref_key):
            reference, receipt = fact_by_ref[fact_ref]
            if (
                receipt.status != "ADMITTED"
                or receipt.request_ref != run.request_ref
                or receipt.run_identity_ref != run_ref
                or receipt.attestation_ref not in run.fact_attestation_refs
                or receipt.subject_digest != fact_ref.digest
                or not {
                    run.evidence_manifest_ref,
                    evidence.request_ref,
                    receipt.attestation_ref,
                    receipt.fact_ref,
                } <= set(receipt.signature.evidence_refs)
            ):
                _fail("CERTIFICATE_FACT_RECEIPT", "fact receipt differs from the run")
            self._verify_service_receipt(
                trust,
                receipt,
                subject_digest=fact_ref.digest,
                run_ref=run_ref,
                now=context.now,
            )
            fact_receipts.append(reference)

        if (
            not set(result.applicable_rule_refs) <= set(verified_rules)
            or not set(result.applicable_rule_refs) <= set(manifest.rule_refs)
            or not result.applicable_rule_refs
        ):
            _fail("CERTIFICATE_PACK", "result rules are outside the verified pack")

        promotion_refs: list[ContentRefV4] = []
        for rule_ref in _sorted_refs(result.applicable_rule_refs, "applicable rules"):
            rule = verified_rules[rule_ref]
            if type(rule) is not RuleV4 or not rule.promotion_receipt_refs:
                _fail("CERTIFICATE_RULE_RECEIPT", "applicable rule lacks promotion receipts")
            if not set(rule.promotion_receipt_refs) <= set(manifest.receipt_refs):
                _fail("CERTIFICATE_RULE_RECEIPT", "promotion receipt is outside the pack manifest")
            promotion_refs.extend(rule.promotion_receipt_refs)
        promotion_tuple = _sorted_refs(tuple(promotion_refs), "rule promotion receipts")

        claim_facts = {reference for claim in result.claims for reference in claim.fact_refs}
        claim_rules = {reference for claim in result.claims for reference in claim.rule_refs}
        claim_sources = {reference for claim in result.claims for reference in claim.source_refs}
        claim_arguments = {
            reference for claim in result.claims for reference in claim.argument_refs
        }
        if (
            any(
                not claim.fact_refs
                or not claim.rule_refs
                or not claim.source_refs
                or not claim.argument_refs
                for claim in result.claims
            )
            or claim_facts != set(result.admitted_fact_refs)
            or claim_rules != set(result.applicable_rule_refs)
            or not claim_sources <= set(snapshot_refs)
            or claim_arguments != set(result.argument_refs)
        ):
            _fail("CERTIFICATE_CLAIM_BINDING", "claims differ from admitted formal inputs")

        invocation_ref = result.runtime_profile.backend_invocation_ref
        solver_ref = result.runtime_profile.backend_receipt_ref
        if invocation_ref is None or solver_ref is None:
            _fail("CERTIFICATE_BACKEND_RECEIPT", "formal result lacks backend receipts")
        invocation = resolver.contract(
            invocation_ref,
            kind="backend-invocation-v4",
            scope="backend",
            contract=BackendInvocationV4,
        )
        problem = resolver.document(
            invocation.ir_ref,
            kind="backend-problem-v4",
            scope="backend",
        )
        if (
            problem.get("run_identity_ref") != run_ref.to_dict()
            or problem.get("request_ref") != run.request_ref.to_dict()
            or type(problem.get("clauses")) is not list
        ):
            _fail("CERTIFICATE_BACKEND_RECEIPT", "backend problem differs from the run")
        solver = resolver.contract(
            solver_ref,
            kind="solver-receipt-v4",
            scope="backend",
            contract=SolverReceiptV4,
        )
        if (
            type(invocation) is not BackendInvocationV4
            or type(solver) is not SolverReceiptV4
            or solver.status != "COMPLETED"
            or solver.exit_status != 0
            or solver.run_identity_ref != run_ref
            or solver.invocation_ref != invocation_ref
            or solver.proof_ref is None
        ):
            _fail("CERTIFICATE_BACKEND_RECEIPT", "backend receipt is not a completed bound run")
        resolver.artifact(solver.proof_ref, kind=solver.proof_ref.kind, scope="backend")
        self._verify_service_receipt(
            trust,
            solver,
            subject_digest=solver.backend_result_ref.digest,
            run_ref=run_ref,
            now=context.now,
        )

        translation_rows: list[tuple[ContentRefV4, TranslationReceiptV4]] = []
        for reference in resolver.refs("translation-receipt"):
            receipt = resolver.contract(
                reference,
                kind="translation-receipt",
                scope="legal-ir",
                contract=TranslationReceiptV4,
            )
            if type(receipt) is TranslationReceiptV4 and receipt.run_identity_ref == run_ref:
                translation_rows.append((reference, receipt))
        selected: list[tuple[ContentRefV4, TranslationReceiptV4]] = []
        for rule_ref in result.applicable_rule_refs:
            first = [row for row in translation_rows if row[1].source_ref == rule_ref]
            if len(first) != 1 or first[0][1].hop != "RuleV4->LegalSpecV4":
                _fail("CERTIFICATE_TRANSLATION_RECEIPT", "rule-to-spec receipt is not exact")
            second = [row for row in translation_rows if row[1].source_ref == first[0][1].target_ref]
            if len(second) != 1 or second[0][1].hop != "LegalSpecV4->LegalIVLV4":
                _fail("CERTIFICATE_TRANSLATION_RECEIPT", "spec-to-IVL receipt is not exact")
            matching_clauses = [
                clause
                for clause in problem["clauses"]
                if type(clause) is dict
                and clause.get("rule_ref") == rule_ref.to_dict()
                and clause.get("ivl_ref") == second[0][1].target_ref.to_dict()
                and clause.get("translation_receipt_refs")
                == [first[0][0].to_dict(), second[0][0].to_dict()]
            ]
            if len(matching_clauses) != 1:
                _fail("CERTIFICATE_TRANSLATION_RECEIPT", "translation does not reach backend input")
            selected.extend((first[0], second[0]))
        selected_by_ref = {reference: receipt for reference, receipt in selected}
        if len(selected_by_ref) != len(selected) or set(selected_by_ref) != {
            reference for reference, _ in translation_rows
        }:
            _fail("CERTIFICATE_RECEIPT_EXTRA", "translation receipt chain has missing or extra rows")
        translation_refs = _sorted_refs(tuple(selected_by_ref), "translation receipts")
        for reference in translation_refs:
            receipt = selected_by_ref[reference]
            if (
                receipt.status != "PASS"
                or not receipt.field_coverage
                or receipt.lost_fields
                or receipt.defaulted_fields
                or receipt.unsupported_fields
            ):
                _fail("CERTIFICATE_TRANSLATION_RECEIPT", "translation is lossy or incomplete")
            self._verify_service_receipt(
                trust,
                receipt,
                subject_digest=receipt.target_ref.digest,
                run_ref=run_ref,
                now=context.now,
            )

        checker_refs = _sorted_refs(
            context.verified_checker_receipt_refs, "verified checker receipts"
        )
        claimed_checker_refs = _sorted_refs(
            tuple(reference for claim in result.claims for reference in claim.checker_receipt_refs),
            "claim checker receipts",
        )
        if not checker_refs or claimed_checker_refs != checker_refs:
            _fail("CERTIFICATE_CHECKER_RECEIPT", "claims differ from independently checked receipts")
        checker_by_ref: dict[ContentRefV4, CheckerReceiptV4] = {}
        for reference in checker_refs:
            receipt = resolver.contract(
                reference,
                kind="checker-receipt-v4",
                scope="independent-checker",
                contract=CheckerReceiptV4,
            )
            if (
                type(receipt) is not CheckerReceiptV4
                or receipt.status != "PASS"
                or receipt.run_identity_ref != run_ref
                or receipt.subject_ref != solver_ref
                or receipt.backend_result_ref != solver.backend_result_ref
            ):
                _fail("CERTIFICATE_CHECKER_RECEIPT", "checker receipt differs from backend run")
            self._verify_service_receipt(
                trust,
                receipt,
                subject_digest=receipt.subject_ref.digest,
                run_ref=run_ref,
                now=context.now,
            )
            checker_by_ref[reference] = receipt

        proof_refs = _sorted_refs(
            tuple(reference for claim in result.claims for reference in claim.proof_receipt_refs),
            "claim proof receipts",
        )
        if not proof_refs:
            _fail("CERTIFICATE_PROOF_RECEIPT", "formal or conflict result lacks proof receipts")
        claim_refs = frozenset(claim.claim_ref for claim in result.claims)
        for reference in proof_refs:
            receipt = resolver.contract(
                reference,
                kind="proof-receipt-v4",
                scope="independent-checker",
                contract=ProofReceiptV4,
            )
            checker_receipt = checker_by_ref.get(receipt.checker_receipt_ref)
            if (
                type(receipt) is not ProofReceiptV4
                or receipt.status != "PASS"
                or receipt.run_identity_ref != run_ref
                or checker_receipt is None
                or receipt.proof_ref != solver.proof_ref
                or receipt.subject_ref not in claim_refs
                or receipt.proof_build_digest != checker_receipt.checker_build_digest
                or not {
                    receipt.proof_ref,
                    receipt.checker_receipt_ref,
                } <= set(receipt.trusted_computing_base_refs)
            ):
                _fail("CERTIFICATE_PROOF_RECEIPT", "proof receipt differs from claim or checker")
            for dependency in receipt.trusted_computing_base_refs:
                resolver.artifact(dependency, kind=dependency.kind)
            self._verify_service_receipt(
                trust,
                receipt,
                subject_digest=receipt.subject_ref.digest,
                run_ref=run_ref,
                now=context.now,
            )

        chain = _ReceiptChain(
            _sorted_refs(tuple(source_receipts), "source receipts"),
            (run.evidence_manifest_ref,),
            _sorted_refs(tuple(fact_receipts), "fact receipts"),
            promotion_tuple,
            translation_refs,
            (solver_ref,),
            proof_refs,
            checker_refs,
        )
        if _sorted_refs(result.receipt_refs, "result receipt refs") != chain.all:
            _fail("CERTIFICATE_RECEIPT_EXTRA", "result receipt set differs from verified chain")
        return chain

    def _recompute(
        self,
        context: CertificateContextV4,
    ) -> tuple[
        CertificateEnvelopeV4,
        _ReceiptChain | None,
        TrustVerifierV4 | None,
    ]:
        context = self._context(context)
        request = context.request
        run = context.run_identity
        result = context.result
        run_ref = ContentRefV4("run-identity", run.canonical_digest())
        result_ref = ContentRefV4("semantic-result", result.canonical_digest())
        if (
            ContentRefV4("case-request", request.canonical_digest()) != run.request_ref
            or request.source_bundle_ref != run.source_bundle_ref
            or request.rule_pack_ref != run.rule_pack_ref
            or result.run_identity_ref != run_ref
            or result.request_ref != run.request_ref
            or run.engine_build_digest != self._current_engine_build_digest
            or result.runtime_profile.engine_build_digest != run.engine_build_digest
            or result.runtime_profile.trust_policy_ref != run.trust_policy_ref
            or run.trust_policy_ref
            != ContentRefV4("trust-policy", self._trust.policy.canonical_digest())
        ):
            _fail("CERTIFICATE_RUN_BINDING", "result, run, build, or trust identity differs")
        artifact_refs = _sorted_refs(
            tuple(item.content_ref for item in context.artifacts), "sealed artifact refs"
        )
        if not set(context.verified_checker_receipt_refs) <= set(artifact_refs):
            _fail("CERTIFICATE_BUNDLE_BINDING", "verified checker receipt is outside bundle core")

        if result.certificate_kind is CertificateKindV4.NONE:
            return (
                CertificateEnvelopeV4(CertificateKindV4.NONE, None, None, None),
                None,
                None,
            )
        if (
            result.execution_status is not ExecutionStatusV4.COMPLETED
            or result.completeness_state is not CompletenessStateV4.COMPLETE
            or result.taint_codes
            or not result.runtime_profile.formal_kernel
        ):
            _fail("CERTIFICATE_GATE", "issued certificate requires complete untainted formal execution")
        if result.certificate_kind is CertificateKindV4.FORMAL_VERIFIED:
            if result.decision_status is not DecisionStatusV4.ACCEPTED_FORMAL_RESULT:
                _fail("CERTIFICATE_DECISION", "formal certificate requires an accepted formal result")
        elif result.certificate_kind is CertificateKindV4.CONFLICT_VERIFIED:
            if result.decision_status is not DecisionStatusV4.CONFLICT_CERTIFICATE:
                _fail("CERTIFICATE_DECISION", "conflict certificate requires a conflict result")
        else:
            _fail("CERTIFICATE_KIND", "unsupported issued certificate kind")

        resolver = _Resolver(context.artifacts)
        trust = self._trust._fresh_without_replay()
        chain = self._chain(context, resolver, trust)
        claim_refs = _sorted_refs(tuple(claim.claim_ref for claim in result.claims), "claim refs")
        if result.certificate_kind is CertificateKindV4.FORMAL_VERIFIED:
            body = {
                "request_ref": run.request_ref.to_dict(),
                "result_ref": result_ref.to_dict(),
                "run_identity_ref": run_ref.to_dict(),
                "bundle_core_digest": str(context.bundle_core_digest),
                "claim_refs": [item.to_dict() for item in claim_refs],
                "source_receipt_refs": [item.to_dict() for item in chain.source],
                "evidence_receipt_refs": [item.to_dict() for item in chain.evidence],
                "fact_admission_receipt_refs": [item.to_dict() for item in chain.fact],
                "rule_promotion_receipt_refs": [item.to_dict() for item in chain.rule],
                "translation_receipt_refs": [item.to_dict() for item in chain.translation],
                "solver_receipt_refs": [item.to_dict() for item in chain.solver],
                "proof_receipt_refs": [item.to_dict() for item in chain.proof],
                "checker_receipt_refs": [item.to_dict() for item in chain.checker],
            }
            certificate = FormalCertificateV4.from_dict({
                **body, "certificate_digest": str(digest_value(body)),
            })
        else:
            body = {
                "request_ref": run.request_ref.to_dict(),
                "result_ref": result_ref.to_dict(),
                "run_identity_ref": run_ref.to_dict(),
                "bundle_core_digest": str(context.bundle_core_digest),
                "conflict_refs": [item.to_dict() for item in claim_refs],
                "argument_refs": [item.to_dict() for item in _sorted_refs(result.argument_refs, "arguments")],
                "attack_refs": [item.to_dict() for item in _sorted_refs(result.attack_refs, "attacks")],
                "exception_resolution_refs": [item.to_dict() for item in _sorted_refs(result.exception_resolution_refs, "exceptions")],
                "priority_resolution_refs": [item.to_dict() for item in _sorted_refs(result.priority_resolution_refs, "priorities")],
                "permission_resolution_refs": [item.to_dict() for item in _sorted_refs(result.permission_resolution_refs, "permissions")],
                "source_receipt_refs": [item.to_dict() for item in chain.source],
                "evidence_receipt_refs": [item.to_dict() for item in chain.evidence],
                "fact_admission_receipt_refs": [item.to_dict() for item in chain.fact],
                "rule_promotion_receipt_refs": [item.to_dict() for item in chain.rule],
                "translation_receipt_refs": [item.to_dict() for item in chain.translation],
                "solver_receipt_refs": [item.to_dict() for item in chain.solver],
                "proof_receipt_refs": [item.to_dict() for item in chain.proof],
                "checker_receipt_refs": [item.to_dict() for item in chain.checker],
            }
            certificate = ConflictCertificateV4.from_dict({
                **body, "certificate_digest": str(digest_value(body)),
            })
        return _unsigned_envelope(result.certificate_kind, certificate), chain, trust

    def verify(
        self,
        context: CertificateContextV4,
        envelope: CertificateEnvelopeV4,
    ) -> CertificateEnvelopeV4:
        if type(envelope) is not CertificateEnvelopeV4:
            _fail("CERTIFICATE_ENVELOPE", "verification requires CertificateEnvelopeV4")
        expected, chain, verified_trust = self._recompute(context)
        if chain is None:
            if envelope != expected:
                _fail("CERTIFICATE_NONE", "non-issuable result carried a certificate")
            return envelope
        if envelope.service_signature is None:
            _fail("CERTIFICATE_SIGNATURE_REQUIRED", "issued certificate lacks service signature")
        unsigned = envelope.to_dict()
        del unsigned["service_signature"]
        expected_wire = expected.to_dict()
        del expected_wire["service_signature"]
        if unsigned != expected_wire:
            _fail("CERTIFICATE_BUNDLE_MISMATCH", "certificate body differs from bundle recomputation")
        certificate = envelope.formal or envelope.conflict
        if certificate is None:
            _fail("CERTIFICATE_BODY_REQUIRED", "issued envelope lacks a certificate body")
        signature = envelope.service_signature
        if (
            signature.run_identity_ref != certificate.run_identity_ref
            or signature.evidence_refs != chain.all
        ):
            _fail("CERTIFICATE_SIGNATURE_BINDING", "service signature context differs")
        if verified_trust is None:
            _fail("CERTIFICATE_TRUST", "issued certificate lacks verified trust state")
        try:
            verified_trust.verify(
                signature,
                expected_subject_digest=certificate.certificate_digest,
                expected_payload_digest=digest_value(expected_wire),
                required_role=SERVICE_ROLE_V4,
                required_scope=SERVICE_SCOPE_V4,
                required_artifact_kind=SERVICE_KIND_V4,
                expected_status="APPROVED",
                now=context.now,
                separation_from_principals=(),
            )
        except ContractV4Error as exc:
            raise CertificateV4Error(
                "CERTIFICATE_SERVICE_SIGNATURE", f"service signature failed: {exc.code}"
            ) from exc
        return envelope


CertificateSignerV4 = Callable[
    [
        DigestV4,
        DigestV4,
        tuple[ContentRefV4, ...],
        ContentRefV4,
        CanonicalTimeV4,
    ],
    SignatureEnvelopeV4,
]


class CertificateIssuerV4:
    """Callable internal issuer; it has no public gate-map or digest issuance API."""

    def __init__(
        self,
        trust: TrustVerifierV4,
        *,
        current_engine_build_digest: DigestV4,
        signer: CertificateSignerV4,
    ) -> None:
        if not callable(signer):
            _fail("CERTIFICATE_SIGNER", "certificate signer must be callable")
        self._verifier = CertificateVerifierV4(
            trust, current_engine_build_digest=current_engine_build_digest
        )
        self._signer = signer

    def __call__(self, context: CertificateContextV4) -> CertificateEnvelopeV4:
        unsigned, chain, _ = self._verifier._recompute(context)
        certificate = unsigned.formal or unsigned.conflict
        if certificate is None or chain is None:
            _fail("CERTIFICATE_NOT_ISSUABLE", "none results never invoke certificate issuance")
        signature = self._signer(
            certificate.certificate_digest,
            digest_value({
                key: value
                for key, value in unsigned.to_dict().items()
                if key != "service_signature"
            }),
            chain.all,
            certificate.run_identity_ref,
            context.now,
        )
        if type(signature) is not SignatureEnvelopeV4:
            _fail("CERTIFICATE_SIGNER", "signer returned a non-V4 envelope")
        envelope = CertificateEnvelopeV4(
            unsigned.kind,
            unsigned.formal,
            unsigned.conflict,
            signature,
        )
        return self._verifier.verify(context, envelope)


__all__ = (
    "CertificateIssuerV4",
    "CertificateV4Error",
    "CertificateVerifierV4",
)
