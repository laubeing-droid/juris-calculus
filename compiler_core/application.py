"""The sole V4 formal evaluation spine."""

from __future__ import annotations

from base64 import b64decode
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
import errno
from threading import RLock

from compiler_core.argumentation import (
    ArgumentGraphV4,
    ArgumentationV4Error,
    AttackRecordV5,
    PermissionRelationV4,
    ProfileEvaluationV5,
    PRIORITY_POLICIES_V5,
    _effective_attacks_v4,
    _strict_preference_closure_v5,
    argument_ref_v4,
    evaluate_argument_graph,
    evaluate_profile_v5,
    priority_edge_decisions_v5,
    resolve_defeats_v5,
    verify_profile_family_v5,
)
from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.assurance import AssuranceV5Error, combine_assurance_v5
from compiler_core.audit_bundle import (
    AuditArtifactV4,
    AuditBundleV4Error,
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
    ATTACK_KIND_MIGRATION_V5,
    BranchResultV4,
    CanonicalTimeV4,
    CaseRequestV4,
    CertificateKindV4,
    ClaimResultV4,
    CompletenessStateV4,
    CompositionCandidateV5,
    ContentRefV4,
    ContractV4Error,
    DecisionStatusV4,
    ErrorV4,
    EvaluationEnvelopeV4,
    EvidenceManifestV4,
    ExecutionStatusV4,
    ExactExpressionV5,
    AssuranceEnvelopeV5,
    FactAttestationV4,
    FactCandidateV4,
    IncrementalParentV5,
    InterruptionStateV4,
    MissingFactRequirementV4,
    OpenObligationEntryV5,
    PriorityEdgeV4,
    ProcedureAuthorityV5,
    ProceduralInputV5,
    ProcedureResultV5,
    ProofReceiptV4,
    ResourceLimitsV4,
    ReviewStateV4,
    RuleV4,
    RunIdentityV4,
    RuntimeProfileV4,
    SemanticResultV4,
    LocalRecordV4,
    SignatureEnvelopeV4,
    SourceBundleV4,
    TransportOutcomeV4,
)
from compiler_core.domain_composition import (
    CompositionV5Error,
    evaluate_expression_v5,
    validate_composition_choice_v5,
)
from compiler_core.fact_admission import (
    ADMITTED_FACT_KIND,
    CASE_EVIDENCE_SCOPE,
    CASE_REQUEST_KIND,
    CASE_REQUEST_SCOPE,
    EVIDENCE_MANIFEST_KIND,
    FACT_ADMISSION_SCOPE,
    FACT_ATTESTATION_KIND,
    FACT_CANDIDATE_KIND,
    FACT_PROPOSITION_KIND,
    FACT_VALUE_KIND,
    LEGAL_APPROVAL_SCOPE,
    RUN_IDENTITY_KIND,
    RUN_IDENTITY_SCOPE,
    FactAdmissionServiceV4,
    case_request_binding_ref,
)
from compiler_core.procedure import BurdenRuleOutcomeV5, ProcedureV5Error, adjudicate_v5
from compiler_core.query_semantics import (
    GateStateV5,
    QueryInputV5,
    QueryRefutationV5,
    QuerySemanticsV5Error,
    QueryStatusV5,
    compose_branch_key_v5,
    evaluate_query_v5,
)
from compiler_core.independent_checker import (
    ARGUMENT_GRAPH_KIND,
    CHECKER_SCOPE,
    CheckerExecutionV4,
    IndependentCheckerV4,
    IndependentCheckerV4Error,
)
from compiler_core.incremental import (
    HornSubjectV5,
    horn_closure_with_metrics,
    incremental_horn_closure,
)
from compiler_core.legal_ir import LegalIRCompilationV4, LegalIRCompilerV4
from compiler_core.rule_packs import (
    JSON_MEDIA_TYPE,
    PACK_CONFIG_KIND,
    RULE_COMPONENT_SCOPE,
    RULE_CONCLUSION_KIND,
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
from compiler_core.storage import StorageV4Error
from compiler_core.trust import LocalRecordTrustV4, TrustVerifierV4


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

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        stage: str = "application",
        retryable: bool = False,
        correlation_id: str | None = None,
    ) -> None:
        self.code = code
        self.detail = detail
        self.stage = stage
        self.retryable = retryable
        self.correlation_id = correlation_id or digest_value({
            "stage": stage,
            "code": code,
        }).hex[:24]
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class _Failure:
    stage: str
    code: str
    retryable: bool


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
    graph: ArgumentGraphV4 | None = None


_EXPECTED_FAILURES = (
    AuditBundleV4Error,
    ContractV4Error,
    BackendV4Error,
    IndependentCheckerV4Error,
    ArgumentationV4Error,
    StorageV4Error,
    OSError,
)

_RETRYABLE_CODES = frozenset({
    "ADMISSION_DEADLINE",
    "AUDIT_IO",
    "AUDIT_QUOTA",
    "BACKEND_RESOURCE_EXHAUSTED",
    "BACKEND_TIMEOUT",
    "STORAGE_CAPACITY",
    "STORAGE_IO",
    "STORAGE_PERMISSION",
})

PROFILE_STAGE_KIND_V5 = "profile-stage-v5"
PROFILE_MAPPING_VERSION_V5 = "jc-aaf-mapping-v5/1"
PROFILE_STAGE_SCHEMA_V5 = "jc/profile-stage-v5/1.0"

HORN_SUBJECT_STATE_KIND_V5 = "horn-subject-state-v5"
HORN_SUBJECT_STATE_SCHEMA_V5 = "jc/horn-subject-state-v5/1.0"
HORN_MAPPING_VERSION_V5 = "jc-horn-mapping-v5/1"
HORN_SUBJECT_STATE_MAX_BYTES = 262_144

_V5_STAGE_ERRORS = (
    ArgumentationV4Error,
    QuerySemanticsV5Error,
    ProcedureV5Error,
    CompositionV5Error,
    AssuranceV5Error,
)


def _v5_scenario_ref(binding: DigestV4, query_id: str) -> DigestV4:
    """Scenario identity a public V5 query must cite for this request."""

    return digest_value({
        "request_binding": str(binding),
        "scenario_id": query_id,
        "assumptions": [],
    })


def _v5_branch_identity(
    request_id: str, profile: str, extension: frozenset[str]
) -> tuple[str, DigestV4]:
    """Deterministic branch id and branch ref for one evaluated extension.

    The branch ref digests the structured identity payload (scenario id,
    assumptions array, profile, sorted extension array); no field is ever
    flattened into a joined string, so ``{"a","b"}`` and ``{"a|b"}`` can never
    share an identity.
    """

    scenario_id, assumptions, profile_name, extension_items = compose_branch_key_v5(
        request_id, (), profile, extension
    )
    branch_ref = digest_value({
        "scenario_id": scenario_id,
        "assumptions": list(assumptions),
        "profile": profile_name,
        "extension": list(extension_items),
    })
    outcome_id = f"{profile}:{branch_ref.hex}"
    return outcome_id, branch_ref


def _exception_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if type(code) is str and code:
        return code
    if isinstance(exc, OSError):
        if exc.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)}:
            return "STORAGE_CAPACITY"
        if exc.errno in {errno.EACCES, errno.EPERM, errno.EROFS}:
            return "STORAGE_PERMISSION"
        return "STORAGE_IO"
    return "APPLICATION_STAGE_ERROR"


def _is_retryable(code: str) -> bool:
    return code in _RETRYABLE_CODES


def _correlation_id(
    run_identity_ref: ContentRefV4 | None,
    stage: str,
    code: str,
) -> str:
    return digest_value({
        "run_identity_ref": (
            None if run_identity_ref is None else run_identity_ref.to_dict()
        ),
        "stage": stage,
        "code": code,
    }).hex[:24]


def _v5_envelope(
    binding: DigestV4,
    profile: str,
    *,
    spec: str,
    run_check: str,
    obligations: tuple[OpenObligationEntryV5, ...],
    notices: tuple[OpenObligationEntryV5, ...],
) -> "AssuranceEnvelopeV5":
    """Build one ULM14 envelope for the V5 stage; implementation stays crossCheckOnly."""

    payload = {
        "scope_request_ref": str(binding),
        "scope_profile": profile,
        "spec": spec,
        "implementation": "crossCheckOnly",
        "run_check": run_check,
        "coverage_open_obligations": [item.to_dict() for item in obligations],
        "coverage_not_applicable": [],
        "pending_refs": [],
        "assumed_refs": [],
        "open_spec_refs": [],
        "formal_assumption_refs": [],
        "tcb_refs": [],
        "notices": [item.to_dict() for item in notices],
    }
    payload["assurance_digest"] = str(digest_value(payload))
    return AssuranceEnvelopeV5.from_dict(payload)


def _ref_key(reference: ContentRefV4) -> tuple[str, str]:
    return reference.kind, reference.digest.hex


@dataclass(frozen=True, slots=True)
class _V5StageOutcome:
    """What the V5 stage sealed for this run, beyond its artifact reference."""

    stage_ref: ContentRefV4
    mapping_coverage: str
    open_obligations: tuple[OpenObligationEntryV5, ...]
    mapping_obligations: tuple[OpenObligationEntryV5, ...]
    solver_incomplete: bool


@dataclass(frozen=True, slots=True)
class _HornStageOutcome:
    """What the Horn subject stage sealed for this run (ULM15 provenance)."""

    state_ref: ContentRefV4
    mode: str
    fallback_reason: str | None
    subject_digest: "DigestV4"
    parent: dict[str, object] | None
    solver_metrics: dict[str, int]
    checker_metrics: dict[str, int]


def _v5_typed_obligations(
    entries: tuple[object, ...],
) -> tuple[OpenObligationEntryV5, ...]:
    """Convert solver-shaped obligations to the typed V5 contract once.

    The bounded profile solver reports ``(code, detail)`` tuples; every V5
    boundary below this point (procedure, assurance, serialization) only ever
    sees :class:`OpenObligationEntryV5`.
    """

    typed: list[OpenObligationEntryV5] = []
    for item in entries:
        if type(item) is OpenObligationEntryV5:
            typed.append(item)
        elif (
            type(item) is tuple and len(item) == 2
            and type(item[0]) is str and type(item[1]) is str and item[0] and item[1]
        ):
            typed.append(OpenObligationEntryV5(item[0], item[1]))
        else:
            raise ContractV4Error(
                "APPLICATION_V5_STAGE",
                "solver open obligations must be (code, detail) pairs",
            )
    return tuple(typed)


def _v5_suppress_query_status(status: "QueryStatusV5") -> "QueryStatusV5":
    """Mapping-incomplete queries may not witness any completed answer."""

    return QueryStatusV5(
        status.query_id, status.profile,
        False, False, False, False, False, False, False,
        "incomplete", (), (),
    )


def _v5_verify_priority_mapping(
    arguments: tuple[str, ...],
    attacks: tuple[AttackRecordV5, ...],
    priority_pairs: tuple[tuple[str, str], ...],
    priority_policy_id: str,
    allowed_kinds: tuple[str, ...],
    published_defeats: tuple[tuple[str, str], ...],
) -> None:
    """Independently recompute the priority-modulated defeat set.

    This recheck re-derives the strategy's decision from the raw attack
    records and the strict preference closure without calling the production
    ``resolve_defeats_v5`` entry, so a mapping stage that silently drops or
    inverts an admitted priority relation cannot certify this request.
    """

    closure = _strict_preference_closure_v5(priority_pairs)
    known = set(arguments)
    expected = sorted({
        (attack.attacker, attack.target)
        for attack in attacks
        if attack.attacker in known and attack.target in known
        and attack.kind in allowed_kinds
        and not (attack.kind == "rebut" and (attack.target, attack.attacker) in closure)
    })
    if sorted(set(published_defeats)) != expected:
        raise ContractV4Error(
            "APPLICATION_V5_VERIFICATION",
            "independent priority mapping recheck rejected the defeat set",
        )


PROCEDURE_AUTHORIZATION_KIND_V5 = "procedure-authorization-v5"
PROCEDURE_AUTHORIZATION_SCHEMA_V5 = "jc/procedure-authorization-v5/1.0"
PROCEDURE_AUTHORIZATION_MAX_BYTES = 262_144


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
        default_limits: ResourceLimitsV4 | None = None,
    ) -> None:
        if default_limits is not None and type(default_limits) is not ResourceLimitsV4:
            raise ApplicationV4Error(
                "APPLICATION_DEPENDENCY", "default_limits must be ResourceLimitsV4"
            )
        if (
            type(resolver) is not ArtifactResolverV4
            or type(trust) not in (TrustVerifierV4, LocalRecordTrustV4)
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
        self._default_limits = default_limits
        self._execution_lock = RLock()

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
        code = _exception_code(exc)
        return _Failure(stage, code, _is_retryable(code))

    @staticmethod
    def _stop_failure(
        stage: str,
        *,
        cancel_check: Callable[[], bool] | None,
    ) -> _Failure | None:
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception:
                return _Failure(stage, "APPLICATION_CANCEL_CHECK", False)
            if type(cancelled) is not bool:
                return _Failure(stage, "APPLICATION_CANCEL_CHECK", False)
            if cancelled:
                return _Failure(stage, "APPLICATION_CANCELLED", False)
        return None

    def _resolve_input(
        self,
        request_ref: ContentRefV4,
        run_identity_ref: ContentRefV4,
        limits: ResourceLimitsV4,
    ) -> tuple[CaseRequestV4, RunIdentityV4]:
        try:
            request_raw = self._resolver.resolve_content(
                request_ref,
                expected_artifact_kind=CASE_REQUEST_KIND,
                expected_media_type=JSON_MEDIA_TYPE,
                expected_scope=CASE_REQUEST_SCOPE,
                max_bytes=min(
                    self._resolver.max_artifact_bytes,
                    limits.max_request_bytes,
                ),
            )
            request = CaseRequestV4.from_json_bytes(request_raw, limits=limits)
            if (
                request_raw != request.canonical_bytes()
                or request.canonical_digest() != request_ref.digest
            ):
                raise ContractV4Error(
                    "APPLICATION_ARTIFACT_BINDING",
                    "case request bytes differ from their reference",
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
            raise ApplicationV4Error(
                failure.code,
                "request or run identity did not resolve",
                stage=failure.stage,
                retryable=failure.retryable,
                correlation_id=_correlation_id(None, failure.stage, failure.code),
            ) from None
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
            return _Failure("trust", "TRUST_POLICY_MISMATCH", False)
        if now < policy.valid_from or (policy.valid_to is not None and not now < policy.valid_to):
            return _Failure("trust", "TRUST_POLICY_INACTIVE", False)
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
            if execution is None:
                if failure.code in {"APPLICATION_CANCELLED", "BACKEND_CANCELLED"}:
                    execution = ExecutionStatusV4.CANCELLED
                elif failure.code in {
                    "ADMISSION_DEADLINE",
                    "BACKEND_RESOURCE_EXHAUSTED",
                    "BACKEND_TIMEOUT",
                }:
                    execution = ExecutionStatusV4.RESOURCE_EXHAUSTED
                else:
                    execution = ExecutionStatusV4.ADMISSION_BLOCKED
            if execution in {
                ExecutionStatusV4.CANCELLED,
                ExecutionStatusV4.ENGINE_ERROR,
                ExecutionStatusV4.INTERRUPTED,
                ExecutionStatusV4.RESOURCE_EXHAUSTED,
            } and interruption is None:
                interruption = InterruptionStateV4(failure.code, failure.stage)
            decision = (
                DecisionStatusV4.ENGINE_ERROR
                if execution is ExecutionStatusV4.ENGINE_ERROR
                else DecisionStatusV4.BLOCKED
            )
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
            graph,
        )

    def _profile_stage_v5(
        self,
        request: CaseRequestV4,
        checked: CheckerExecutionV4,
        argument: _ArgumentOutcome,
        *,
        now: CanonicalTimeV4,
    ) -> "_V5StageOutcome":
        """Run the public V5 profile stage inside the sole formal spine.

        Takes the checker-verified argument graph of the current run, resolves
        defeats under the request's admitted policy (admitted priority
        relations participate through their registered priority policy or
        block completeness), evaluates every requested profile, gates each
        complete family through the independent definition-driven verifier,
        and derives query statuses, procedure consequences, same-branch
        composition and per-profile assurance envelopes. The deterministic
        stage document is registered as an auditable artifact and referenced
        from the run result.
        """

        graph = argument.graph
        if graph is None:
            raise ContractV4Error(
                "APPLICATION_V5_STAGE",
                "profile queries require the certified AAF argument provider",
            )
        policy = request.defeat_policy_v5
        queries = request.profile_queries_v5
        if policy is None or not queries:
            raise ContractV4Error(
                "APPLICATION_V5_STAGE", "profile stage requires policy and queries"
            )
        binding = case_request_binding_ref(request).digest
        try:
            if policy.request_ref != binding:
                raise ContractV4Error(
                    "APPLICATION_V5_STAGE",
                    "defeat_policy_v5 does not bind the request identity",
                )
            argument_ids = tuple(sorted(item.argument_id for item in graph.arguments))
            claim_by_argument = {
                item.argument_id: str(item.claim_ref.digest) for item in graph.arguments
            }
            known_claims = frozenset(claim_by_argument.values())
            known_query_ids = {query.query_id for query in queries}
            for query in queries:
                if query.mapping_version != PROFILE_MAPPING_VERSION_V5:
                    raise ContractV4Error(
                        "APPLICATION_V5_STAGE",
                        f"query {query.query_id!r} cites mapping {query.mapping_version!r}; "
                        f"this chain provides {PROFILE_MAPPING_VERSION_V5}",
                    )
                if query.scenario_ref != _v5_scenario_ref(binding, query.query_id):
                    raise ContractV4Error(
                        "APPLICATION_V5_STAGE",
                        f"query {query.query_id!r} cites a scenario outside this request",
                    )
                if query.claim not in known_claims:
                    raise ContractV4Error(
                        "APPLICATION_V5_STAGE",
                        f"query {query.query_id!r} claims an argument conclusion "
                        "outside the checked graph",
                    )
            for row in request.query_refutations_v5:
                if row.request_ref != binding:
                    raise ContractV4Error(
                        "APPLICATION_V5_STAGE",
                        f"refutation {row.refuter!r}->{row.target!r} does not bind "
                        "this request identity",
                    )
                if row.refuter not in known_claims or row.target not in known_claims:
                    raise ContractV4Error(
                        "APPLICATION_V5_STAGE",
                        f"refutation {row.refuter!r}->{row.target!r} cites a claim "
                        "outside the checked graph",
                    )
            for gate_row in request.query_gates_v5:
                if gate_row.query_id not in known_query_ids:
                    raise ContractV4Error(
                        "APPLICATION_V5_STAGE",
                        f"gate cites unknown query {gate_row.query_id!r}",
                    )
            procedural = request.procedural_input_v5
            if procedural is not None and procedural.request_ref != binding:
                raise ContractV4Error(
                    "APPLICATION_V5_STAGE",
                    "procedural_input_v5 does not bind the request identity",
                )

            id_by_ref = {
                argument_ref_v4(item): item.argument_id for item in graph.arguments
            }
            effective = _effective_attacks_v4(graph)
            attacks: list[AttackRecordV5] = []
            derived_priority_attacks = 0
            for attack in effective:
                kind = ATTACK_KIND_MIGRATION_V5.get(attack.attack_type)
                if kind is None:
                    derived_priority_attacks += 1
                    continue
                attacks.append(AttackRecordV5(
                    attack.attack_id,
                    id_by_ref[attack.attacker_ref],
                    id_by_ref[attack.target_ref],
                    kind,
                    attack.attack_id,
                ))
            priority_pairs = tuple(
                (
                    id_by_ref[edge.preferred_ref],
                    id_by_ref[edge.defeated_ref],
                )
                for edge in graph.priority_edges
            )
            if derived_priority_attacks != len(priority_pairs):
                raise ContractV4Error(
                    "APPLICATION_V5_STAGE",
                    "derived priority attacks and graph priority edges disagree",
                )

            # Priority relations participate only through a registered policy;
            # anything the build cannot explain becomes a formal mapping
            # obligation that blocks completeness claims for this request.
            mapping_obligations: list[OpenObligationEntryV5] = []
            priority_decisions: tuple[dict[str, object], ...] = ()
            defeats = resolve_defeats_v5(
                argument_ids,
                tuple(attacks),
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                allowed_kinds=policy.allowed_kinds,
                request_ref=str(binding),
            )
            if priority_pairs:
                declared = policy.priority_policy_id
                if declared is None:
                    mapping_obligations.append(OpenObligationEntryV5(
                        "priority_policy_missing",
                        f"{len(priority_pairs)} admitted priority relations have no "
                        "registered priority policy in the defeat policy",
                    ))
                elif declared not in PRIORITY_POLICIES_V5:
                    mapping_obligations.append(OpenObligationEntryV5(
                        "priority_policy_unsupported",
                        f"priority policy {declared!r} is not registered in this "
                        "build; the defeat mapping is not coverage-complete",
                    ))
                else:
                    try:
                        defeats = resolve_defeats_v5(
                            argument_ids,
                            tuple(attacks),
                            policy_id=policy.policy_id,
                            policy_version=policy.policy_version,
                            allowed_kinds=policy.allowed_kinds,
                            request_ref=str(binding),
                            priority_edges=priority_pairs,
                            priority_policy_id=declared,
                        )
                        priority_decisions = priority_edge_decisions_v5(
                            argument_ids, tuple(attacks), priority_pairs, declared,
                        )
                    except ArgumentationV4Error as exc:
                        mapping_obligations.append(OpenObligationEntryV5(
                            "priority_policy_unresolved",
                            f"{exc.code}: {exc.detail}",
                        ))
                    else:
                        _v5_verify_priority_mapping(
                            argument_ids,
                            tuple(attacks),
                            priority_pairs,
                            declared,
                            policy.allowed_kinds,
                            defeats,
                        )
            mapping_incomplete = bool(mapping_obligations)

            profiles = sorted({query.profile for query in queries})
            evaluations: dict[str, ProfileEvaluationV5] = {}
            for profile in profiles:
                evaluation = evaluate_profile_v5(profile, argument_ids, defeats)
                evaluations[profile] = evaluation
                if evaluation.claims_complete_family:
                    verified, reason = verify_profile_family_v5(
                        profile,
                        argument_ids,
                        defeats,
                        evaluation.extensions,
                        coverage="exact",
                    )
                    if not verified:
                        raise ContractV4Error(
                            "APPLICATION_V5_VERIFICATION",
                            f"independent verification rejected the {profile} "
                            f"family ({reason}); refusing to certify the solve",
                        )

            notices: list[OpenObligationEntryV5] = []

            query_rows: list[dict[str, object]] = []
            procedure_rows: list[dict[str, object]] = []
            envelope_by_profile: dict[str, AssuranceEnvelopeV5] = {}
            candidates: list[CompositionCandidateV5] = []
            solver_incomplete_profiles: set[str] = set()
            for profile in profiles:
                evaluation = evaluations[profile]
                for extension in evaluation.extensions:
                    outcome_id, branch_ref = _v5_branch_identity(
                        request.request_id, profile, extension
                    )
                    candidates.append(CompositionCandidateV5(
                        outcome_id, binding, branch_ref,
                    ))
            refutations = tuple(
                QueryRefutationV5(row.refuter, row.target)
                for row in request.query_refutations_v5
            )
            gates_by_query: dict[str, tuple[GateStateV5, ...]] = {}
            branch_refs_by_profile: dict[str, list[DigestV4]] = {}
            for profile in profiles:
                branch_refs_by_profile[profile] = [
                    _v5_branch_identity(request.request_id, profile, extension)[1]
                    for extension in evaluations[profile].extensions
                ]
            for gate_row in request.query_gates_v5:
                # Gate binding happens here, against the evaluated families of
                # this very request; a stale or foreign branch digest is an
                # admission violation, never a silent no-op.
                profile_of_query = next(
                    query.profile for query in queries
                    if query.query_id == gate_row.query_id
                )
                family = branch_refs_by_profile[profile_of_query]
                if gate_row.branch_digest is None:
                    branch_indexes = tuple(range(len(family)))
                else:
                    branch_indexes = tuple(
                        index for index, ref in enumerate(family)
                        if ref == gate_row.branch_digest
                    )
                    if not branch_indexes:
                        raise ContractV4Error(
                            "APPLICATION_V5_STAGE",
                            f"gate for {gate_row.query_id!r} cites a branch outside "
                            "this request's evaluated family",
                        )
                current = gates_by_query.get(gate_row.query_id)
                if current is None:
                    current = tuple(
                        GateStateV5(index, "enterable") for index in range(len(family))
                    )
                for index in branch_indexes:
                    replaced = GateStateV5(
                        index, gate_row.gate, gate_row.reason,
                    )
                    current = tuple(
                        replaced if item.branch_index == index else item
                        for item in current
                    )
                gates_by_query[gate_row.query_id] = current

            authorization_verified = False
            if procedural is not None and procedural.authority is not None:
                authorization_verified = self._verify_procedure_authorization(
                    procedural, binding, now=now,
                )
            for query in queries:
                evaluation = evaluations[query.profile]
                if evaluation.kind == "incomplete":
                    solver_incomplete_profiles.add(query.profile)
                status = evaluate_query_v5(QueryInputV5(
                    query_id=query.query_id,
                    claim=query.claim,
                    profile=query.profile,
                    evaluation=evaluation,
                    argument_claims=claim_by_argument,
                    refutations=refutations,
                    gates=gates_by_query.get(query.query_id, ()),
                ))
                if mapping_incomplete:
                    # An unmapped priority relation can change which attacks
                    # survive, so no branch status of this request may carry a
                    # completed query answer.
                    status = _v5_suppress_query_status(status)
                query_rows.append({
                    "query_id": query.query_id,
                    "profile": query.profile,
                    "claim": query.claim,
                    "branch_refs": [
                        str(ref) for ref in branch_refs_by_profile[query.profile]
                    ],
                    **{
                        field: getattr(status, field)
                        for field in (
                            "common", "possible", "common_refuted", "possibly_refuted",
                            "undecided_some", "inconsistent_some", "excluded", "gate",
                        )
                    },
                    "acceptance_witnesses": list(status.acceptance_witnesses),
                    "refutation_witnesses": list(status.refutation_witnesses),
                    "mapping_incomplete": mapping_incomplete,
                })
                typed_obligations = _v5_typed_obligations(
                    evaluation.open_obligations
                )
                procedure = adjudicate_v5(
                    request_ref=binding,
                    evaluation_kind=evaluation.kind,
                    evaluation_open_obligations=typed_obligations,
                    procedural_status=(
                        None if procedural is None else procedural.procedural_status
                    ),
                    authority=None if procedural is None else procedural.authority,
                    authorization_verified=authorization_verified,
                    rule_outcomes=(
                        None if procedural is None or procedural.rule_outcomes is None
                        else BurdenRuleOutcomeV5(
                            satisfied_status=procedural.rule_outcomes.satisfied_status,
                            failure_status=procedural.rule_outcomes.failure_status,
                        )
                    ),
                )
                if mapping_incomplete and procedure.kind in {
                    "adjudicated_status", "procedural_disposition",
                }:
                    procedure = ProcedureResultV5(
                        request_ref=procedure.request_ref,
                        kind="pending_legal_judgment",
                        status=None,
                        missing=("v5-mapping-incomplete",),
                        open_obligations=(),
                        authority_ref=None,
                    )
                elif mapping_incomplete and procedure.kind == "pending_legal_judgment":
                    procedure = ProcedureResultV5(
                        request_ref=procedure.request_ref,
                        kind="pending_legal_judgment",
                        status=None,
                        missing=(*procedure.missing, "v5-mapping-incomplete"),
                        open_obligations=(),
                        authority_ref=None,
                    )
                elif mapping_incomplete and procedure.kind == "solver_incomplete":
                    procedure = ProcedureResultV5(
                        request_ref=procedure.request_ref,
                        kind="solver_incomplete",
                        status=None,
                        missing=(),
                        open_obligations=(
                            *procedure.open_obligations, *mapping_obligations,
                        ),
                        authority_ref=None,
                    )
                procedure_rows.append({
                    "query_id": query.query_id,
                    **procedure.to_dict(),
                })
                profile_obligations = (
                    (*typed_obligations, *mapping_obligations)
                    if evaluation.kind == "incomplete"
                    else tuple(mapping_obligations)
                )
                envelope = _v5_envelope(
                    binding,
                    query.profile,
                    spec=(
                        "openObligations"
                        if profile_obligations else "proved"
                    ),
                    run_check="checked",
                    obligations=profile_obligations,
                    notices=tuple(notices),
                )
                previous = envelope_by_profile.get(query.profile)
                envelope_by_profile[query.profile] = (
                    envelope if previous is None
                    else combine_assurance_v5(previous, envelope)
                )

            composition_document: dict[str, object] | None = None
            if request.composition_choice_v5 is not None:
                choice = request.composition_choice_v5
                policy_v5 = request.composition_policy_v5
                expression = request.composition_expression_v5
                if policy_v5 is None or expression is None:
                    raise ContractV4Error(
                        "APPLICATION_V5_STAGE",
                        "composition choice requires its policy and expression",
                    )
                if policy_v5.request_ref != binding or choice.request_ref != binding:
                    raise ContractV4Error(
                        "APPLICATION_V5_STAGE",
                        "composition policy or choice does not bind the request identity",
                    )
                validate_composition_choice_v5(
                    tuple(candidates),
                    policy_v5,
                    choice,
                    allowed_outcome_ids=frozenset(item.outcome_id for item in candidates),
                )
                operands: dict[str, ExactExpressionV5] = {}
                for node in request.composition_operands_v5:
                    key = str(node.canonical_digest())
                    if key in operands:
                        raise ContractV4Error(
                            "APPLICATION_V5_STAGE", "composition operands repeat a digest"
                        )
                    operands[key] = node
                exact = evaluate_expression_v5(expression, operands)
                rounding: tuple[OpenObligationEntryV5, ...] = (
                    (OpenObligationEntryV5(
                        "rounding_required", "exact result is not integral"
                    ),)
                    if exact.rounding_required else ()
                )
                composition_document = {
                    "outcome_ids": sorted(item.outcome_id for item in choice.selected),
                    "value": exact.value.to_dict(),
                    "rounding_required": exact.rounding_required,
                    "open_obligations": [item.to_dict() for item in rounding],
                }
                if rounding:
                    for profile in list(envelope_by_profile):
                        merged = envelope_by_profile[profile]
                        for obligation in rounding:
                            merged = combine_assurance_v5(
                                merged,
                                _v5_envelope(
                                    binding,
                                    profile,
                                    spec="openObligations",
                                    run_check="checked",
                                    obligations=(obligation,),
                                    notices=(),
                                ),
                            )
                        envelope_by_profile[profile] = merged

            stage_document = {
                "schema_version": PROFILE_STAGE_SCHEMA_V5,
                "request_binding": str(binding),
                "mapping_version": PROFILE_MAPPING_VERSION_V5,
                "argument_graph_ref": checked.receipt.argument_graph_ref.to_dict(),
                "defeat_policy": policy.to_dict(),
                "arguments": list(argument_ids),
                "attacks": sorted(
                    [item.attacker, item.target, item.kind] for item in attacks
                ),
                "defeats": [list(pair) for pair in defeats],
                "priority": {
                    "edges": [list(pair) for pair in priority_pairs],
                    "policy": (
                        None if policy.priority_policy_id is None
                        else policy.priority_policy_id
                    ),
                    "decisions": [dict(row) for row in priority_decisions],
                },
                "mapping_coverage": {
                    "status": "incomplete" if mapping_incomplete else "complete",
                    "open_obligations": [
                        item.to_dict() for item in mapping_obligations
                    ],
                },
                "profiles": {
                    profile: {
                        "kind": evaluations[profile].kind,
                        "extensions": [
                            sorted(extension)
                            for extension in evaluations[profile].extensions
                        ],
                        "open_obligations": [
                            item.to_dict()
                            for item in _v5_typed_obligations(
                                evaluations[profile].open_obligations
                            )
                        ],
                        "verification": {
                            "coverage": (
                                "exact"
                                if evaluations[profile].claims_complete_family
                                else "incomplete"
                            ),
                            "verified": evaluations[profile].claims_complete_family,
                            "reason": "",
                            "mapping": (
                                "incomplete" if mapping_incomplete else "complete"
                            ),
                        },
                        "assurance": envelope_by_profile[profile].to_dict(),
                    }
                    for profile in profiles
                },
                "queries": query_rows,
                "procedures": procedure_rows,
                "composition": composition_document,
            }
        except _V5_STAGE_ERRORS as exc:
            raise ContractV4Error("APPLICATION_V5_STAGE", str(exc)) from exc
        raw = canonical_bytes(stage_document)
        reference = ContentRefV4(PROFILE_STAGE_KIND_V5, DigestV4.from_bytes(raw))
        stage_ref = self._resolver.register_bytes(
            artifact_id=f"{PROFILE_STAGE_KIND_V5}-{reference.digest.hex}",
            content_ref=reference,
            artifact_kind=PROFILE_STAGE_KIND_V5,
            media_type=JSON_MEDIA_TYPE,
            scope=CHECKER_SCOPE,
            content=raw,
        )
        solver_obligations = tuple(
            obligation
            for profile in sorted(solver_incomplete_profiles)
            for obligation in _v5_typed_obligations(
                evaluations[profile].open_obligations
            )
        )
        return _V5StageOutcome(
            stage_ref=stage_ref,
            mapping_coverage="incomplete" if mapping_incomplete else "complete",
            open_obligations=(*mapping_obligations, *solver_obligations),
            mapping_obligations=tuple(mapping_obligations),
            solver_incomplete=bool(solver_incomplete_profiles),
        )

    def _horn_universe(self, pack: VerifiedRulePackV4) -> frozenset[str]:
        """The fixed finite fact-key universe declared by the verified pack."""

        keys: set[str] = set()
        for rule in pack.rules:
            for premise_ref in rule.premise_refs:
                premise = self._document(
                    premise_ref,
                    kind=RULE_PREMISE_KIND,
                    scope=RULE_COMPONENT_SCOPE,
                )
                if premise.get("required") is True and type(premise.get("fact_key")) is str:
                    keys.add(premise["fact_key"])
            conclusion = self._document(
                rule.conclusion_ref,
                kind=RULE_CONCLUSION_KIND,
                scope=RULE_COMPONENT_SCOPE,
            )
            head = conclusion.get("fact_key")
            if type(head) is str and head:
                keys.add(head)
        return frozenset(keys)

    def _horn_true_fact_keys(self, facts: _FactState) -> frozenset[str]:
        """Fact keys admitted with boolean-true values for this run."""

        keys: set[str] = set()
        for fact_ref in facts.admitted_refs:
            document = self._document(
                fact_ref,
                kind=ADMITTED_FACT_KIND,
                scope=FACT_ADMISSION_SCOPE,
            )
            if document.get("value_kind") != "boolean":
                continue
            proposition = self._document(
                ContentRefV4.from_dict(document["proposition_ref"]),
                kind=FACT_PROPOSITION_KIND,
                scope=FACT_ADMISSION_SCOPE,
            )
            value = self._document(
                ContentRefV4.from_dict(document["value_ref"]),
                kind=FACT_VALUE_KIND,
                scope=FACT_ADMISSION_SCOPE,
            )
            if (
                proposition.get("schema_version") == "jc/fact-proposition/1.0"
                and value.get("schema_version") == "jc/fact-value/1.0"
                and value.get("value") is True
                and type(proposition.get("proposition")) is str
            ):
                keys.add(proposition["proposition"])
        return frozenset(keys)

    def _horn_parent_state_document(
        self,
        parent: "IncrementalParentV5",
        *,
        case_scope: str,
        now: CanonicalTimeV4,
    ) -> tuple[dict[str, object] | None, str]:
        """Load and bind-check a reusable parent Horn state (ULM15).

        The state is read from the live resolver first, then from the sealed
        audit bundle of the referenced parent run, so a later process with
        only the persisted store can still reuse it. Binding, case scope,
        run identity, mapping version and the self-digest of the subject are
        all verified before any reuse; a forged or foreign reference is a
        recorded fallback, never a silent cache hit.
        """

        def _bound(document: dict[str, object]) -> dict[str, object] | None:
            if (
                document.get("schema_version") != HORN_SUBJECT_STATE_SCHEMA_V5
                or document.get("status") != "verified_complete"
                or document.get("case_scope") != case_scope
                or document.get("mapping_version") != HORN_MAPPING_VERSION_V5
            ):
                return None
            try:
                run_ref = ContentRefV4.from_dict(document["run_identity_ref"])
            except (KeyError, TypeError, ValueError):
                return None
            if run_ref != parent.parent_run_ref:
                return None
            parent_subject = HornSubjectV5.build(
                universe=frozenset(str(item) for item in document["universe"]),
                facts=frozenset(str(item) for item in document["facts"]),
                rules=tuple(
                    (str(head), tuple(str(atom) for atom in body))
                    for head, body, _rule_id in document["rules"]
                ),
            )
            if str(parent_subject.subject_digest) != str(parent.parent_subject_digest):
                return None
            if document.get("subject_digest") != str(parent_subject.subject_digest):
                return None
            return document

        try:
            raw = self._resolver.resolve_content(
                parent.parent_state_ref,
                expected_artifact_kind=HORN_SUBJECT_STATE_KIND_V5,
                expected_media_type=JSON_MEDIA_TYPE,
                expected_scope=CHECKER_SCOPE,
                max_bytes=HORN_SUBJECT_STATE_MAX_BYTES,
            )
            document = parse_json_document(raw)
            if type(document) is dict:
                bound = _bound(document)
                if bound is not None:
                    return bound, ""
        except (ContractV4Error, ValueError):
            pass
        try:
            capability = self._audit_store.capability_for(parent.parent_run_ref)
            verified = self._audit_store.verify_run(capability, now=now)
        except (AuditBundleV4Error, ContractV4Error, StorageV4Error, OSError):
            return None, "parent_state_unavailable"
        for name in sorted(verified.files):
            try:
                payload = parse_json_document(verified.files[name])
            except ValueError:
                continue
            if type(payload) is not dict or type(payload.get("artifacts")) is not list:
                continue
            for row in payload["artifacts"]:
                if type(row) is not dict or row.get("artifact_kind") != HORN_SUBJECT_STATE_KIND_V5:
                    continue
                try:
                    reference = ContentRefV4.from_dict(row.get("content_ref"))
                except (TypeError, ValueError):
                    continue
                if reference != parent.parent_state_ref:
                    continue
                try:
                    content = b64decode(row["content_base64"], validate=True)
                except (KeyError, ValueError, TypeError):
                    continue
                document = parse_json_document(content)
                if type(document) is dict:
                    bound = _bound(document)
                    if bound is not None:
                        return bound, ""
        return None, "parent_state_unavailable"

    def _horn_subject_stage_v5(
        self,
        request: CaseRequestV4,
        run: RunIdentityV4,
        run_identity_ref: ContentRefV4,
        pack: VerifiedRulePackV4,
        facts: _FactState,
        selected: tuple[tuple[ContentRefV4, RuleV4, tuple[str, ...]], ...],
        *,
        case_scope: str,
    ) -> "_HornStageOutcome":
        """Compute, reuse and seal the Horn subject state of this run (ULM15).

        First run or an ineligible parent computes the closure with the full
        scan; a qualified add-only child of a completed, verified parent run
        extends the parent closure through the incremental worklist. Either
        way the independent full recomputation of the same child subject must
        equal the produced closure or the run fails closed. The sealed state
        artifact records the mode, the parent/child binding, the fallback
        reason and the deterministic solver/checker workload counts.
        """

        true_facts = self._horn_true_fact_keys(facts)
        horn_rules: list[tuple[str, str, tuple[str, ...]]] = []
        for _reference, rule, requirements in selected:
            if rule.modality != "CONSTITUTIVE":
                continue
            conclusion = self._document(
                rule.conclusion_ref,
                kind=RULE_CONCLUSION_KIND,
                scope=RULE_COMPONENT_SCOPE,
            )
            head = conclusion.get("fact_key")
            if type(head) is not str or not head:
                continue
            horn_rules.append((rule.rule_id, head, requirements))
        universe = self._horn_universe(pack) | true_facts
        subject = HornSubjectV5.build(
            universe=universe,
            facts=true_facts,
            rules=tuple(
                (head, body) for _rule_id, head, body in horn_rules
            ),
        )

        mode = "full_recompute"
        fallback_reason: str | None = "no_parent_reference"
        parent_row: dict[str, object] | None = None
        parent_closure: frozenset[str] | None = None
        parent_rules: tuple[tuple[str, tuple[str, ...]], ...] = ()
        added_facts: frozenset[str] = frozenset()
        added_rules: tuple[tuple[str, tuple[str, ...]], ...] = ()
        parent_input = request.incremental_parent_v5
        if parent_input is not None:
            if parent_input.mode == "force_full":
                fallback_reason = "forced_full_diagnostic"
            else:
                document, unavailable_reason = self._horn_parent_state_document(
                    parent_input, case_scope=case_scope, now=self._clock(),
                )
                if document is None:
                    fallback_reason = unavailable_reason or "parent_state_unavailable"
                else:
                    parent_facts = frozenset(str(item) for item in document["facts"])
                    parent_rule_rows = tuple(
                        (str(head), tuple(str(atom) for atom in body))
                        for head, body, _rule_id in document["rules"]
                    )
                    parent_universe = frozenset(
                        str(item) for item in document["universe"]
                    )
                    if parent_facts - set(subject.facts):
                        fallback_reason = "fact_deletion"
                    elif set(parent_rule_rows) - set(subject.rules):
                        fallback_reason = "rule_rewrite_or_removal"
                    elif parent_universe != set(subject.universe):
                        fallback_reason = "universe_growth"
                    else:
                        mode = "incremental"
                        fallback_reason = None
                        parent_closure = frozenset(
                            str(item) for item in document["closure"]
                        )
                        parent_rules = parent_rule_rows
                        added_facts = frozenset(subject.facts) - parent_facts
                        added_rules = tuple(
                            rule for rule in subject.rules
                            if rule not in set(parent_rule_rows)
                        )
                        parent_row = {
                            "run_ref": parent_input.parent_run_ref.to_dict(),
                            "state_ref": parent_input.parent_state_ref.to_dict(),
                            "subject_digest": str(parent_input.parent_subject_digest),
                        }

        if mode == "incremental" and parent_closure is not None:
            closure, solver_metrics = incremental_horn_closure(
                parent_closure, parent_rules, added_facts, added_rules,
            )
        else:
            closure, solver_metrics = horn_closure_with_metrics(subject)
        checker_closure, checker_metrics = horn_closure_with_metrics(subject)
        if closure != checker_closure:
            raise ContractV4Error(
                "APPLICATION_HORN_INCREMENTAL_MISMATCH",
                "the Horn closure differs from the independent full recomputation",
            )

        state_document = {
            "schema_version": HORN_SUBJECT_STATE_SCHEMA_V5,
            "status": "verified_complete",
            "case_scope": case_scope,
            "run_identity_ref": run_identity_ref.to_dict(),
            "request_binding": str(case_request_binding_ref(request).digest),
            "mapping_version": HORN_MAPPING_VERSION_V5,
            "subject_digest": str(subject.subject_digest),
            "universe": sorted(subject.universe),
            "facts": sorted(subject.facts),
            "rules": [
                [head, list(body), rule_id]
                for rule_id, head, body in sorted(horn_rules)
            ],
            "closure": sorted(closure),
            "mode": mode,
            "fallback_reason": fallback_reason,
            "parent": parent_row,
            "solver_metrics": dict(solver_metrics),
            "checker_metrics": dict(checker_metrics),
        }
        raw = canonical_bytes(state_document)
        reference = ContentRefV4(
            HORN_SUBJECT_STATE_KIND_V5, DigestV4.from_bytes(raw),
        )
        state_ref = self._resolver.register_bytes(
            artifact_id=f"{HORN_SUBJECT_STATE_KIND_V5}-{reference.digest.hex}",
            content_ref=reference,
            artifact_kind=HORN_SUBJECT_STATE_KIND_V5,
            media_type=JSON_MEDIA_TYPE,
            scope=CHECKER_SCOPE,
            content=raw,
        )
        return _HornStageOutcome(
            state_ref=state_ref,
            mode=mode,
            fallback_reason=fallback_reason,
            subject_digest=subject.subject_digest,
            parent=parent_row,
            solver_metrics=solver_metrics,
            checker_metrics=checker_metrics,
        )

    def _verify_procedure_authorization(
        self,
        procedural: "ProceduralInputV5",
        binding: DigestV4,
        *,
        now: CanonicalTimeV4,
    ) -> bool:
        """Verify the referenced authorization artifact through trust.

        The wire never carries verification: the authority's authorization
        reference must resolve to a stored, self-consistent document whose
        legal-approval signature verifies under the active trust policy and
        whose findings match the request's authority row. Any failure leaves
        the authority unverified, which routes the procedure to the pending
        state — never to an adjudicated status.
        """

        authority = procedural.authority
        if authority is None or authority.request_ref != binding:
            return False
        try:
            raw = self._resolver.resolve_content(
                ContentRefV4(
                    PROCEDURE_AUTHORIZATION_KIND_V5, authority.authorization_ref,
                ),
                expected_artifact_kind=PROCEDURE_AUTHORIZATION_KIND_V5,
                expected_media_type=JSON_MEDIA_TYPE,
                expected_scope=LEGAL_APPROVAL_SCOPE,
                max_bytes=PROCEDURE_AUTHORIZATION_MAX_BYTES,
            )
            document = parse_json_document(raw)
        except (ContractV4Error, ValueError):
            return False
        if type(document) is not dict:
            return False
        if document.get("schema_version") != PROCEDURE_AUTHORIZATION_SCHEMA_V5:
            return False
        signature_row = document.get("signature")
        body = {key: value for key, value in document.items() if key != "signature"}
        expected_digest = digest_value(body)
        if (
            document.get("request_ref") != str(binding)
            or document.get("burden_rule_ref") != authority.burden_rule_ref
            or document.get("finding") != authority.finding
            or document.get("reviewer") != authority.reviewer
        ):
            return False
        try:
            signature = SignatureEnvelopeV4.from_dict(signature_row)
        except (ContractV4Error, TypeError):
            return False
        if (
            signature.subject_digest != expected_digest
            or signature.payload_digest != expected_digest
        ):
            return False
        try:
            self._trust._fresh_without_replay().verify(
                signature,
                expected_subject_digest=expected_digest,
                expected_payload_digest=expected_digest,
                required_role="legal_reviewer",
                required_scope="legal-approval",
                required_artifact_kind="legal-approval",
                expected_status="APPROVED",
                now=now,
                separation_from_principals=(),
            )
        except ContractV4Error:
            return False
        return True

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
        if type(signature) not in (SignatureEnvelopeV4, LocalRecordV4):
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
        v5_stage: "_V5StageOutcome | None" = None,
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
        v5_reasons: tuple[str, ...] = ()
        v5_completeness = CompletenessStateV4.COMPLETE
        if v5_stage is not None:
            if v5_stage.mapping_coverage == "incomplete":
                v5_completeness = CompletenessStateV4.PARTIAL
                v5_reasons = (*v5_reasons, "v5_mapping_incomplete")
            if v5_stage.solver_incomplete:
                v5_completeness = CompletenessStateV4.PARTIAL
                v5_reasons = (*v5_reasons, "v5_solver_incomplete")
        certificate_kind = (
            CertificateKindV4.CONFLICT_VERIFIED
            if conflict
            else CertificateKindV4.FORMAL_VERIFIED
        )
        if v5_completeness is CompletenessStateV4.PARTIAL:
            # A certificate asserts complete untainted verification; an open
            # V5 mapping or solver coverage downgrades the run to partial and
            # the sealed answer carries no certificate.
            certificate_kind = CertificateKindV4.NONE
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
            completeness=v5_completeness,
            interruption=None,
            certificate=certificate_kind,
            claims=tuple(claims),
            admitted_fact_refs=facts.admitted_refs,
            rejected_fact_refs=facts.rejected_refs,
            applicable_rule_refs=applicable,
            inapplicable_rule_refs=tuple(set(pack.manifest.rule_refs) - set(applicable)),
            argument_refs=argument.argument_refs,
            attack_refs=argument.attack_refs,
            exception_resolution_refs=argument.exception_refs,
            permission_resolution_refs=argument.permission_refs,
            decision_reason_codes=(
                ("argument_conflict",) if conflict else ()
            ) + v5_reasons,
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
            snapshot = self._resolver._active_snapshot.get()
            records = dict(self._resolver._by_ref if snapshot is None else snapshot)
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
        try:
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
        except (AuditBundleV4Error, ContractV4Error, StorageV4Error, OSError) as exc:
            code = _exception_code(exc)
            raise ApplicationV4Error(
                code,
                f"formal audit storage failed: {exc}" + "",
                stage="audit",
                retryable=_is_retryable(code),
                correlation_id=_correlation_id(run_identity_ref, "audit", code),
            ) from None
        if failure is None:
            transport = TransportOutcomeV4("success", None)
        else:
            transport = TransportOutcomeV4(
                "error",
                ErrorV4(
                    failure.code,
                    f"formal evaluation stopped at {failure.stage}",
                    failure.stage,
                    failure.retryable,
                    _correlation_id(run_identity_ref, failure.stage, failure.code),
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

        with self._execution_lock:
            return self._evaluate(
                request_ref,
                run_identity_ref,
                case_scope=case_scope,
                limits=limits,
                seed=seed,
                cancel_check=cancel_check,
            )

    def _evaluate(
        self,
        request_ref: ContentRefV4,
        run_identity_ref: ContentRefV4,
        *,
        case_scope: str,
        limits: ResourceLimitsV4 | None = None,
        seed: int = 0,
        cancel_check: Callable[[], bool] | None = None,
    ) -> EvaluationEnvelopeV4:
        if (
            type(request_ref) is not ContentRefV4
            or type(run_identity_ref) is not ContentRefV4
            or type(case_scope) is not str
            or not case_scope
            or type(seed) is not int
            or (cancel_check is not None and not callable(cancel_check))
        ):
            raise ApplicationV4Error(
                "APPLICATION_INPUT_TYPE",
                "evaluation context is invalid",
                stage="resolver",
            )
        admitted_limits = (
            self._default_limits if limits is None and self._default_limits is not None
            else ResourceLimitsV4() if limits is None
            else limits
        )
        if type(admitted_limits) is not ResourceLimitsV4:
            raise ApplicationV4Error(
                "APPLICATION_INPUT_TYPE",
                "limits must be ResourceLimitsV4",
                stage="resolver",
            )
        now = self._clock()
        if type(now) is not CanonicalTimeV4:
            raise ApplicationV4Error(
                "APPLICATION_CLOCK",
                "clock returned a non-canonical time",
                stage="trust",
            )
        request, run = self._resolve_input(
            request_ref,
            run_identity_ref,
            admitted_limits,
        )
        events: list[tuple[str, ContentRefV4]] = [("resolver", request_ref)]

        failure = self._trust_failure(run, now)
        failure = failure or self._stop_failure(
            "trust", cancel_check=cancel_check
        )
        events.append(("trust", run_identity_ref))
        source_bundle, applicable_source, source_failure = self._source_and_evidence(
            request,
            case_scope=case_scope,
            now=now,
        )
        failure = failure or source_failure
        failure = failure or self._stop_failure(
            "source", cancel_check=cancel_check
        )
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
        failure = failure or self._stop_failure(
            "fact", cancel_check=cancel_check
        )
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
        failure = failure or self._stop_failure(
            "pack", cancel_check=cancel_check
        )
        events.append(("pack", request.rule_pack_ref))
        if failure is not None or pack is None or source_bundle is None:
            failure = failure or _Failure("pack", "PACK_NOT_VERIFIED", False)
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
            horn_stage = self._horn_subject_stage_v5(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                case_scope=case_scope,
            )
            events.append(("horn-subject-v5", horn_stage.state_ref))
        except _EXPECTED_FAILURES as exc:
            failure = self._failure("horn-subject-v5", exc)
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                failure=failure,
                execution=ExecutionStatusV4.ENGINE_ERROR,
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=failure
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
            execution_status = None
            if stage == "backend":
                if failure.code == "BACKEND_CANCELLED":
                    execution_status = ExecutionStatusV4.CANCELLED
                elif failure.code in {"BACKEND_RESOURCE_EXHAUSTED", "BACKEND_TIMEOUT"}:
                    execution_status = ExecutionStatusV4.RESOURCE_EXHAUSTED
                else:
                    execution_status = ExecutionStatusV4.ENGINE_ERROR
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                failure=failure,
                execution=execution_status,
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=failure
            )
        if not executions:
            failure = _Failure("backend", "BACKEND_NO_EXECUTION", False)
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
            elif status == "CANCELLED":
                execution_status = ExecutionStatusV4.CANCELLED
            elif status == "UNSUPPORTED_SEMANTICS":
                execution_status = ExecutionStatusV4.UNSUPPORTED
            else:
                execution_status = ExecutionStatusV4.ENGINE_ERROR
            failure = _Failure(
                "backend",
                f"BACKEND_{status}",
                _is_retryable(f"BACKEND_{status}"),
            )
            interruption = (
                InterruptionStateV4(failure.code, "backend")
                if execution_status
                in {
                    ExecutionStatusV4.CANCELLED,
                    ExecutionStatusV4.RESOURCE_EXHAUSTED,
                    ExecutionStatusV4.ENGINE_ERROR,
                }
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
            if failure.code in {"APPLICATION_CANCELLED", "BACKEND_CANCELLED"}:
                execution_status = ExecutionStatusV4.CANCELLED
            elif failure.code in {"ADMISSION_DEADLINE", "BACKEND_TIMEOUT"}:
                execution_status = ExecutionStatusV4.RESOURCE_EXHAUSTED
            else:
                execution_status = ExecutionStatusV4.ENGINE_ERROR
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                failure=failure,
                execution=execution_status,
                backend_execution=primary,
                extra_receipts=(primary.receipt_ref,),
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=failure
            )
        if argument.state in {"empty", "missing"}:
            reasons = [f"argument_{argument.state}"]
            if request.profile_queries_v5:
                reasons.append("profile_queries_without_arguments")
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
                reasons=tuple(reasons),
                extra_receipts=(primary.receipt_ref, checked.receipt_ref),
            )
            return self._finish(
                request, run, run_identity_ref, result, events, now=now, failure=None
            )
        v5_stage: _V5StageOutcome | None = None
        if request.profile_queries_v5:
            try:
                v5_stage = self._profile_stage_v5(request, checked, argument, now=now)
            except _EXPECTED_FAILURES as exc:
                failure = self._failure("profile-v5", exc)
                result = self._nonformal_result(
                    request,
                    run,
                    run_identity_ref,
                    pack,
                    facts,
                    selected,
                    failure=failure,
                    execution=ExecutionStatusV4.ENGINE_ERROR,
                    backend_execution=primary,
                    extra_receipts=(primary.receipt_ref, checked.receipt_ref),
                )
                return self._finish(
                    request, run, run_identity_ref, result, events, now=now, failure=failure
                )
            events.append(("profile-v5", v5_stage.stage_ref))
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
                v5_stage=v5_stage,
            )
        except _EXPECTED_FAILURES as exc:
            failure = self._failure("result", exc)
            if failure.code in {"APPLICATION_CANCELLED", "BACKEND_CANCELLED"}:
                execution_status = ExecutionStatusV4.CANCELLED
            elif failure.code in {"ADMISSION_DEADLINE", "BACKEND_TIMEOUT"}:
                execution_status = ExecutionStatusV4.RESOURCE_EXHAUSTED
            else:
                execution_status = ExecutionStatusV4.ENGINE_ERROR
            result = self._nonformal_result(
                request,
                run,
                run_identity_ref,
                pack,
                facts,
                selected,
                failure=failure,
                execution=execution_status,
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
