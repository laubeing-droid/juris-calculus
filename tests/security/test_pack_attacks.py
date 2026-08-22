from __future__ import annotations

from base64 import b64encode
from dataclasses import replace

import pytest

from compiler_core.canonical_serialization import parse_json_document
from compiler_core.contracts import ContractV4Error
from compiler_core.contracts import PackSignatureV4
from compiler_core.rule_packs import PACK_SIGNATURE_KIND, RULE_PACK_SCOPE
from tests.contract.test_rule_packs import NOW, _PackHarness, _error_code


def test_candidate_cannot_self_activate() -> None:
    harness = _PackHarness()
    pack_ref = harness.build(candidate=True)
    with pytest.raises(TypeError):
        harness.verifier.verify(pack_ref, now=NOW, active=True)
    with pytest.raises(TypeError):
        harness.verifier.verify(pack_ref, now=NOW, status="PASS")
    with pytest.raises(ContractV4Error):
        harness.verifier.verify(pack_ref, now=NOW)


def test_candidate_without_promotion_receipt_is_not_executable() -> None:
    harness = _PackHarness()
    pack_ref = harness.build(candidate=True)
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)).startswith(
        ("RULE_", "PACK_")
    )


@pytest.mark.parametrize(
    "empty_field",
    (
        "rule_refs",
        "source_refs",
        "config_refs",
        "receipt_refs",
        "coverage_receipt_refs",
        "verification_receipt_refs",
    ),
)
def test_empty_formal_manifest_reference_sets_block(empty_field: str) -> None:
    harness = _PackHarness()
    pack_ref = harness.build(empty_field=empty_field)
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)).startswith("PACK_")


def test_empty_official_pack_and_format_only_attestation_fail() -> None:
    empty = _PackHarness()
    empty_ref = empty.build(empty_field="rule_refs")
    with pytest.raises(ContractV4Error):
        empty.verifier.verify(empty_ref, now=NOW)

    format_only = _PackHarness()
    format_only_ref = format_only.build(format_only_build=True)
    with pytest.raises(ContractV4Error):
        format_only.verifier.verify(format_only_ref, now=NOW)


@pytest.mark.parametrize(
    ("option", "value"),
    (
        ("forged_source", True),
        ("wrong_locator", True),
        ("wrong_structure", True),
    ),
)
def test_unverified_source_or_wrong_locator_blocks(option: str, value: bool) -> None:
    harness = _PackHarness()
    pack_ref = harness.build(**{option: value})
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)).startswith(
        ("SOURCE_", "TRUST_", "RULE_", "PACK_RULE_")
    )


def test_missing_review_signature_blocks_promotion() -> None:
    harness = _PackHarness()
    pack_ref = harness.build(missing_review=True)
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)).startswith(
        ("ARTIFACT_", "RULE_")
    )


def test_unsigned_pack_blocks() -> None:
    harness = _PackHarness()
    pack_ref = harness.build(release_fault="unsigned")
    with pytest.raises(ContractV4Error):
        harness.verifier.verify(pack_ref, now=NOW)


def test_test_keys_cannot_activate_a_production_pack() -> None:
    harness = _PackHarness(target_environment="production")
    pack_ref = harness.build()
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)) == (
        "TRUST_TEST_KEY_FORBIDDEN"
    )


def test_cached_test_pack_cannot_be_reused_after_switching_to_production() -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    handle = harness.verifier.verify(pack_ref, now=NOW)
    harness.trust.target_environment = "production"
    assert not handle.verifier_issued
    assert _error_code(lambda: handle.status) == "PACK_HANDLE_NOT_ISSUED"
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)) == (
        "TRUST_TEST_KEY_FORBIDDEN"
    )


def test_prewarmed_source_cache_cannot_survive_public_key_rotation() -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    harness.source_service.admit_snapshot(harness.last_source_ref, now=NOW)
    key_id = "w2-03-source-key"
    harness.trust._keys[key_id] = replace(
        harness.trust._keys[key_id],
        public_key=bytes([99]) * 32,
    )
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)) == (
        "TRUST_SIGNATURE_INVALID"
    )


def test_same_principal_cannot_supply_legal_and_engineering_review() -> None:
    harness = _PackHarness(same_review_principal=True)
    pack_ref = harness.build()
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)) == (
        "TRUST_SEPARATION_OF_DUTIES"
    )


def test_principal_cannot_change_governance_role_across_rules() -> None:
    harness = _PackHarness(cross_rule_role_overlap=True)
    pack_ref = harness.build()
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)) == (
        "TRUST_SEPARATION_OF_DUTIES"
    )


def test_source_attestor_cannot_also_approve_a_rule() -> None:
    harness = _PackHarness(same_source_and_legal_principal=True)
    pack_ref = harness.build()
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)) == (
        "TRUST_SEPARATION_OF_DUTIES"
    )


@pytest.mark.parametrize(
    "release_fault",
    ("forged", "expired", "wrong-scope", "signature-replacement"),
)
def test_forged_expired_or_wrong_scope_release_signature_blocks(
    release_fault: str,
) -> None:
    harness = _PackHarness()
    pack_ref = harness.build(release_fault=release_fault)
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)).startswith(
        ("TRUST_", "SIGNATURE_")
    )


def test_revoked_release_signature_blocks() -> None:
    harness = _PackHarness(revoked_nonces=("release-nonce",))
    pack_ref = harness.build()
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)) == (
        "TRUST_SIGNATURE_REVOKED"
    )


def test_promotion_nonce_replay_blocks_second_rule() -> None:
    harness = _PackHarness()
    pack_ref = harness.build(promotion_replay=True)
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)) == "TRUST_REPLAY"


def test_manifest_reference_replacement_breaks_attached_signature_binding() -> None:
    harness = _PackHarness()
    pack_ref = harness.build(release_fault="manifest-replacement")
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)) == (
        "SIGNATURE_SUBJECT_MISMATCH"
    )


def test_pack_signature_byte_replacement_is_not_a_valid_release() -> None:
    harness = _PackHarness()
    pack_ref = harness.build(release_fault="signature-replacement")
    assert _error_code(lambda: harness.verifier.verify(pack_ref, now=NOW)) == (
        "TRUST_SIGNATURE_INVALID"
    )


def test_signature_cache_cannot_be_preheated_with_another_envelope() -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    raw = harness.resolver.resolve_content(
        pack_ref,
        expected_artifact_kind=PACK_SIGNATURE_KIND,
        expected_media_type="application/json",
        expected_scope=RULE_PACK_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    )
    pack = PackSignatureV4.from_dict(parse_json_document(raw.decode("utf-8")))
    verify = harness.verifier._verify_signature
    arguments = {
        "expected_subject": pack.signature.subject_digest,
        "expected_payload": pack.signature.payload_digest,
        "role": "pack_releaser",
        "scope": "pack-release",
        "artifact_kind": "rule-pack",
        "status": "APPROVED",
        "now": NOW,
        "separation": (),
    }
    verify(pack_ref, pack.signature, **arguments)
    forged = replace(pack.signature, signature=b64encode(bytes(64)).decode("ascii"))
    assert _error_code(lambda: verify(pack_ref, forged, **arguments)) == (
        "TRUST_SIGNATURE_INVALID"
    )
