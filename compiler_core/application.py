"""The sole V4 formal evaluation spine."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass

from compiler_core.argumentation import (
    ArgumentGraphV4,
    ArgumentationV4Error,
    PermissionRelationV4,
    argument_ref_v4,
    evaluate_argument_graph,
)
from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.audit_bundle import (
    AuditArtifactV4,
    AuditBundleMaterialsV4,
    AuditBundleStoreV4,
    AuditEventV4,
)
from compiler_core.backend_router import (
    BACKEND_RESULT_KIND,
    BACKEND_SCOPE,
    BackendExecutionV4,
    BackendRouterV4,
    BackendV4Error,
)
from compiler_core.backends import AAF_PROVIDER_ID, EXACT_PROVIDER_ID, HORN_PROVIDER_ID
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.certificates import CertificateIssuerV4
from compiler_core.contracts import (
    ArgumentV4,
    AttackV4,
    BranchResultV4,
    CanonicalTimeV4,
    CaseRequestV4,
    CertificateKindV4,
    ClaimResultV4,
    CompletenessStateV4,
    ContentRefV4,
    ContractV4Error,
    DecisionStatusV4,
    ErrorV4,
    EvaluationEnvelopeV4,
    EvidenceManifestV4,
    ExecutionStatusV4,
    FactAttestationV4,
    FactCandidateV4,
    InterruptionStateV4,
    MissingFactRequirementV4,
    PriorityEdgeV4,
    ProofReceiptV4,
    ResourceLimitsV4,
    ReviewStateV4,
    RuleV4,
    RunIdentityV4,
    RuntimeProfileV4,
    SemanticResultV4,
    SignatureEnvelopeV4,
    SourceBundleV4,
    TransportOutcomeV4,
)
from compiler_core.fact_admission import (
    CASE_EVIDENCE_SCOPE,
    CASE_REQUEST_KIND,
    CASE_REQUEST_SCOPE,
    EVIDENCE_MANIFEST_KIND,
    FACT_ADMISSION_SCOPE,
    FACT_ATTESTATION_KIND,
    FACT_CANDIDATE_KIND,
    FACT_PROPOSITION_KIND,
    LEGAL_APPROVAL_SCOPE,
    RUN_IDENTITY_KIND,
    RUN_IDENTITY_SCOPE,
    FactAdmissionServiceV4,
    case_request_binding_ref,
)
from compiler_core.independent_checker import (
    ARGUMENT_GRAPH_KIND,
    CHECKER_SCOPE,
    CheckerExecutionV4,
    IndependentCheckerV4,
    IndependentCheckerV4Error,
)
from compiler_core.legal_ir import LegalIRCompilationV4, LegalIRCompilerV4
from compiler_core.rule_packs import (
    JSON_MEDIA_TYPE,
    PACK_CONFIG_KIND,
    RULE_COMPONENT_SCOPE,
    RULE_KIND,
    RULE_PACK_SCOPE,
    RULE_PREMISE_KIND,
    RulePackVerifierV4,
    VerifiedRulePackV4,
)
from compiler_core.source_service import (
    SOURCE_BUNDLE_KIND,
    SourceServiceV4,
    source_snapshot_ref,
)
from compiler_core.trust import TrustVerifierV4


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


class ApplicationV4Error(RuntimeError):
    """Stable error for a request that cannot reach the typed-result boundary."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class _Failure:
    stage: str
    code: str


@dataclass(frozen=True, slots=True)
class _FactState:
    receipt_refs: tuple[ContentRefV4, ...]
    admitted_refs: tuple[ContentRefV4, ...]
    rejected_refs: tuple[ContentRefV4, ...]
    observed: tuple[tuple[str, ContentRefV4], ...]
    unresolved_refs: tuple[ContentRefV4, ...]
    release_condition_refs: tuple[ContentRefV4, ...]
    hypothetical: bool
    review: bool


@dataclass(frozen=True, slots=True)
class _ArgumentOutcome:
    state: str
    labels: tuple[tuple[ContentRefV4, str, tuple[ContentRefV4, ...]], ...]
    argument_refs: tuple[ContentRefV4, ...]
    attack_refs: tuple[ContentRefV4, ...]
    exception_refs: tuple[ContentRefV4, ...]
    permission_refs: tuple[ContentRefV4, ...]


_EXPECTED_FAILURES = (
    ContractV4Error,
    BackendV4Error,
    IndependentCheckerV4Error,
    ArgumentationV4Error,
)


def _ref_key(reference: ContentRefV4) -> tuple[str, str]:
    return reference.kind, reference.digest.hex


def _sorted_refs(references: tuple[ContentRefV4, ...]) -> tuple[ContentRefV4, ...]:
    return tuple(sorted(set(references), key=_ref_key))


def _semantic_digest(body: dict[str, object]) -> DigestV4:
    projection = deepcopy(body)
    runtime = projection["runtime_profile"]
    if type(runtime) is not dict:
        raise ApplicationV4Error("APPLICATION_RESULT", "runtime profile is not an object")
    runtime.pop("backend_receipt_ref")
    claims = projection["claims"]
    if type(claims) is not list:
        raise ApplicationV4Error("APPLICATION_RESULT", "claims are not an array")
    for claim in claims:
        if type(claim) is not dict:
            raise ApplicationV4Error("APPLICATION_RESULT", "claim is not an object")
        claim.pop("proof_receipt_refs")
        claim.pop("checker_receipt_refs")
    projection.pop("receipt_refs")
    return digest_value(projection)


class ApplicationV4:
    """Compose the already verified V4 components without an advisory fallback."""

    def __init__(
        self,
        resolver: ArtifactResolverV4,
        trust: TrustVerifierV4,
        source_service: SourceServiceV4,
        fact_service: FactAdmissionServiceV4,
        pack_verifier: RulePackVerifierV4,
        ir_compiler: LegalIRCompilerV4,
        backend_router: BackendRouterV4,
        checker: IndependentCheckerV4,
        audit_store: AuditBundleStoreV4,
        certificate_issuer: CertificateIssuerV4,
        *,
        receipt_signer: ReceiptSignerV4,
        clock: Callable[[], CanonicalTimeV4],
    ) -> None:
        if (
            type(resolver) is not ArtifactResolverV4
            or type(trust) is not TrustVerifierV4
            or type(source_service) is not SourceServiceV4
            or type(fact_service) is not FactAdmissionServiceV4
            or type(pack_verifier) is not RulePackVerifierV4
            or type(ir_compiler) is not LegalIRCompilerV4
            or type(backend_router) is not BackendRouterV4
            or type(checker) is not IndependentCheckerV4
            or type(audit_store) is not AuditBundleStoreV4
            or type(certificate_issuer) is not CertificateIssuerV4
            or not callable(receipt_signer)
            or not callable(clock)
        ):
            raise ApplicationV4Error(
                "APPLICATION_DEPENDENCY", "ApplicationV4 dependencies are invalid"
            )
        if (
            source_service._resolver is not resolver
            or source_service._trust is not trust
            or fact_service._resolver is not resolver
            or fact_service._source_service is not source_service
            or fact_service._trust is not trust
            or pack_verifier._resolver is not resolver
            or pack_verifier._source_service is not source_service
            or pack_verifier._trust is not trust
            or ir_compiler._pack_verifier is not pack_verifier
            or backend_router._ir_compiler is not ir_compiler
            or backend_router._fact_service is not fact_service
            or checker._resolver is not resolver
            or checker._trust is not trust
            or certificate_issuer._verifier._trust is not trust
            or audit_store._trust_material.policy != trust.policy
            or audit_store._trust_material.target_environment != trust.target_environment
            or audit_store._trust_material.revoked_subject_digests
            != tuple(sorted(trust._revoked_subjects, key=str))
            or audit_store._trust_material.revoked_nonces
            != tuple(sorted(trust._revoked_nonces))
        ):
            raise ApplicationV4Error(
                "APPLICATION_DEPENDENCY_DRIFT",
                "formal components do not share one resolver, trust, and storage authority",
            )
        self._resolver = resolver
        self._trust = trust
        self._source_service = source_service
        self._fact_service = fact_service
        self._pack_verifier = pack_verifier
        self._ir_compiler = ir_compiler
        self._backend_router = backend_router
        self._checker = checker
        self._audit_store = audit_store
        self._certificate_issuer = certificate_issuer
        self._receipt_signer = receipt_signer
        self._clock = clock

    def _document(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
    ) -> dict[str, object]:
        raw = self._resolver.resolve_content(
            reference,
            expected_artifact_kind=kind,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope=scope,
            max_bytes=self._resolver.max_artifact_bytes,
        )
        try:
            value = parse_json_document(raw)
        except (TypeError, ValueError) as exc:
            raise ContractV4Error("APPLICATION_JSON", f"{kind} is not strict JSON") from exc
        if type(value) is not dict or raw != canonical_bytes(value):
            raise ContractV4Error("APPLICATION_JSON", f"{kind} is not canonical JSON")
        return value

    def _contract(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
        contract: type[object],
        digest_field: str | None = None,
    ) -> object:
        document = self._document(reference, kind=kind, scope=scope)
        if digest_field is None:
            value = contract.from_dict(document)
            if value.canonical_digest() != reference.digest:
                raise ContractV4Error(
                    "APPLICATION_ARTIFACT_BINDING", f"{kind} bytes differ from their reference"
                )
            return value
        if digest_field in document:
            raise ContractV4Error(
                "APPLICATION_DIGEST_BODY", f"{kind} stores a recursive digest field"
            )
        value = contract.from_dict({**document, digest_field: str(reference.digest)})
        if value.canonical_digest() != reference.digest or value.digest_body() != document:
            raise ContractV4Error(
                "APPLICATION_ARTIFACT_BINDING", f"{kind} digest body is inconsistent"
            )
        return value

    @staticmethod
    def _failure(stage: str, exc: Exception) -> _Failure:
        code = getattr(exc, "code", None)
        return _Failure(stage, code if type(code) is str and code else "APPLICATION_STAGE_ERROR")

    def _resolve_input(
        self,
        request_ref: ContentRefV4,
        run_identity_ref: ContentRefV4,
    ) -> tuple[CaseRequestV4, RunIdentityV4]:
        try:
            request = self._contract(
                request_ref,
                kind=CASE_REQUEST_KIND,
                scope=CASE_REQUEST_SCOPE,
                contract=CaseRequestV4,
            )
            run = self._contract(
                run_identity_ref,
                kind=RUN_IDENTITY_KIND,
                scope=RUN_IDENTITY_SCOPE,
                contract=RunIdentityV4,
                digest_field="run_digest",
            )
        except _EXPECTED_FAILURES as exc:
            failure = self._failure("resolver", exc)
            raise ApplicationV4Error(failure.code, "request or run identity did not resolve") from exc
        if type(request) is not CaseRequestV4 or type(run) is not RunIdentityV4:
            raise ApplicationV4Error("APPLICATION_INPUT_TYPE", "resolved input has a wrong type")
        expected_policy_ref = ContentRefV4("trust-policy", self._trust.policy.canonical_digest())
        if (
            run.request_ref != request_ref
            or run.source_bundle_ref != request.source_bundle_ref
            or run.evidence_manifest_ref != request.evidence_manifest_ref
            or run.fact_attestation_refs != request.fact_attestation_refs
            or run.rule_pack_ref != request.rule_pack_ref
            or run.trust_policy_ref != expected_policy_ref
            or run_identity_ref != ContentRefV4(RUN_IDENTITY_KIND, run.canonical_digest())
        ):
            raise ApplicationV4Error(
                "APPLICATION_RUN_BINDING", "run identity does not bind the canonical request"
            )
        if self._audit_store._current_engine_build_digest != run.engine_build_digest:
            raise ApplicationV4Error(
                "APPLICATION_BUILD_BINDING", "audit authority and run use different builds"
            )
        return request, run

    def _trust_failure(self, run: RunIdentityV4, now: CanonicalTimeV4) -> _Failure | None:
        policy = self._trust.policy
        if run.trust_policy_ref != ContentRefV4("trust-policy", policy.canonical_digest()):
            return _Failure("trust", "TRUST_POLICY_MISMATCH")
        if now < policy.valid_from or (policy.valid_to is not None and not now < policy.valid_to):
            return _Failure("trust", "TRUST_POLICY_INACTIVE")
        return None

    def _source_and_evidence(
        self,
        request: CaseRequestV4,
        *,
        case_scope: str,
        now: CanonicalTimeV4,
    ) -> tuple[SourceBundleV4 | None, ContentRefV4 | None, _Failure | None]:
        try:
            bundle = self._contract(
                request.source_bundle_ref,
                kind=SOURCE_BUNDLE_KIND,
                scope="source-path",
                contract=SourceBundleV4,
                digest_field="bundle_digest",
            )
            if type(bundle) is not SourceBundleV4:
                raise ContractV4Error("APPLICATION_SOURCE", "source bundle has a wrong type")
            for snapshot in bundle.snapshots:
                self._source_service.admit_snapshot(source_snapshot_ref(snapshot), now=now)
            applicable = self._source_service.resolve_applicable(
                request.source_bundle_ref,
                decision_time=request.decision_time,
            )
        except _EXPECTED_FAILURES as exc:
            return None, None, self._failure("source", exc)
        try:
            manifest = self._contract(
                request.evidence_manifest_ref,
                kind=EVIDENCE_MANIFEST_KIND,
                scope=CASE_EVIDENCE_SCOPE,
                contract=EvidenceManifestV4,
                digest_field="manifest_digest",
            )
            if (
                type(manifest) is not EvidenceManifestV4
                or manifest.request_ref != case_request_binding_ref(request)
                or manifest.case_scope != case_scope
            ):
                raise ContractV4Error(
                    "APPLICATION_EVIDENCE_BINDING",
                    "evidence manifest binds another request or case scope",
                )
        except _EXPECTED_FAILURES as exc:
            return bundle, applicable, self._failure("evidence", exc)
        return bundle, applicable, None

    def _fact_key(self, candidate: FactCandidateV4) -> str:
        proposition = self._document(
            candidate.proposition_ref,
            kind=FACT_PROPOSITION_KIND,
            scope=FACT_ADMISSION_SCOPE,
        )
        if (
            set(proposition) != {"schema_version", "proposition"}
            or proposition.get("schema_version") != "jc/fact-proposition/1.0"
            or type(proposition.get("proposition")) is not str
            or not proposition["proposition"]
        ):
            raise ContractV4Error(
                "APPLICATION_FACT_PROPOSITION", "fact proposition is not a closed fact key"
            )
        return proposition["proposition"]

    def _facts(
        self,
        request: CaseRequestV4,
        request_ref: ContentRefV4,
        run_identity_ref: ContentRefV4,
        *,
        case_scope: str,
        now: CanonicalTimeV4,
        enabled: bool,
    ) -> tuple[_FactState, _Failure | None]:
        receipts: list[ContentRefV4] = []
        admitted: list[ContentRefV4] = []
        rejected: list[ContentRefV4] = []
        observed: list[tuple[str, ContentRefV4]] = []
        unresolved: list[ContentRefV4] = []
        release_conditions: list[ContentRefV4] = []
        hypothetical = False
        review = False
        for attestation_ref in request.fact_attestation_refs:
            try:
                attestation = self._contract(
                    attestation_ref,
                    kind=FACT_ATTESTATION_KIND,
                    scope=LEGAL_APPROVAL_SCOPE,
                    contract=FactAttestationV4,
                )
                if type(attestation) is not FactAttestationV4:
                    raise ContractV4Error(
                        "APPLICATION_FACT_TYPE", "fact attestation has a wrong type"
                    )
                candidate = self._contract(
                    attestation.candidate_ref,
                    kind=FACT_CANDIDATE_KIND,
                    scope=FACT_ADMISSION_SCOPE,
                    contract=FactCandidateV4,
                )
                if type(candidate) is not FactCandidateV4:
                    raise ContractV4Error(
                        "APPLICATION_FACT_TYPE", "fact candidate has a wrong type"
                    )
                fact_key = self._fact_key(candidate)
                observed.append((fact_key, attestation.candidate_ref))
                if not enabled:
                    continue
                try:
                    receipt_ref = self._fact_service.admit(
                        request_ref,
                        attestation.candidate_ref,
                        attestation_ref,
                        case_scope=case_scope,
                        run_identity_ref=run_identity_ref,
                        now=now,
                    )
                except ContractV4Error as exc:
                    if exc.code != "FACT_NOT_FORMAL":
                        raise
                    rejected.append(attestation.candidate_ref)
                    unresolved.append(attestation.candidate_ref)
                    release_conditions.append(attestation_ref)
                    hypothetical = hypothetical or (
                        attestation.assumption_state != "NONE"
                        or attestation.dispute_state == "USER_ASSUMED"
                    )
                    review = review or attestation.dispute_state in {"UNKNOWN", "DISPUTED"}
                    continue
                fact_ref = self._fact_service.verify_receipt(
                    receipt_ref,
                    request_ref=request_ref,
                    case_scope=case_scope,
                    run_identity_ref=run_identity_ref,
                    now=now,
                )
                receipts.append(receipt_ref)
                admitted.append(fact_ref)
            except _EXPECTED_FAILURES as exc:
                return (
                    _FactState(
                        _sorted_refs(tuple(receipts)),
                        _sorted_refs(tuple(admitted)),
                        _sorted_refs(tuple(rejected)),
                        tuple(sorted(observed, key=lambda item: (item[0], _ref_key(item[1])))),
                        _sorted_refs(tuple(unresolved)),
                        _sorted_refs(tuple(release_conditions)),
                        hypothetical,
                        review,
                    ),
                    self._failure("fact", exc),
                )
        return (
            _FactState(
                _sorted_refs(tuple(receipts)),
                _sorted_refs(tuple(admitted)),
                _sorted_refs(tuple(rejected)),
                tuple(sorted(observed, key=lambda item: (item[0], _ref_key(item[1])))),
                _sorted_refs(tuple(unresolved)),
                _sorted_refs(tuple(release_conditions)),
                hypothetical,
                review,
            ),
            None,
        )

    def _rule_requirements(self, rule: RuleV4) -> tuple[str, ...]:
        keys: list[str] = []
        for premise_ref in rule.premise_refs:
            premise = self._document(
                premise_ref,
                kind=RULE_PREMISE_KIND,
                scope=RULE_COMPONENT_SCOPE,
            )
            if (
                set(premise) != {"schema_version", "rule_id", "fact_key", "required"}
                or premise.get("schema_version") != "jc/rule-premise/1.0"
                or premise.get("rule_id") != rule.rule_id
                or type(premise.get("fact_key")) is not str
                or not premise["fact_key"]
                or type(premise.get("required")) is not bool
            ):
                raise ContractV4Error(
                    "APPLICATION_RULE_PREMISE", "signed rule premise is not closed and typed"
                )
            if premise["required"]:
                keys.append(premise["fact_key"])
        return tuple(sorted(set(keys)))

    def _select_rules(
        self,
        request: CaseRequestV4,
        pack: VerifiedRulePackV4,
        observed_keys: frozenset[str],
    ) -> tuple[tuple[ContentRefV4, RuleV4, tuple[str, ...]], ...]:
        bindings = {
            (domain_id, namespace): refs
            for domain_id, namespace, refs in pack.domain_bindings
        }
        domain_refs: list[tuple[ContentRefV4, ...]] = []
        for config_ref in pack.manifest.config_refs:
            config = self._document(
                config_ref,
                kind=PACK_CONFIG_KIND,
                scope=RULE_PACK_SCOPE,
            )
            if set(config) != {
                "schema_version",
                "domain_id",
                "namespace",
                "jurisdiction",
                "governing_law",
                "rule_refs",
            } or config.get("schema_version") != "jc/domain-config/1.0":
                raise ContractV4Error(
                    "APPLICATION_DOMAIN_CONFIG",
                    "signed domain configuration is not closed",
                )
            try:
                config_rules = tuple(
                    ContentRefV4.from_dict(item) for item in config["rule_refs"]
                )
            except (TypeError, ValueError, ContractV4Error) as exc:
                raise ContractV4Error(
                    "APPLICATION_DOMAIN_CONFIG",
                    "signed domain rule references are invalid",
                ) from exc
            if bindings.get((config["domain_id"], config["namespace"])) != config_rules:
                raise ContractV4Error(
                    "APPLICATION_DOMAIN_CONFIG",
                    "verified domain projection differs from signed config bytes",
                )
            if (config["jurisdiction"], config["governing_law"]) == (
                request.legal_context.jurisdiction,
                request.legal_context.governing_law,
            ):
                domain_refs.append(config_rules)
        if len(domain_refs) != 1:
            raise ContractV4Error(
                "APPLICATION_DOMAIN_CONFIG",
                "signed pack has no unique configuration for the legal context",
            )
        allowed = set(domain_refs[0])
        by_ref = {
            reference: rule
            for reference, rule in zip(pack.manifest.rule_refs, pack.rules, strict=True)
            if reference in allowed
            and rule.effective_from <= request.decision_time
            and (rule.effective_to is None or request.decision_time < rule.effective_to)
        }
        if request.proposal_refs:
            requested = set(request.proposal_refs)
            if any(reference.kind != RULE_KIND for reference in requested) or not requested <= set(by_ref):
                raise ContractV4Error(
                    "APPLICATION_RULE_SELECTION",
                    "proposal_refs contain a rule outside the signed domain configuration",
                )
        else:
            requested = set()
        selected: list[tuple[ContentRefV4, RuleV4, tuple[str, ...]]] = []
        for reference, rule in sorted(by_ref.items(), key=lambda item: _ref_key(item[0])):
            requirements = self._rule_requirements(rule)
            if reference in requested or (not requested and set(requirements) & observed_keys):
                selected.append((reference, rule, requirements))
        return tuple(selected)

    @staticmethod
    def _runtime_profile(
        run: RunIdentityV4,
        *,
        formal_kernel: bool,
        execution: BackendExecutionV4 | None = None,
    ) -> RuntimeProfileV4:
        return RuntimeProfileV4(
            run.engine_version,
            run.engine_build_digest,
            formal_kernel,
            None if execution is None else execution.invocation_ref,
            None if execution is None else execution.receipt_ref,
            run.trust_policy_ref,
            run.storage_capability_ref,
        )

    def _result(
        self,
        request_ref: ContentRefV4,
        run_identity_ref: ContentRefV4,
        runtime_profile: RuntimeProfileV4,
        *,
        execution: ExecutionStatusV4,
        decision: DecisionStatusV4,
        review: ReviewStateV4,
        completeness: CompletenessStateV4,
        interruption: InterruptionStateV4 | None,
        certificate: CertificateKindV4,
        claims: tuple[ClaimResultV4, ...] = (),
        branches: tuple[object, ...] = (),
        missing_facts: tuple[MissingFactRequirementV4, ...] = (),
        admitted_fact_refs: tuple[ContentRefV4, ...] = (),
        rejected_fact_refs: tuple[ContentRefV4, ...] = (),
        applicable_rule_refs: tuple[ContentRefV4, ...] = (),
        inapplicable_rule_refs: tuple[ContentRefV4, ...] = (),
        argument_refs: tuple[ContentRefV4, ...] = (),
        attack_refs: tuple[ContentRefV4, ...] = (),
        exception_resolution_refs: tuple[ContentRefV4, ...] = (),
        permission_resolution_refs: tuple[ContentRefV4, ...] = (),
        decision_reason_codes: tuple[str, ...] = (),
        receipt_refs: tuple[ContentRefV4, ...] = (),
    ) -> SemanticResultV4:
        body = {
            "request_ref": request_ref.to_dict(),
            "execution_status": execution.value,
            "decision_status": decision.value,
            "review_state": review.to_dict(),
            "completeness_state": completeness.value,
            "interruption_state": None if interruption is None else interruption.to_dict(),
            "certificate_kind": certificate.value,
            "runtime_profile": runtime_profile.to_dict(),
            "claims": [item.to_dict() for item in claims],
            "branches": [item.to_dict() for item in branches],
            "missing_facts": [item.to_dict() for item in missing_facts],
            "admitted_fact_refs": [item.to_dict() for item in _sorted_refs(admitted_fact_refs)],
            "rejected_fact_refs": [item.to_dict() for item in _sorted_refs(rejected_fact_refs)],
            "applicable_rule_refs": [item.to_dict() for item in _sorted_refs(applicable_rule_refs)],
            "inapplicable_rule_refs": [item.to_dict() for item in _sorted_refs(inapplicable_rule_refs)],
            "argument_refs": [item.to_dict() for item in _sorted_refs(argument_refs)],
            "attack_refs": [item.to_dict() for item in _sorted_refs(attack_refs)],
            "exception_resolution_refs": [
                item.to_dict() for item in _sorted_refs(exception_resolution_refs)
            ],
            "permission_resolution_refs": [
                item.to_dict() for item in _sorted_refs(permission_resolution_refs)
            ],
            "priority_resolution_refs": [],
            "temporal_result_refs": [],
            "numeric_result_refs": [],
            "decision_reason_codes": list(decision_reason_codes),
            "taint_codes": [],
            "risk_codes": [],
            "receipt_refs": [item.to_dict() for item in _sorted_refs(receipt_refs)],
            "run_identity_ref": run_identity_ref.to_dict(),
        }
        return SemanticResultV4.from_dict(
            {**body, "result_digest": str(_semantic_digest(body))}
        )

    @staticmethod
    def _review_state(
        unresolved: tuple[ContentRefV4, ...],
        release_conditions: tuple[ContentRefV4, ...],
    ) -> ReviewStateV4:
        if not unresolved:
            return ReviewStateV4("not_required", (), None, (), None)
        return ReviewStateV4(
            "required",
            _sorted_refs(unresolved),
            "legal_reviewer",
            _sorted_refs(release_conditions or unresolved),
            None,
        )

    def _nonformal_result(
        self,
        request: CaseRequestV4,
        run: RunIdentityV4,
        run_identity_ref: ContentRefV4,
        pack: VerifiedRulePackV4 | None,
        facts: _FactState,
        selected: tuple[tuple[ContentRefV4, RuleV4, tuple[str, ...]], ...],
        *,
        failure: _Failure | None = None,
        decision: DecisionStatusV4 | None = None,
        execution: ExecutionStatusV4 | None = None,
        interruption: InterruptionStateV4 | None = None,
        backend_execution: BackendExecutionV4 | None = None,
        missing: tuple[MissingFactRequirementV4, ...] = (),
        branches: tuple[object, ...] = (),
        reasons: tuple[str, ...] = (),
        extra_receipts: tuple[ContentRefV4, ...] = (),
    ) -> SemanticResultV4:
        if failure is not None:
            decision = (
                DecisionStatusV4.ENGINE_ERROR
                if execution is ExecutionStatusV4.ENGINE_ERROR
                else DecisionStatusV4.BLOCKED
            )
            execution = execution or ExecutionStatusV4.ADMISSION_BLOCKED
            reasons = reasons or (f"{failure.stage}:{failure.code}",)
        elif decision is None or execution is None:
            raise ApplicationV4Error("APPLICATION_RESULT", "nonformal state is incomplete")
        unresolved = facts.unresolved_refs
        release = facts.release_condition_refs
        if decision is DecisionStatusV4.MISSING_REQUIRED_FACT:
            unresolved = tuple(
                reference
                for _, rule, requirements in selected
                for reference in rule.premise_refs
                if requirements
            )
            release = unresolved
        review = self._review_state(unresolved, release)
        if decision in {DecisionStatusV4.BLOCKED, DecisionStatusV4.ENGINE_ERROR}:
            review = ReviewStateV4("not_required", (), None, (), None)
        applicable = tuple(reference for reference, _, _ in selected)
        all_rules = () if pack is None else pack.manifest.rule_refs
        return self._result(
            run.request_ref,
            run_identity_ref,
            self._runtime_profile(
                run,
                formal_kernel=False,
                execution=backend_execution,
            ),
            execution=execution,
            decision=decision,
            review=review,
            completeness=CompletenessStateV4.PARTIAL,
            interruption=interruption,
            certificate=CertificateKindV4.NONE,
            branches=branches,
            missing_facts=missing,
            admitted_fact_refs=facts.admitted_refs,
            rejected_fact_refs=facts.rejected_refs,
            applicable_rule_refs=applicable,
            inapplicable_rule_refs=tuple(set(all_rules) - set(applicable)),
            decision_reason_codes=reasons,
            receipt_refs=(*facts.receipt_refs, *extra_receipts),
        )

    def _compile(
        self,
        pack: VerifiedRulePackV4,
        selected: tuple[tuple[ContentRefV4, RuleV4, tuple[str, ...]], ...],
        *,
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> tuple[LegalIRCompilationV4, ...]:
        return tuple(
            self._ir_compiler.compile_rule(
                pack,
                rule_ref=reference,
                run_identity_ref=run_identity_ref,
                now=now,
            )
            for reference, _, _ in selected
        )

    @staticmethod
    def _primary_execution(
        executions: tuple[BackendExecutionV4, ...],
    ) -> BackendExecutionV4 | None:
        by_provider = {item.invocation.provider_id: item for item in executions}
        rich = [
            by_provider[provider]
            for provider in (AAF_PROVIDER_ID, EXACT_PROVIDER_ID)
            if provider in by_provider
        ]
        if len(rich) > 1:
            return None
        if rich:
            return rich[0]
        return by_provider.get(HORN_PROVIDER_ID)

    def _register_contract(self, kind: str, value: object) -> ContentRefV4:
        raw = value.canonical_bytes()
        reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
        return self._resolver.register_bytes(
            artifact_id=f"{kind}-{reference.digest.hex}",
            content_ref=reference,
            artifact_kind=kind,
            media_type=JSON_MEDIA_TYPE,
            scope=CHECKER_SCOPE,
            content=raw,
        )

    def _argument_outcome(
        self,
        execution: BackendExecutionV4,
        checked: CheckerExecutionV4,
    ) -> _ArgumentOutcome:
        graph_document = self._document(
            checked.receipt.argument_graph_ref,
            kind=ARGUMENT_GRAPH_KIND,
            scope=CHECKER_SCOPE,
        )
        result_document = self._document(
            execution.receipt.backend_result_ref,
            kind=BACKEND_RESULT_KIND,
            scope=BACKEND_SCOPE,
        )
        outputs = result_document.get("outputs")
        if type(outputs) is not dict:
            raise ContractV4Error("APPLICATION_BACKEND_RESULT", "backend outputs are not an object")
        if execution.invocation.provider_id != AAF_PROVIDER_ID:
            semantic_state = graph_document.get("semantic_state")
            if (
                type(semantic_state) is not dict
                or semantic_state.get("outcome") != result_document.get("outcome")
                or semantic_state.get("outputs_digest") != str(digest_value(outputs))
                or graph_document.get("arguments") != []
            ):
                raise ContractV4Error(
                    "APPLICATION_ARGUMENT_BINDING",
                    "checker semantic-state graph differs from the backend result",
                )
            if execution.invocation.provider_id == HORN_PROVIDER_ID:
                missing = outputs.get("missing_fact_keys")
                norms = outputs.get("applicable_norms")
                state = "missing" if missing else "accepted" if norms else "empty"
            else:
                state = "accepted"
            return _ArgumentOutcome(
                state,
                (),
                (checked.receipt.argument_graph_ref,),
                (),
                (),
                (),
            )
        arguments_wire = graph_document.get("arguments")
        if type(arguments_wire) is not list:
            raise ContractV4Error("APPLICATION_ARGUMENT_GRAPH", "arguments are not an array")
        if not arguments_wire:
            if outputs.get("state") != "empty":
                raise ContractV4Error(
                    "APPLICATION_ARGUMENT_BINDING", "empty graph has a non-empty result state"
                )
            return _ArgumentOutcome("empty", (), (checked.receipt.argument_graph_ref,), (), (), ())
        try:
            graph = ArgumentGraphV4(
                tuple(ArgumentV4.from_dict(item) for item in arguments_wire),
                tuple(AttackV4.from_dict(item) for item in graph_document["attacks"]),
                tuple(PriorityEdgeV4.from_dict(item) for item in graph_document["priority_edges"]),
                tuple(
                    PermissionRelationV4(
                        item["permission_id"],
                        ContentRefV4.from_dict(item["permission_claim_ref"]),
                        None
                        if item["prohibition_claim_ref"] is None
                        else ContentRefV4.from_dict(item["prohibition_claim_ref"]),
                        ContentRefV4.from_dict(item["source_ref"]),
                    )
                    for item in graph_document["permission_relations"]
                ),
            )
            evaluation = evaluate_argument_graph(graph)
        except (KeyError, TypeError, ValueError, ContractV4Error) as exc:
            raise ContractV4Error(
                "APPLICATION_ARGUMENT_GRAPH", "checker graph is not canonical ArgumentGraphV4"
            ) from exc
        if evaluation.to_dict() != outputs:
            raise ContractV4Error(
                "APPLICATION_ARGUMENT_BINDING",
                "independent argument evaluation differs from checked backend outputs",
            )
        argument_by_ref = {argument_ref_v4(item): item for item in graph.arguments}
        labels = tuple(
            (
                argument_by_ref[label.argument_ref].rule_ref,
                label.label,
                (label.argument_ref,),
            )
            for label in evaluation.labels
        )
        attack_refs = tuple(
            self._register_contract("attack-v4", item) for item in evaluation.effective_attacks
        )
        exception_refs = tuple(
            self._register_contract("exception-resolution-v4", item)
            for item in evaluation.exception_resolutions
        )
        permission_refs = tuple(
            self._register_contract("permission-resolution-v4", item)
            for item in evaluation.permission_resolutions
        )
        return _ArgumentOutcome(
            evaluation.state,
            labels,
            tuple(argument_ref_v4(item) for item in graph.arguments),
            attack_refs,
            exception_refs,
            permission_refs,
        )

    def _proof_receipt(
        self,
        claim_ref: ContentRefV4,
        execution: BackendExecutionV4,
        checked: CheckerExecutionV4,
        *,
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> ContentRefV4:
        proof_ref = execution.receipt.proof_ref
        if proof_ref is None:
            raise ContractV4Error("APPLICATION_PROOF", "completed backend has no proof")
        trusted = _sorted_refs((proof_ref, checked.receipt_ref))
        body = {
            "receipt_id": f"proof-{claim_ref.digest.hex}",
            "run_identity_ref": run_identity_ref.to_dict(),
            "subject_ref": claim_ref.to_dict(),
            "proof_kind": "independent-checker-confirmed-backend-proof",
            "proof_ref": proof_ref.to_dict(),
            "checker_receipt_ref": checked.receipt_ref.to_dict(),
            "proof_build_digest": str(checked.receipt.checker_build_digest),
            "trusted_computing_base_refs": [item.to_dict() for item in trusted],
            "status": "PASS",
            "issued_at": now.to_dict(),
        }
        signature = self._receipt_signer(
            claim_ref.digest,
            digest_value(body),
            _sorted_refs((claim_ref, proof_ref, checked.receipt_ref)),
            run_identity_ref,
            now,
        )
        if type(signature) is not SignatureEnvelopeV4:
            raise ContractV4Error("APPLICATION_PROOF_SIGNATURE", "proof signer returned a wrong type")
        proof = ProofReceiptV4.from_dict({**body, "signature": signature.to_dict()})
        return self._register_contract("proof-receipt-v4", proof)

    def _formal_result(
        self,
        request: CaseRequestV4,
        run: RunIdentityV4,
        run_identity_ref: ContentRefV4,
        pack: VerifiedRulePackV4,
        facts: _FactState,
        selected: tuple[tuple[ContentRefV4, RuleV4, tuple[str, ...]], ...],
        compilations: tuple[LegalIRCompilationV4, ...],
        execution: BackendExecutionV4,
        checked: CheckerExecutionV4,
        argument: _ArgumentOutcome,
        source_bundle: SourceBundleV4,
        *,
        now: CanonicalTimeV4,
    ) -> SemanticResultV4:
        labels = {reference: (label, arguments) for reference, label, arguments in argument.labels}
        claims: list[ClaimResultV4] = []
        proof_refs: list[ContentRefV4] = []
        for reference, rule, _ in selected:
            label, argument_refs = labels.get(
                reference,
                ("IN", (checked.receipt.argument_graph_ref,)),
            )
            proof_ref = self._proof_receipt(
                rule.conclusion_ref,
                execution,
                checked,
                run_identity_ref=run_identity_ref,
                now=now,
            )
            proof_refs.append(proof_ref)
            claims.append(
                ClaimResultV4(
                    rule.rule_id,
                    rule.conclusion_ref,
                    "accepted" if label == "IN" else "rejected" if label == "OUT" else "undecided",
                    label,
                    argument_refs,
                    facts.admitted_refs,
                    (reference,),
                    (rule.source_snapshot_ref,),
                    (proof_ref,),
                    (checked.receipt_ref,),
                )
            )
        if not claims or not any(item.label == "IN" for item in claims):
            raise ContractV4Error("APPLICATION_NO_ACCEPTED_CLAIM", "formal run has no accepted claim")
        source_receipts = tuple(
            snapshot.authenticity_receipt_ref for snapshot in source_bundle.snapshots
        )
        promotions = tuple(
            receipt
            for _, rule, _ in selected
            for receipt in rule.promotion_receipt_refs
        )
        translations = tuple(
            receipt
            for compilation in compilations
            for receipt in (
                compilation.rule_to_spec_receipt_ref,
                compilation.spec_to_ivl_receipt_ref,
            )
        )
        receipts = _sorted_refs((
            *source_receipts,
            request.evidence_manifest_ref,
            *facts.receipt_refs,
            *promotions,
            *translations,
            execution.receipt_ref,
            *proof_refs,
            checked.receipt_ref,
        ))
        conflict = argument.state in {"disputed", "cycle_blocked"}
        review = (
            self._review_state(argument.attack_refs, argument.attack_refs)
            if conflict
            else ReviewStateV4("not_required", (), None, (), None)
        )
        applicable = tuple(reference for reference, _, _ in selected)
        return self._result(
            run.request_ref,
            run_identity_ref,
            self._runtime_profile(run, formal_kernel=True, execution=execution),
            execution=ExecutionStatusV4.COMPLETED,
            decision=(
                DecisionStatusV4.CONFLICT_CERTIFICATE
                if conflict
                else DecisionStatusV4.ACCEPTED_FORMAL_RESULT
            ),
            review=review,
            completeness=CompletenessStateV4.COMPLETE,
            interruption=None,
            certificate=(
                CertificateKindV4.CONFLICT_VERIFIED
                if conflict
                else CertificateKindV4.FORMAL_VERIFIED
            ),
            claims=tuple(claims),
            admitted_fact_refs=facts.admitted_refs,
            rejected_fact_refs=facts.rejected_refs,
            applicable_rule_refs=applicable,
            inapplicable_rule_refs=tuple(set(pack.manifest.rule_refs) - set(applicable)),
            argument_refs=argument.argument_refs,
            attack_refs=argument.attack_refs,
            exception_resolution_refs=argument.exception_refs,
            permission_resolution_refs=argument.permission_refs,
            decision_reason_codes=("argument_conflict",) if conflict else (),
            receipt_refs=receipts,
        )

    @staticmethod
    def _wire_references(value: object) -> set[ContentRefV4]:
        references: set[ContentRefV4] = set()
        pending = [value]
        while pending:
            current = pending.pop()
            if type(current) is dict:
                if set(current) == {"kind", "digest"}:
                    try:
                        references.add(ContentRefV4.from_dict(current))
                    except (ContractV4Error, TypeError, ValueError):
                        pass
                    continue
                pending.extend(current.values())
            elif type(current) is list:
                pending.extend(current)
        return references

    def _artifact_groups(
        self,
        auto: frozenset[ContentRefV4],
        roots: set[ContentRefV4],
    ) -> dict[str, tuple[AuditArtifactV4, ...]]:
        groups: dict[str, list[AuditArtifactV4]] = {
            "source_artifacts": [],
            "fact_artifacts": [],
            "rule_pack_artifacts": [],
            "translation_artifacts": [],
            "backend_artifacts": [],
            "checker_artifacts": [],
            "graph_artifacts": [],
        }
        with self._resolver._lock:
            records = dict(self._resolver._by_ref)
        selected: dict[ContentRefV4, object] = {}
        pending = list(roots)
        while pending:
            reference = pending.pop()
            if reference in selected or reference in auto:
                continue
            record = records.get(reference)
            if record is None:
                continue
            selected[reference] = record
            if record.media_type != JSON_MEDIA_TYPE:
                continue
            try:
                document = parse_json_document(record.content)
            except (TypeError, ValueError):
                continue
            pending.extend(self._wire_references(document) - set(selected))
        for record in selected.values():
            if record.content_ref in auto:
                continue
            artifact = AuditArtifactV4(
                record.artifact_id,
                record.content_ref,
                record.artifact_kind,
                record.media_type,
                record.scope,
                record.content,
            )
            if record.scope == CHECKER_SCOPE:
                group = "checker_artifacts"
            elif record.scope == BACKEND_SCOPE:
                group = "backend_artifacts"
            elif record.scope == "legal-ir":
                group = "translation_artifacts"
            elif record.scope in {RULE_PACK_SCOPE, RULE_COMPONENT_SCOPE}:
                group = "rule_pack_artifacts"
            elif record.scope in {FACT_ADMISSION_SCOPE, LEGAL_APPROVAL_SCOPE, CASE_EVIDENCE_SCOPE}:
                group = "fact_artifacts"
            else:
                group = "source_artifacts"
            groups[group].append(artifact)
        return {
            name: tuple(sorted(values, key=lambda item: item.sort_key))
            for name, values in groups.items()
        }

    def _finish(
        self,
        request: CaseRequestV4,
        run: RunIdentityV4,
        run_identity_ref: ContentRefV4,
        result: SemanticResultV4,
        events: list[tuple[str, ContentRefV4]],
        *,
        now: CanonicalTimeV4,
        failure: _Failure | None,
    ) -> EvaluationEnvelopeV4:
        result_ref = ContentRefV4("semantic-result", result.canonical_digest())
        events.append(("result", result_ref))
        roots = self._wire_references({
            "request": request.to_dict(),
            "run": run.to_dict(),
            "result": result.to_dict(),
            "events": [reference.to_dict() for _, reference in events],
        })
        materials = AuditBundleMaterialsV4(
            request=request,
            run_identity=run,
            replay_policy_ref=self._trust.policy.replay_policy_ref,
            result=result,
            events=tuple(
                AuditEventV4(index, stage, reference)
                for index, (stage, reference) in enumerate(events)
            ),
            **self._artifact_groups(
                frozenset((run.request_ref, run_identity_ref)),
                roots,
            ),
        )
        capability = self._audit_store.capability_for(run_identity_ref)
        completed = self._audit_store.write_run(
            capability,
            materials,
            now=now,
            certificate_factory=(
                None
                if result.certificate_kind is CertificateKindV4.NONE
                else self._certificate_issuer
            ),
        )
        completed = self._audit_store.verify_run(capability, now=now)
        if failure is None:
            transport = TransportOutcomeV4("success", None)
        else:
            correlation = digest_value({
                "run_identity_ref": run_identity_ref.to_dict(),
                "stage": failure.stage,
                "code": failure.code,
            }).hex[:24]
            transport = TransportOutcomeV4(
                "error",
                ErrorV4(
                    failure.code,
                    f"formal evaluation stopped at {failure.stage}",
                    failure.stage,
                    False,
                    correlation,
                    (),
                ),
            )
        return EvaluationEnvelopeV4(
            completed.request,
            completed.result,
            completed.run_identity,
            completed.certificate,
            transport,
            completed.bundle_index.manifest_ref,
            completed.bundle_index,
        )

    def evaluate(
        self,
        request_ref: ContentRefV4,
        run_identity_ref: ContentRefV4,
        *,
        case_scope: str,
        limits: ResourceLimitsV4 | None = None,
        seed: int = 0,
        cancel_check: Callable[[], bool] | None = None,
    ) -> EvaluationEnvelopeV4:
        """Execute one request through the sole V4 formal spine and seal its final bundle."""

        if (
            type(request_ref) is not ContentRefV4
            or type(run_identity_ref) is not ContentRefV4
            or type(case_scope) is not str
            or not case_scope
            or type(seed) is not int
            or (cancel_check is not None and not callable(cancel_check))
        ):
            raise ApplicationV4Error("APPLICATION_INPUT_TYPE", "evaluation context is invalid")
        admitted_limits = ResourceLimitsV4() if limits is None else limits
        if type(admitted_limits) is not ResourceLimitsV4:
            raise ApplicationV4Error("APPLICATION_INPUT_TYPE", "limits must be ResourceLimitsV4")
        now = self._clock()
        if type(now) is not CanonicalTimeV4:
            raise ApplicationV4Error("APPLICATION_CLOCK", "clock returned a non-canonical time")
        request, run = self._resolve_input(request_ref, run_identity_ref)
        events: list[tuple[str, ContentRefV4]] = [("resolver", request_ref)]

        failure = self._trust_failure(run, now)
        events.append(("trust", run_identity_ref))
        source_bundle, applicable_source, source_failure = self._source_and_evidence(
            request,
            case_scope=case_scope,
            now=now,
        )
        failure = failure or source_failure
        if applicable_source is not None:
            events.append(("source", applicable_source))
        events.append(("evidence", request.evidence_manifest_ref))

        facts, fact_failure = self._facts(
            request,
            request_ref,
            run_identity_ref,
            case_scope=case_scope,
            now=now,
            enabled=failure is None,
        )
        failure = failure or fact_failure
        events.append(
            (
                "fact",
                facts.receipt_refs[-1]
                if facts.receipt_refs
                else request.evidence_manifest_ref,
            )
        )

        pack: VerifiedRulePackV4 | None = None
        try:
            pack = self._pack_verifier.verify(request.rule_pack_ref, now=now)
        except _EXPECTED_FAILURES as exc:
            failure = failure or self._failure("pack", exc)
        events.append(("pack", request.rule_pack_ref))
        if failure is not None or pack is None or source_bundle is None:
            failure = failure or _Failure("pack", "PACK_NOT_VERIFIED")
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                (),
                failure=failure,
            )
            return self._finish(
                request,
                run,
                run_identity_ref,
                result,
                events,
                now=now,
                failure=failure,
            )

        try:
            selected = self._select_rules(
                request,
                pack,
                frozenset(key for key, _ in facts.observed),
            )
        except _EXPECTED_FAILURES as exc:
            failure = self._failure("pack", exc)
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                (),
                failure=failure,
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=failure
            )

        if facts.hypothetical or facts.review:
            decision = (
                DecisionStatusV4.HYPOTHETICAL_RESULT
                if facts.hypothetical
                else DecisionStatusV4.REVIEW_ONLY_RESULT
            )
            branches: tuple[object, ...] = ()
            if decision is DecisionStatusV4.HYPOTHETICAL_RESULT:
                branch_body = {
                    "branch_id": "caller-assumption",
                    "assumption_refs": [item.to_dict() for item in facts.rejected_refs],
                    "claim_refs": [rule.conclusion_ref.to_dict() for _, rule, _ in selected],
                    "decision_status": DecisionStatusV4.HYPOTHETICAL_RESULT.value,
                }
                branches = (
                    BranchResultV4.from_dict({
                        **branch_body,
                        "branch_digest": str(digest_value(branch_body)),
                    }),
                )
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                decision=decision,
                execution=ExecutionStatusV4.COMPLETED,
                branches=branches,
                reasons=("nonformal_fact_input",),
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=None
            )

        admitted_keys = frozenset(
            key for key, candidate_ref in facts.observed if candidate_ref not in facts.rejected_refs
        )
        missing = tuple(
            MissingFactRequirementV4(
                fact_key,
                (reference,),
                (rule.conclusion_ref,),
                ("typed-v4-fact-value",),
                ("signed-source-snapshot",),
                1,
            )
            for reference, rule, requirements in selected
            for fact_key in requirements
            if fact_key not in admitted_keys
        )
        if missing:
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                decision=DecisionStatusV4.MISSING_REQUIRED_FACT,
                execution=ExecutionStatusV4.COMPLETED,
                missing=missing,
                reasons=("missing_required_fact",),
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=None
            )
        if not selected:
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                decision=DecisionStatusV4.UNKNOWN,
                execution=ExecutionStatusV4.COMPLETED,
                reasons=("no_applicable_rule",),
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=None
            )

        try:
            compilations = self._compile(
                pack,
                selected,
                run_identity_ref=run_identity_ref,
                now=now,
            )
            events.append(("ir", compilations[-1].spec_to_ivl_receipt_ref))
            executions = self._backend_router.execute(
                compilations,
                run_identity_ref=run_identity_ref,
                fact_admission_receipt_refs=facts.receipt_refs,
                limits=admitted_limits,
                now=now,
                seed=seed,
                cancel_check=cancel_check,
            )
        except _EXPECTED_FAILURES as exc:
            stage = "ir" if not events or events[-1][0] != "ir" else "backend"
            failure = self._failure(stage, exc)
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                failure=failure,
                execution=(
                    ExecutionStatusV4.ENGINE_ERROR if stage == "backend" else None
                ),
                interruption=(
                    InterruptionStateV4(failure.code, stage)
                    if stage == "backend"
                    else None
                ),
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=failure
            )
        if not executions:
            failure = _Failure("backend", "BACKEND_NO_EXECUTION")
            result = self._nonformal_result(
                request, run, run_identity_ref, pack, facts, selected, failure=failure
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=failure
            )
        events.append(("backend", executions[-1].receipt_ref))
        failed = next((item for item in executions if not item.completed), None)
        if failed is not None:
            status = failed.receipt.status
            if status in {"TIMEOUT", "RESOURCE_EXHAUSTED"}:
                execution_status = ExecutionStatusV4.RESOURCE_EXHAUSTED
            elif status == "UNSUPPORTED_SEMANTICS":
                execution_status = ExecutionStatusV4.UNSUPPORTED
            else:
                execution_status = ExecutionStatusV4.ENGINE_ERROR
            failure = _Failure("backend", f"BACKEND_{status}")
            interruption = (
                InterruptionStateV4(failure.code, "backend")
                if execution_status
                in {ExecutionStatusV4.RESOURCE_EXHAUSTED, ExecutionStatusV4.ENGINE_ERROR}
                else None
            )
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                failure=failure,
                execution=execution_status,
                interruption=interruption,
                backend_execution=failed,
                extra_receipts=(failed.receipt_ref,),
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=failure
            )
        primary = self._primary_execution(executions)
        if primary is None:
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                decision=DecisionStatusV4.UNKNOWN,
                execution=ExecutionStatusV4.COMPLETED,
                reasons=("composite_backend_semantics",),
                extra_receipts=tuple(item.receipt_ref for item in executions),
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=None
            )
        try:
            for execution_row in executions:
                if not self._backend_router.replay(execution_row, now=now):
                    raise BackendV4Error(
                        "BACKEND_REPLAY_MISMATCH", "backend replay did not reproduce semantic bytes"
                    )
            checked = self._checker.check(
                run_identity_ref=run_identity_ref,
                solver_receipt_ref=primary.receipt_ref,
                now=now,
            )
            events.append(("checker", checked.receipt_ref))
            argument = self._argument_outcome(primary, checked)
            events.append(("argument", checked.receipt.argument_graph_ref))
        except _EXPECTED_FAILURES as exc:
            stage = "checker" if not events or events[-1][0] != "checker" else "argument"
            failure = self._failure(stage, exc)
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                failure=failure,
                execution=ExecutionStatusV4.ENGINE_ERROR,
                interruption=InterruptionStateV4(failure.code, stage),
                backend_execution=primary,
                extra_receipts=(primary.receipt_ref,),
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=failure
            )
        if argument.state in {"empty", "missing"}:
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                decision=DecisionStatusV4.UNKNOWN,
                execution=ExecutionStatusV4.COMPLETED,
                backend_execution=primary,
                reasons=(f"argument_{argument.state}",),
                extra_receipts=(primary.receipt_ref, checked.receipt_ref),
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=None
            )
        try:
            result = self._formal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                compilations,
                primary,
                checked,
                argument,
                source_bundle,
                now=now,
            )
        except _EXPECTED_FAILURES as exc:
            failure = self._failure("result", exc)
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                failure=failure,
                execution=ExecutionStatusV4.ENGINE_ERROR,
                interruption=InterruptionStateV4(failure.code, "result"),
                backend_execution=primary,
                extra_receipts=(primary.receipt_ref, checked.receipt_ref),
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=failure
            )
        return self._finish(
            request, run, run_identity_ref, result, events, now=now, failure=None
        )


__all__ = ["ApplicationV4", "ApplicationV4Error"]
