"""Full ApplicationV4 concurrency and COMPLETE-before-kill recovery."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from compiler_core.contracts import CertificateKindV4, DecisionStatusV4
from tests.contract.test_application import _application
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


@pytest.mark.parametrize("kill_before", ("manifest.json", "COMPLETE"))
def test_vertical_slice_kill_before_publication_recovers_on_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kill_before: str,
) -> None:
    harness = _ChainHarness()
    application, store, _ = _application(tmp_path, harness)
    write_file = store._write_file
    interrupted = False

    def kill(directory: Path, name: str, raw: bytes) -> None:
        nonlocal interrupted
        if name == kill_before and not interrupted:
            interrupted = True
            raise SystemExit(91)
        write_file(directory, name, raw)

    monkeypatch.setattr(store, "_write_file", kill)
    with pytest.raises(SystemExit):
        application.evaluate(
            harness.request_ref,
            harness.run_identity_ref,
            case_scope=CASE_SCOPE,
        )
    assert not list((store._store.root / "audit-bundles").iterdir())

    monkeypatch.setattr(store, "_write_file", write_file)
    envelope = application.evaluate(
        harness.request_ref,
        harness.run_identity_ref,
        case_scope=CASE_SCOPE,
    )
    capability = store.capability_for(harness.run_identity_ref)
    verified = store.verify_run(capability, now=harness.now)

    assert envelope.result.decision_status is DecisionStatusV4.ACCEPTED_FORMAL_RESULT
    assert envelope.certificate.kind is CertificateKindV4.FORMAL_VERIFIED
    assert verified.result == envelope.result
    assert not list((store._store.root / "audit-staging").iterdir())
    assert len(list((store._store.root / "audit-quarantine").iterdir())) == 1


def test_concurrent_same_run_returns_one_verified_bundle(tmp_path: Path) -> None:
    harness = _ChainHarness()
    application, store, _ = _application(tmp_path, harness)

    def evaluate():
        return application.evaluate(
            harness.request_ref,
            harness.run_identity_ref,
            case_scope=CASE_SCOPE,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        envelopes = tuple(pool.map(lambda _: evaluate(), range(4)))

    assert {item.result.result_digest for item in envelopes} == {
        envelopes[0].result.result_digest
    }
    assert {item.audit_manifest_ref for item in envelopes} == {
        envelopes[0].audit_manifest_ref
    }
    capability = store.capability_for(harness.run_identity_ref)
    assert store.verify_run(capability, now=harness.now).verification.status == "VERIFIED"
    assert len(list((store._store.root / "audit-bundles").iterdir())) == 1
