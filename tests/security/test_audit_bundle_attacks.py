"""Tamper, capability, trust and certificate-authority attacks on AuditBundleV4."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

import pytest

from compiler_core.audit_bundle import AuditBundleStoreV4, AuditBundleV4Error
from compiler_core.canonical_serialization import DigestV4, canonical_bytes, parse_json_document
from compiler_core.contracts import CanonicalTimeV4, ContentRefV4, ContractV4Error
from compiler_core.storage import _harden_windows
from tests.contract.test_audit_bundle import _bundle_directory, _minimal_fixture


def test_caller_gate_and_digest_cannot_issue_certificate(tmp_path: Path) -> None:
    _, _, _, bundles, capability, materials = _minimal_fixture(tmp_path)
    caller_claim = {
        "all_gates": True,
        "bundle_core_digest": "sha256:" + "0" * 64,
        "status": "PASS",
    }
    invoked = False

    def caller_factory(_context):
        nonlocal invoked
        invoked = True
        return caller_claim

    assert not hasattr(bundles, "issue_certificate")
    with pytest.raises(AuditBundleV4Error) as caught:
        bundles.write_run(
            capability,
            materials,
            now=materials.request.decision_time,
            certificate_factory=caller_factory,
        )
    assert caught.value.code == "AUDIT_CERTIFICATE_AUTHORITY"
    assert invoked is False
    assert not _bundle_directory(bundles._store, capability.token).exists()


@pytest.mark.parametrize(
    "attack",
    ("missing", "extra", "replacement", "reordered-checksums", "bit-flip", "early-complete", "v3"),
)
def test_missing_extra_replacement_reorder_bitflip_and_v3_fail_closed(
    tmp_path: Path,
    attack: str,
) -> None:
    _, _, storage, bundles, capability, materials = _minimal_fixture(tmp_path)
    bundles.write_run(capability, materials, now=materials.request.decision_time)
    directory = _bundle_directory(storage, capability.token)

    if attack == "missing":
        (directory / "graph.json").unlink()
    elif attack == "extra":
        extra = directory / "extra.json"
        extra.write_bytes(b"{}")
        if os.name == "nt":
            _harden_windows(extra)
    elif attack == "replacement":
        (directory / "result.json").write_bytes(materials.request.canonical_bytes())
    elif attack == "reordered-checksums":
        path = directory / "checksums.sha256"
        path.write_bytes(b"\n".join(reversed(path.read_bytes().splitlines())) + b"\n")
    elif attack == "bit-flip":
        path = directory / "certificate.json"
        raw = path.read_bytes()
        path.write_bytes(bytes((raw[0] ^ 1,)) + raw[1:])
    elif attack == "early-complete":
        (directory / "manifest.json").unlink()
        assert (directory / "COMPLETE").is_file()
    else:
        path = directory / "input.json"
        payload = parse_json_document(path.read_bytes())
        payload["schema_version"] = "jc/audit-input/3.0"
        path.write_bytes(canonical_bytes(payload))

    with pytest.raises((AuditBundleV4Error, ContractV4Error)):
        bundles.verify_run(capability, now=materials.request.decision_time)


def test_handle_binds_run_scope_expiry_bounds_and_chunk_digest(tmp_path: Path) -> None:
    harness, _, _, bundles, capability, materials = _minimal_fixture(tmp_path)
    completed = bundles.write_run(capability, materials, now=materials.request.decision_time)
    expires = CanonicalTimeV4("2027-01-01T00:00:00Z")
    max_bytes = min(64, len(completed.files["input.json"]))
    handle = bundles.issue_artifact_handle(
        capability,
        "input.json",
        now=materials.request.decision_time,
        expires_at=expires,
        max_bytes=max_bytes,
        signer=harness._sign_receipt,
    )
    chunk = bundles.read_artifact(
        handle,
        offset=0,
        length=16,
        now=materials.request.decision_time,
    )
    assert chunk.offset == 0
    assert chunk.length == 16
    assert chunk.next_offset == 16
    assert chunk.chunk_digest == DigestV4.from_bytes(completed.files["input.json"][:16])
    assert "path" not in chunk.to_dict()
    tail = bundles.read_artifact(
        handle,
        offset=16,
        length=max_bytes - 16,
        now=materials.request.decision_time,
    )
    assert tail.eof is True
    assert tail.next_offset is None

    with pytest.raises(AuditBundleV4Error) as bounds:
        bundles.read_artifact(
            handle,
            offset=max_bytes - 1,
            length=2,
            now=materials.request.decision_time,
        )
    assert bounds.value.code == "AUDIT_HANDLE_RANGE"

    with pytest.raises(AuditBundleV4Error) as expired:
        bundles.read_artifact(
            handle,
            offset=0,
            length=1,
            now=CanonicalTimeV4("2027-01-02T00:00:00Z"),
        )
    assert expired.value.code == "AUDIT_HANDLE_EXPIRED"

    with pytest.raises(ContractV4Error):
        replace(
            handle,
            run_identity_ref=ContentRefV4(
                "run-identity", DigestV4.from_bytes(b"another-run")
            ),
        )
    with pytest.raises(ContractV4Error):
        replace(handle, max_bytes=max_bytes - 1)


def test_current_build_and_current_revocation_authority_reject_old_bundle(
    tmp_path: Path,
) -> None:
    _, trust, storage, bundles, capability, materials = _minimal_fixture(tmp_path)
    bundles.write_run(capability, materials, now=materials.request.decision_time)

    wrong_build = AuditBundleStoreV4(
        storage,
        trust_material=trust,
        current_engine_build_digest=DigestV4.from_bytes(b"new-build"),
        checker_receipt_issuer="synthetic-service-issuer",
    )
    with pytest.raises(AuditBundleV4Error) as build:
        wrong_build.verify_run(capability, now=materials.request.decision_time)
    assert build.value.code == "AUDIT_BUILD_BINDING"

    revoked = AuditBundleStoreV4(
        storage,
        trust_material=replace(trust, revoked_nonces=("revoked-after-run",)),
        current_engine_build_digest=materials.run_identity.engine_build_digest,
        checker_receipt_issuer="synthetic-service-issuer",
    )
    with pytest.raises(AuditBundleV4Error) as revocation:
        revoked.verify_run(capability, now=materials.request.decision_time)
    assert revocation.value.code == "AUDIT_TRUST_BINDING"
