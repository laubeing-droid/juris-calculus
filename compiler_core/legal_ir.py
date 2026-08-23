"""Loss-accounted RuleV4 -> LegalSpecV4 -> LegalIVLV4 lowering."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Callable

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
    LegalIVLV4,
    LegalSpecV4,
    PackSignatureV4,
    RulePromotionReceiptV4,
    RuleV4,
    RunIdentityV4,
    SignatureEnvelopeV4,
    TranslationReceiptV4,
)
from compiler_core.rule_packs import (
    JSON_MEDIA_TYPE,
    LEGAL_APPROVAL_KIND,
    LEGAL_APPROVAL_SCOPE,
    PACK_SIGNATURE_KIND,
    RULE_KIND,
    RULE_PACK_SCOPE,
    RULE_PROMOTION_RECEIPT_KIND,
    TRUST_POLICY_KIND,
    RulePackVerifierV4,
    VerifiedRulePackV4,
    rule_promotion_subject_ref,
    rule_review_evidence_refs,
)
from compiler_core.trust import TrustVerifierV4


LEGAL_IR_SCOPE = "legal-ir"
LEGAL_SPEC_KIND = "legal-spec-v4"
LEGAL_IVL_KIND = "legal-ivl-v4"
IR_TYPE_ENVIRONMENT_KIND = "legal-ir-type-environment"
IR_MODALITY_KIND = "legal-ir-modality"
IR_CLAUSE_KIND = "legal-ir-clause"
IR_SOURCE_MAP_KIND = "legal-ir-source-map"
IR_PROOF_OBLIGATION_KIND = "legal-ir-proof-obligation"
IR_FIELD_MAPPING_KIND = "legal-ir-field-mapping"
IR_TRANSLATOR_KIND = "legal-ir-translator"
TRANSLATION_RECEIPT_KIND = "translation-receipt"
RUN_IDENTITY_KIND = "run-identity"
RUN_IDENTITY_SCOPE = "run"

RULE_TO_SPEC_HOP = "RuleV4->LegalSpecV4"
SPEC_TO_IVL_HOP = "LegalSpecV4->LegalIVLV4"

TranslationSignerV4 = Callable[
    [
        DigestV4,
        DigestV4,
        tuple[ContentRefV4, ...],
        ContentRefV4,
        CanonicalTimeV4,
    ],
    SignatureEnvelopeV4,
]

_MappingRow = tuple[tuple[str, ...], tuple[str, ...], str, str]

_RULE_TO_SPEC_ROWS: tuple[_MappingRow, ...] = (
    (("rule_id",), ("spec_id",), "preserve", "identity"),
    (("rule_digest",), ("rule_ref",), "lower", "content-ref"),
) + tuple(
    ((name,), (name,), "preserve", "identity")
    for name in (
        "jurisdiction",
        "governing_law",
        "authority_ref",
        "variable_declaration_refs",
        "premise_refs",
        "conclusion_ref",
        "modality",
        "permission_ref",
        "exception_refs",
        "priority_refs",
        "attack_refs",
        "temporal_constraint_refs",
        "numeric_constraint_refs",
        "source_snapshot_ref",
        "source_locator",
        "source_structure_ref",
        "interpretation_choice_refs",
        "defined_term_refs",
        "promotion_receipt_refs",
        "effective_from",
        "effective_to",
    )
)

_SPEC_TO_IVL_ROWS: tuple[_MappingRow, ...] = (
    (("spec_id",), ("ivl_id",), "preserve", "identity"),
    (("spec_digest",), ("spec_ref",), "lower", "content-ref"),
    (("authority_ref",), ("authority_ref",), "preserve", "identity"),
    (
        ("variable_declaration_refs",),
        ("variable_declaration_refs",),
        "preserve",
        "identity",
    ),
    (("premise_refs",), ("premise_refs",), "preserve", "identity"),
    (("conclusion_ref",), ("conclusion_ref",), "preserve", "identity"),
    (("permission_ref",), ("permission_refs",), "lower", "optional-to-tuple"),
    (
        ("exception_refs", "attack_refs"),
        ("exception_attack_refs",),
        "lower",
        "typed-ref-concat",
    ),
    (("priority_refs",), ("priority_refs",), "preserve", "identity"),
    (
        ("temporal_constraint_refs",),
        ("temporal_constraint_refs",),
        "preserve",
        "identity",
    ),
    (
        ("numeric_constraint_refs",),
        ("numeric_constraint_refs",),
        "preserve",
        "identity",
    ),
    (
        ("interpretation_choice_refs",),
        ("interpretation_choice_refs",),
        "preserve",
        "identity",
    ),
    (("defined_term_refs",), ("defined_term_refs",), "preserve", "identity"),
    (
        ("jurisdiction", "governing_law", "variable_declaration_refs", "defined_term_refs"),
        ("type_environment_ref",),
        "lower",
        "type-environment",
    ),
    (("modality", "permission_ref"), ("modality_ref",), "lower", "modality"),
    (
        ("premise_refs", "conclusion_ref", "modality", "permission_ref", "effective_from", "effective_to"),
        ("clause_refs",),
        "lower",
        "clause",
    ),
    (
        (
            "rule_ref",
            "source_snapshot_ref",
            "source_locator",
            "source_structure_ref",
            "promotion_receipt_refs",
            "effective_from",
            "effective_to",
        ),
        ("source_map_ref",),
        "lower",
        "source-map",
    ),
    (
        ("interpretation_choice_refs", "promotion_receipt_refs"),
        ("interpretation_approval_refs",),
        "lower",
        "approved-interpretation",
    ),
)


def _fail(code: str, detail: str) -> None:
    raise ContractV4Error(code, detail)


def _sorted_refs(references: tuple[ContentRefV4, ...]) -> tuple[ContentRefV4, ...]:
    if any(type(reference) is not ContentRefV4 for reference in references):
        _fail("IR_REFERENCE_TYPE", "evidence must contain exact ContentRefV4 values")
    if len(set(references)) != len(references):
        _fail("IR_DUPLICATE_REFERENCE", "evidence references must not repeat")
    return tuple(sorted(references, key=lambda item: (item.kind, str(item.digest))))


@dataclass(frozen=True, slots=True)
class LegalIRCompilationV4:
    rule: RuleV4
    rule_ref: ContentRefV4
    spec: LegalSpecV4
    spec_ref: ContentRefV4
    ivl: LegalIVLV4
    ivl_ref: ContentRefV4
    rule_to_spec_receipt: TranslationReceiptV4
    rule_to_spec_receipt_ref: ContentRefV4
    spec_to_ivl_receipt: TranslationReceiptV4
    spec_to_ivl_receipt_ref: ContentRefV4


class LegalIRCompilerV4:
    """Issue formal translations only for an already verified pack rule."""

    def __init__(
        self,
        pack_verifier: RulePackVerifierV4,
        *,
        receipt_issuer: str,
        receipt_signer: TranslationSignerV4,
    ) -> None:
        if (
            type(pack_verifier) is not RulePackVerifierV4
            or type(receipt_issuer) is not str
            or not receipt_issuer
            or not callable(receipt_signer)
        ):
            _fail("IR_INPUT_TYPE", "legal IR compiler dependencies are invalid")
        self._pack_verifier = pack_verifier
        self._resolver = pack_verifier._resolver
        self._trust = pack_verifier._trust
        self._receipt_issuer = receipt_issuer
        self._receipt_signer = receipt_signer
        self._compiled: dict[
            tuple[ContentRefV4, ContentRefV4, ContentRefV4], LegalIRCompilationV4
        ] = {}

    def _register_json(self, kind: str, payload: dict[str, object]) -> ContentRefV4:
        raw = canonical_bytes(payload)
        reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
        return self._resolver.register_bytes(
            artifact_id=f"{kind}-{reference.digest.hex}",
            content_ref=reference,
            artifact_kind=kind,
            media_type=JSON_MEDIA_TYPE,
            scope=LEGAL_IR_SCOPE,
            content=raw,
        )

    def _register_self_digest(self, kind: str, value: object) -> ContentRefV4:
        digest = value.canonical_digest()
        reference = ContentRefV4(kind, digest)
        raw = canonical_bytes(value.digest_body())
        if DigestV4.from_bytes(raw) != digest:
            _fail("IR_SELF_DIGEST", f"{kind} digest body is inconsistent")
        return self._resolver.register_bytes(
            artifact_id=f"{kind}-{digest.hex}",
            content_ref=reference,
            artifact_kind=kind,
            media_type=JSON_MEDIA_TYPE,
            scope=LEGAL_IR_SCOPE,
            content=raw,
        )

    def _resolve_contract(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
        contract: type,
    ) -> object:
        if type(reference) is not ContentRefV4 or reference.kind != kind:
            _fail("IR_REF_KIND", f"expected {kind} content reference")
        raw = self._resolver.resolve_content(
            reference,
            expected_artifact_kind=kind,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope=scope,
            max_bytes=self._resolver.max_artifact_bytes,
        )
        document = parse_json_document(raw)
        if type(document) is not dict:
            _fail("IR_JSON_TYPE", f"{kind} must be a JSON object")
        value = contract.from_dict(document)
        if raw != value.canonical_bytes():
            _fail("IR_NONCANONICAL_JSON", f"{kind} must use canonical contract bytes")
        return value

    def _resolve_self_digest(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
        contract: type,
        digest_field: str,
    ) -> object:
        if type(reference) is not ContentRefV4 or reference.kind != kind:
            _fail("IR_REF_KIND", f"expected {kind} content reference")
        raw = self._resolver.resolve_content(
            reference,
            expected_artifact_kind=kind,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope=scope,
            max_bytes=self._resolver.max_artifact_bytes,
        )
        body = parse_json_document(raw)
        if type(body) is not dict or digest_field in body or raw != canonical_bytes(body):
            _fail("IR_DIGEST_BODY", f"{kind} must store its canonical digest body")
        value = contract.from_dict({**body, digest_field: str(reference.digest)})
        if value.canonical_digest() != reference.digest or value.digest_body() != body:
            _fail("IR_SELF_DIGEST", f"{kind} self digest is inconsistent")
        return value

    def _select_rule(
        self, pack: VerifiedRulePackV4, rule_ref: ContentRefV4
    ) -> RuleV4:
        if type(pack) is not VerifiedRulePackV4:
            _fail("IR_PACK_HANDLE", "formal lowering requires VerifiedRulePackV4")
        if (
            not pack.verifier_issued
            or self._pack_verifier._verified.get(pack.pack_ref) is not pack
            or pack.status != "VERIFIED_ACTIVE"
        ):
            _fail("IR_PACK_HANDLE", "pack handle is not verifier-issued and active")
        if type(rule_ref) is not ContentRefV4 or rule_ref.kind != RULE_KIND:
            _fail("IR_INPUT_TYPE", "rule_ref must be an exact rule-v4 reference")
        matches = [
            rule
            for reference, rule in zip(pack.manifest.rule_refs, pack.rules)
            if reference == rule_ref
        ]
        if len(matches) != 1 or matches[0].rule_digest != rule_ref.digest:
            _fail("IR_RULE_NOT_IN_PACK", "rule_ref is not the exact verified pack rule")
        return matches[0]

    def _validate_run_identity(
        self,
        reference: ContentRefV4,
        *,
        pack: VerifiedRulePackV4,
    ) -> RunIdentityV4:
        value = self._resolve_self_digest(
            reference,
            kind=RUN_IDENTITY_KIND,
            scope=RUN_IDENTITY_SCOPE,
            contract=RunIdentityV4,
            digest_field="run_digest",
        )
        if type(value) is not RunIdentityV4:
            _fail("IR_RUN_BINDING", "run identity has the wrong contract type")
        policy_ref = ContentRefV4(TRUST_POLICY_KIND, self._trust.policy.canonical_digest())
        if (
            value.rule_pack_ref != pack.pack_ref
            or value.trust_policy_ref != policy_ref
            or value.schema_digest != pack.manifest.schema_digest
        ):
            _fail("IR_RUN_BINDING", "run identity does not bind pack, trust, and schema")
        return value

    def _current_interpretation_approval(
        self,
        pack: VerifiedRulePackV4,
        rule: RuleV4,
        *,
        now: CanonicalTimeV4,
    ) -> tuple[tuple[ContentRefV4, ...], str, CanonicalTimeV4]:
        if len(rule.promotion_receipt_refs) != 1:
            _fail("IR_PROMOTION_BINDING", "formal rule requires one promotion receipt")
        promotion_ref = rule.promotion_receipt_refs[0]
        promotion = self._resolve_contract(
            promotion_ref,
            kind=RULE_PROMOTION_RECEIPT_KIND,
            scope=RULE_PACK_SCOPE,
            contract=RulePromotionReceiptV4,
        )
        if type(promotion) is not RulePromotionReceiptV4:
            _fail("IR_PROMOTION_BINDING", "promotion receipt has the wrong type")
        subject_ref = rule_promotion_subject_ref(rule)
        if (
            promotion.rule_subject_digest != subject_ref.digest
            or promotion.status != "APPROVED"
            or promotion.signature.issued_at != promotion.issued_at
        ):
            _fail("IR_PROMOTION_BINDING", "promotion does not approve the exact rule")
        legal = self._resolve_contract(
            promotion.legal_review_ref,
            kind=LEGAL_APPROVAL_KIND,
            scope=LEGAL_APPROVAL_SCOPE,
            contract=SignatureEnvelopeV4,
        )
        if type(legal) is not SignatureEnvelopeV4 or legal.run_identity_ref is not None:
            _fail("IR_INTERPRETATION_APPROVAL", "legal approval has the wrong envelope")
        expected_evidence = rule_review_evidence_refs(
            rule,
            subject_ref,
            self._trust.policy.replay_policy_ref,
            "legal",
        )
        if legal.evidence_refs != expected_evidence:
            _fail(
                "IR_INTERPRETATION_APPROVAL",
                "legal approval does not bind exact interpretation choices",
            )
        principal = self._trust._fresh_without_replay().verify(
            legal,
            expected_subject_digest=subject_ref.digest,
            expected_payload_digest=subject_ref.digest,
            required_role="legal_reviewer",
            required_scope=LEGAL_APPROVAL_SCOPE,
            required_artifact_kind=LEGAL_APPROVAL_KIND,
            expected_status="APPROVED",
            now=now,
            separation_from_principals=(),
        )
        release = self._resolve_contract(
            pack.pack_ref,
            kind=PACK_SIGNATURE_KIND,
            scope=RULE_PACK_SCOPE,
            contract=PackSignatureV4,
        )
        expiries = (
            legal.expires_at,
            promotion.signature.expires_at,
            release.signature.expires_at,
        )
        if (
            type(release) is not PackSignatureV4
            or any(expiry is None or not now < expiry for expiry in expiries)
            or now < promotion.issued_at
            or now < release.signature.issued_at
        ):
            _fail("IR_APPROVAL_TIME", "approval or pack release is not active")
        return (promotion.legal_review_ref,), principal, min(expiries)

    def _project_rule_to_spec(
        self,
        rule: RuleV4,
        *,
        rule_ref: ContentRefV4,
    ) -> tuple[LegalSpecV4, ContentRefV4]:
        if (
            type(rule) is not RuleV4
            or type(rule_ref) is not ContentRefV4
            or rule_ref.kind != RULE_KIND
            or rule_ref.digest != rule.rule_digest
        ):
            _fail("IR_RULE_REFERENCE", "projection requires the exact RuleV4 reference")
        rule_wire = rule.to_dict()
        body = {
            "spec_id": rule.rule_id,
            "rule_ref": rule_ref.to_dict(),
            **{
                name: rule_wire[name]
                for name in (
                    "jurisdiction",
                    "governing_law",
                    "authority_ref",
                    "variable_declaration_refs",
                    "premise_refs",
                    "conclusion_ref",
                    "modality",
                    "permission_ref",
                    "exception_refs",
                    "priority_refs",
                    "attack_refs",
                    "temporal_constraint_refs",
                    "numeric_constraint_refs",
                    "source_snapshot_ref",
                    "source_locator",
                    "source_structure_ref",
                    "interpretation_choice_refs",
                    "defined_term_refs",
                    "promotion_receipt_refs",
                    "effective_from",
                    "effective_to",
                )
            },
        }
        spec = LegalSpecV4.from_dict({**body, "spec_digest": str(digest_value(body))})
        return spec, self._register_self_digest(LEGAL_SPEC_KIND, spec)

    def _project_spec_to_ivl(
        self,
        spec: LegalSpecV4,
        *,
        spec_ref: ContentRefV4,
        interpretation_approval_refs: tuple[ContentRefV4, ...],
    ) -> tuple[LegalIVLV4, ContentRefV4]:
        if (
            type(spec) is not LegalSpecV4
            or type(spec_ref) is not ContentRefV4
            or spec_ref.kind != LEGAL_SPEC_KIND
            or spec_ref.digest != spec.spec_digest
            or type(interpretation_approval_refs) is not tuple
            or not interpretation_approval_refs
            or any(
                type(reference) is not ContentRefV4
                or reference.kind != LEGAL_APPROVAL_KIND
                for reference in interpretation_approval_refs
            )
        ):
            _fail("IR_SPEC_REFERENCE", "IVL projection requires exact spec and approvals")

        type_environment_ref = self._register_json(IR_TYPE_ENVIRONMENT_KIND, {
            "schema_version": "jc/legal-ir-type-environment/1.0",
            "spec_ref": spec_ref.to_dict(),
            "jurisdiction": spec.jurisdiction,
            "governing_law": spec.governing_law,
            "variable_declaration_refs": [item.to_dict() for item in spec.variable_declaration_refs],
            "defined_term_refs": [item.to_dict() for item in spec.defined_term_refs],
        })
        modality_ref = self._register_json(IR_MODALITY_KIND, {
            "schema_version": "jc/legal-ir-modality/1.0",
            "spec_ref": spec_ref.to_dict(),
            "modality": spec.modality,
            "permission_ref": spec.permission_ref.to_dict() if spec.permission_ref else None,
        })
        clause_ref = self._register_json(IR_CLAUSE_KIND, {
            "schema_version": "jc/legal-ir-clause/1.0",
            "spec_ref": spec_ref.to_dict(),
            "premise_refs": [item.to_dict() for item in spec.premise_refs],
            "conclusion_ref": spec.conclusion_ref.to_dict(),
            "modality_ref": modality_ref.to_dict(),
            "effective_from": spec.effective_from.to_dict(),
            "effective_to": spec.effective_to.to_dict() if spec.effective_to else None,
        })
        source_map_ref = self._register_json(IR_SOURCE_MAP_KIND, {
            "schema_version": "jc/legal-ir-source-map/1.0",
            "spec_ref": spec_ref.to_dict(),
            "rule_ref": spec.rule_ref.to_dict(),
            "source_snapshot_ref": spec.source_snapshot_ref.to_dict(),
            "source_locator": spec.source_locator.to_dict(),
            "source_structure_ref": spec.source_structure_ref.to_dict(),
            "promotion_receipt_refs": [item.to_dict() for item in spec.promotion_receipt_refs],
            "effective_from": spec.effective_from.to_dict(),
            "effective_to": spec.effective_to.to_dict() if spec.effective_to else None,
        })
        exception_attack_refs = (*spec.exception_refs, *spec.attack_refs)
        permission_refs = (spec.permission_ref,) if spec.permission_ref is not None else ()
        proof_ref = self._register_json(IR_PROOF_OBLIGATION_KIND, {
            "schema_version": "jc/legal-ir-proof-obligation/1.0",
            "obligation": "loss-accounted-ivl-lowering",
            "spec_ref": spec_ref.to_dict(),
            "type_environment_ref": type_environment_ref.to_dict(),
            "modality_ref": modality_ref.to_dict(),
            "clause_refs": [clause_ref.to_dict()],
            "source_map_ref": source_map_ref.to_dict(),
            "authority_ref": spec.authority_ref.to_dict(),
            "exception_attack_refs": [item.to_dict() for item in exception_attack_refs],
            "permission_refs": [item.to_dict() for item in permission_refs],
            "priority_refs": [item.to_dict() for item in spec.priority_refs],
            "temporal_constraint_refs": [item.to_dict() for item in spec.temporal_constraint_refs],
            "numeric_constraint_refs": [item.to_dict() for item in spec.numeric_constraint_refs],
            "interpretation_choice_refs": [item.to_dict() for item in spec.interpretation_choice_refs],
            "interpretation_approval_refs": [item.to_dict() for item in interpretation_approval_refs],
            "defined_term_refs": [item.to_dict() for item in spec.defined_term_refs],
        })
        body = {
            "ivl_id": spec.spec_id,
            "spec_ref": spec_ref.to_dict(),
            "type_environment_ref": type_environment_ref.to_dict(),
            "authority_ref": spec.authority_ref.to_dict(),
            "variable_declaration_refs": [item.to_dict() for item in spec.variable_declaration_refs],
            "premise_refs": [item.to_dict() for item in spec.premise_refs],
            "conclusion_ref": spec.conclusion_ref.to_dict(),
            "modality_ref": modality_ref.to_dict(),
            "clause_refs": [clause_ref.to_dict()],
            "exception_attack_refs": [item.to_dict() for item in exception_attack_refs],
            "permission_refs": [item.to_dict() for item in permission_refs],
            "priority_refs": [item.to_dict() for item in spec.priority_refs],
            "temporal_constraint_refs": [item.to_dict() for item in spec.temporal_constraint_refs],
            "numeric_constraint_refs": [item.to_dict() for item in spec.numeric_constraint_refs],
            "source_map_ref": source_map_ref.to_dict(),
            "interpretation_choice_refs": [item.to_dict() for item in spec.interpretation_choice_refs],
            "interpretation_approval_refs": [item.to_dict() for item in interpretation_approval_refs],
            "defined_term_refs": [item.to_dict() for item in spec.defined_term_refs],
            "proof_obligation_refs": [proof_ref.to_dict()],
        }
        ivl = LegalIVLV4.from_dict({**body, "ivl_digest": str(digest_value(body))})
        return ivl, self._register_self_digest(LEGAL_IVL_KIND, ivl)

    def _field_mapping(
        self,
        *,
        hop: str,
        source: object,
        source_ref: ContentRefV4,
        target: object,
        target_ref: ContentRefV4,
        rows: tuple[_MappingRow, ...],
        derived_targets: tuple[str, ...],
    ) -> tuple[ContentRefV4, tuple[str, ...]]:
        source_fields = tuple(item.name for item in fields(source))
        target_fields = tuple(item.name for item in fields(target))
        known_source = set(source_fields)
        known_target = set(target_fields)
        covered_source: set[str] = set()
        covered_target = set(derived_targets)
        unsupported: set[str] = set()
        wire_rows: list[dict[str, object]] = []
        for sources, targets, disposition, transform in rows:
            if (
                disposition not in {"preserve", "lower", "explicitly_unsupported"}
                or not set(sources) <= known_source
                or not set(targets) <= known_target
                or (disposition == "explicitly_unsupported") != (not targets)
            ):
                _fail("IR_FIELD_MAPPING", f"{hop} contains an invalid field mapping row")
            if disposition == "preserve" and transform == "identity":
                if len(sources) != 1 or len(targets) != 1 or (
                    getattr(source, sources[0]) != getattr(target, targets[0])
                ):
                    _fail("IR_FIELD_MAPPING", f"{hop} changed preserved field {sources[0]}")
            if transform == "content-ref":
                if len(sources) != 1 or len(targets) != 1 or (
                    getattr(target, targets[0]).digest != getattr(source, sources[0])
                ):
                    _fail("IR_FIELD_MAPPING", f"{hop} changed content identity")
            if transform == "optional-to-tuple":
                value = getattr(source, sources[0])
                expected = (value,) if value is not None else ()
                if getattr(target, targets[0]) != expected:
                    _fail("IR_FIELD_MAPPING", f"{hop} defaulted an optional reference")
            if transform == "typed-ref-concat" and getattr(target, targets[0]) != (
                getattr(source, sources[0]) + getattr(source, sources[1])
            ):
                _fail("IR_FIELD_MAPPING", f"{hop} changed typed exception/attack refs")
            covered_source.update(sources)
            covered_target.update(targets)
            if disposition == "explicitly_unsupported":
                unsupported.update(sources)
            wire_rows.append({
                "source_fields": list(sources),
                "target_fields": list(targets),
                "disposition": disposition,
                "transform": transform,
            })
        lost = tuple(name for name in source_fields if name not in covered_source)
        defaulted = tuple(name for name in target_fields if name not in covered_target)
        unsupported_fields = tuple(name for name in source_fields if name in unsupported)
        if lost or defaulted or unsupported_fields:
            _fail(
                "IR_TRANSLATION_LOSS",
                f"{hop} lost={lost!r} defaulted={defaulted!r} unsupported={unsupported_fields!r}",
            )
        mapping_ref = self._register_json(IR_FIELD_MAPPING_KIND, {
            "schema_version": "jc/legal-ir-field-mapping/1.0",
            "hop": hop,
            "source_ref": source_ref.to_dict(),
            "target_ref": target_ref.to_dict(),
            "source_contract": type(source).__name__,
            "target_contract": type(target).__name__,
            "source_fields": list(source_fields),
            "target_fields": list(target_fields),
            "derived_target_fields": list(derived_targets),
            "mappings": wire_rows,
        })
        return mapping_ref, source_fields

    def _translator_ref(self, hop: str, run: RunIdentityV4) -> ContentRefV4:
        return self._register_json(IR_TRANSLATOR_KIND, {
            "schema_version": "jc/legal-ir-translator/1.0",
            "implementation": "compiler_core.legal_ir:LegalIRCompilerV4",
            "hop": hop,
            "engine_build_digest": str(run.engine_build_digest),
            "package_digest": str(run.package_digest),
            "schema_digest": str(run.schema_digest),
            "algorithm_profile_digest": str(run.algorithm_profile_digest),
        })

    def _receipt_evidence(
        self,
        *,
        pack: VerifiedRulePackV4,
        run_identity_ref: ContentRefV4,
        translator_ref: ContentRefV4,
        source_ref: ContentRefV4,
        target_ref: ContentRefV4,
        field_mapping_ref: ContentRefV4,
        approval_refs: tuple[ContentRefV4, ...],
        proof_refs: tuple[ContentRefV4, ...],
        previous_receipt_ref: ContentRefV4 | None,
    ) -> tuple[ContentRefV4, ...]:
        return _sorted_refs((
            pack.pack_ref,
            pack.manifest_ref,
            run_identity_ref,
            translator_ref,
            source_ref,
            target_ref,
            field_mapping_ref,
            *approval_refs,
            *proof_refs,
            *((previous_receipt_ref,) if previous_receipt_ref is not None else ()),
            self._trust.policy.replay_policy_ref,
        ))

    def _make_receipt(
        self,
        *,
        hop: str,
        run_identity_ref: ContentRefV4,
        translator_ref: ContentRefV4,
        source_ref: ContentRefV4,
        target_ref: ContentRefV4,
        field_mapping_ref: ContentRefV4,
        field_coverage: tuple[str, ...],
        proof_refs: tuple[ContentRefV4, ...],
        evidence_refs: tuple[ContentRefV4, ...],
        now: CanonicalTimeV4,
    ) -> tuple[TranslationReceiptV4, ContentRefV4]:
        body = {
            "receipt_id": f"translation-{target_ref.digest.hex}-{hop.split('->')[0].lower()}",
            "run_identity_ref": run_identity_ref.to_dict(),
            "hop": hop,
            "translator_ref": translator_ref.to_dict(),
            "source_ref": source_ref.to_dict(),
            "target_ref": target_ref.to_dict(),
            "field_mapping_ref": field_mapping_ref.to_dict(),
            "field_coverage": list(field_coverage),
            "lost_fields": [],
            "defaulted_fields": [],
            "unsupported_fields": [],
            "counterexample_refs": [],
            "proof_obligation_refs": [item.to_dict() for item in proof_refs],
            "status": "PASS",
            "issued_at": now.to_dict(),
        }
        signature = self._receipt_signer(
            target_ref.digest,
            digest_value(body),
            evidence_refs,
            run_identity_ref,
            now,
        )
        if type(signature) is not SignatureEnvelopeV4:
            _fail("IR_RECEIPT_SIGNATURE", "receipt signer returned the wrong contract")
        receipt = TranslationReceiptV4.from_dict({**body, "signature": signature.to_dict()})
        reference = ContentRefV4(
            TRANSLATION_RECEIPT_KIND,
            DigestV4.from_bytes(receipt.canonical_bytes()),
        )
        return receipt, reference

    def _verify_receipt(
        self,
        receipt: TranslationReceiptV4,
        *,
        reference: ContentRefV4,
        expected_hop: str,
        run_identity_ref: ContentRefV4,
        translator_ref: ContentRefV4,
        source_ref: ContentRefV4,
        target_ref: ContentRefV4,
        field_mapping_ref: ContentRefV4,
        field_coverage: tuple[str, ...],
        proof_refs: tuple[ContentRefV4, ...],
        evidence_refs: tuple[ContentRefV4, ...],
        legal_principal: str,
        expiry_ceiling: CanonicalTimeV4,
        now: CanonicalTimeV4,
        trust: TrustVerifierV4,
    ) -> None:
        expected_id = f"translation-{target_ref.digest.hex}-{expected_hop.split('->')[0].lower()}"
        if (
            type(receipt) is not TranslationReceiptV4
            or reference.kind != TRANSLATION_RECEIPT_KIND
            or reference.digest != DigestV4.from_bytes(receipt.canonical_bytes())
            or receipt.receipt_id != expected_id
            or receipt.run_identity_ref != run_identity_ref
            or receipt.hop != expected_hop
            or receipt.translator_ref != translator_ref
            or receipt.source_ref != source_ref
            or receipt.target_ref != target_ref
            or receipt.field_mapping_ref != field_mapping_ref
            or receipt.field_coverage != field_coverage
            or receipt.lost_fields
            or receipt.defaulted_fields
            or receipt.unsupported_fields
            or receipt.counterexample_refs
            or receipt.proof_obligation_refs != proof_refs
            or receipt.status != "PASS"
        ):
            _fail("IR_RECEIPT_BINDING", "translation receipt is not exact zero-loss PASS")
        signature = receipt.signature
        if (
            signature.issuer != self._receipt_issuer
            or signature.run_identity_ref != run_identity_ref
            or signature.issued_at != receipt.issued_at
            or now < signature.issued_at
            or signature.expires_at is None
            or not now < signature.expires_at
            or expiry_ceiling < signature.expires_at
            or signature.evidence_refs != evidence_refs
        ):
            _fail("IR_RECEIPT_ENVELOPE", "translation signature context or lifetime differs")
        trust.verify(
            signature,
            expected_subject_digest=target_ref.digest,
            expected_payload_digest=digest_value(receipt.signature_body()),
            required_role="service_signer",
            required_scope="service-certificate",
            required_artifact_kind="service-certificate",
            expected_status="APPROVED",
            now=now,
            separation_from_principals=(legal_principal,),
        )

    def _register_receipt(
        self, receipt: TranslationReceiptV4, reference: ContentRefV4
    ) -> ContentRefV4:
        return self._resolver.register_bytes(
            artifact_id=f"{TRANSLATION_RECEIPT_KIND}-{reference.digest.hex}",
            content_ref=reference,
            artifact_kind=TRANSLATION_RECEIPT_KIND,
            media_type=JSON_MEDIA_TYPE,
            scope=LEGAL_IR_SCOPE,
            content=receipt.canonical_bytes(),
        )

    def compile_rule(
        self,
        pack: VerifiedRulePackV4,
        *,
        rule_ref: ContentRefV4,
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> LegalIRCompilationV4:
        """Compile one exact verified rule and internally issue both receipts."""

        if (
            type(now) is not CanonicalTimeV4
            or type(run_identity_ref) is not ContentRefV4
            or run_identity_ref.kind != RUN_IDENTITY_KIND
        ):
            _fail("IR_INPUT_TYPE", "compile context requires canonical run reference and time")
        rule = self._select_rule(pack, rule_ref)
        run = self._validate_run_identity(run_identity_ref, pack=pack)
        approval_refs, legal_principal, expiry_ceiling = (
            self._current_interpretation_approval(pack, rule, now=now)
        )
        key = (pack.pack_ref, rule_ref, run_identity_ref)
        cached = self._compiled.get(key)
        if cached is not None:
            self._verify_cached(
                cached,
                pack=pack,
                run_identity_ref=run_identity_ref,
                approval_refs=approval_refs,
                legal_principal=legal_principal,
                expiry_ceiling=expiry_ceiling,
                now=now,
            )
            return cached

        spec, spec_ref = self._project_rule_to_spec(rule, rule_ref=rule_ref)
        first_mapping_ref, first_coverage = self._field_mapping(
            hop=RULE_TO_SPEC_HOP,
            source=rule,
            source_ref=rule_ref,
            target=spec,
            target_ref=spec_ref,
            rows=_RULE_TO_SPEC_ROWS,
            derived_targets=("spec_digest",),
        )
        first_proof_ref = self._register_json(IR_PROOF_OBLIGATION_KIND, {
            "schema_version": "jc/legal-ir-proof-obligation/1.0",
            "obligation": "loss-accounted-spec-translation",
            "source_ref": rule_ref.to_dict(),
            "target_ref": spec_ref.to_dict(),
            "field_mapping_ref": first_mapping_ref.to_dict(),
        })
        ivl, ivl_ref = self._project_spec_to_ivl(
            spec,
            spec_ref=spec_ref,
            interpretation_approval_refs=approval_refs,
        )
        second_mapping_ref, second_coverage = self._field_mapping(
            hop=SPEC_TO_IVL_HOP,
            source=spec,
            source_ref=spec_ref,
            target=ivl,
            target_ref=ivl_ref,
            rows=_SPEC_TO_IVL_ROWS,
            derived_targets=("proof_obligation_refs", "ivl_digest"),
        )
        first_translator_ref = self._translator_ref(RULE_TO_SPEC_HOP, run)
        second_translator_ref = self._translator_ref(SPEC_TO_IVL_HOP, run)
        first_proof_refs = (first_proof_ref,)
        second_proof_refs = ivl.proof_obligation_refs
        first_evidence = self._receipt_evidence(
            pack=pack,
            run_identity_ref=run_identity_ref,
            translator_ref=first_translator_ref,
            source_ref=rule_ref,
            target_ref=spec_ref,
            field_mapping_ref=first_mapping_ref,
            approval_refs=approval_refs,
            proof_refs=first_proof_refs,
            previous_receipt_ref=None,
        )
        first_receipt, first_receipt_ref = self._make_receipt(
            hop=RULE_TO_SPEC_HOP,
            run_identity_ref=run_identity_ref,
            translator_ref=first_translator_ref,
            source_ref=rule_ref,
            target_ref=spec_ref,
            field_mapping_ref=first_mapping_ref,
            field_coverage=first_coverage,
            proof_refs=first_proof_refs,
            evidence_refs=first_evidence,
            now=now,
        )
        second_evidence = self._receipt_evidence(
            pack=pack,
            run_identity_ref=run_identity_ref,
            translator_ref=second_translator_ref,
            source_ref=spec_ref,
            target_ref=ivl_ref,
            field_mapping_ref=second_mapping_ref,
            approval_refs=approval_refs,
            proof_refs=second_proof_refs,
            previous_receipt_ref=first_receipt_ref,
        )
        second_receipt, second_receipt_ref = self._make_receipt(
            hop=SPEC_TO_IVL_HOP,
            run_identity_ref=run_identity_ref,
            translator_ref=second_translator_ref,
            source_ref=spec_ref,
            target_ref=ivl_ref,
            field_mapping_ref=second_mapping_ref,
            field_coverage=second_coverage,
            proof_refs=second_proof_refs,
            evidence_refs=second_evidence,
            now=now,
        )
        preflight = self._trust._fresh_without_replay()
        for trust in (preflight, self._trust):
            self._verify_receipt(
                first_receipt,
                reference=first_receipt_ref,
                expected_hop=RULE_TO_SPEC_HOP,
                run_identity_ref=run_identity_ref,
                translator_ref=first_translator_ref,
                source_ref=rule_ref,
                target_ref=spec_ref,
                field_mapping_ref=first_mapping_ref,
                field_coverage=first_coverage,
                proof_refs=first_proof_refs,
                evidence_refs=first_evidence,
                legal_principal=legal_principal,
                expiry_ceiling=expiry_ceiling,
                now=now,
                trust=trust,
            )
            self._verify_receipt(
                second_receipt,
                reference=second_receipt_ref,
                expected_hop=SPEC_TO_IVL_HOP,
                run_identity_ref=run_identity_ref,
                translator_ref=second_translator_ref,
                source_ref=spec_ref,
                target_ref=ivl_ref,
                field_mapping_ref=second_mapping_ref,
                field_coverage=second_coverage,
                proof_refs=second_proof_refs,
                evidence_refs=second_evidence,
                legal_principal=legal_principal,
                expiry_ceiling=expiry_ceiling,
                now=now,
                trust=trust,
            )
        self._register_receipt(first_receipt, first_receipt_ref)
        self._register_receipt(second_receipt, second_receipt_ref)
        result = LegalIRCompilationV4(
            rule=rule,
            rule_ref=rule_ref,
            spec=spec,
            spec_ref=spec_ref,
            ivl=ivl,
            ivl_ref=ivl_ref,
            rule_to_spec_receipt=first_receipt,
            rule_to_spec_receipt_ref=first_receipt_ref,
            spec_to_ivl_receipt=second_receipt,
            spec_to_ivl_receipt_ref=second_receipt_ref,
        )
        self._compiled[key] = result
        return result

    def _verify_cached(
        self,
        result: LegalIRCompilationV4,
        *,
        pack: VerifiedRulePackV4,
        run_identity_ref: ContentRefV4,
        approval_refs: tuple[ContentRefV4, ...],
        legal_principal: str,
        expiry_ceiling: CanonicalTimeV4,
        now: CanonicalTimeV4,
    ) -> None:
        stored_spec = self._resolve_self_digest(
            result.spec_ref,
            kind=LEGAL_SPEC_KIND,
            scope=LEGAL_IR_SCOPE,
            contract=LegalSpecV4,
            digest_field="spec_digest",
        )
        stored_ivl = self._resolve_self_digest(
            result.ivl_ref,
            kind=LEGAL_IVL_KIND,
            scope=LEGAL_IR_SCOPE,
            contract=LegalIVLV4,
            digest_field="ivl_digest",
        )
        stored_first = self._resolve_contract(
            result.rule_to_spec_receipt_ref,
            kind=TRANSLATION_RECEIPT_KIND,
            scope=LEGAL_IR_SCOPE,
            contract=TranslationReceiptV4,
        )
        stored_second = self._resolve_contract(
            result.spec_to_ivl_receipt_ref,
            kind=TRANSLATION_RECEIPT_KIND,
            scope=LEGAL_IR_SCOPE,
            contract=TranslationReceiptV4,
        )
        if (
            stored_spec != result.spec
            or stored_ivl != result.ivl
            or stored_first != result.rule_to_spec_receipt
            or stored_second != result.spec_to_ivl_receipt
        ):
            _fail("IR_CACHE_BINDING", "cached translation differs from resolved bytes")
        first = result.rule_to_spec_receipt
        second = result.spec_to_ivl_receipt
        first_evidence = self._receipt_evidence(
            pack=pack,
            run_identity_ref=run_identity_ref,
            translator_ref=first.translator_ref,
            source_ref=result.rule_ref,
            target_ref=result.spec_ref,
            field_mapping_ref=first.field_mapping_ref,
            approval_refs=approval_refs,
            proof_refs=first.proof_obligation_refs,
            previous_receipt_ref=None,
        )
        second_evidence = self._receipt_evidence(
            pack=pack,
            run_identity_ref=run_identity_ref,
            translator_ref=second.translator_ref,
            source_ref=result.spec_ref,
            target_ref=result.ivl_ref,
            field_mapping_ref=second.field_mapping_ref,
            approval_refs=approval_refs,
            proof_refs=second.proof_obligation_refs,
            previous_receipt_ref=result.rule_to_spec_receipt_ref,
        )
        verification_trust = self._trust._fresh_without_replay()
        self._verify_receipt(
            first,
            reference=result.rule_to_spec_receipt_ref,
            expected_hop=RULE_TO_SPEC_HOP,
            run_identity_ref=run_identity_ref,
            translator_ref=first.translator_ref,
            source_ref=result.rule_ref,
            target_ref=result.spec_ref,
            field_mapping_ref=first.field_mapping_ref,
            field_coverage=tuple(item.name for item in fields(RuleV4)),
            proof_refs=first.proof_obligation_refs,
            evidence_refs=first_evidence,
            legal_principal=legal_principal,
            expiry_ceiling=expiry_ceiling,
            now=now,
            trust=verification_trust,
        )
        self._verify_receipt(
            second,
            reference=result.spec_to_ivl_receipt_ref,
            expected_hop=SPEC_TO_IVL_HOP,
            run_identity_ref=run_identity_ref,
            translator_ref=second.translator_ref,
            source_ref=result.spec_ref,
            target_ref=result.ivl_ref,
            field_mapping_ref=second.field_mapping_ref,
            field_coverage=tuple(item.name for item in fields(LegalSpecV4)),
            proof_refs=second.proof_obligation_refs,
            evidence_refs=second_evidence,
            legal_principal=legal_principal,
            expiry_ceiling=expiry_ceiling,
            now=now,
            trust=verification_trust,
        )
