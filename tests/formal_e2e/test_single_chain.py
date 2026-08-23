"""One real synthetic request through the complete V4 formal spine."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler_core.application import ApplicationV4
from compiler_core.canonical_serialization import parse_json_document
from compiler_core.contracts import CertificateKindV4, DecisionStatusV4
from tests.contract.test_application import _application
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


def test_application_issues_and_reverifies_one_bundle_bound_formal_result(
    tmp_path: Path,
) -> None:
    harness = _ChainHarness()
    application, store, _ = _application(tmp_path, harness)

    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )
    capability = store.capability_for(harness.run_identity_ref)
    verified = store.verify_run(capability, now=harness.now)

    assert (
        envelope.result.decision_status is DecisionStatusV4.ACCEPTED_FORMAL_RESULT
    ), envelope.transport_outcome.to_dict()
    assert envelope.result.certificate_kind is CertificateKindV4.FORMAL_VERIFIED
    assert envelope.certificate.kind is CertificateKindV4.FORMAL_VERIFIED
    assert envelope.certificate.formal is not None
    assert envelope.certificate.service_signature is not None
    assert verified.result == envelope.result
    assert verified.certificate == envelope.certificate
    assert verified.verification.status == "VERIFIED"
    assert envelope.result.claims[0].claim_id == "synthetic-positive"
    assert envelope.result.claims[0].proof_receipt_refs
    assert envelope.result.claims[0].checker_receipt_refs
    stages = [
        parse_json_document(line)["stage"]
        for line in verified.files["events.jsonl"].splitlines()
    ]
    assert stages == [
        "resolver",
        "trust",
        "source",
        "evidence",
        "fact",
        "pack",
        "ir",
        "backend",
        "checker",
        "argument",
        "result",
    ]


def test_advisory_boolean_cannot_be_formal(tmp_path: Path) -> None:
    harness = _ChainHarness()
    application, _, _ = _application(tmp_path, harness)

    with pytest.raises(TypeError, match="advisory_verified"):
        application.evaluate(
            harness.request_ref,
            harness.run_identity_ref,
            case_scope=CASE_SCOPE,
            advisory_verified=True,  # type: ignore[call-arg]
        )

    assert ApplicationV4.evaluate is type(application).evaluate
