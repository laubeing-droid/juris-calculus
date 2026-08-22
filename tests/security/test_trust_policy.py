from __future__ import annotations

from base64 import b64decode, b64encode
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from compiler_core.canonical_serialization import DigestV4, canonical_bytes, digest_value
from compiler_core.contracts import (
    CanonicalTimeV4,
    ContractV4Error,
    SignatureEnvelopeV4,
    TrustPolicyV4,
)
from compiler_core.trust import TRUST_PROFILES_V4, TrustKeyV4, TrustVerifierV4


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads(
    (ROOT / "tests/fixtures/golden/v4-test-trust-policy.json").read_text(encoding="utf-8")
)
KEY_FIXTURE = json.loads((ROOT / FIXTURE["key_fixture"]).read_text(encoding="utf-8"))
PROFILES = tuple(FIXTURE["profiles"])
SUBJECT = DigestV4.from_bytes(b"signed-subject")
PAYLOAD = DigestV4.from_bytes(b"signed-payload")
NOW = CanonicalTimeV4("2026-08-22T12:00:00Z")


def _policy(
    *,
    trusted_key_ids: tuple[str, ...] | None = None,
    revoked_key_ids: tuple[str, ...] = (),
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> TrustPolicyV4:
    body = {
        "policy_id": FIXTURE["policy_id"],
        "allowed_algorithms": ["Ed25519"],
        "trusted_key_ids": list(trusted_key_ids or (KEY_FIXTURE["key_id"],)),
        "revoked_key_ids": list(revoked_key_ids),
        "allowed_issuers": [FIXTURE["issuer"]],
        "allowed_roles": [profile["role"] for profile in PROFILES],
        "allowed_scopes": [profile["scope"] for profile in PROFILES],
        "allowed_artifact_kinds": [profile["artifact_kind"] for profile in PROFILES],
        "valid_from": {"wire": valid_from or FIXTURE["valid_from"]},
        "valid_to": {"wire": valid_to or FIXTURE["valid_to"]},
        "authorization_policy_ref": FIXTURE["policy_refs"]["authorization"],
        "revocation_policy_ref": FIXTURE["policy_refs"]["revocation"],
        "replay_policy_ref": FIXTURE["policy_refs"]["replay"],
        "separation_of_duties_ref": FIXTURE["policy_refs"]["separation_of_duties"],
    }
    return TrustPolicyV4.from_dict({**body, "policy_digest": str(digest_value(body))})


def _key() -> TrustKeyV4:
    return TrustKeyV4(
        key_id=KEY_FIXTURE["key_id"],
        issuer=FIXTURE["issuer"],
        principal_id=FIXTURE["principal_id"],
        roles=tuple(profile["role"] for profile in PROFILES),
        scopes=tuple(profile["scope"] for profile in PROFILES),
        artifact_kinds=tuple(profile["artifact_kind"] for profile in PROFILES),
        public_key=b64decode(KEY_FIXTURE["public_key_base64"], validate=True),
        production_allowed=FIXTURE["production_allowed"],
    )


def _verifier(
    policy: TrustPolicyV4,
    *,
    target_environment: str = "test",
    revoked_subjects: tuple[DigestV4, ...] = (),
    revoked_nonces: tuple[str, ...] = (),
) -> TrustVerifierV4:
    return TrustVerifierV4(
        policy=policy,
        keys=(_key(),),
        target_environment=target_environment,
        revoked_subject_digests=revoked_subjects,
        revoked_nonces=revoked_nonces,
    )


def _envelope(
    policy: TrustPolicyV4,
    profile: dict[str, str],
    **overrides: object,
) -> SignatureEnvelopeV4:
    body: dict[str, object] = {
        "algorithm": "Ed25519",
        "key_id": KEY_FIXTURE["key_id"],
        "issuer": FIXTURE["issuer"],
        "role": profile["role"],
        "scope": profile["scope"],
        "kind": profile["artifact_kind"],
        "schema_version": "jc/4.0",
        "subject_digest": str(SUBJECT),
        "run_identity_ref": None,
        "status": "APPROVED",
        "issued_at": {"wire": "2026-08-22T11:00:00Z"},
        "expires_at": {"wire": "2026-08-23T11:00:00Z"},
        "nonce": f"nonce-{profile['scope']}",
        "evidence_refs": [],
        "payload_digest": str(PAYLOAD),
        "policy_digest": str(policy.policy_digest),
        "revocation_ref": policy.revocation_policy_ref.to_dict(),
    }
    body.update(overrides)
    private_key = Ed25519PrivateKey.from_private_bytes(
        b64decode(KEY_FIXTURE["private_key_base64"], validate=True)
    )
    signature = b64encode(private_key.sign(canonical_bytes(body))).decode("ascii")
    return SignatureEnvelopeV4.from_dict({**body, "signature": signature})


def _verify(
    verifier: TrustVerifierV4,
    envelope: SignatureEnvelopeV4,
    profile: dict[str, str],
    *,
    now: CanonicalTimeV4 = NOW,
    subject: DigestV4 = SUBJECT,
    separation: tuple[str, ...] = (),
) -> str:
    return verifier.verify(
        envelope,
        expected_subject_digest=subject,
        expected_payload_digest=PAYLOAD,
        required_role=profile["role"],
        required_scope=profile["scope"],
        required_artifact_kind=profile["artifact_kind"],
        expected_status="APPROVED",
        now=now,
        separation_from_principals=separation,
    )


@pytest.mark.parametrize("profile", PROFILES, ids=lambda item: item["scope"])
def test_each_scope_accepts_a_real_ed25519_signature(profile: dict[str, str]) -> None:
    policy = _policy()
    assert TRUST_PROFILES_V4[profile["scope"]] == (
        profile["role"],
        profile["artifact_kind"],
    )
    assert _verify(_verifier(policy), _envelope(policy, profile), profile) == FIXTURE["principal_id"]


def test_six_trust_profiles_are_exact_and_immutable() -> None:
    assert dict(TRUST_PROFILES_V4) == {
        profile["scope"]: (profile["role"], profile["artifact_kind"])
        for profile in PROFILES
    }
    with pytest.raises(TypeError):
        TRUST_PROFILES_V4["injected-scope"] = ("attacker", "attacker")  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ({"key_id": "unknown-key"}, "TRUST_KEY_NOT_TRUSTED"),
        ({"issuer": "unknown-issuer"}, "TRUST_ISSUER_MISMATCH"),
        ({"scope": "legal-approval"}, "TRUST_SCOPE_MISMATCH"),
        ({"role": "legal_reviewer"}, "TRUST_ROLE_MISMATCH"),
        ({"kind": "legal-approval"}, "TRUST_KIND_MISMATCH"),
        ({"subject_digest": str(DigestV4.from_bytes(b"other-subject"))}, "TRUST_SUBJECT_MISMATCH"),
        ({"policy_digest": str(DigestV4.from_bytes(b"other-policy"))}, "TRUST_POLICY_MISMATCH"),
        ({"payload_digest": str(DigestV4.from_bytes(b"other-payload"))}, "TRUST_PAYLOAD_MISMATCH"),
        ({"algorithm": "Ed448"}, "TRUST_ALGORITHM"),
        ({"status": "PASS"}, "TRUST_STATUS_MISMATCH"),
        ({"issued_at": {"wire": "2026-08-23T13:00:00Z"}, "expires_at": {"wire": "2026-08-24T13:00:00Z"}}, "TRUST_ISSUED_TIME"),
        ({"expires_at": {"wire": "2026-08-22T11:59:59Z"}}, "TRUST_SIGNATURE_EXPIRED"),
        ({"revocation_ref": FIXTURE["policy_refs"]["authorization"]}, "TRUST_REVOCATION_POLICY"),
    ),
)
def test_signed_but_wrong_claims_are_rejected(mutation: dict[str, object], code: str) -> None:
    profile = PROFILES[0]
    policy = _policy()
    with pytest.raises(ContractV4Error, match=f"^{code}:"):
        _verify(_verifier(policy), _envelope(policy, profile, **mutation), profile)


def test_revoked_and_unregistered_keys_are_distinct_failures() -> None:
    profile = PROFILES[0]
    revoked = _policy(trusted_key_ids=("other-key",), revoked_key_ids=(KEY_FIXTURE["key_id"],))
    with pytest.raises(ContractV4Error, match="^TRUST_KEY_REVOKED:"):
        _verify(_verifier(revoked), _envelope(revoked, profile), profile)

    unknown_policy = _policy(trusted_key_ids=("unknown-key",))
    unknown = _envelope(unknown_policy, profile, key_id="unknown-key")
    with pytest.raises(ContractV4Error, match="^TRUST_KEY_UNKNOWN:"):
        _verify(_verifier(unknown_policy), unknown, profile)


def test_inactive_policy_and_signature_outliving_policy_are_rejected() -> None:
    profile = PROFILES[0]
    inactive = _policy(valid_from="2026-08-22T13:00:00Z")
    with pytest.raises(ContractV4Error, match="^TRUST_POLICY_INACTIVE:"):
        _verify(_verifier(inactive), _envelope(inactive, profile), profile)

    short_policy = _policy(valid_to="2026-08-22T12:30:00Z")
    with pytest.raises(ContractV4Error, match="^TRUST_SIGNATURE_EXPIRY:"):
        _verify(_verifier(short_policy), _envelope(short_policy, profile), profile)


@pytest.mark.parametrize(
    ("revoked_subjects", "revoked_nonces"),
    (({SUBJECT}, ()), (set(), ("nonce-source-authenticity",))),
)
def test_subject_and_nonce_revocation_are_enforced(
    revoked_subjects: set[DigestV4], revoked_nonces: tuple[str, ...]
) -> None:
    profile = PROFILES[0]
    policy = _policy()
    verifier = _verifier(
        policy,
        revoked_subjects=tuple(revoked_subjects),
        revoked_nonces=revoked_nonces,
    )
    with pytest.raises(ContractV4Error, match="^TRUST_SIGNATURE_REVOKED:"):
        _verify(verifier, _envelope(policy, profile), profile)


def test_same_principal_cannot_satisfy_separated_approval() -> None:
    profile = PROFILES[1]
    policy = _policy()
    with pytest.raises(ContractV4Error, match="^TRUST_SEPARATION_OF_DUTIES:"):
        _verify(
            _verifier(policy),
            _envelope(policy, profile),
            profile,
            separation=(FIXTURE["principal_id"],),
        )


def test_nonce_consumption_is_atomic_under_concurrency() -> None:
    profile = PROFILES[3]
    policy = _policy()
    verifier = _verifier(policy)
    envelope = _envelope(policy, profile)

    def consume() -> str:
        try:
            return _verify(verifier, envelope, profile)
        except ContractV4Error as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(lambda _index: consume(), range(2)))
    assert outcomes == ["TRUST_REPLAY", FIXTURE["principal_id"]]


@pytest.mark.parametrize("malformed", ("%%%", "short"))
def test_malformed_or_bit_flipped_signatures_are_rejected(malformed: str) -> None:
    profile = PROFILES[0]
    policy = _policy()
    envelope = _envelope(policy, profile)
    wire = envelope.to_dict()
    if malformed == "short":
        signature = bytearray(b64decode(wire["signature"], validate=True))
        signature[0] ^= 1
        wire["signature"] = b64encode(signature).decode("ascii")
        expected = "TRUST_SIGNATURE_INVALID"
    else:
        wire["signature"] = malformed
        expected = "TRUST_SIGNATURE_ENCODING"
    with pytest.raises(ContractV4Error, match=f"^{expected}:"):
        _verify(_verifier(policy), SignatureEnvelopeV4.from_dict(wire), profile)


def test_test_root_cannot_authorize_production() -> None:
    profile = PROFILES[5]
    policy = _policy()
    with pytest.raises(ContractV4Error, match="^TRUST_TEST_KEY_FORBIDDEN:"):
        _verify(
            _verifier(policy, target_environment="production"),
            _envelope(policy, profile),
            profile,
        )
