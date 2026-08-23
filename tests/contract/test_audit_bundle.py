"""Contract tests for atomic, independently verified V4 audit bundles."""

from __future__ import annotations

from base64 import b64decode, b64encode
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from compiler_core.audit_bundle import (
    BUNDLE_FILES_V4,
    AuditArtifactV4,
    AuditBundleMaterialsV4,
    AuditBundleStoreV4,
    AuditBundleV4Error,
    AuditEventV4,
    AuditTrustMaterialV4,
    ReplayExecutionV4,
)
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    CanonicalTimeV4,
    ContentRefV4,
    RunIdentityV4,
    SemanticResultV4,
)
from compiler_core.independent_checker import CHECKER_SCOPE
from compiler_core.storage import V4TransactionStore
from tests.contract.test_backend_router import HORN_PROVIDER_ID, _execute, _provider
from tests.contract.test_independent_checker import _checker
from tests.integration.test_trust_chain import _ChainHarness


REPO = Path(__file__).resolve().parents[2]
VECTORS = json.loads(
    (REPO / "tests/contract/v4-contract-vectors.json").read_text(encoding="utf-8")
)


def _semantic_digest(payload: dict[str, object]) -> DigestV4:
    projection = deepcopy(payload)
    projection.pop("result_digest", None)
    projection["runtime_profile"].pop("backend_receipt_ref")
    for claim in projection["claims"]:
        claim.pop("proof_receipt_refs")
        claim.pop("checker_receipt_refs")
    projection.pop("receipt_refs")
    return digest_value(projection)


def _result(
    run: RunIdentityV4,
    *,
    backend_invocation_ref: ContentRefV4 | None = None,
    backend_receipt_ref: ContentRefV4 | None = None,
    checker_receipt_ref: ContentRefV4 | None = None,
) -> SemanticResultV4:
    body = deepcopy(VECTORS["objects"]["SemanticResultV4"])
    body["request_ref"] = run.request_ref.to_dict()
    body["run_identity_ref"] = ContentRefV4(
        "run-identity", run.canonical_digest()
    ).to_dict()
    body["runtime_profile"] = {
        "engine_version": run.engine_version,
        "engine_build_digest": str(run.engine_build_digest),
        "formal_kernel": checker_receipt_ref is not None,
        "backend_invocation_ref": (
            None if backend_invocation_ref is None else backend_invocation_ref.to_dict()
        ),
        "backend_receipt_ref": (
            None if backend_receipt_ref is None else backend_receipt_ref.to_dict()
        ),
        "trust_policy_ref": run.trust_policy_ref.to_dict(),
        "storage_capability_ref": run.storage_capability_ref.to_dict(),
    }
    body["receipt_refs"] = (
        [] if checker_receipt_ref is None else [checker_receipt_ref.to_dict()]
    )
    body.pop("result_digest")
    return SemanticResultV4.from_dict({
        **body, "result_digest": str(_semantic_digest(body)),
    })


def _artifacts(harness, *, checked_ref: ContentRefV4) -> dict[str, tuple[AuditArtifactV4, ...]]:
    groups: dict[str, list[AuditArtifactV4]] = {
        "source_artifacts": [],
        "fact_artifacts": [],
        "rule_pack_artifacts": [],
        "translation_artifacts": [],
        "backend_artifacts": [],
        "checker_artifacts": [],
        "graph_artifacts": [],
    }
    auto = {harness.request_ref, harness.run_identity_ref}
    for reference, record in harness.resolver._by_ref.items():
        if reference in auto:
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
        elif record.scope == "backend":
            group = "backend_artifacts"
        elif record.scope == "legal-ir":
            group = "translation_artifacts"
        elif record.scope in {"rule-pack", "rule-component"}:
            group = "rule_pack_artifacts"
        elif record.scope in {"fact-admission", "legal-approval", "case-evidence"}:
            group = "fact_artifacts"
        else:
            group = "source_artifacts"
        groups[group].append(artifact)
    assert any(
        item.content_ref == checked_ref for item in groups["checker_artifacts"]
    )
    return {
        name: tuple(sorted(values, key=lambda item: item.sort_key))
        for name, values in groups.items()
    }


def _fixture(tmp_path: Path):
    harness, _, _, _, _, executions = _execute("synthetic-positive")
    solver = _provider(executions, HORN_PROVIDER_ID)
    checked = _checker(harness).check(
        run_identity_ref=harness.run_identity_ref,
        solver_receipt_ref=solver.receipt_ref,
        now=harness.now,
    )
    trust = AuditTrustMaterialV4(
        harness.policy,
        tuple(key for _, key in sorted(harness.trust._keys.items())),
        "test",
    )
    groups = _artifacts(harness, checked_ref=checked.receipt_ref)
    result = _result(
        harness.run,
        backend_invocation_ref=solver.invocation_ref,
        backend_receipt_ref=solver.receipt_ref,
        checker_receipt_ref=checked.receipt_ref,
    )
    materials = AuditBundleMaterialsV4(
        request=harness.request,
        run_identity=harness.run,
        replay_policy_ref=harness.policy.replay_policy_ref,
        result=result,
        events=(AuditEventV4(0, "checker-complete", checked.receipt_ref),),
        **groups,
    )
    storage = V4TransactionStore.create(
        (tmp_path / "state").resolve(), quota_bytes=256 * 1024 * 1024
    )
    bundles = AuditBundleStoreV4(
        storage,
        trust_material=trust,
        current_engine_build_digest=harness.run.engine_build_digest,
        checker_receipt_issuer="synthetic-service-issuer",
    )
    capability = bundles.capability_for(harness.run_identity_ref)
    return harness, storage, bundles, capability, materials, checked.receipt_ref


def _minimal_fixture(tmp_path: Path, *, state_name: str = "state"):
    harness = _ChainHarness()
    trust = AuditTrustMaterialV4(
        harness.policy,
        tuple(key for _, key in sorted(harness.trust._keys.items())),
        "test",
    )
    result = _result(harness.run)
    materials = AuditBundleMaterialsV4(
        request=harness.request,
        run_identity=harness.run,
        replay_policy_ref=harness.policy.replay_policy_ref,
        result=result,
        source_artifacts=(),
        fact_artifacts=(),
        rule_pack_artifacts=(),
        translation_artifacts=(),
        backend_artifacts=(),
        checker_artifacts=(),
        graph_artifacts=(),
        events=(AuditEventV4(0, "request-sealed", harness.request_ref),),
    )
    storage = V4TransactionStore.create(
        (tmp_path / state_name).resolve(), quota_bytes=64 * 1024 * 1024
    )
    bundles = AuditBundleStoreV4(
        storage,
        trust_material=trust,
        current_engine_build_digest=harness.run.engine_build_digest,
        checker_receipt_issuer="synthetic-service-issuer",
    )
    capability = bundles.capability_for(harness.run_identity_ref)
    return harness, trust, storage, bundles, capability, materials


def _bundle_directory(storage: V4TransactionStore, token: str) -> Path:
    return storage.root / "audit-bundles" / token


def test_atomic_bundle_has_fixed_files_complete_last_and_independent_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, storage, bundles, capability, materials, checked_ref = _fixture(tmp_path)
    writes: list[str] = []
    original = bundles._write_file

    def recording_write(directory: Path, name: str, raw: bytes) -> None:
        writes.append(name)
        original(directory, name, raw)

    monkeypatch.setattr(bundles, "_write_file", recording_write)
    completed = bundles.write_run(capability, materials, now=materials.request.decision_time)

    assert writes[-1] == "COMPLETE"
    assert set(completed.files) == set(BUNDLE_FILES_V4)
    assert set(path.name for path in _bundle_directory(storage, capability.token).iterdir()) == set(
        BUNDLE_FILES_V4
    )
    assert completed.checker_receipt_refs == (checked_ref,)
    assert completed.verification.status == "VERIFIED"
    assert not hasattr(completed, "run_directory")
    assert bundles.verify_run(capability, now=materials.request.decision_time) == completed


def test_existing_bundle_cannot_mix_old_digest_with_new_result(tmp_path: Path) -> None:
    _, _, bundles, capability, materials, _ = _fixture(tmp_path)
    bundles.write_run(capability, materials, now=materials.request.decision_time)
    result_body = materials.result.to_dict()
    result_body["risk_codes"] = ["old-complete-new-result"]
    result_body.pop("result_digest")
    changed_result = SemanticResultV4.from_dict({
        **result_body, "result_digest": str(_semantic_digest(result_body)),
    })
    changed = replace(materials, result=changed_result)

    with pytest.raises(AuditBundleV4Error) as caught:
        bundles.write_run(capability, changed, now=materials.request.decision_time)
    assert caught.value.code == "RUN_ID_COLLISION"


def test_offline_replay_uses_new_run_and_cannot_modify_original(tmp_path: Path) -> None:
    _, _, bundles, capability, materials, _ = _fixture(tmp_path)
    empty_groups = {
        "source_artifacts": (),
        "fact_artifacts": (),
        "rule_pack_artifacts": (),
        "translation_artifacts": (),
        "backend_artifacts": (),
        "checker_artifacts": (),
        "graph_artifacts": (),
    }
    materials = replace(
        materials,
        result=_result(materials.run_identity),
        events=(AuditEventV4(0, "request-sealed", materials.run_identity.request_ref),),
        **empty_groups,
    )
    original = bundles.write_run(capability, materials, now=materials.request.decision_time)
    run_body = materials.run_identity.digest_body()
    run_body["engine_source_commit"] = "c" * 40
    replay_run = RunIdentityV4.from_dict({
        **run_body, "run_digest": str(digest_value(run_body)),
    })
    replay_result = _result(replay_run)
    replay_materials = replace(
        materials,
        run_identity=replay_run,
        result=replay_result,
        events=(AuditEventV4(0, "request-sealed", replay_run.request_ref),),
    )

    def execute(sealed):
        assert tuple(name for name, _ in sealed.files) == (
            "input.json", "source-index.json", "fact-admission.json", "rule-pack.json",
        )
        assert sealed.replay_policy_ref == materials.replay_policy_ref
        return ReplayExecutionV4(replay_materials)

    replay = bundles.replay_run(
        capability, now=materials.request.decision_time, executor=execute
    )
    assert replay.replay_run_identity_ref != replay.run_identity_ref
    assert replay.original_bundle_ref != replay.replay_bundle_ref
    assert replay.exact_equal is False
    assert replay.semantic_equal is True
    assert bundles.verify_run(capability, now=materials.request.decision_time) == original


def test_stale_staging_is_quarantined_before_next_write(tmp_path: Path) -> None:
    _, storage, bundles, capability, materials, _ = _fixture(tmp_path)
    stale = storage.root / "audit-staging" / "stale"
    stale.mkdir(mode=0o700)
    if __import__("os").name == "nt":
        from compiler_core.storage import _harden_windows

        _harden_windows(stale)
    completed = bundles.write_run(capability, materials, now=materials.request.decision_time)
    assert completed.verification.status == "VERIFIED"
    assert list((storage.root / "audit-staging").iterdir()) == []
    assert len(list((storage.root / "audit-quarantine").iterdir())) == 1


def test_checker_receipt_is_cryptographically_recomputed_not_status_trusted(
    tmp_path: Path,
) -> None:
    _, _, bundles, capability, materials, checked_ref = _fixture(tmp_path)
    artifacts = list(materials.checker_artifacts)
    index = next(
        index for index, item in enumerate(artifacts) if item.content_ref == checked_ref
    )
    target = artifacts[index]
    payload = parse_json_document(target.content)
    signature = b64decode(payload["signature"]["signature"], validate=True)
    payload["signature"]["signature"] = b64encode(
        bytes((signature[0] ^ 1,)) + signature[1:]
    ).decode("ascii")
    tampered = canonical_bytes(payload)
    tampered_ref = ContentRefV4(target.content_ref.kind, DigestV4.from_bytes(tampered))
    artifacts[index] = replace(
        target, content_ref=tampered_ref, content=tampered
    )
    changed = replace(
        materials,
        checker_artifacts=tuple(sorted(artifacts, key=lambda item: item.sort_key)),
        events=(AuditEventV4(0, "checker-complete", tampered_ref),),
    )

    with pytest.raises(AuditBundleV4Error) as caught:
        bundles.write_run(capability, changed, now=materials.request.decision_time)
    assert caught.value.code == "AUDIT_RECEIPT_DAG"


def test_same_complete_run_is_disk_verified_and_idempotent(tmp_path: Path) -> None:
    _, storage, bundles, capability, materials, _ = _fixture(tmp_path)
    first = bundles.write_run(capability, materials, now=materials.request.decision_time)
    second = bundles.write_run(capability, materials, now=materials.request.decision_time)
    assert second == first
    assert len(list((storage.root / "audit-bundles").iterdir())) == 1
    assert list((storage.root / "audit-staging").iterdir()) == []
