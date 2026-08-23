"""Certificate authority, binding, receipt and revocation attacks."""

from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import replace
from pathlib import Path

import pytest

from compiler_core.canonical_serialization import DigestV4, digest_value, parse_json_document
from compiler_core.certificates import (
    CertificateIssuerV4,
    CertificateV4Error,
    CertificateVerifierV4,
)
from compiler_core.contracts import (
    CertificateEnvelopeV4,
    ContentRefV4,
    FactAdmissionReceiptV4,
    FormalCertificateV4,
    SemanticResultV4,
    TrustPolicyV4,
)
from compiler_core.trust import TrustVerifierV4
from tests.contract.test_certificates import (
    _context,
    _formal_fixture,
    _semantic_digest,
)


def _issued(tmp_path: Path):
    harness, bundles, capability, materials, issuer = _formal_fixture(tmp_path)
    completed = bundles.write_run(
        capability,
        materials,
        now=harness.now,
        certificate_factory=issuer,
    )
    context = _context(bundles, materials)
    verifier = CertificateVerifierV4(
        harness.trust,
        current_engine_build_digest=harness.run.engine_build_digest,
    )
    return harness, bundles, capability, materials, issuer, context, verifier, completed.certificate


def test_caller_gate_map_and_digest_cannot_reach_the_issuer(tmp_path: Path) -> None:
    _, _, _, _, issuer, _, _, _ = _issued(tmp_path)
    with pytest.raises(CertificateV4Error) as caught:
        issuer({
            "source": "PASS",
            "fact": "PASS",
            "checker": "PASS",
            "bundle_core_digest": "sha256:" + "0" * 64,
        })
    assert caught.value.code == "CERTIFICATE_CONTEXT_AUTHORITY"


@pytest.mark.parametrize("attack", ("unknown-key", "fake-issuer", "bit-flip"))
def test_unknown_key_fake_issuer_and_signature_bitflip_fail_closed(
    tmp_path: Path,
    attack: str,
) -> None:
    harness, _, _, _, _, context, verifier, certificate = _issued(tmp_path)
    signature = certificate.service_signature
    assert signature is not None
    if attack == "unknown-key":
        signature = replace(signature, key_id="unknown-service-key")
    elif attack == "fake-issuer":
        signature = replace(signature, issuer="fake-service-issuer")
    else:
        raw = b64decode(signature.signature, validate=True)
        signature = replace(
            signature,
            signature=b64encode(bytes((raw[0] ^ 1,)) + raw[1:]).decode("ascii"),
        )
    attacked = replace(certificate, service_signature=signature)
    with pytest.raises(CertificateV4Error) as caught:
        verifier.verify(context, attacked)
    assert caught.value.code == "CERTIFICATE_SERVICE_SIGNATURE"
    if attack == "fake-issuer":
        fact_artifact = next(
            item
            for item in context.artifacts
            if item.artifact_kind == "fact-admission-receipt"
        )
        fact_receipt = FactAdmissionReceiptV4.from_dict(
            parse_json_document(fact_artifact.content)
        )
        formal = certificate.formal
        assert formal is not None
        unsigned = certificate.to_dict()
        del unsigned["service_signature"]
        replayed_signature = harness._signature(
            "service",
            subject_digest=formal.certificate_digest,
            payload_digest=digest_value(unsigned),
            evidence_refs=certificate.service_signature.evidence_refs,
            nonce=fact_receipt.signature.nonce,
            issued_at=context.now,
            run_identity_ref=formal.run_identity_ref,
        )
        with pytest.raises(CertificateV4Error) as replayed:
            verifier.verify(
                context,
                replace(certificate, service_signature=replayed_signature),
            )
        assert replayed.value.code == "CERTIFICATE_SERVICE_SIGNATURE"


@pytest.mark.parametrize("attack", ("bundle", "run"))
def test_wrong_bundle_core_and_run_binding_fail_even_when_resigned(
    tmp_path: Path,
    attack: str,
) -> None:
    harness, _, _, _, _, context, verifier, certificate = _issued(tmp_path)
    formal = certificate.formal
    signature = certificate.service_signature
    assert formal is not None and signature is not None
    body = formal.digest_body()
    if attack == "bundle":
        body["bundle_core_digest"] = str(DigestV4.from_bytes(b"wrong-bundle-core"))
    else:
        body["run_identity_ref"] = ContentRefV4(
            "run-identity", DigestV4.from_bytes(b"wrong-run")
        ).to_dict()
    changed = FormalCertificateV4.from_dict({
        **body, "certificate_digest": str(digest_value(body)),
    })
    unsigned = {
        "kind": "formal_verified",
        "formal": changed.to_dict(),
        "conflict": None,
    }
    resigned = harness._sign_receipt(
        changed.certificate_digest,
        digest_value(unsigned),
        signature.evidence_refs,
        changed.run_identity_ref,
        context.now,
    )
    attacked = CertificateEnvelopeV4.from_dict({
        **unsigned, "service_signature": resigned.to_dict(),
    })
    with pytest.raises(CertificateV4Error) as caught:
        verifier.verify(context, attacked)
    assert caught.value.code == "CERTIFICATE_BUNDLE_MISMATCH"


def test_wrong_current_build_invalidates_an_issued_certificate(tmp_path: Path) -> None:
    harness, _, _, _, _, context, _, certificate = _issued(tmp_path)
    verifier = CertificateVerifierV4(
        harness.trust,
        current_engine_build_digest=DigestV4.from_bytes(b"different-engine-build"),
    )
    with pytest.raises(CertificateV4Error) as caught:
        verifier.verify(context, certificate)
    assert caught.value.code == "CERTIFICATE_RUN_BINDING"


@pytest.mark.parametrize("attack", ("missing", "extra", "replay"))
def test_receipt_missing_extra_and_replay_cannot_issue(
    tmp_path: Path,
    attack: str,
) -> None:
    harness, bundles, capability, materials, issuer = _formal_fixture(tmp_path)
    body = materials.result.to_dict()
    receipts = list(body["receipt_refs"])
    if attack == "missing":
        receipts.pop()
    elif attack == "extra":
        receipts.append(ContentRefV4(
            "fake-receipt", DigestV4.from_bytes(b"extra-receipt")
        ).to_dict())
    else:
        receipts.append(receipts[0])
    body["receipt_refs"] = receipts
    body.pop("result_digest")
    changed = SemanticResultV4.from_dict({
        **body, "result_digest": str(_semantic_digest(body)),
    })
    with pytest.raises(CertificateV4Error) as caught:
        bundles.write_run(
            capability,
            replace(materials, result=changed),
            now=harness.now,
            certificate_factory=issuer,
        )
    assert caught.value.code in {"CERTIFICATE_RECEIPT_EXTRA", "CERTIFICATE_RECEIPT_REPLAY"}


def test_missing_proof_receipt_bytes_cannot_issue(tmp_path: Path) -> None:
    harness, bundles, capability, materials, issuer = _formal_fixture(tmp_path)
    changed = replace(
        materials,
        checker_artifacts=tuple(
            item
            for item in materials.checker_artifacts
            if item.artifact_kind != "proof-receipt-v4"
        ),
    )
    with pytest.raises(CertificateV4Error) as caught:
        bundles.write_run(
            capability,
            changed,
            now=harness.now,
            certificate_factory=issuer,
        )
    assert caught.value.code == "CERTIFICATE_RECEIPT_MISSING"


def test_revoked_service_key_policy_invalidates_the_bound_run(tmp_path: Path) -> None:
    harness, _, _, _, _, context, _, certificate = _issued(tmp_path)
    body = harness.policy.digest_body()
    body["trusted_key_ids"] = [
        key_id for key_id in body["trusted_key_ids"] if key_id != "synthetic-service-key"
    ]
    body["revoked_key_ids"] = sorted({
        *body["revoked_key_ids"], "synthetic-service-key",
    })
    revoked = TrustPolicyV4.from_dict({
        **body, "policy_digest": str(digest_value(body)),
    })
    trust = TrustVerifierV4(
        policy=revoked,
        keys=tuple(key for _, key in sorted(harness.trust._keys.items())),
        target_environment="test",
    )
    verifier = CertificateVerifierV4(
        trust,
        current_engine_build_digest=harness.run.engine_build_digest,
    )
    with pytest.raises(CertificateV4Error) as caught:
        verifier.verify(context, certificate)
    assert caught.value.code == "CERTIFICATE_RUN_BINDING"
