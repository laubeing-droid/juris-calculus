from __future__ import annotations

from base64 import b64decode, b64encode
from pathlib import Path
import subprocess
import sys
from typing import Callable, Iterator
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from compiler_core.artifact_store import ArtifactResolverV4
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
    PackManifestV4,
    PackSignatureV4,
    SignatureEnvelopeV4,
    SourceBundleV4,
    SourceSnapshotV4,
    TrustPolicyV4,
)
from compiler_core.rule_packs import (
    BUILD_ATTESTATION_KIND,
    BUILD_ATTESTATION_SCOPE,
    JSON_MEDIA_TYPE,
    PACK_MANIFEST_KIND,
    PACK_SIGNATURE_KIND,
    RULE_PACK_SCOPE,
    RulePackVerifierV4,
    build_attestation_evidence_refs,
    build_subject_ref,
    pack_release_evidence_refs,
)
from compiler_core.source_service import (
    SOURCE_BUNDLE_KIND,
    SOURCE_NORMALIZED_KIND,
    SOURCE_RAW_KIND,
    SOURCE_SNAPSHOT_KIND,
    SourceServiceV4,
)
from compiler_core.trust import TrustKeyV4, TrustVerifierV4
from tools.build_synthetic_pack import (
    FIXTURE_PATH,
    TEST_MASTER_KEY_PATH,
    TRUST_CONTEXT_PATH,
    _SyntheticPackBuilder,
)


ROOT = Path(__file__).resolve().parents[2]
_EXTERNAL_TRUST_KINDS = frozenset({
    "trust-policy",
    "trust-authorization-policy",
    "trust-revocation-policy",
    "trust-replay-policy",
    "trust-separation-policy",
})


def _document(path: Path) -> dict[str, object]:
    value = parse_json_document(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _error_code(call: Callable[[], object]) -> str:
    with pytest.raises(ContractV4Error) as caught:
        call()
    return caught.value.code


def _load(
    *,
    target_environment: str = "test",
    production_keys: bool = False,
    fixture_document: dict[str, object] | None = None,
):
    fixture = _document(FIXTURE_PATH) if fixture_document is None else fixture_document
    trusted = _document(TRUST_CONTEXT_PATH)
    policy = TrustPolicyV4.from_dict(trusted["trust_policy"])
    keys = tuple(
        TrustKeyV4(
            key_id=row["key_id"],
            issuer=row["issuer"],
            principal_id=row["principal_id"],
            roles=tuple(row["roles"]),
            scopes=tuple(row["scopes"]),
            artifact_kinds=tuple(row["artifact_kinds"]),
            public_key=b64decode(row["public_key_base64"], validate=True),
            production_allowed=(True if production_keys else row["production_allowed"]),
        )
        for row in trusted["trust_keys"]
    )
    resolver = ArtifactResolverV4(max_artifact_bytes=262_144)
    for row in fixture["artifacts"]:
        resolver.register_bytes(
            artifact_id=row["artifact_id"],
            content_ref=ContentRefV4.from_dict(row["content_ref"]),
            artifact_kind=row["artifact_kind"],
            media_type=row["media_type"],
            scope=row["scope"],
            content=b64decode(row["content_base64"], validate=True),
        )
    trust = TrustVerifierV4(
        policy=policy,
        keys=keys,
        target_environment=target_environment,
    )
    source_service = SourceServiceV4(resolver, trust)
    identity = trusted["runtime_identity"]
    verifier = RulePackVerifierV4(
        resolver,
        source_service,
        trust,
        expected_engine_api=identity["engine_api"],
        expected_compiler_build_digest=DigestV4(identity["compiler_build_digest"]),
        expected_source_tree_digest=DigestV4(identity["source_tree_digest"]),
        expected_schema_digest=DigestV4(identity["schema_digest"]),
    )
    return fixture, trusted, resolver, trust, verifier


def _verify(
    fixture: dict[str, object],
    trusted: dict[str, object],
    verifier: RulePackVerifierV4,
):
    return verifier.verify(
        ContentRefV4.from_dict(fixture["pack_ref"]),
        now=CanonicalTimeV4.from_dict(trusted["verification_time"]),
    )


def _component(resolver: ArtifactResolverV4, reference: ContentRefV4) -> dict[str, object]:
    document = parse_json_document(resolver.resolve_content(
        reference,
        expected_artifact_kind=reference.kind,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope="rule-component",
        max_bytes=resolver.max_artifact_bytes,
    ))
    assert isinstance(document, dict)
    return document


def _content_refs(value: object) -> Iterator[ContentRefV4]:
    if isinstance(value, dict):
        if set(value) == {"kind", "digest"}:
            yield ContentRefV4.from_dict(value)
            return
        for nested in value.values():
            yield from _content_refs(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _content_refs(nested)


def _signature_identities(value: object) -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        if value.get("algorithm") == "Ed25519" and {
            "key_id", "nonce", "signature"
        } <= set(value):
            yield value["key_id"], value["nonce"]
        for nested in value.values():
            yield from _signature_identities(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _signature_identities(nested)


def _private_material_variants() -> tuple[bytes, ...]:
    master = _document(TEST_MASTER_KEY_PATH)
    master_seed = b64decode(master["private_key_base64"], validate=True)
    seeds = [master_seed]
    for row in _document(TRUST_CONTEXT_PATH)["trust_keys"]:
        name = row["key_id"].removeprefix("synthetic-").removesuffix("-key")
        seeds.append(HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"jc-v4-synthetic-test-only-v1",
            info=f"juris-calculus/{name}".encode("ascii"),
        ).derive(master_seed))
    return tuple(
        variant
        for seed in seeds
        for variant in (seed, seed.hex().encode("ascii"), b64encode(seed))
    )


def test_two_independent_cli_builds_equal_committed_fixture(tmp_path: Path) -> None:
    outputs = (tmp_path / "first.json", tmp_path / "second.json")
    for output in outputs:
        subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "tools/build_synthetic_pack.py"),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    assert outputs[0].read_bytes() == outputs[1].read_bytes() == FIXTURE_PATH.read_bytes()


def test_public_verifier_accepts_fixture_and_same_pack_retry_is_idempotent() -> None:
    fixture, trusted, _, _, verifier = _load()
    first = _verify(fixture, trusted, verifier)
    second = _verify(fixture, trusted, verifier)
    assert first is second
    assert first.verifier_issued
    assert first.status == "VERIFIED_ACTIVE"
    assert {rule.rule_id for rule in first.rules} == set(fixture["formal_rule_ids"])


def test_fixture_covers_typed_relations_and_future_case_vectors() -> None:
    fixture, trusted, resolver, _, verifier = _load()
    verified = _verify(fixture, trusted, verifier)
    by_id = {rule.rule_id: rule for rule in verified.rules}
    features = fixture["feature_rules"]

    assert by_id[features["positive"]].premise_refs
    exception = _component(
        resolver, by_id[features["exception"]].exception_refs[0]
    )
    assert {"attacker", "target", "attack_type", "target_aspect"} <= set(exception)
    priority = _component(resolver, by_id[features["priority"]].priority_refs[0])
    assert {"source", "target", "condition"} <= set(priority)
    permission_rule = by_id[features["permission"]]
    assert permission_rule.modality == "PERMISSION"
    permission = _component(resolver, permission_rule.permission_ref)
    assert {"permission_id", "permits", "relation_to", "relation_kind"} <= set(permission)
    temporal = by_id[features["temporal"]]
    assert temporal.temporal_constraint_refs and temporal.effective_to is not None

    scenario_rule = by_id[features["missing"]]
    premise = _component(resolver, scenario_rule.premise_refs[0])
    assert premise["required"] is True and "state" not in premise
    cases = {row["case_id"]: row for row in fixture["case_vectors"]}
    assert cases["missing-required-fact"] == {
        "case_id": "missing-required-fact",
        "rule_id": scenario_rule.rule_id,
        "fact_key": premise["fact_key"],
        "input_fact_state": "ABSENT",
        "expected_admission": "BLOCKED",
    }
    assert cases["disputed-required-fact"]["input_fact_state"] == "DISPUTED"
    assert cases["disputed-required-fact"]["fact_key"] == premise["fact_key"]
    assert features["missing"] == features["disputed"]


def test_signed_candidate_pack_cannot_activate() -> None:
    fixture, trusted, resolver, trust, _ = _load()
    candidate_ref = ContentRefV4.from_dict(fixture["candidate_pack_ref"])
    now = CanonicalTimeV4.from_dict(trusted["verification_time"])
    candidate_document = parse_json_document(resolver.resolve_content(
        candidate_ref,
        expected_artifact_kind=PACK_SIGNATURE_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=RULE_PACK_SCOPE,
        max_bytes=resolver.max_artifact_bytes,
    ))
    candidate = PackSignatureV4.from_dict(candidate_document)
    manifest_body = parse_json_document(resolver.resolve_content(
        candidate.manifest_ref,
        expected_artifact_kind=PACK_MANIFEST_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=RULE_PACK_SCOPE,
        max_bytes=resolver.max_artifact_bytes,
    ))
    assert isinstance(manifest_body, dict)
    manifest = PackManifestV4.from_dict({
        **manifest_body,
        "manifest_digest": str(candidate.manifest_ref.digest),
    })
    build_refs = tuple(
        reference
        for reference in manifest.receipt_refs
        if reference.kind == BUILD_ATTESTATION_KIND
    )
    assert len(build_refs) == 1
    build_document = parse_json_document(resolver.resolve_content(
        build_refs[0],
        expected_artifact_kind=BUILD_ATTESTATION_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=BUILD_ATTESTATION_SCOPE,
        max_bytes=resolver.max_artifact_bytes,
    ))
    build = SignatureEnvelopeV4.from_dict(build_document)
    subject_ref = build_subject_ref(manifest)
    assert build.evidence_refs == build_attestation_evidence_refs(manifest, subject_ref)
    build_principal = trust.verify(
        build,
        expected_subject_digest=subject_ref.digest,
        expected_payload_digest=subject_ref.digest,
        required_role="build_attestor",
        required_scope=BUILD_ATTESTATION_SCOPE,
        required_artifact_kind=BUILD_ATTESTATION_KIND,
        expected_status="APPROVED",
        now=now,
        separation_from_principals=("synthetic-source-principal",),
    )
    assert build_principal == "synthetic-build-principal"
    assert candidate.signature.evidence_refs == pack_release_evidence_refs(
        candidate.manifest_ref, manifest, subject_ref
    )
    assert trust.verify(
        candidate.signature,
        expected_subject_digest=candidate.manifest_ref.digest,
        expected_payload_digest=digest_value(candidate.signature_body()),
        required_role="pack_releaser",
        required_scope="pack-release",
        required_artifact_kind="rule-pack",
        expected_status="APPROVED",
        now=now,
        separation_from_principals=("synthetic-source-principal", build_principal),
    ) == "synthetic-release-principal"

    fresh_fixture, fresh_trusted, _, _, fresh_verifier = _load()
    fresh_ref = ContentRefV4.from_dict(fresh_fixture["candidate_pack_ref"])
    fresh_now = CanonicalTimeV4.from_dict(fresh_trusted["verification_time"])
    assert _error_code(lambda: fresh_verifier.verify(fresh_ref, now=fresh_now)) == (
        "PACK_PROMOTION_REQUIRED"
    )


def test_candidate_failure_does_not_poison_formal_verification() -> None:
    fixture, trusted, _, _, verifier = _load()
    now = CanonicalTimeV4.from_dict(trusted["verification_time"])
    candidate_ref = ContentRefV4.from_dict(fixture["candidate_pack_ref"])
    assert _error_code(lambda: verifier.verify(candidate_ref, now=now)) == (
        "PACK_PROMOTION_REQUIRED"
    )
    assert _verify(fixture, trusted, verifier).status == "VERIFIED_ACTIVE"


def test_new_verifier_with_consumed_live_trust_rejects_signature_replay() -> None:
    fixture, trusted, resolver, trust, verifier = _load()
    assert _verify(fixture, trusted, verifier).status == "VERIFIED_ACTIVE"
    identity = trusted["runtime_identity"]
    replaying = RulePackVerifierV4(
        resolver,
        SourceServiceV4(resolver, trust),
        trust,
        expected_engine_api=identity["engine_api"],
        expected_compiler_build_digest=DigestV4(identity["compiler_build_digest"]),
        expected_source_tree_digest=DigestV4(identity["source_tree_digest"]),
        expected_schema_digest=DigestV4(identity["schema_digest"]),
    )
    assert _error_code(lambda: _verify(fixture, trusted, replaying)) == "TRUST_REPLAY"
    fresh_fixture, fresh_trusted, _, _, fresh_verifier = _load()
    assert _verify(fresh_fixture, fresh_trusted, fresh_verifier).status == "VERIFIED_ACTIVE"


def test_synthetic_source_tier_is_rejected_outside_test() -> None:
    fixture, trusted, _, _, verifier = _load(
        target_environment="production", production_keys=True
    )
    assert _error_code(lambda: _verify(fixture, trusted, verifier)) == (
        "SOURCE_TEST_FIXTURE_FORBIDDEN"
    )


def test_cached_synthetic_source_tier_is_rejected_after_environment_switch() -> None:
    fixture, trusted, resolver, trust, verifier = _load()
    handle = _verify(fixture, trusted, verifier)
    source_ref = handle.rules[0].source_snapshot_ref
    source_document = parse_json_document(resolver.resolve_content(
        source_ref,
        expected_artifact_kind=SOURCE_SNAPSHOT_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope="source-authenticity",
        max_bytes=resolver.max_artifact_bytes,
    ))
    source = SourceSnapshotV4.from_dict(source_document)
    bundle_body = {
        "bundle_id": "synthetic-cache-environment-switch",
        "root_source_ref": source_ref.to_dict(),
        "terminal_source_ref": source_ref.to_dict(),
        "snapshots": [source.to_dict()],
        "version_edges": [],
    }
    bundle = SourceBundleV4.from_dict({
        **bundle_body,
        "bundle_digest": str(digest_value(bundle_body)),
    })
    bundle_ref = ContentRefV4(SOURCE_BUNDLE_KIND, bundle.canonical_digest())
    resolver.register_bytes(
        artifact_id="synthetic-cache-environment-switch-bundle",
        content_ref=bundle_ref,
        artifact_kind=SOURCE_BUNDLE_KIND,
        media_type=JSON_MEDIA_TYPE,
        scope="source-path",
        content=canonical_bytes(bundle.digest_body()),
    )
    trust.target_environment = "production"
    now = CanonicalTimeV4.from_dict(trusted["verification_time"])
    assert _error_code(
        lambda: verifier._source_service.admit_snapshot(source_ref, now=now)
    ) == "SOURCE_TEST_FIXTURE_FORBIDDEN"
    assert _error_code(
        lambda: verifier._source_service.resolve_applicable(
            bundle_ref,
            decision_time=now,
        )
    ) == "SOURCE_TEST_FIXTURE_FORBIDDEN"


def test_source_authenticity_must_precede_rule_reviews() -> None:
    late_fixture = _SyntheticPackBuilder(issued_at_by_signer={
        "source": CanonicalTimeV4("2026-08-22T11:30:00Z"),
    }).build()
    fixture, trusted, _, _, verifier = _load(fixture_document=late_fixture)
    assert _error_code(lambda: _verify(fixture, trusted, verifier)) == "PACK_REVIEW_TIME"


@pytest.mark.parametrize(
    ("issued_at_by_signer", "error_code"),
    (
        ({"legal": CanonicalTimeV4("2026-08-22T11:30:00Z")}, "PACK_PROMOTION_TIME"),
        ({"build": CanonicalTimeV4("2026-08-22T10:30:00Z")}, "PACK_BUILD_TIME"),
        ({"release": CanonicalTimeV4("2026-08-22T10:30:00Z")}, "PACK_RELEASE_TIME"),
    ),
)
def test_signature_issue_order_must_follow_causal_chain(
    issued_at_by_signer: dict[str, CanonicalTimeV4],
    error_code: str,
) -> None:
    mutated_fixture = _SyntheticPackBuilder(
        issued_at_by_signer=issued_at_by_signer
    ).build()
    fixture, trusted, _, _, verifier = _load(fixture_document=mutated_fixture)
    assert _error_code(lambda: _verify(fixture, trusted, verifier)) == error_code


def test_test_only_release_key_is_rejected_by_production_trust() -> None:
    fixture, trusted, resolver, trust, _ = _load(target_environment="production")
    pack_ref = ContentRefV4.from_dict(fixture["pack_ref"])
    document = parse_json_document(resolver.resolve_content(
        pack_ref,
        expected_artifact_kind=PACK_SIGNATURE_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=RULE_PACK_SCOPE,
        max_bytes=resolver.max_artifact_bytes,
    ))
    pack = PackSignatureV4.from_dict(document)
    assert _error_code(lambda: trust.verify(
        pack.signature,
        expected_subject_digest=pack.manifest_ref.digest,
        expected_payload_digest=digest_value(pack.signature_body()),
        required_role="pack_releaser",
        required_scope="pack-release",
        required_artifact_kind="rule-pack",
        expected_status="APPROVED",
        now=CanonicalTimeV4.from_dict(trusted["verification_time"]),
        separation_from_principals=(),
    )) == "TRUST_TEST_KEY_FORBIDDEN"


def test_fixture_has_external_trust_context_no_private_or_orphan_artifacts() -> None:
    fixture = _document(FIXTURE_PATH)
    trusted = _document(TRUST_CONTEXT_PATH)
    assert set(fixture) == {
        "schema_version",
        "scope",
        "production_allowed",
        "pack_ref",
        "candidate_pack_ref",
        "formal_rule_ids",
        "feature_rules",
        "case_vectors",
        "artifacts",
    }
    assert set(trusted) == {
        "schema_version",
        "scope",
        "production_allowed",
        "verification_time",
        "runtime_identity",
        "trust_policy",
        "trust_keys",
    }
    assert all(set(row) == {
        "key_id",
        "issuer",
        "principal_id",
        "roles",
        "scopes",
        "artifact_kinds",
        "public_key_base64",
        "production_allowed",
    } for row in trusted["trust_keys"])
    assert fixture["scope"] == "test-only" and fixture["production_allowed"] is False
    public_keys = [
        b64decode(row["public_key_base64"], validate=True)
        for row in trusted["trust_keys"]
    ]
    principals = [row["principal_id"] for row in trusted["trust_keys"]]
    assert len(public_keys) == len(set(public_keys)) == len(set(principals)) == 6
    assert all(row["production_allowed"] is False for row in trusted["trust_keys"])
    private_material = _private_material_variants()
    trusted_raw = TRUST_CONTEXT_PATH.read_bytes()
    assert b"private_key" not in trusted_raw
    assert all(material not in trusted_raw for material in private_material)

    by_ref = {
        ContentRefV4.from_dict(row["content_ref"]): row
        for row in fixture["artifacts"]
    }
    pending = [
        ContentRefV4.from_dict(fixture["pack_ref"]),
        ContentRefV4.from_dict(fixture["candidate_pack_ref"]),
    ]
    reachable: set[ContentRefV4] = set()
    signatures: list[tuple[str, str]] = []
    while pending:
        reference = pending.pop()
        if reference in reachable:
            continue
        row = by_ref.get(reference)
        assert row is not None, f"missing artifact: {reference}"
        reachable.add(reference)
        raw = b64decode(row["content_base64"], validate=True)
        assert all(material not in raw for material in private_material)
        if row["media_type"] != JSON_MEDIA_TYPE:
            continue
        document = parse_json_document(raw)
        signatures.extend(_signature_identities(document))
        for nested_ref in _content_refs(document):
            if nested_ref in by_ref:
                pending.append(nested_ref)
            else:
                assert nested_ref.kind in _EXTERNAL_TRUST_KINDS
        if row["artifact_kind"] == SOURCE_SNAPSHOT_KIND:
            pending.extend((
                ContentRefV4(SOURCE_RAW_KIND, DigestV4(document["raw_digest"])),
                ContentRefV4(SOURCE_NORMALIZED_KIND, DigestV4(document["normalized_digest"])),
            ))
    assert reachable == set(by_ref)
    assert len(signatures) == len(set(signatures)) == 17


def test_builder_fixture_and_private_test_keys_are_absent_from_wheel(tmp_path: Path) -> None:
    out = tmp_path / "wheel"
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(out),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        assert not any(name.startswith(("tools/", "tests/")) for name in names)
        private_material = _private_material_variants()
        assert all(
            material not in archive.read(name)
            for name in names
            for material in private_material
        )
