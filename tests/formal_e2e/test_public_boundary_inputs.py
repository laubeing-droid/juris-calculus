"""Typed public-boundary states derived from registered canonical bytes."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler_core.application import ApplicationV4Error
from compiler_core.contracts import CertificateKindV4, DecisionStatusV4
from tests.contract.test_application import (
    _application,
    _nonformal_attestation,
    _register_request_and_run,
    _rule_ref,
)
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


def test_public_request_derives_all_trust(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _ChainHarness()
    application, _, _ = _application(tmp_path, harness)
    calls: list[str] = []
    source = harness.source_service.resolve_applicable
    fact = harness.fact_service.admit
    pack = harness.pack_verifier.verify

    def source_call(*args, **kwargs):
        calls.append("source")
        return source(*args, **kwargs)

    def fact_call(*args, **kwargs):
        calls.append("fact")
        return fact(*args, **kwargs)

    def pack_call(*args, **kwargs):
        calls.append("pack")
        return pack(*args, **kwargs)

    monkeypatch.setattr(harness.source_service, "resolve_applicable", source_call)
    monkeypatch.setattr(harness.fact_service, "admit", fact_call)
    monkeypatch.setattr(harness.pack_verifier, "verify", pack_call)
    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )

    assert calls[0] == "source"
    assert "fact" in calls and "pack" in calls
    assert calls.index("fact") < calls.index("pack")
    assert envelope.result.decision_status is DecisionStatusV4.ACCEPTED_FORMAL_RESULT
    with pytest.raises(ApplicationV4Error, match="^APPLICATION_INPUT_TYPE:"):
        application.evaluate(  # type: ignore[arg-type]
            {"status": "PASS"},
            {"status": "PASS"},
            case_scope=CASE_SCOPE,
        )


def test_missing_fact_is_a_typed_nonformal_result(tmp_path: Path) -> None:
    harness = _ChainHarness()
    rule_ref = _rule_ref(harness, "synthetic-missing-disputed")
    _, request_ref, _, run_ref = _register_request_and_run(
        harness,
        attestation_refs=(),
        proposal_refs=(rule_ref,),
    )
    application, _, _ = _application(tmp_path, harness)

    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)

    assert envelope.result.decision_status is DecisionStatusV4.MISSING_REQUIRED_FACT
    assert envelope.result.missing_facts
    assert envelope.certificate.kind is CertificateKindV4.NONE


def test_disputed_fact_is_review_only_and_never_formal(tmp_path: Path) -> None:
    harness = _ChainHarness()
    attestation_ref = _nonformal_attestation(
        harness,
        dispute_state="DISPUTED",
        assumption_state="NONE",
        label="w4-07-disputed",
    )
    _, request_ref, _, run_ref = _register_request_and_run(
        harness,
        attestation_refs=(attestation_ref,),
    )
    application, _, _ = _application(tmp_path, harness)

    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)

    assert envelope.result.decision_status is DecisionStatusV4.REVIEW_ONLY_RESULT
    assert envelope.certificate.kind is CertificateKindV4.NONE


@pytest.mark.parametrize(
    ("rule_id", "relation_field"),
    (
        ("synthetic-exception-priority", "exception_refs"),
        ("synthetic-exception-priority", "priority_refs"),
        ("synthetic-permission-temporal", "permission_ref"),
        ("synthetic-permission-temporal", "temporal_constraint_refs"),
    ),
)
def test_typed_relation_rules_enter_only_through_verified_pack_bytes(
    tmp_path: Path,
    rule_id: str,
    relation_field: str,
) -> None:
    harness = _ChainHarness()
    verified_pack = harness.verify_pack()
    pair = next(
        (reference, rule)
        for reference, rule in zip(
            verified_pack.manifest.rule_refs,
            verified_pack.rules,
            strict=True,
        )
        if rule.rule_id == rule_id
    )
    rule_ref, rule = pair
    assert getattr(rule, relation_field)
    _, request_ref, _, run_ref = _register_request_and_run(
        harness,
        attestation_refs=(),
        proposal_refs=(rule_ref,),
    )
    application, _, _ = _application(tmp_path, harness)

    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)

    assert envelope.result.decision_status is DecisionStatusV4.MISSING_REQUIRED_FACT
    assert envelope.certificate.kind is CertificateKindV4.NONE
