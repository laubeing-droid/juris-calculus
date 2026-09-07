"""End-to-end acceptance: the V5 profile stage runs inside the formal spine.

These tests drive the sole ApplicationV4 chain with public requests that carry
defeat_policy_v5 / profile_queries_v5 (and optional composition inputs). The
stage document must be reachable from the run result receipts, the independent
verifier must gate a wrong solver inside the chain, and a repeat run must
re-derive byte-identical stage artifacts.
"""
from __future__ import annotations

from base64 import b64decode
from dataclasses import replace
from pathlib import Path

import pytest

import compiler_core.application as application_module
from compiler_core.application import ApplicationV4
from compiler_core.argumentation import ProfileEvaluationV5
from compiler_core.audit_bundle import AuditBundleStoreV4, AuditTrustMaterialV4
from compiler_core.backend_router import BackendRouterV4
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.certificates import CertificateIssuerV4
from compiler_core.contracts import (
    CanonicalLocatorV4,
    CaseRequestV4,
    CertificateKindV4,
    ClaimRefutationV5,
    CompositionCandidateV5,
    CompositionChoiceV5,
    CompositionPolicyV5,
    ContentRefV4,
    DecisionStatusV4,
    DefeatPolicyV5,
    EvidenceItemV4,
    EvidenceManifestV4,
    ExactExpressionV5,
    ExactQuantityV5,
    FactCandidateV4,
    FactAttestationV4,
    IncrementalParentV5,
    LegalContextV4,
    ProceduralInputV5,
    QueryGateRequestV5,
    QueryRequestV5,
    RequestedOutputV4,
    RunIdentityV4,
)
from compiler_core.fact_admission import (
    CASE_EVIDENCE_SCOPE,
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
    case_request_binding_ref,
    evidence_item_ref,
    fact_attestation_evidence_refs,
)
from compiler_core.independent_checker import IndependentCheckerV4
from compiler_core.legal_ir import LegalIRCompilerV4
from compiler_core.storage import V4TransactionStore
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness

APPLICATION = application_module


def _application(tmp_path: Path, harness: _ChainHarness) -> tuple[ApplicationV4, AuditBundleStoreV4]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    compiler = LegalIRCompilerV4(
        harness.pack_verifier,
        receipt_issuer="synthetic-service-issuer",
        receipt_signer=harness._sign_receipt,
    )
    router = BackendRouterV4(
        compiler,
        harness.fact_service,
        receipt_signer=harness._sign_receipt,
    )
    checker = IndependentCheckerV4(
        harness.resolver,
        harness.trust,
        receipt_issuer="synthetic-service-issuer",
        receipt_signer=harness._sign_receipt,
    )
    trust_material = AuditTrustMaterialV4(
        harness.policy,
        tuple(key for _, key in sorted(harness.trust._keys.items())),
        harness.trust.target_environment,
        tuple(sorted(harness.trust._revoked_subjects, key=str)),
        tuple(sorted(harness.trust._revoked_nonces)),
    )
    store = AuditBundleStoreV4(
        V4TransactionStore.create(
            (tmp_path / "state").resolve(),
            quota_bytes=256 * 1024 * 1024,
        ),
        trust_material=trust_material,
        current_engine_build_digest=harness.run.engine_build_digest,
        checker_receipt_issuer="synthetic-service-issuer",
    )
    issuer = CertificateIssuerV4(
        harness.trust,
        current_engine_build_digest=harness.run.engine_build_digest,
        signer=harness._sign_receipt,
    )
    application = ApplicationV4(
        harness.resolver,
        harness.trust,
        harness.source_service,
        harness.fact_service,
        harness.pack_verifier,
        compiler,
        router,
        checker,
        store,
        issuer,
        receipt_signer=harness._sign_receipt,
        clock=lambda: harness.now,
        default_limits=harness.default_limits,
    )
    return application, store


def _claim_digest(harness: _ChainHarness, rule_id: str) -> str:
    pack = harness.verify_pack()
    rule = next(item for item in pack.rules if item.rule_id == rule_id)
    return str(rule.conclusion_ref.digest)


def _computed_ref(kind: str, value: dict) -> ContentRefV4:
    return ContentRefV4(kind, DigestV4.from_bytes(canonical_bytes(value)))


def _stage_fact_row(harness: _ChainHarness, fact_key: str, label: str) -> dict:
    """Stage one evidence-backed boolean fact candidate; returns its wire rows.

    Content identical to the harness's own default staging (the boolean true
    value document, the custody text, the synthetic-positive proposition and
    candidate) is addressed by its content digest instead of being registered
    a second time.
    """

    proposition_payload = {
        "schema_version": "jc/fact-proposition/1.0", "proposition": fact_key,
    }
    value_payload = {
        "schema_version": "jc/fact-value/1.0", "value_kind": "boolean", "value": True,
    }
    custody_payload = {
        "schema_version": "jc/evidence-custody/1.0", "custody": "test-only",
    }
    document = f"synthetic reviewed evidence {label}".encode()
    document_ref = ContentRefV4(EVIDENCE_DOCUMENT_KIND, DigestV4.from_bytes(document))
    if fact_key == "synthetic-positive.required-fact":
        # The harness already staged and registered this row; recover its wire
        # documents from the resolver instead of re-registering the digests.
        candidate_record = harness.resolver._by_ref[harness.candidate_ref]
        candidate_doc = parse_json_document(candidate_record.content)
        evidence_ref = ContentRefV4.from_dict(candidate_doc["evidence_refs"][0])
        evidence_doc = parse_json_document(harness.resolver._by_ref[evidence_ref].content)
        return {
            "label": label,
            "proposition_ref": ContentRefV4.from_dict(candidate_doc["proposition_ref"]),
            "value_ref": ContentRefV4.from_dict(candidate_doc["value_ref"]),
            "evidence": EvidenceItemV4.from_dict(evidence_doc),
            "evidence_ref": evidence_ref,
            "candidate": None,
            "candidate_ref": harness.candidate_ref,
        }

    proposition_ref = harness._json(
        FACT_PROPOSITION_KIND, FACT_ADMISSION_SCOPE, proposition_payload,
    )
    value_ref = _computed_ref(FACT_VALUE_KIND, value_payload)
    custody_ref = _computed_ref(EVIDENCE_CUSTODY_KIND, custody_payload)
    harness._register(
        document_ref,
        document,
        kind=EVIDENCE_DOCUMENT_KIND,
        media_type="application/octet-stream",
        scope=CASE_EVIDENCE_SCOPE,
    )
    evidence = EvidenceItemV4(
        f"{label}-evidence",
        document_ref,
        (CanonicalLocatorV4("page", f"{label}.pdf", 1, 0, 10),),
        (custody_ref,),
        "NONE",
        "REVIEWED",
    )
    evidence_ref = harness._contract(EVIDENCE_ITEM_KIND, CASE_EVIDENCE_SCOPE, evidence)
    candidate = FactCandidateV4(
        f"{label}-candidate",
        proposition_ref,
        "boolean",
        value_ref,
        (evidence_ref,),
        "lawyer",
        None,
    )
    candidate_ref = harness._contract(FACT_CANDIDATE_KIND, FACT_ADMISSION_SCOPE, candidate)
    return {
        "label": label,
        "proposition_ref": proposition_ref,
        "value_ref": value_ref,
        "evidence": evidence,
        "evidence_ref": evidence_ref,
        "candidate": candidate,
        "candidate_ref": candidate_ref,
    }


def _seed_with_v5(
    harness: _ChainHarness,
    *,
    policy: DefeatPolicyV5,
    queries: tuple[QueryRequestV5, ...],
    extra_fact_keys: tuple[str, ...] = (),
    composition_policy: CompositionPolicyV5 | None = None,
    composition_choice: CompositionChoiceV5 | None = None,
    expression: ExactExpressionV5 | None = None,
    operands: tuple[ExactExpressionV5, ...] = (),
    incremental_parent: IncrementalParentV5 | None = None,
    query_refutations: tuple[ClaimRefutationV5, ...] = (),
    query_gates: tuple[QueryGateRequestV5, ...] = (),
    procedural_input: ProceduralInputV5 | None = None,
) -> tuple[CaseRequestV4, ContentRefV4, RunIdentityV4, ContentRefV4]:
    from tests.integration.test_trust_chain import ISSUED_AT

    rows = [_stage_fact_row(harness, "synthetic-positive.required-fact", "synthetic")]
    for index, key in enumerate(extra_fact_keys):
        rows.append(_stage_fact_row(harness, key, f"extra-{index}"))

    placeholder_manifest = ContentRefV4(
        EVIDENCE_MANIFEST_KIND,
        digest_value({"placeholder": "v5-chain-manifest"}),
    )
    placeholder_attestation = ContentRefV4(
        FACT_ATTESTATION_KIND,
        digest_value({"placeholder": "v5-chain-attestation"}),
    )
    seed = replace(
        harness.request,
        evidence_manifest_ref=placeholder_manifest,
        fact_attestation_refs=(placeholder_attestation,),
        defeat_policy_v5=policy,
        profile_queries_v5=queries,
        composition_policy_v5=composition_policy,
        composition_choice_v5=composition_choice,
        composition_expression_v5=expression,
        composition_operands_v5=operands,
        incremental_parent_v5=incremental_parent,
        query_refutations_v5=query_refutations,
        query_gates_v5=query_gates,
        procedural_input_v5=procedural_input,
    )
    binding = case_request_binding_ref(seed)
    manifest_body = {
        "manifest_id": "v5-chain-evidence-manifest",
        "request_ref": binding.to_dict(),
        "case_scope": CASE_SCOPE,
        "items": [row["evidence"].to_dict() for row in rows],
        "fact_candidate_refs": [row["candidate_ref"].to_dict() for row in rows],
        "contradictions": [],
    }
    manifest = EvidenceManifestV4.from_dict({
        **manifest_body,
        "manifest_digest": str(digest_value(manifest_body)),
    })
    manifest_ref = harness._digest_contract(
        EVIDENCE_MANIFEST_KIND, CASE_EVIDENCE_SCOPE, manifest
    )
    attestation_refs: list[ContentRefV4] = []
    for row in rows:
        legal_evidence = fact_attestation_evidence_refs(
            request_binding_ref=binding,
            manifest_ref=manifest_ref,
            candidate_ref=row["candidate_ref"],
            proposition_ref=row["proposition_ref"],
            value_ref=row["value_ref"],
            source_refs=(harness.source_ref,),
            evidence_refs=(row["evidence_ref"],),
            replay_policy_ref=harness.policy.replay_policy_ref,
        )
        attestation_body = {
            "attestation_id": f"v5-chain-{row['label']}-attestation",
            "candidate_ref": row["candidate_ref"].to_dict(),
            "request_ref": binding.to_dict(),
            "case_scope": CASE_SCOPE,
            "proposition_digest": str(row["proposition_ref"].digest),
            "value_digest": str(row["value_ref"].digest),
            "source_refs": [harness.source_ref.to_dict()],
            "evidence_refs": [row["evidence_ref"].to_dict()],
            "interpretation_version": "synthetic-v1",
            "admission_basis": "documentary_evidence_human_reviewed",
            "issuer_role": "legal_reviewer",
            "issued_at": ISSUED_AT.to_dict(),
            "expires_at": harness.attestation.expires_at.to_dict(),
            "dispute_state": "UNDISPUTED",
            "assumption_state": "NONE",
            "nonce": f"v5-chain-{row['label']}",
            "replay_policy_ref": harness.policy.replay_policy_ref.to_dict(),
            "revocation_ref": None,
        }
        signature = harness._signature(
            "legal",
            subject_digest=row["candidate_ref"].digest,
            payload_digest=digest_value(attestation_body),
            evidence_refs=legal_evidence,
            nonce=attestation_body["nonce"],
            issued_at=ISSUED_AT,
            run_identity_ref=None,
        )
        attestation = FactAttestationV4.from_dict({
            **attestation_body,
            "signature": signature.to_dict(),
        })
        attestation_refs.append(harness._contract(
            FACT_ATTESTATION_KIND, LEGAL_APPROVAL_SCOPE, attestation,
        ))
    seed = replace(
        seed,
        evidence_manifest_ref=manifest_ref,
        fact_attestation_refs=tuple(attestation_refs),
    )
    request_ref = harness._contract(CASE_REQUEST_KIND, CASE_REQUEST_SCOPE, seed)
    original = harness.run
    run = RunIdentityV4.build(
        seed,
        request_ref,
        engine_version=original.engine_version,
        engine_source_commit=original.engine_source_commit,
        engine_source_tree=original.engine_source_tree,
        engine_build_digest=original.engine_build_digest,
        wheel_digest=original.wheel_digest,
        package_digest=original.package_digest,
        schema_digest=original.schema_digest,
        tool_spec_digest=original.tool_spec_digest,
        lock_digest=original.lock_digest,
        runtime_config_digest=original.runtime_config_digest,
        algorithm_profile_digest=original.algorithm_profile_digest,
        trust_policy_ref=original.trust_policy_ref,
        storage_capability_ref=original.storage_capability_ref,
        backend_profile_digest=original.backend_profile_digest,
    )
    run_ref = harness._digest_contract(RUN_IDENTITY_KIND, RUN_IDENTITY_SCOPE, run)
    return seed, request_ref, run, run_ref


def _v5_inputs(
    harness: _ChainHarness,
    *,
    profiles=("grounded", "preferred", "stable", "complete"),
    rule_id: str = "synthetic-exception-priority",
) -> tuple[DefeatPolicyV5, tuple[QueryRequestV5, ...], str]:
    binding = case_request_binding_ref(harness.request).digest
    policy = DefeatPolicyV5(
        policy_id="chain-policy",
        policy_version="1",
        request_ref=binding,
        allowed_kinds=("exception_attack",),
        legal_evidence_ref=digest_value({"governance": "synthetic-defeat-policy"}),
    )
    claim = _claim_digest(harness, rule_id)
    queries = tuple(
        QueryRequestV5(
            query_id=f"q-{profile}",
            claim=claim,
            profile=profile,
            mapping_version=APPLICATION.PROFILE_MAPPING_VERSION_V5,
            scenario_ref=APPLICATION._v5_scenario_ref(binding, f"q-{profile}"),
        )
        for profile in profiles
    )
    return policy, queries, claim


EXCEPTION_FACTS = (
    "synthetic-exception-priority.required-fact",
    "synthetic-exception-priority.exception-fact",
)
ATTACKER = "synthetic-exception-priority"


def _stage_document(store: AuditBundleStoreV4, envelope, harness: _ChainHarness, run_ref) -> dict:
    """Read the V5 stage document out of the sealed audit bundle.

    The stage artifact is sealed into checker-receipts.json of the verified
    bundle, which is exactly what an external reader obtains through the
    audit bundle and read-artifact surface.
    """

    assert envelope.transport_outcome.status == "success"
    capability = store.capability_for(run_ref)
    verified = store.verify_run(capability, now=harness.now)
    payload = parse_json_document(verified.files["checker-receipts.json"])
    for item in payload["artifacts"]:
        if item["content_ref"]["kind"] == APPLICATION.PROFILE_STAGE_KIND_V5:
            document = parse_json_document(b64decode(item["content_base64"], validate=True))
            assert document["schema_version"] == APPLICATION.PROFILE_STAGE_SCHEMA_V5
            return document
    raise AssertionError("the V5 stage artifact is missing from the sealed audit bundle")


def test_profile_stage_runs_inside_the_formal_spine(tmp_path: Path) -> None:
    harness = _ChainHarness()
    policy, queries, claim = _v5_inputs(harness)
    seed, request_ref, _, run_ref = _seed_with_v5(
        harness, policy=policy, queries=queries, extra_fact_keys=EXCEPTION_FACTS,
    )
    application, store = _application(tmp_path, harness)

    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)

    assert envelope.transport_outcome.status == "success"
    assert envelope.result.decision_status is DecisionStatusV4.ACCEPTED_FORMAL_RESULT
    assert envelope.result.certificate_kind is CertificateKindV4.FORMAL_VERIFIED
    assert envelope.certificate.kind is CertificateKindV4.FORMAL_VERIFIED

    document = _stage_document(store, envelope, harness, run_ref)
    assert document["request_binding"] == str(case_request_binding_ref(seed).digest)
    assert document["arguments"] == ["synthetic-exception-priority", "synthetic-positive"]
    assert document["attacks"] == [[
        "synthetic-exception-priority", "synthetic-positive", "exception_attack",
    ]]
    assert document["defeats"] == [["synthetic-exception-priority", "synthetic-positive"]]
    for profile in ("grounded", "preferred", "stable", "complete"):
        entry = document["profiles"][profile]
        assert entry["kind"] == "extensions"
        assert entry["extensions"] == [["synthetic-exception-priority"]]
        assert entry["verification"]["coverage"] == "exact"
        assert entry["verification"]["verified"] is True
        assurance = entry["assurance"]
        assert assurance["implementation"] == "crossCheckOnly"
        assert assurance["run_check"] == "checked"
        assert assurance["spec"] == "proved"
        assert assurance["scope_profile"] == profile
    for row in document["queries"]:
        assert row["common"] is True
        assert row["possible"] is True
        assert row["acceptance_witnesses"] == ["synthetic-exception-priority"]
        assert row["gate"] == "enterable"
    for row in document["procedures"]:
        assert row["kind"] == "pending_legal_judgment"
        assert row["missing"] == ["burden-rule-or-finding"]
    assert document["composition"] is None
    # The queried claim is exactly the admitted rule conclusion identity.
    assert {row["claim"] for row in document["queries"]} == {claim}


def test_profile_stage_is_deterministically_replayable(tmp_path: Path) -> None:
    harness = _ChainHarness()
    policy, queries, _ = _v5_inputs(harness)
    seed, request_ref, _, run_ref = _seed_with_v5(
        harness, policy=policy, queries=queries, extra_fact_keys=EXCEPTION_FACTS,
    )
    application, store = _application(tmp_path, harness)

    first = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)
    second = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)

    first_document = _stage_document(store, first, harness, run_ref)
    second_document = _stage_document(store, second, harness, run_ref)
    assert first_document == second_document


def test_wrong_solver_family_is_rejected_inside_the_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ChainHarness()
    policy, queries, _ = _v5_inputs(harness, profiles=("stable",))
    _, request_ref, _, run_ref = _seed_with_v5(
        harness, policy=policy, queries=queries, extra_fact_keys=EXCEPTION_FACTS,
    )
    application, store = _application(tmp_path, harness)
    production = application_module.evaluate_profile_v5

    def lying_solver(profile, arguments, defeats, **kwargs):
        result = production(profile, arguments, defeats, **kwargs)
        if profile == "stable":
            # Simulate the inverted-stable implementation error: the family the
            # production solver would publish is not the Dung family.
            return ProfileEvaluationV5(profile, "extensions", (frozenset(),), ())
        return result

    monkeypatch.setattr(application_module, "evaluate_profile_v5", lying_solver)

    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)

    assert envelope.transport_outcome.status == "error"
    assert envelope.transport_outcome.error.code == "APPLICATION_V5_VERIFICATION"
    assert envelope.result.decision_status is DecisionStatusV4.ENGINE_ERROR
    assert envelope.certificate.kind is CertificateKindV4.NONE


def test_profile_queries_without_an_aaf_graph_fail_closed(tmp_path: Path) -> None:
    harness = _ChainHarness()
    policy, queries, _ = _v5_inputs(harness, profiles=("stable",))
    _, request_ref, _, run_ref = _seed_with_v5(
        harness, policy=policy, queries=queries, extra_fact_keys=EXCEPTION_FACTS,
    )
    application, store = _application(tmp_path, harness)

    def horn_only_outcome(execution, checked):
        return APPLICATION._ArgumentOutcome(
            "accepted",
            (),
            (checked.receipt.argument_graph_ref,),
            (),
            (),
            (),
            None,
        )

    monkey = pytest.MonkeyPatch()
    monkey.setattr(application, "_argument_outcome", horn_only_outcome)
    try:
        envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)
    finally:
        monkey.undo()

    assert envelope.transport_outcome.status == "error"
    assert envelope.transport_outcome.error.code == "APPLICATION_V5_STAGE"
    assert envelope.transport_outcome.error.stage == "profile-v5"
    assert envelope.result.decision_status is DecisionStatusV4.ENGINE_ERROR


def test_empty_graph_defers_profile_queries_observably(tmp_path: Path) -> None:
    harness = _ChainHarness()
    policy, queries, _ = _v5_inputs(harness, profiles=("stable",))
    _, request_ref, _, run_ref = _seed_with_v5(
        harness, policy=policy, queries=queries, extra_fact_keys=EXCEPTION_FACTS,
    )
    application, store = _application(tmp_path, harness)

    def empty_outcome(execution, checked):
        return APPLICATION._ArgumentOutcome(
            "empty",
            (),
            (checked.receipt.argument_graph_ref,),
            (),
            (),
            (),
            None,
        )

    monkey = pytest.MonkeyPatch()
    monkey.setattr(application, "_argument_outcome", empty_outcome)
    try:
        envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)
    finally:
        monkey.undo()

    assert envelope.transport_outcome.status == "success"
    assert envelope.result.decision_status is DecisionStatusV4.UNKNOWN
    assert "profile_queries_without_arguments" in envelope.result.decision_reason_codes
    assert envelope.certificate.kind is CertificateKindV4.NONE


def test_same_branch_composition_rides_the_profile_stage(tmp_path: Path) -> None:
    harness = _ChainHarness()
    policy, queries, _ = _v5_inputs(harness)
    binding = case_request_binding_ref(harness.request).digest
    extension = frozenset({ATTACKER})
    outcome_id, branch_ref = APPLICATION._v5_branch_identity(
        harness.request.request_id, "stable", extension
    )
    governance = CompositionPolicyV5(
        policy_id="composition-policy",
        policy_version="1",
        request_ref=binding,
        governance_ref=digest_value({"governance": "synthetic-composition"}),
    )
    quantity = ExactQuantityV5("money", "CNY", None, None, 7, 1)
    operand = ExactExpressionV5("lit", "money", None, None, quantity, None, None)
    expression = ExactExpressionV5(
        "scale",
        "money",
        operand.canonical_digest(),
        None,
        None,
        3,
        2,
    )
    choice = CompositionChoiceV5(
        policy_id=governance.policy_id,
        policy_version=governance.policy_version,
        request_ref=binding,
        branch_ref=branch_ref,
        selected=(CompositionCandidateV5(outcome_id, binding, branch_ref),),
        child_branch_hint=None,
    )
    seed, request_ref, _, run_ref = _seed_with_v5(
        harness,
        policy=policy,
        queries=queries,
        extra_fact_keys=EXCEPTION_FACTS,
        composition_policy=governance,
        composition_choice=choice,
        expression=expression,
        operands=(operand,),
    )
    application, store = _application(tmp_path, harness)

    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)

    assert envelope.transport_outcome.status == "success"
    assert envelope.result.decision_status is DecisionStatusV4.ACCEPTED_FORMAL_RESULT
    document = _stage_document(store, envelope, harness, run_ref)
    composition = document["composition"]
    assert composition["rounding_required"] is True
    assert composition["value"]["numerator"] == 21
    assert composition["value"]["denominator"] == 2
    assert composition["open_obligations"] == [
        {"code": "rounding_required", "detail": "exact result is not integral"},
    ]
    for profile in ("grounded", "preferred", "stable", "complete"):
        assurance = document["profiles"][profile]["assurance"]
        obligation_codes = [
            item["code"] for item in assurance["coverage_open_obligations"]
        ]
        assert "rounding_required" in obligation_codes
        assert assurance["spec"] == "openObligations"
