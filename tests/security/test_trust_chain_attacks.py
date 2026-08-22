from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import replace

import pytest

from compiler_core.canonical_serialization import DigestV4, parse_json_document
from compiler_core.contracts import (
    ContentRefV4,
    FactAdmissionReceiptV4,
    PackSignatureV4,
    SignatureEnvelopeV4,
)
from compiler_core.fact_admission import (
    FACT_ADMISSION_RECEIPT_KIND,
    FACT_ADMISSION_SCOPE,
    FactAdmissionServiceV4,
)
from compiler_core.rule_packs import (
    PACK_SIGNATURE_KIND,
    RULE_PACK_SCOPE,
    RulePackVerifierV4,
)
from compiler_core.source_service import (
    SOURCE_AUTHENTICITY_RECEIPT_KIND,
    SOURCE_SNAPSHOT_KIND,
    SourceServiceV4,
)
from tests.integration.test_trust_chain import _ChainHarness, _error_code


def _flip(envelope: SignatureEnvelopeV4) -> SignatureEnvelopeV4:
    raw = b64decode(envelope.signature, validate=True)
    return replace(
        envelope,
        signature=b64encode(bytes((raw[0] ^ 1,)) + raw[1:]).decode("ascii"),
    )


def _signature_envelope(
    harness: _ChainHarness,
    reference: ContentRefV4,
    *,
    kind: str,
    scope: str,
) -> SignatureEnvelopeV4:
    document = parse_json_document(harness.resolver.resolve_content(
        reference,
        expected_artifact_kind=kind,
        expected_media_type="application/json",
        expected_scope=scope,
        max_bytes=harness.resolver.max_artifact_bytes,
    ))
    assert isinstance(document, dict)
    return SignatureEnvelopeV4.from_dict(document)


def _pack_signature(harness: _ChainHarness) -> PackSignatureV4:
    document = parse_json_document(harness.resolver.resolve_content(
        harness.pack_ref,
        expected_artifact_kind=PACK_SIGNATURE_KIND,
        expected_media_type="application/json",
        expected_scope=RULE_PACK_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    ))
    assert isinstance(document, dict)
    return PackSignatureV4.from_dict(document)


def _receipt(
    harness: _ChainHarness,
    reference: ContentRefV4,
) -> FactAdmissionReceiptV4:
    document = parse_json_document(harness.resolver.resolve_content(
        reference,
        expected_artifact_kind=FACT_ADMISSION_RECEIPT_KIND,
        expected_media_type="application/json",
        expected_scope=FACT_ADMISSION_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    ))
    assert isinstance(document, dict)
    return FactAdmissionReceiptV4.from_dict(document)


def _rotate_key(harness: _ChainHarness, signer: str) -> None:
    key_id = f"synthetic-{signer}-key"
    harness.trust._keys[key_id] = replace(
        harness.trust._keys[key_id],
        public_key=bytes([71]) * 32,
    )


@pytest.mark.parametrize("layer", ("source", "fact", "pack"))
def test_signature_bit_flip_blocks_exact_chain_layer(layer: str) -> None:
    if layer == "fact":
        harness = _ChainHarness(tamper_fact_signature=True)
        assert _error_code(harness.admit_fact) == "TRUST_SIGNATURE_INVALID"
        assert harness.fact_service._admissions == {}
        assert harness.pack_verifier._verified == {}
        return

    harness = _ChainHarness()
    if layer == "source":
        envelope = _signature_envelope(
            harness,
            harness.source.authenticity_receipt_ref,
            kind=SOURCE_AUTHENTICITY_RECEIPT_KIND,
            scope="source-authenticity",
        )
        bad_envelope_ref = harness._contract(
            SOURCE_AUTHENTICITY_RECEIPT_KIND,
            "source-authenticity",
            _flip(envelope),
        )
        bad_snapshot = replace(
            harness.source,
            authenticity_receipt_ref=bad_envelope_ref,
        )
        bad_snapshot_ref = harness._contract(
            SOURCE_SNAPSHOT_KIND,
            "source-authenticity",
            bad_snapshot,
        )
        assert _error_code(
            lambda: harness.source_service.admit_snapshot(
                bad_snapshot_ref, now=harness.now
            )
        ) == "TRUST_SIGNATURE_INVALID"
        assert harness.fact_service._admissions == {}
        assert harness.pack_verifier._verified == {}
        return

    pack = _pack_signature(harness)
    bad_pack = replace(pack, signature=_flip(pack.signature))
    bad_pack_ref = harness._contract(
        PACK_SIGNATURE_KIND,
        RULE_PACK_SCOPE,
        bad_pack,
    )
    harness.admit_fact()
    assert _error_code(
        lambda: harness.pack_verifier.verify(bad_pack_ref, now=harness.now)
    ) == "TRUST_SIGNATURE_INVALID"
    assert harness.pack_verifier._verified == {}


@pytest.mark.parametrize("signer", ("source", "legal", "service", "release"))
def test_cached_chain_rechecks_rotated_public_keys(signer: str) -> None:
    harness = _ChainHarness()
    if signer == "source":
        harness.source_service.admit_snapshot(harness.source_ref, now=harness.now)
        _rotate_key(harness, signer)
        assert _error_code(
            lambda: harness.source_service.resolve_applicable(
                harness.source_bundle_ref, decision_time=harness.now
            )
        ) == "TRUST_SIGNATURE_INVALID"
        assert _error_code(
            lambda: harness.source_service.admit_snapshot(
                harness.source_ref, now=harness.now
            )
        ) == "TRUST_SIGNATURE_INVALID"
        return
    if signer in {"legal", "service"}:
        receipt_ref, _ = harness.admit_fact()
        _rotate_key(harness, signer)
        assert _error_code(lambda: harness.fact_service.verify_receipt(
            receipt_ref,
            request_ref=harness.request_ref,
            case_scope="synthetic-case",
            run_identity_ref=harness.run_identity_ref,
            now=harness.now,
        )) == "TRUST_SIGNATURE_INVALID"
        return
    harness.admit_fact()
    handle = harness.verify_pack()
    _rotate_key(harness, signer)
    assert _error_code(lambda: handle.status) == "PACK_HANDLE_NOT_ISSUED"
    assert _error_code(harness.verify_pack) == "TRUST_REPLAY"


@pytest.mark.parametrize("signer", ("source", "legal", "service", "release"))
def test_cached_chain_rechecks_revoked_nonces(signer: str) -> None:
    harness = _ChainHarness()
    if signer == "source":
        harness.source_service.admit_snapshot(harness.source_ref, now=harness.now)
        nonce = _signature_envelope(
            harness,
            harness.source.authenticity_receipt_ref,
            kind=SOURCE_AUTHENTICITY_RECEIPT_KIND,
            scope="source-authenticity",
        ).nonce
        harness.trust._revoked_nonces = frozenset({nonce})
        assert _error_code(
            lambda: harness.source_service.resolve_applicable(
                harness.source_bundle_ref, decision_time=harness.now
            )
        ) == "TRUST_SIGNATURE_REVOKED"
        assert _error_code(
            lambda: harness.source_service.admit_snapshot(
                harness.source_ref, now=harness.now
            )
        ) == "TRUST_SIGNATURE_REVOKED"
        return
    if signer in {"legal", "service"}:
        receipt_ref, _ = harness.admit_fact()
        nonce = (
            harness.attestation.signature.nonce
            if signer == "legal"
            else _receipt(harness, receipt_ref).signature.nonce
        )
        harness.trust._revoked_nonces = frozenset({nonce})
        assert _error_code(lambda: harness.fact_service.verify_receipt(
            receipt_ref,
            request_ref=harness.request_ref,
            case_scope="synthetic-case",
            run_identity_ref=harness.run_identity_ref,
            now=harness.now,
        )) == "TRUST_SIGNATURE_REVOKED"
        return
    harness.admit_fact()
    handle = harness.verify_pack()
    harness.trust._revoked_nonces = frozenset({_pack_signature(harness).signature.nonce})
    assert _error_code(lambda: handle.status) == "PACK_HANDLE_NOT_ISSUED"
    assert _error_code(harness.verify_pack) == "TRUST_REPLAY"


@pytest.mark.parametrize("layer", ("source", "fact", "pack"))
def test_fresh_service_cannot_replay_consumed_chain(layer: str) -> None:
    harness = _ChainHarness()
    if layer == "source":
        harness.source_service.admit_snapshot(harness.source_ref, now=harness.now)
        fresh = SourceServiceV4(harness.resolver, harness.trust)
        assert _error_code(
            lambda: fresh.admit_snapshot(harness.source_ref, now=harness.now)
        ) == "TRUST_REPLAY"
        return
    if layer == "fact":
        harness.admit_fact()
        fresh = FactAdmissionServiceV4(
            harness.resolver,
            harness.source_service,
            harness.trust,
            receipt_issuer="synthetic-service-issuer",
            receipt_signer=harness._sign_receipt,
        )
        assert _error_code(lambda: fresh.admit(
            harness.request_ref,
            harness.candidate_ref,
            harness.attestation_ref,
            case_scope="synthetic-case",
            run_identity_ref=harness.run_identity_ref,
            now=harness.now,
        )) == "TRUST_REPLAY"
        return
    harness.admit_fact()
    harness.verify_pack()
    identity = harness.trusted["runtime_identity"]
    fresh = RulePackVerifierV4(
        harness.resolver,
        harness.source_service,
        harness.trust,
        expected_engine_api=identity["engine_api"],
        expected_compiler_build_digest=DigestV4(
            identity["compiler_build_digest"]
        ),
        expected_source_tree_digest=DigestV4(identity["source_tree_digest"]),
        expected_schema_digest=DigestV4(identity["schema_digest"]),
    )
    assert _error_code(
        lambda: fresh.verify(harness.pack_ref, now=harness.now)
    ) == "TRUST_REPLAY"


def test_same_service_retry_is_idempotent_across_the_chain() -> None:
    harness = _ChainHarness()
    source_ref = harness.source_service.admit_snapshot(
        harness.source_ref, now=harness.now
    )
    receipt_ref, fact_ref = harness.admit_fact()
    handle = harness.verify_pack()
    assert harness.source_service.admit_snapshot(
        harness.source_ref, now=harness.now
    ) == source_ref
    assert harness.admit_fact() == (receipt_ref, fact_ref)
    assert harness.verify_pack() is handle


def test_cached_test_chain_cannot_cross_into_production() -> None:
    harness = _ChainHarness()
    receipt_ref, _ = harness.admit_fact()
    handle = harness.verify_pack()
    harness.trust.target_environment = "production"
    assert _error_code(
        lambda: harness.source_service.admit_snapshot(
            harness.source_ref, now=harness.now
        )
    ) == "SOURCE_TEST_FIXTURE_FORBIDDEN"
    assert _error_code(lambda: harness.fact_service.verify_receipt(
        receipt_ref,
        request_ref=harness.request_ref,
        case_scope="synthetic-case",
        run_identity_ref=harness.run_identity_ref,
        now=harness.now,
    )) == "SOURCE_TEST_FIXTURE_FORBIDDEN"
    assert _error_code(lambda: handle.status) == "PACK_HANDLE_NOT_ISSUED"
    assert _error_code(harness.verify_pack) == "SOURCE_TEST_FIXTURE_FORBIDDEN"


def test_candidate_is_discoverable_but_never_formal() -> None:
    harness = _ChainHarness()
    row = next(
        item
        for item in harness.fixture["artifacts"]
        if ContentRefV4.from_dict(item["content_ref"]) == harness.candidate_pack_ref
    )
    assert b64decode(row["content_base64"], validate=True)
    assert _error_code(lambda: harness.verify_pack(candidate=True)) == (
        "PACK_PROMOTION_REQUIRED"
    )
