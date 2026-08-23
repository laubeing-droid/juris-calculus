"""Derive V4 backend features, invoke a certified provider, and attest the run."""

from __future__ import annotations

from dataclasses import dataclass
import multiprocessing
import time
from typing import Callable

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.backends import (
    AAF_PROVIDER_ID,
    EXACT_PROVIDER_ID,
    HORN_PROVIDER_ID,
    PROVIDER_VERSION,
    ProviderRunV4,
    decode_provider_message,
    provider_process_entry,
    provider_runtime_identity,
)
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
    ContentRefV4,
    FactAdmissionReceiptV4,
    LegalIVLV4,
    ResourceLimitsV4,
    RunIdentityV4,
    SignatureEnvelopeV4,
    SolverReceiptV4,
)
from compiler_core.fact_admission import (
    ADMITTED_FACT_KIND,
    CASE_REQUEST_KIND,
    CASE_REQUEST_SCOPE,
    FACT_ADMISSION_RECEIPT_KIND,
    FACT_ADMISSION_SCOPE,
    FACT_PROPOSITION_KIND,
    FACT_VALUE_KIND,
    FactAdmissionServiceV4,
)
from compiler_core.legal_ir import (
    IR_CLAUSE_KIND,
    IR_MODALITY_KIND,
    LEGAL_IR_SCOPE,
    LEGAL_IVL_KIND,
    LegalIRCompilationV4,
    LegalIRCompilerV4,
)
from compiler_core.rule_packs import (
    JSON_MEDIA_TYPE,
    RULE_ATTACK_KIND,
    RULE_COMPONENT_SCOPE,
    RULE_CONCLUSION_KIND,
    RULE_EXCEPTION_KIND,
    RULE_NUMERIC_KIND,
    RULE_PERMISSION_KIND,
    RULE_PREMISE_KIND,
    RULE_PRIORITY_KIND,
    RULE_TEMPORAL_KIND,
)


BACKEND_SCOPE = "backend"
BACKEND_PROBLEM_KIND = "backend-problem-v4"
BACKEND_CAPABILITY_KIND = "backend-capability-v4"
BACKEND_LIMITS_KIND = "backend-limits-v4"
BACKEND_INVOCATION_KIND = "backend-invocation-v4"
BACKEND_RESULT_KIND = "backend-result-v4"
BACKEND_PROOF_KIND = "backend-proof-v4"
SOLVER_RECEIPT_KIND = "solver-receipt-v4"
RUN_IDENTITY_KIND = "run-identity"
RUN_IDENTITY_SCOPE = "run"
BACKEND_PROFILE_SCHEMA_V4 = "jc/backend-profile/1.0"
BACKEND_ROUTING_POLICY_V4 = "horn-base-plus-feature-routes-v1"
CERTIFIED_PROVIDER_IDS_V4 = (
    HORN_PROVIDER_ID,
    AAF_PROVIDER_ID,
    EXACT_PROVIDER_ID,
)
BACKEND_ROUTE_TABLE_V4 = (
    (HORN_PROVIDER_ID, ()),
    (AAF_PROVIDER_ID, ("conflict_structure",)),
    (EXACT_PROVIDER_ID, ("temporal_constraints", "numeric_constraints")),
)

_FAILURE_EXIT_STATUS = {
    "UNSUPPORTED_SEMANTICS": 65,
    "CRASHED": 70,
    "UNKNOWN": 75,
    "TIMEOUT": 124,
    "CANCELLED": 130,
}

BackendSignerV4 = Callable[
    [
        DigestV4,
        DigestV4,
        tuple[ContentRefV4, ...],
        ContentRefV4,
        CanonicalTimeV4,
    ],
    SignatureEnvelopeV4,
]


class BackendV4Error(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class BackendFeaturesV4:
    conflict_structure: bool
    temporal_constraints: bool
    numeric_constraints: bool

    def to_dict(self) -> dict[str, bool]:
        return {
            "conflict_structure": self.conflict_structure,
            "temporal_constraints": self.temporal_constraints,
            "numeric_constraints": self.numeric_constraints,
        }


@dataclass(frozen=True, slots=True)
class BackendExecutionV4:
    features: BackendFeaturesV4
    problem_ref: ContentRefV4
    invocation: BackendInvocationV4
    invocation_ref: ContentRefV4
    receipt: SolverReceiptV4
    receipt_ref: ContentRefV4

    @property
    def completed(self) -> bool:
        return self.receipt.status == "COMPLETED" and self.receipt.exit_status == 0


def _fail(code: str, detail: str) -> None:
    raise BackendV4Error(code, detail)


def _routing_policy_wire_v4() -> dict[str, object]:
    return {
        "policy_id": BACKEND_ROUTING_POLICY_V4,
        "routes": [
            {"provider_id": provider_id, "any_features": list(any_features)}
            for provider_id, any_features in BACKEND_ROUTE_TABLE_V4
        ],
    }


def _provider_runtime_wire_v4(
    runtime_identity: tuple[DigestV4, DigestV4, dict[str, str]],
) -> dict[str, object]:
    if type(runtime_identity) is not tuple or len(runtime_identity) != 3:
        _fail("BACKEND_PROFILE", "provider runtime identity is invalid")
    binary_digest, package_digest, build_inputs = runtime_identity
    if (
        type(binary_digest) is not DigestV4
        or type(package_digest) is not DigestV4
        or type(build_inputs) is not dict
        or not build_inputs
        or any(type(key) is not str or not key for key in build_inputs)
        or any(type(value) is not str for value in build_inputs.values())
    ):
        _fail("BACKEND_PROFILE", "provider runtime identity is invalid")
    try:
        parsed_inputs = {
            key: str(DigestV4.parse(value)) for key, value in sorted(build_inputs.items())
        }
    except (TypeError, ValueError) as exc:
        raise BackendV4Error(
            "BACKEND_PROFILE", "provider build inputs are invalid"
        ) from exc
    if package_digest != DigestV4.from_bytes(canonical_bytes(parsed_inputs)):
        _fail("BACKEND_PROFILE", "provider package digest does not bind build inputs")
    return {
        "provider_binary_digest": str(binary_digest),
        "provider_package_digest": str(package_digest),
        "provider_build_inputs": parsed_inputs,
    }


def _backend_profile_digest_v4(
    *,
    solver_deadline_ms: int,
    seed: int,
    provider_ids: tuple[str, ...],
    runtime_identity: tuple[DigestV4, DigestV4, dict[str, str]],
) -> DigestV4:
    if (
        type(solver_deadline_ms) is not int
        or solver_deadline_ms <= 0
        or type(seed) is not int
        or type(provider_ids) is not tuple
        or not provider_ids
        or any(type(item) is not str or not item for item in provider_ids)
        or len(set(provider_ids)) != len(provider_ids)
    ):
        _fail("BACKEND_PROFILE", "backend profile inputs are invalid")
    return digest_value({
        "schema_version": BACKEND_PROFILE_SCHEMA_V4,
        "provider_ids": list(provider_ids),
        "provider_version": PROVIDER_VERSION,
        "routing_policy": _routing_policy_wire_v4(),
        "provider_runtime": _provider_runtime_wire_v4(runtime_identity),
        "solver_deadline_ms": solver_deadline_ms,
        "seed": seed,
    })


def backend_profile_digest_v4(
    *,
    solver_deadline_ms: int,
    seed: int = 0,
    provider_ids: tuple[str, ...] = CERTIFIED_PROVIDER_IDS_V4,
) -> DigestV4:
    """Commit the complete pre-execution provider and routing policy."""

    return _backend_profile_digest_v4(
        solver_deadline_ms=solver_deadline_ms,
        seed=seed,
        provider_ids=provider_ids,
        runtime_identity=provider_runtime_identity(),
    )


def _providers_from_route_table_v4(features: BackendFeaturesV4) -> tuple[str, ...]:
    return tuple(
        provider_id
        for provider_id, any_features in BACKEND_ROUTE_TABLE_V4
        if not any_features or any(getattr(features, name) for name in any_features)
    )


class BackendRouterV4:
    """Controlled router; callers provide inputs, never features or receipts."""

    def __init__(
        self,
        ir_compiler: LegalIRCompilerV4,
        fact_service: FactAdmissionServiceV4,
        *,
        receipt_signer: BackendSignerV4,
    ) -> None:
        if (
            type(ir_compiler) is not LegalIRCompilerV4
            or type(fact_service) is not FactAdmissionServiceV4
            or ir_compiler._resolver is not fact_service._resolver
            or not callable(receipt_signer)
        ):
            _fail("BACKEND_INPUT_TYPE", "router dependencies are invalid")
        self._ir_compiler = ir_compiler
        self._fact_service = fact_service
        self._resolver: ArtifactResolverV4 = ir_compiler._resolver
        self._trust = fact_service._trust
        self._receipt_signer = receipt_signer

    def _resolve_json(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
    ) -> dict[str, object]:
        if type(reference) is not ContentRefV4 or reference.kind != kind:
            _fail("BACKEND_REF_KIND", f"expected {kind}")
        raw = self._resolver.resolve_content(
            reference,
            expected_artifact_kind=kind,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope=scope,
            max_bytes=self._resolver.max_artifact_bytes,
        )
        document = parse_json_document(raw)
        if type(document) is not dict or raw != canonical_bytes(document):
            _fail("BACKEND_NONCANONICAL_INPUT", f"{kind} must be canonical JSON")
        return document

    def _resolve_run(self, reference: ContentRefV4) -> RunIdentityV4:
        body = self._resolve_json(
            reference,
            kind=RUN_IDENTITY_KIND,
            scope=RUN_IDENTITY_SCOPE,
        )
        if "run_digest" in body:
            _fail("BACKEND_RUN_IDENTITY", "run artifact must store its digest body")
        run = RunIdentityV4.from_dict({**body, "run_digest": str(reference.digest)})
        if run.canonical_digest() != reference.digest:
            _fail("BACKEND_RUN_IDENTITY", "run identity digest is inconsistent")
        return run

    def _request(self, run: RunIdentityV4) -> CaseRequestV4:
        body = self._resolve_json(
            run.request_ref,
            kind=CASE_REQUEST_KIND,
            scope=CASE_REQUEST_SCOPE,
        )
        try:
            request = CaseRequestV4.from_dict(body)
        except (TypeError, ValueError) as exc:
            raise BackendV4Error(
                "BACKEND_REQUEST_BINDING", "run request is malformed"
            ) from exc
        if request.canonical_digest() != run.request_ref.digest:
            _fail("BACKEND_REQUEST_BINDING", "run request digest is inconsistent")
        return request

    def _validate_ivl(self, ivl: LegalIVLV4, reference: ContentRefV4) -> None:
        if (
            type(ivl) is not LegalIVLV4
            or type(reference) is not ContentRefV4
            or reference.kind != LEGAL_IVL_KIND
            or reference.digest != ivl.ivl_digest
        ):
            _fail("BACKEND_IVL_REFERENCE", "exact LegalIVLV4 and reference are required")
        body = self._resolve_json(reference, kind=LEGAL_IVL_KIND, scope=LEGAL_IR_SCOPE)
        if "ivl_digest" in body or body != ivl.digest_body():
            _fail("BACKEND_IVL_REFERENCE", "stored IVL differs from the supplied contract")

    def _compilations(
        self,
        values: tuple[LegalIRCompilationV4, ...],
        *,
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> tuple[LegalIRCompilationV4, ...]:
        if (
            type(values) is not tuple
            or not values
            or any(type(item) is not LegalIRCompilationV4 for item in values)
        ):
            _fail("BACKEND_IR_HANDLE", "one or more compiler-issued IVLs are required")
        ordered = tuple(sorted(values, key=lambda item: (item.ivl.ivl_id, str(item.ivl_ref.digest))))
        if (
            len({item.ivl_ref for item in ordered}) != len(ordered)
            or len({item.ivl.ivl_id for item in ordered}) != len(ordered)
        ):
            _fail("BACKEND_IR_HANDLE", "compiled IVLs must be unique")
        for compilation in ordered:
            self._ir_compiler.verify_compilation(compilation, now=now)
            if (
                compilation.rule_to_spec_receipt.run_identity_ref != run_identity_ref
                or compilation.spec_to_ivl_receipt.run_identity_ref != run_identity_ref
            ):
                _fail("BACKEND_IR_HANDLE", "translation receipts bind another run")
            self._validate_ivl(compilation.ivl, compilation.ivl_ref)
        return ordered

    def _fact(
        self,
        receipt_ref: ContentRefV4,
        run: RunIdentityV4,
        run_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> dict[str, object]:
        receipt_document = self._resolve_json(
            receipt_ref,
            kind=FACT_ADMISSION_RECEIPT_KIND,
            scope=FACT_ADMISSION_SCOPE,
        )
        receipt = FactAdmissionReceiptV4.from_dict(receipt_document)
        fact_ref = self._fact_service.verify_receipt(
            receipt_ref,
            request_ref=run.request_ref,
            case_scope=receipt.case_scope,
            run_identity_ref=run_ref,
            now=now,
        )
        fact = self._resolve_json(
            fact_ref,
            kind=ADMITTED_FACT_KIND,
            scope=FACT_ADMISSION_SCOPE,
        )
        if (
            fact.get("schema_version") != "jc/admitted-fact/1.0"
            or fact.get("status") != "ADMITTED"
            or fact.get("run_identity_ref") != run_ref.to_dict()
            or fact.get("case_scope") != receipt.case_scope
        ):
            _fail("BACKEND_FACT_BINDING", "fact is not admitted for this run")
        try:
            proposition_ref = ContentRefV4.from_dict(fact["proposition_ref"])
            value_ref = ContentRefV4.from_dict(fact["value_ref"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BackendV4Error("BACKEND_FACT_BINDING", "fact references are malformed") from exc
        proposition = self._resolve_json(
            proposition_ref,
            kind=FACT_PROPOSITION_KIND,
            scope=FACT_ADMISSION_SCOPE,
        )
        value = self._resolve_json(
            value_ref,
            kind=FACT_VALUE_KIND,
            scope=FACT_ADMISSION_SCOPE,
        )
        if (
            proposition.get("schema_version") != "jc/fact-proposition/1.0"
            or type(proposition.get("proposition")) is not str
            or value.get("schema_version") != "jc/fact-value/1.0"
            or value.get("value_kind") != fact.get("value_kind")
        ):
            _fail("BACKEND_FACT_BINDING", "fact proposition or value is malformed")
        return {
            "admission_receipt_ref": receipt_ref.to_dict(),
            "fact_ref": fact_ref.to_dict(),
            "case_scope": receipt.case_scope,
            "proposition": proposition["proposition"],
            "value_kind": value["value_kind"],
            "value": value.get("value"),
        }

    def _component(
        self,
        reference: ContentRefV4,
        *,
        expected_kind: str,
        owner_rule_id: str,
        selected_rule_ids: set[str],
    ) -> dict[str, object]:
        value = self._resolve_json(
            reference,
            kind=expected_kind,
            scope=RULE_COMPONENT_SCOPE,
        )
        allowed_fields = {
            RULE_PREMISE_KIND: {"schema_version", "rule_id", "fact_key", "required"},
            RULE_CONCLUSION_KIND: {"schema_version", "rule_id", "fact_key", "value"},
            RULE_EXCEPTION_KIND: {
                "schema_version", "rule_id", "attacker", "target", "attack_type",
                "target_aspect", "condition_fact_key",
            },
            RULE_ATTACK_KIND: {
                "schema_version", "rule_id", "attacker", "target", "attack_type",
                "target_aspect", "condition_fact_key",
            },
            RULE_PRIORITY_KIND: {
                "schema_version", "rule_id", "source", "target", "condition",
            },
            RULE_PERMISSION_KIND: {
                "schema_version", "rule_id", "permission_id", "permits", "relation_to",
                "relation_kind",
            },
            RULE_TEMPORAL_KIND: {
                "schema_version", "rule_id", "target_rule_id", "operation", "start", "end",
            },
            RULE_NUMERIC_KIND: {
                "schema_version", "rule_id", "target_rule_id", "operation", "operands",
                "fact_key", "ratio",
            },
        }.get(expected_kind)
        required_fields = {
            RULE_PREMISE_KIND: {"schema_version", "rule_id", "fact_key", "required"},
            RULE_CONCLUSION_KIND: {"schema_version", "rule_id"},
            RULE_EXCEPTION_KIND: {
                "schema_version", "rule_id", "attacker", "target", "attack_type",
                "target_aspect", "condition_fact_key",
            },
            RULE_ATTACK_KIND: {
                "schema_version", "rule_id", "attacker", "target", "attack_type",
                "target_aspect",
            },
            RULE_PRIORITY_KIND: {
                "schema_version", "rule_id", "source", "target", "condition",
            },
            RULE_PERMISSION_KIND: {
                "schema_version", "rule_id", "permission_id", "permits", "relation_to",
                "relation_kind",
            },
            RULE_TEMPORAL_KIND: {"schema_version", "rule_id", "start", "end"},
            RULE_NUMERIC_KIND: {"schema_version", "rule_id", "operation"},
        }.get(expected_kind)
        if (
            allowed_fields is None
            or required_fields is None
            or value.get("schema_version") != f"jc/{expected_kind}/1.0"
            or value.get("rule_id") != owner_rule_id
            or not set(value) <= allowed_fields
            or not required_fields <= set(value)
            or (
                expected_kind == RULE_CONCLUSION_KIND
                and len({"fact_key", "value"} & set(value)) != 1
            )
        ):
            _fail("BACKEND_COMPONENT_SCHEMA", f"{expected_kind} schema is unsupported")
        target = value.get("target_rule_id")
        if target is not None and target not in selected_rule_ids:
            _fail("BACKEND_COMPONENT_SCHEMA", f"{expected_kind} target is outside selected IVLs")
        if expected_kind in {RULE_EXCEPTION_KIND, RULE_ATTACK_KIND} and (
            value.get("attacker") != owner_rule_id or value.get("target") not in selected_rule_ids
        ):
            _fail("BACKEND_COMPONENT_SCHEMA", "attack endpoints do not match selected IVLs")
        if expected_kind == RULE_PRIORITY_KIND and (
            value.get("source") != owner_rule_id or value.get("target") not in selected_rule_ids
        ):
            _fail("BACKEND_COMPONENT_SCHEMA", "priority endpoints do not match selected IVLs")
        if expected_kind == RULE_PERMISSION_KIND and value.get("relation_to") not in selected_rule_ids:
            _fail("BACKEND_COMPONENT_SCHEMA", "permission target is outside selected IVLs")
        if expected_kind == RULE_PREMISE_KIND and (
            type(value.get("fact_key")) is not str
            or not value["fact_key"]
            or type(value.get("required")) is not bool
        ):
            _fail("BACKEND_COMPONENT_SCHEMA", "premise fields are malformed")
        if expected_kind == RULE_PRIORITY_KIND and (
            type(value.get("condition")) is not str or not value["condition"]
        ):
            _fail("BACKEND_COMPONENT_SCHEMA", "priority condition is malformed")
        if expected_kind == RULE_PERMISSION_KIND and any(
            type(value.get(field)) is not str or not value[field]
            for field in ("permission_id", "permits", "relation_kind")
        ):
            _fail("BACKEND_COMPONENT_SCHEMA", "permission fields are malformed")
        return value

    def _ivl_context(
        self, ivl: LegalIVLV4
    ) -> tuple[dict[str, object], dict[str, object], CanonicalTimeV4, CanonicalTimeV4 | None]:
        if len(ivl.clause_refs) != 1:
            _fail("BACKEND_IVL_CLAUSE", "certified IVL requires exactly one legal clause")
        clause = self._resolve_json(
            ivl.clause_refs[0],
            kind=IR_CLAUSE_KIND,
            scope=LEGAL_IR_SCOPE,
        )
        modality = self._resolve_json(
            ivl.modality_ref,
            kind=IR_MODALITY_KIND,
            scope=LEGAL_IR_SCOPE,
        )
        try:
            effective_from = CanonicalTimeV4.from_dict(clause["effective_from"])
            effective_to = (
                None
                if clause.get("effective_to") is None
                else CanonicalTimeV4.from_dict(clause["effective_to"])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BackendV4Error(
                "BACKEND_IVL_CLAUSE", "legal clause interval is malformed"
            ) from exc
        if (
            set(clause) != {
                "schema_version", "spec_ref", "premise_refs", "conclusion_ref",
                "modality_ref", "effective_from", "effective_to",
            }
            or set(modality) != {
                "schema_version", "spec_ref", "modality", "permission_ref",
            }
            or clause.get("schema_version") != "jc/legal-ir-clause/1.0"
            or clause.get("spec_ref") != ivl.spec_ref.to_dict()
            or clause.get("premise_refs") != [item.to_dict() for item in ivl.premise_refs]
            or clause.get("conclusion_ref") != ivl.conclusion_ref.to_dict()
            or clause.get("modality_ref") != ivl.modality_ref.to_dict()
            or modality.get("schema_version") != "jc/legal-ir-modality/1.0"
            or modality.get("spec_ref") != ivl.spec_ref.to_dict()
            or type(modality.get("modality")) is not str
            or (effective_to is not None and not effective_from < effective_to)
        ):
            _fail("BACKEND_IVL_CLAUSE", "legal clause or modality differs from its IVL")
        return clause, modality, effective_from, effective_to

    @staticmethod
    def _features(compilations: tuple[LegalIRCompilationV4, ...]) -> BackendFeaturesV4:
        return BackendFeaturesV4(
            conflict_structure=any(
                item.ivl.exception_attack_refs
                or item.ivl.permission_refs
                or item.ivl.priority_refs
                for item in compilations
            ),
            temporal_constraints=any(
                item.ivl.temporal_constraint_refs for item in compilations
            ),
            numeric_constraints=any(
                item.ivl.numeric_constraint_refs for item in compilations
            ),
        )

    @staticmethod
    def _providers(features: BackendFeaturesV4) -> tuple[str, ...]:
        return _providers_from_route_table_v4(features)

    def _register(self, kind: str, payload: dict[str, object]) -> ContentRefV4:
        raw = canonical_bytes(payload)
        reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
        return self._resolver.register_bytes(
            artifact_id=f"{kind}-{reference.digest.hex}",
            content_ref=reference,
            artifact_kind=kind,
            media_type=JSON_MEDIA_TYPE,
            scope=BACKEND_SCOPE,
            content=raw,
        )

    def _problem(
        self,
        compilations: tuple[LegalIRCompilationV4, ...],
        *,
        run: RunIdentityV4,
        run_ref: ContentRefV4,
        fact_admission_receipt_refs: tuple[ContentRefV4, ...],
        now: CanonicalTimeV4,
        decision_time: CanonicalTimeV4,
        limits_ref: ContentRefV4,
        provider_id: str,
        features: BackendFeaturesV4,
        seed: int,
    ) -> tuple[dict[str, object], ContentRefV4]:
        if (
            type(fact_admission_receipt_refs) is not tuple
            or not fact_admission_receipt_refs
            or len(set(fact_admission_receipt_refs)) != len(fact_admission_receipt_refs)
        ):
            _fail(
                "BACKEND_FACT_BINDING",
                "fact admission receipts must be a non-empty unique tuple",
            )
        facts = [
            self._fact(reference, run, run_ref, now)
            for reference in fact_admission_receipt_refs
        ]
        case_scopes = {str(row["case_scope"]) for row in facts}
        if len(case_scopes) != 1:
            _fail("BACKEND_FACT_BINDING", "fact receipts cross case scopes")
        case_scope = next(iter(case_scopes))
        clauses: list[dict[str, object]] = []
        selected_rule_ids = {item.ivl.ivl_id for item in compilations}
        for compilation in compilations:
            ivl = compilation.ivl
            _, modality, effective_from, effective_to = self._ivl_context(ivl)
            relations: list[dict[str, object]] = []
            for reference in ivl.exception_attack_refs:
                if reference.kind not in {RULE_EXCEPTION_KIND, RULE_ATTACK_KIND}:
                    _fail("BACKEND_REF_KIND", "exception/attack ref kind is unsupported")
                row = self._component(
                    reference,
                    expected_kind=reference.kind,
                    owner_rule_id=ivl.ivl_id,
                    selected_rule_ids=selected_rule_ids,
                )
                aspect = row.get("target_aspect", "rule_applicability")
                if aspect == "applicability":
                    aspect = "rule_applicability"
                relations.append({
                    "kind": "attack",
                    "source_ref": reference.to_dict(),
                    "attack_type": row.get("attack_type", "undercut"),
                    "target_aspect": aspect,
                    "source": row.get("attacker"),
                    "target": row.get("target"),
                    "condition_fact_key": row.get("condition_fact_key"),
                })
            for reference in ivl.priority_refs:
                row = self._component(
                    reference,
                    expected_kind=RULE_PRIORITY_KIND,
                    owner_rule_id=ivl.ivl_id,
                    selected_rule_ids=selected_rule_ids,
                )
                relations.append({
                    "kind": "priority",
                    "source_ref": reference.to_dict(),
                    "source": row.get("source"),
                    "target": row.get("target"),
                    "condition": row.get("condition"),
                })
            for reference in ivl.permission_refs:
                row = self._component(
                    reference,
                    expected_kind=RULE_PERMISSION_KIND,
                    owner_rule_id=ivl.ivl_id,
                    selected_rule_ids=selected_rule_ids,
                )
                relations.append({
                    "kind": "permission",
                    "source_ref": reference.to_dict(),
                    "permission_id": row.get("permission_id"),
                    "permits": row.get("permits"),
                    "relation_kind": row.get("relation_kind"),
                    "source": ivl.ivl_id,
                    "target": row.get("relation_to"),
                })
            clauses.append({
                "ivl_id": ivl.ivl_id,
                "ivl_ref": compilation.ivl_ref.to_dict(),
                "rule_ref": compilation.rule_ref.to_dict(),
                "translation_receipt_refs": [
                    compilation.rule_to_spec_receipt_ref.to_dict(),
                    compilation.spec_to_ivl_receipt_ref.to_dict(),
                ],
                "premise_refs": [item.to_dict() for item in ivl.premise_refs],
                "premises": [
                    self._component(
                        reference,
                        expected_kind=RULE_PREMISE_KIND,
                        owner_rule_id=ivl.ivl_id,
                        selected_rule_ids=selected_rule_ids,
                    )
                    for reference in ivl.premise_refs
                ],
                "conclusion_ref": ivl.conclusion_ref.to_dict(),
                "conclusion": self._component(
                    ivl.conclusion_ref,
                    expected_kind=RULE_CONCLUSION_KIND,
                    owner_rule_id=ivl.ivl_id,
                    selected_rule_ids=selected_rule_ids,
                ),
                "derivation_refs": [
                    item.to_dict() for item in ivl.proof_obligation_refs
                ],
                "modality": modality["modality"],
                "effective_from": effective_from.wire,
                "effective_to": None if effective_to is None else effective_to.wire,
                "relations": sorted(
                    relations,
                    key=lambda row: (
                        str(row["kind"]), str(row["source"]), str(row["target"])
                    ),
                ),
                "temporal_constraints": [
                    {
                        "constraint_ref": reference.to_dict(),
                        "owner_ivl_id": ivl.ivl_id,
                        "target_ivl_id": row.get("target_rule_id", ivl.ivl_id),
                        "expression": row,
                    }
                    for reference in ivl.temporal_constraint_refs
                    for row in [self._component(
                        reference,
                        expected_kind=RULE_TEMPORAL_KIND,
                        owner_rule_id=ivl.ivl_id,
                        selected_rule_ids=selected_rule_ids,
                    )]
                ],
                "numeric_constraints": [
                    {
                        "constraint_ref": reference.to_dict(),
                        "owner_ivl_id": ivl.ivl_id,
                        "target_ivl_id": row.get("target_rule_id", ivl.ivl_id),
                        "expression": row,
                    }
                    for reference in ivl.numeric_constraint_refs
                    for row in [self._component(
                        reference,
                        expected_kind=RULE_NUMERIC_KIND,
                        owner_rule_id=ivl.ivl_id,
                        selected_rule_ids=selected_rule_ids,
                    )]
                ],
            })
        body: dict[str, object] = {
            "schema_version": "jc/backend-problem/1.0",
            "provider_id": provider_id,
            "run_identity_ref": run_ref.to_dict(),
            "request_ref": run.request_ref.to_dict(),
            "case_scope": case_scope,
            "limits_ref": limits_ref.to_dict(),
            "decision_time": decision_time.wire,
            "seed": seed,
            "features": features.to_dict(),
            "facts": sorted(facts, key=lambda row: (row["proposition"], str(row["fact_ref"]))),
            "clauses": clauses,
        }
        return body, self._register(BACKEND_PROBLEM_KIND, body)

    def _provider_identity(
        self,
        provider_id: str,
        features: BackendFeaturesV4,
        limits: ResourceLimitsV4,
        runtime_identity: tuple[DigestV4, DigestV4, dict[str, str]] | None = None,
    ) -> tuple[dict[str, object], ContentRefV4]:
        runtime_wire = _provider_runtime_wire_v4(
            provider_runtime_identity() if runtime_identity is None else runtime_identity
        )
        capability = {
            "schema_version": "jc/backend-capability/1.0",
            "provider_id": provider_id,
            "provider_version": PROVIDER_VERSION,
            "certified_semantics": {
                HORN_PROVIDER_ID: (
                    "constitutive-horn-least-fixpoint-plus-deontic-applicability"
                ),
                AAF_PROVIDER_ID: "finite-typed-dung-grounded-with-empty-framework",
                EXACT_PROVIDER_ID: "applicable-integer-rational-gregorian-closed-form",
            }[provider_id],
            "features": features.to_dict(),
            "solver_deadline_ms": limits.solver_deadline_ms,
            "implementation_kind": "pure-python-source",
            **runtime_wire,
        }
        build_digest = digest_value(capability)
        capability["provider_build_digest"] = str(build_digest)
        return capability, self._register(BACKEND_CAPABILITY_KIND, capability)

    @staticmethod
    def _failure_run(
        provider_id: str,
        input_digest: DigestV4,
        status: str,
    ) -> ProviderRunV4:
        raw = canonical_bytes({
            "schema_version": "jc/backend-result/1.0",
            "provider_id": provider_id,
            "provider_version": PROVIDER_VERSION,
            "input_digest": str(input_digest),
            "status": status,
            "outcome": "NO_FORMAL_RESULT",
            "outputs": {},
        })
        return ProviderRunV4(
            provider_id,
            PROVIDER_VERSION,
            input_digest,
            status,
            _FAILURE_EXIT_STATUS[status],
            raw,
            None,
        )

    def _invoke_provider(
        self,
        provider_id: str,
        problem_bytes: bytes,
        input_digest: DigestV4,
        *,
        deadline_ms: int,
        cancel_check: Callable[[], bool] | None,
        expected_runtime_identity: dict[str, object] | None = None,
    ) -> ProviderRunV4:
        """Execute behind a process boundary that can actually be terminated."""

        if cancel_check is not None and cancel_check():
            return self._failure_run(provider_id, input_digest, "CANCELLED")
        if expected_runtime_identity is None:
            binary, package, inputs = provider_runtime_identity()
            expected_runtime_identity = {
                "provider_binary_digest": str(binary),
                "provider_package_digest": str(package),
                "provider_build_inputs": inputs,
            }
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=provider_process_entry,
            args=(provider_id, problem_bytes, sender),
            daemon=True,
        )
        deadline_ns = time.monotonic_ns() + deadline_ms * 1_000_000
        resolved: ProviderRunV4 | None = None
        cleanup_failed = False
        try:
            process.start()
            sender.close()
            while True:
                if cancel_check is not None and cancel_check():
                    resolved = self._failure_run(provider_id, input_digest, "CANCELLED")
                    break
                remaining_ns = deadline_ns - time.monotonic_ns()
                if remaining_ns <= 0:
                    resolved = self._failure_run(provider_id, input_digest, "TIMEOUT")
                    break
                if receiver.poll(min(remaining_ns / 1_000_000_000, 0.01)):
                    try:
                        raw = receiver.recv_bytes(
                            maxlength=self._resolver.max_artifact_bytes * 3
                        )
                        outcome, payload, child_identity = decode_provider_message(raw)
                    except (EOFError, OSError, TypeError, ValueError):
                        resolved = self._failure_run(provider_id, input_digest, "CRASHED")
                        break
                    if cancel_check is not None and cancel_check():
                        resolved = self._failure_run(provider_id, input_digest, "CANCELLED")
                    elif time.monotonic_ns() >= deadline_ns:
                        resolved = self._failure_run(provider_id, input_digest, "TIMEOUT")
                    elif child_identity != expected_runtime_identity:
                        resolved = self._failure_run(provider_id, input_digest, "CRASHED")
                    elif outcome == "completed" and type(payload) is ProviderRunV4:
                        resolved = payload
                    elif outcome == "provider_error" and payload == "UNSUPPORTED_SEMANTICS":
                        resolved = self._failure_run(
                            provider_id, input_digest, "UNSUPPORTED_SEMANTICS"
                        )
                    elif outcome == "provider_error":
                        resolved = self._failure_run(provider_id, input_digest, "UNKNOWN")
                    else:
                        resolved = self._failure_run(provider_id, input_digest, "CRASHED")
                    break
                if not process.is_alive():
                    resolved = self._failure_run(provider_id, input_digest, "CRASHED")
                    break
        except (OSError, RuntimeError):
            resolved = self._failure_run(provider_id, input_digest, "CRASHED")
        finally:
            try:
                receiver.close()
                sender.close()
                if process.pid is not None:
                    if process.is_alive():
                        process.kill()
                    process.join(timeout=1)
            except (OSError, RuntimeError, ValueError):
                cleanup_failed = True
        if cleanup_failed or (process.pid is not None and process.is_alive()):
            return self._failure_run(provider_id, input_digest, "CRASHED")
        return resolved or self._failure_run(provider_id, input_digest, "CRASHED")

    @staticmethod
    def _validate_run(run: ProviderRunV4, provider_id: str, problem_ref: ContentRefV4) -> None:
        if (
            type(run) is not ProviderRunV4
            or type(run.exit_status) is not int
            or type(run.result_bytes) is not bytes
            or (run.proof_bytes is not None and type(run.proof_bytes) is not bytes)
        ):
            _fail("BACKEND_PROVIDER_RESULT", "provider returned the wrong result type")
        if (
            run.provider_id != provider_id
            or run.provider_version != PROVIDER_VERSION
            or run.input_digest != problem_ref.digest
        ):
            _fail("BACKEND_PROVIDER_IDENTITY", "provider output identity differs")
        try:
            result = parse_json_document(run.result_bytes)
        except (TypeError, ValueError) as exc:
            raise BackendV4Error(
                "BACKEND_PROVIDER_RESULT", "provider result is not canonical JSON"
            ) from exc
        if (
            type(result) is not dict
            or run.result_bytes != canonical_bytes(result)
            or set(result) != {
                "schema_version", "provider_id", "provider_version", "input_digest",
                "status", "outcome", "outputs",
            }
            or result.get("schema_version") != "jc/backend-result/1.0"
            or result.get("provider_id") != provider_id
            or result.get("provider_version") != PROVIDER_VERSION
            or result.get("input_digest") != str(problem_ref.digest)
            or result.get("status") != run.status
            or type(result.get("outcome")) is not str
            or type(result.get("outputs")) is not dict
        ):
            _fail("BACKEND_PROVIDER_RESULT", "provider result binding is malformed")
        if run.status == "COMPLETED":
            if run.exit_status != 0 or run.proof_bytes is None:
                _fail("BACKEND_PROVIDER_RESULT", "completed provider requires proof and zero exit")
            try:
                proof = parse_json_document(run.proof_bytes)
            except (TypeError, ValueError) as exc:
                raise BackendV4Error(
                    "BACKEND_PROVIDER_PROOF", "provider proof is not canonical JSON"
                ) from exc
            if (
                type(proof) is not dict
                or run.proof_bytes != canonical_bytes(proof)
                or set(proof) != {
                    "schema_version", "provider_id", "provider_version", "input_digest",
                    "result_digest", "witness",
                }
                or proof.get("schema_version") != "jc/backend-proof/1.0"
                or proof.get("provider_id") != provider_id
                or proof.get("provider_version") != PROVIDER_VERSION
                or proof.get("input_digest") != str(problem_ref.digest)
                or proof.get("result_digest") != str(DigestV4.from_bytes(run.result_bytes))
                or type(proof.get("witness")) is not dict
            ):
                _fail("BACKEND_PROVIDER_PROOF", "provider proof does not bind its result")
        elif (
            run.status not in _FAILURE_EXIT_STATUS
            or run.exit_status != _FAILURE_EXIT_STATUS.get(run.status)
            or run.proof_bytes is not None
            or result.get("outcome") != "NO_FORMAL_RESULT"
            or result.get("outputs") != {}
        ):
            _fail("BACKEND_PROVIDER_RESULT", "non-completed provider result is inconsistent")

    def _verify_receipt_signature(
        self,
        receipt: SolverReceiptV4,
        *,
        problem_ref: ContentRefV4,
        invocation_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> None:
        evidence_refs = (
            problem_ref,
            invocation_ref,
            receipt.backend_result_ref,
            *((receipt.proof_ref,) if receipt.proof_ref is not None else ()),
        )
        signature = receipt.signature
        payload_digest = digest_value(receipt.signature_body())
        if (
            type(signature) is not SignatureEnvelopeV4
            or signature.subject_digest != receipt.backend_result_ref.digest
            or signature.payload_digest != payload_digest
            or signature.evidence_refs != evidence_refs
            or signature.run_identity_ref != receipt.run_identity_ref
            or signature.issued_at != receipt.issued_at
            or signature.status != "APPROVED"
        ):
            _fail("BACKEND_RECEIPT_SIGNATURE", "solver receipt signature shape differs")
        self._trust._fresh_without_replay().verify(
            signature,
            expected_subject_digest=receipt.backend_result_ref.digest,
            expected_payload_digest=payload_digest,
            required_role="service_signer",
            required_scope="service-certificate",
            required_artifact_kind="service-certificate",
            expected_status="APPROVED",
            now=now,
            separation_from_principals=(),
        )

    def _execute_provider(
        self,
        provider_id: str,
        compilations: tuple[LegalIRCompilationV4, ...],
        *,
        run: RunIdentityV4,
        run_identity_ref: ContentRefV4,
        fact_admission_receipt_refs: tuple[ContentRefV4, ...],
        decision_time: CanonicalTimeV4,
        limits: ResourceLimitsV4,
        limits_ref: ContentRefV4,
        features: BackendFeaturesV4,
        now: CanonicalTimeV4,
        seed: int,
        cancel_check: Callable[[], bool] | None,
        runtime_identity: tuple[DigestV4, DigestV4, dict[str, str]],
    ) -> BackendExecutionV4:
        problem, problem_ref = self._problem(
            compilations,
            run=run,
            run_ref=run_identity_ref,
            fact_admission_receipt_refs=fact_admission_receipt_refs,
            now=now,
            decision_time=decision_time,
            limits_ref=limits_ref,
            provider_id=provider_id,
            features=features,
            seed=seed,
        )
        capability, capability_ref = self._provider_identity(
            provider_id, features, limits, runtime_identity
        )
        invocation = BackendInvocationV4(
            invocation_id=f"backend-{problem_ref.digest.hex}",
            provider_id=provider_id,
            provider_version=PROVIDER_VERSION,
            provider_package_digest=DigestV4.parse(capability["provider_package_digest"]),
            provider_binary_digest=DigestV4.parse(capability["provider_binary_digest"]),
            provider_build_digest=DigestV4.parse(capability["provider_build_digest"]),
            provider_capability_ref=capability_ref,
            ir_ref=problem_ref,
            algorithm_profile_digest=digest_value({
                "provider_id": provider_id,
                "provider_version": PROVIDER_VERSION,
                "features": features.to_dict(),
            }),
            limits_ref=limits_ref,
            seed=seed,
        )
        invocation_ref = self._register(BACKEND_INVOCATION_KIND, invocation.to_dict())
        provider_run = self._invoke_provider(
            provider_id,
            canonical_bytes(problem),
            problem_ref.digest,
            deadline_ms=limits.solver_deadline_ms,
            cancel_check=cancel_check,
            expected_runtime_identity={
                "provider_binary_digest": capability["provider_binary_digest"],
                "provider_package_digest": capability["provider_package_digest"],
                "provider_build_inputs": capability["provider_build_inputs"],
            },
        )
        self._validate_run(provider_run, provider_id, problem_ref)
        result_document = parse_json_document(provider_run.result_bytes)
        if type(result_document) is not dict:
            _fail("BACKEND_PROVIDER_RESULT", "backend result must be an object")
        result_ref = self._register(BACKEND_RESULT_KIND, result_document)
        proof_ref = None
        if provider_run.proof_bytes is not None:
            proof_document = parse_json_document(provider_run.proof_bytes)
            if type(proof_document) is not dict:
                _fail("BACKEND_PROVIDER_PROOF", "backend proof must be an object")
            proof_ref = self._register(BACKEND_PROOF_KIND, proof_document)
        receipt_body = {
            "receipt_id": f"solver-{invocation_ref.digest.hex}-{result_ref.digest.hex}",
            "run_identity_ref": run_identity_ref.to_dict(),
            "invocation_ref": invocation_ref.to_dict(),
            "status": provider_run.status,
            "exit_status": provider_run.exit_status,
            "backend_result_ref": result_ref.to_dict(),
            "model_or_core_ref": None,
            "proof_ref": None if proof_ref is None else proof_ref.to_dict(),
            "issued_at": now.to_dict(),
        }
        evidence_refs = (
            problem_ref,
            invocation_ref,
            result_ref,
            *((proof_ref,) if proof_ref is not None else ()),
        )
        payload_digest = digest_value(receipt_body)
        signature = self._receipt_signer(
            result_ref.digest,
            payload_digest,
            evidence_refs,
            run_identity_ref,
            now,
        )
        if type(signature) is not SignatureEnvelopeV4:
            _fail("BACKEND_RECEIPT_SIGNATURE", "receipt signer returned the wrong type")
        receipt = SolverReceiptV4.from_dict({
            **receipt_body,
            "signature": signature.to_dict(),
        })
        self._verify_receipt_signature(
            receipt,
            problem_ref=problem_ref,
            invocation_ref=invocation_ref,
            now=now,
        )
        receipt_ref = self._register(SOLVER_RECEIPT_KIND, receipt.to_dict())
        return BackendExecutionV4(
            features,
            problem_ref,
            invocation,
            invocation_ref,
            receipt,
            receipt_ref,
        )

    def execute(
        self,
        compilations: tuple[LegalIRCompilationV4, ...],
        *,
        run_identity_ref: ContentRefV4,
        fact_admission_receipt_refs: tuple[ContentRefV4, ...],
        limits: ResourceLimitsV4,
        now: CanonicalTimeV4,
        seed: int = 0,
        cancel_check: Callable[[], bool] | None = None,
    ) -> tuple[BackendExecutionV4, ...]:
        if (
            type(now) is not CanonicalTimeV4
            or type(limits) is not ResourceLimitsV4
            or type(seed) is not int
            or (cancel_check is not None and not callable(cancel_check))
            or type(limits.solver_deadline_ms) is not int
        ):
            _fail("BACKEND_INPUT_TYPE", "backend context is invalid")
        run = self._resolve_run(run_identity_ref)
        runtime_identity = provider_runtime_identity()
        if run.backend_profile_digest != _backend_profile_digest_v4(
            solver_deadline_ms=limits.solver_deadline_ms,
            seed=seed,
            provider_ids=CERTIFIED_PROVIDER_IDS_V4,
            runtime_identity=runtime_identity,
        ):
            _fail(
                "BACKEND_PROFILE_BINDING",
                "run identity does not bind the active backend profile",
            )
        request = self._request(run)
        compilations = self._compilations(
            compilations,
            run_identity_ref=run_identity_ref,
            now=now,
        )
        features = self._features(compilations)
        providers = self._providers(features)
        if providers != _providers_from_route_table_v4(features):
            _fail(
                "BACKEND_ROUTING_BINDING",
                "provider selection differs from the bound routing table",
            )
        limits_ref = self._register(BACKEND_LIMITS_KIND, {
            "schema_version": "jc/backend-limits/1.0",
            "solver_deadline_ms": limits.solver_deadline_ms,
            "seed": seed,
        })
        return tuple(
            self._execute_provider(
                provider_id,
                compilations,
                run=run,
                run_identity_ref=run_identity_ref,
                fact_admission_receipt_refs=fact_admission_receipt_refs,
                decision_time=request.decision_time,
                limits=limits,
                limits_ref=limits_ref,
                features=features,
                now=now,
                seed=seed,
                cancel_check=cancel_check,
                runtime_identity=runtime_identity,
            )
            for provider_id in providers
        )

    def replay(
        self,
        execution: BackendExecutionV4,
        *,
        now: CanonicalTimeV4,
        cancel_check: Callable[[], bool] | None = None,
    ) -> bool:
        """Re-execute exact canonical input and compare semantic bytes only."""

        if type(execution) is not BackendExecutionV4 or type(now) is not CanonicalTimeV4:
            _fail("BACKEND_REPLAY_INPUT", "replay requires an issued execution and time")
        invocation_document = self._resolve_json(
            execution.invocation_ref,
            kind=BACKEND_INVOCATION_KIND,
            scope=BACKEND_SCOPE,
        )
        receipt_document = self._resolve_json(
            execution.receipt_ref,
            kind=SOLVER_RECEIPT_KIND,
            scope=BACKEND_SCOPE,
        )
        if (
            invocation_document != execution.invocation.to_dict()
            or receipt_document != execution.receipt.to_dict()
            or execution.invocation.ir_ref != execution.problem_ref
            or execution.receipt.invocation_ref != execution.invocation_ref
        ):
            _fail("BACKEND_REPLAY_BINDING", "execution artifacts differ from their handles")
        problem = self._resolve_json(
            execution.problem_ref,
            kind=BACKEND_PROBLEM_KIND,
            scope=BACKEND_SCOPE,
        )
        stored_result = self._resolve_json(
            execution.receipt.backend_result_ref,
            kind=BACKEND_RESULT_KIND,
            scope=BACKEND_SCOPE,
        )
        stored_proof = (
            None
            if execution.receipt.proof_ref is None
            else self._resolve_json(
                execution.receipt.proof_ref,
                kind=BACKEND_PROOF_KIND,
                scope=BACKEND_SCOPE,
            )
        )
        if (
            problem.get("run_identity_ref") != execution.receipt.run_identity_ref.to_dict()
            or problem.get("limits_ref") != execution.invocation.limits_ref.to_dict()
        ):
            _fail("BACKEND_REPLAY_BINDING", "problem context differs from execution")
        limits = self._resolve_json(
            execution.invocation.limits_ref,
            kind=BACKEND_LIMITS_KIND,
            scope=BACKEND_SCOPE,
        )
        deadline_ms = limits.get("solver_deadline_ms")
        if (
            limits.get("schema_version") != "jc/backend-limits/1.0"
            or type(deadline_ms) is not int
            or limits.get("seed") != execution.invocation.seed
        ):
            _fail("BACKEND_REPLAY_BINDING", "backend limits are malformed")
        live_capability, live_capability_ref = self._provider_identity(
            execution.invocation.provider_id,
            execution.features,
            ResourceLimitsV4(solver_deadline_ms=deadline_ms),
        )
        if live_capability_ref != execution.invocation.provider_capability_ref:
            _fail("BACKEND_PROVIDER_IDENTITY", "live provider build differs from invocation")
        replayed = self._invoke_provider(
            execution.invocation.provider_id,
            canonical_bytes(problem),
            execution.problem_ref.digest,
            deadline_ms=deadline_ms,
            cancel_check=cancel_check,
            expected_runtime_identity={
                "provider_binary_digest": live_capability["provider_binary_digest"],
                "provider_package_digest": live_capability["provider_package_digest"],
                "provider_build_inputs": live_capability["provider_build_inputs"],
            },
        )
        self._validate_run(replayed, execution.invocation.provider_id, execution.problem_ref)
        if (
            replayed.status != execution.receipt.status
            or replayed.exit_status != execution.receipt.exit_status
            or replayed.result_bytes != canonical_bytes(stored_result)
            or (
                replayed.proof_bytes
            )
            != (
                None
                if stored_proof is None
                else canonical_bytes(stored_proof)
            )
        ):
            _fail("BACKEND_REPLAY_MISMATCH", "provider semantic replay differs")
        self._verify_receipt_signature(
            execution.receipt,
            problem_ref=execution.problem_ref,
            invocation_ref=execution.invocation_ref,
            now=now,
        )
        return True
