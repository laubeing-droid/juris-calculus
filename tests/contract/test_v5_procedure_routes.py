"""The four procedure routes driven by public requests (FIX-06 / G01).

adjudicated_status, procedural_disposition, pending_legal_judgment and
solver_incomplete are all reachable from ``CaseRequestV4.procedural_input_v5``
through the sole spine. The authorization route verifies a stored
legal-approval signature through the trust machinery; a user-supplied boolean
can never mark an authority verified.
"""
from __future__ import annotations

from pathlib import Path

from compiler_core.application import PROCEDURE_AUTHORIZATION_SCHEMA_V5
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
)
from compiler_core.contracts import (
    BurdenRuleOutcomeWireV5,
    ProcedureAuthorityV5,
    ProceduralInputV5,
)

from tests.contract.test_v5_profile_chain import (
    EXCEPTION_FACTS,
    _application,
    _seed_with_v5,
    _stage_document,
    _v5_inputs,
)
from tests.integration.test_trust_chain import CASE_SCOPE, ISSUED_AT, _ChainHarness

BURDEN_RULE = "synthetic-positive"


def _signed_authorization(harness: _ChainHarness, binding: DigestV4, finding: str):
    """Register one stored, legally signed procedure authorization artifact."""

    body = {
        "schema_version": PROCEDURE_AUTHORIZATION_SCHEMA_V5,
        "request_ref": str(binding),
        "burden_rule_ref": BURDEN_RULE,
        "standard_id": "preponderance",
        "standard_version": "1",
        "finding": finding,
        "reviewer": "synthetic-legal-reviewer",
        "issued_at": ISSUED_AT.to_dict(),
        "expires_at": harness.attestation.expires_at.to_dict(),
    }
    subject = digest_value(body)
    signature = harness._signature(
        "legal",
        subject_digest=subject,
        payload_digest=subject,
        evidence_refs=(),
        nonce=f"procedure-authorization-{finding}",
        issued_at=ISSUED_AT,
        run_identity_ref=None,
    )
    document = {**body, "signature": signature.to_dict()}
    raw = canonical_bytes(document)
    from compiler_core.application import PROCEDURE_AUTHORIZATION_KIND_V5
    from compiler_core.contracts import ContentRefV4
    from compiler_core.fact_admission import LEGAL_APPROVAL_SCOPE
    from compiler_core.rule_packs import JSON_MEDIA_TYPE

    reference = ContentRefV4(
        PROCEDURE_AUTHORIZATION_KIND_V5, DigestV4.from_bytes(raw),
    )
    harness._register(
        reference, raw,
        kind=PROCEDURE_AUTHORIZATION_KIND_V5,
        scope=LEGAL_APPROVAL_SCOPE,
        media_type=JSON_MEDIA_TYPE,
    )
    return reference


def _authority(harness, binding: DigestV4, finding: str) -> ProcedureAuthorityV5:
    return ProcedureAuthorityV5(
        burden_rule_ref=BURDEN_RULE,
        standard_id="preponderance",
        standard_version="1",
        finding=finding,
        reviewer="synthetic-legal-reviewer",
        authorization_ref=_signed_authorization(harness, binding, finding).digest,
        request_ref=binding,
    )


def _outcomes(binding: DigestV4) -> BurdenRuleOutcomeWireV5:
    return BurdenRuleOutcomeWireV5(
        burden_rule_ref=BURDEN_RULE,
        satisfied_status="claim-satisfied",
        failure_status="claim-unmet",
        request_ref=binding,
    )


def _run(tmp_path: Path, harness: _ChainHarness, procedural, *, fact_keys=EXCEPTION_FACTS):
    policy, queries, _ = _v5_inputs(harness, profiles=("grounded",))
    seed, request_ref, _, run_ref = _seed_with_v5(
        harness,
        policy=policy,
        queries=queries,
        extra_fact_keys=fact_keys,
        procedural_input=procedural,
    )
    application, store = _application(tmp_path, harness)
    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)
    assert envelope.transport_outcome.status == "success"
    document = _stage_document(store, envelope, harness, run_ref)
    return document


def test_route_pending_legal_judgment_without_inputs(tmp_path: Path) -> None:
    """No procedural input and a complete solve => pending_legal_judgment."""

    document = _run(tmp_path, _ChainHarness(), None)
    for row in document["procedures"]:
        assert row["kind"] == "pending_legal_judgment"
        assert row["missing"] == ["burden-rule-or-finding"]


def test_route_procedural_disposition_with_admitted_status(tmp_path: Path) -> None:
    """A valid procedural disposition with its basis rides the public path."""

    harness = _ChainHarness()
    binding = _v5_inputs(harness, profiles=("grounded",))[0].request_ref
    procedural = ProceduralInputV5(
        request_ref=binding,
        procedural_status="procedurally-barred",
        procedural_basis_ref=digest_value({"procedural": "dismissed-for-procedure"}),
    )
    document = _run(tmp_path, harness, procedural)
    kinds = {row["kind"] for row in document["procedures"]}
    assert kinds == {"procedural_disposition"}
    for row in document["procedures"]:
        assert row["status"] == "procedurally-barred"
        assert row["open_obligations"] == []


def test_route_adjudicated_status_with_verified_authority(tmp_path: Path) -> None:
    """A signed, trust-verified burden finding plus its admitted rule
    consequences produce an adjudicated status for every query."""

    harness = _ChainHarness()
    binding = _v5_inputs(harness, profiles=("grounded",))[0].request_ref
    procedural = ProceduralInputV5(
        request_ref=binding,
        authority=_authority(harness, binding, "satisfied"),
        rule_outcomes=_outcomes(binding),
    )
    document = _run(tmp_path, harness, procedural)
    kinds = {row["kind"] for row in document["procedures"]}
    assert kinds == {"adjudicated_status"}
    for row in document["procedures"]:
        assert row["status"] == "claim-satisfied"
        assert row["authority_ref"] is not None


def test_unverified_authority_fails_safe_to_pending(tmp_path: Path) -> None:
    """An authority row whose referenced artifact is absent is never verified:
    the run fails safe into pending_legal_judgment (never adjudicated)."""

    harness = _ChainHarness()
    binding = _v5_inputs(harness, profiles=("grounded",))[0].request_ref
    unverified = ProceduralInputV5(
        request_ref=binding,
        authority=ProcedureAuthorityV5(
            burden_rule_ref=BURDEN_RULE,
            standard_id="preponderance",
            standard_version="1",
            finding="satisfied",
            reviewer="synthetic-legal-reviewer",
            authorization_ref=digest_value({"forged": "not-registered"}),
            request_ref=binding,
        ),
        rule_outcomes=_outcomes(binding),
    )
    document = _run(tmp_path, harness, unverified)
    for row in document["procedures"]:
        assert row["kind"] == "pending_legal_judgment"
        assert row["missing"] == ["authorization-unverified"]


def test_tampered_authority_signature_fails_safe(tmp_path: Path) -> None:
    """A stored authorization whose body was tampered with after signing does
    not verify: pending again, never adjudicated."""

    harness = _ChainHarness()
    binding = _v5_inputs(harness, profiles=("grounded",))[0].request_ref
    reference = _signed_authorization(harness, binding, "satisfied")
    # re-register different bytes under a new ref that the authority cites:
    # body no longer matches the signature payload
    tampered_body = {
        "schema_version": PROCEDURE_AUTHORIZATION_SCHEMA_V5,
        "request_ref": str(binding),
        "burden_rule_ref": BURDEN_RULE,
        "standard_id": "preponderance",
        "standard_version": "1",
        "finding": "unmet",  # flipped after signing
        "reviewer": "synthetic-legal-reviewer",
    }
    tampered = ProceduralInputV5(
        request_ref=binding,
        authority=ProcedureAuthorityV5(
            burden_rule_ref=BURDEN_RULE,
            standard_id="preponderance",
            standard_version="1",
            finding="unmet",
            reviewer="synthetic-legal-reviewer",
            authorization_ref=reference.digest,  # signed artifact says satisfied
            request_ref=binding,
        ),
        rule_outcomes=_outcomes(binding),
    )
    document = _run(tmp_path, harness, tampered)
    for row in document["procedures"]:
        assert row["kind"] == "pending_legal_judgment"
        assert row["missing"] == ["authorization-unverified"]


def test_route_solver_incomplete_with_typed_obligations(tmp_path: Path) -> None:
    """A complete solve that exhausts the enumeration budget keeps the fourth
    route with typed obligations even with procedural input present."""

    harness = _ChainHarness()
    binding = _v5_inputs(harness, profiles=("preferred",))[0].request_ref
    budget_facts = tuple(
        f"synthetic-budget-{index}.required-fact" for index in range(15)
    )
    procedural = ProceduralInputV5(
        request_ref=binding,
        authority=_authority(harness, binding, "satisfied"),
        rule_outcomes=_outcomes(binding),
    )
    document = _run(
        tmp_path, harness, procedural,
        fact_keys=EXCEPTION_FACTS + budget_facts,
    )
    for row in document["procedures"]:
        assert row["kind"] == "solver_incomplete"
        assert row["status"] is None
        assert row["open_obligations"]
    for row in document["queries"]:
        assert row["gate"] == "incomplete"
