"""Crash-boundary tests for AuditBundleV4 staging and COMPLETE-last publication."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler_core.audit_bundle import AuditBundleStoreV4
from tests.contract.test_audit_bundle import _bundle_directory, _minimal_fixture


@pytest.mark.parametrize("kill_before", ("manifest.json", "COMPLETE"))
def test_interrupted_bundle_is_never_published_and_next_writer_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kill_before: str,
) -> None:
    _, trust, storage, bundles, capability, materials = _minimal_fixture(tmp_path)
    original = bundles._write_file

    def interrupted(directory: Path, name: str, raw: bytes) -> None:
        if name == kill_before:
            raise SystemExit(91)
        original(directory, name, raw)

    monkeypatch.setattr(bundles, "_write_file", interrupted)
    with pytest.raises(SystemExit):
        bundles.write_run(capability, materials, now=materials.request.decision_time)
    assert not _bundle_directory(storage, capability.token).exists()
    assert len(list((storage.root / "audit-staging").iterdir())) == 1

    resumed = AuditBundleStoreV4(
        storage,
        trust_material=trust,
        current_engine_build_digest=materials.run_identity.engine_build_digest,
        checker_receipt_issuer="synthetic-service-issuer",
    )
    completed = resumed.write_run(
        capability, materials, now=materials.request.decision_time
    )
    assert completed.verification.status == "VERIFIED"
    assert list((storage.root / "audit-staging").iterdir()) == []
    assert len(list((storage.root / "audit-quarantine").iterdir())) == 1
