"""Scoped Ed25519 trust verification for immutable V4 signature envelopes."""

from __future__ import annotations

from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from dataclasses import dataclass
from threading import Lock
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from compiler_core.canonical_serialization import DigestV4, canonical_bytes
from compiler_core.contracts import (
    CanonicalTimeV4,
    ContractV4Error,
    SignatureEnvelopeV4,
    TrustPolicyV4,
)


TRUST_PROFILES_V4 = MappingProxyType({
    "source-authenticity": ("source_attestor", "source-snapshot"),
    "legal-approval": ("legal_reviewer", "legal-approval"),
    "engineering-approval": ("engineering_reviewer", "engineering-approval"),
    "pack-release": ("pack_releaser", "rule-pack"),
    "service-certificate": ("service_signer", "service-certificate"),
    "build-attestation": ("build_attestor", "build-attestation"),
})


def _fail(code: str, detail: str) -> None:
    raise ContractV4Error(code, detail)


def _nonempty(value: object, field: str) -> str:
    if type(value) is not str or not value:
        _fail("TRUST_INPUT_TYPE", f"{field} must be a non-empty string")
    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        _fail("TRUST_KEY_CONFIG", f"{field} must be a non-empty tuple")
    if any(type(item) is not str or not item for item in value):
        _fail("TRUST_KEY_CONFIG", f"{field} must contain non-empty strings")
    if len(set(value)) != len(value):
        _fail("TRUST_KEY_CONFIG", f"{field} must not contain duplicates")
    return value


@dataclass(frozen=True, slots=True)
class TrustKeyV4:
    """One in-memory public key and its exact authorization boundary."""

    key_id: str
    issuer: str
    principal_id: str
    roles: tuple[str, ...]
    scopes: tuple[str, ...]
    artifact_kinds: tuple[str, ...]
    public_key: bytes
    production_allowed: bool

    def __post_init__(self) -> None:
        _nonempty(self.key_id, "TrustKeyV4.key_id")
        _nonempty(self.issuer, "TrustKeyV4.issuer")
        _nonempty(self.principal_id, "TrustKeyV4.principal_id")
        roles = _string_tuple(self.roles, "TrustKeyV4.roles")
        scopes = _string_tuple(self.scopes, "TrustKeyV4.scopes")
        kinds = _string_tuple(self.artifact_kinds, "TrustKeyV4.artifact_kinds")
        if type(self.public_key) is not bytes or len(self.public_key) != 32:
            _fail("TRUST_KEY_CONFIG", "TrustKeyV4.public_key must be 32 immutable bytes")
        if type(self.production_allowed) is not bool:
            _fail("TRUST_KEY_CONFIG", "TrustKeyV4.production_allowed must be boolean")
        for scope in scopes:
            profile = TRUST_PROFILES_V4.get(scope)
            if profile is None or profile[0] not in roles or profile[1] not in kinds:
                _fail("TRUST_KEY_CONFIG", "key scope lacks its exact role and artifact kind")


class TrustVerifierV4:
    """Verify signed envelopes without filesystem, network, or private-key authority."""

    def __init__(
        self,
        *,
        policy: TrustPolicyV4,
        keys: tuple[TrustKeyV4, ...],
        target_environment: str,
        revoked_subject_digests: tuple[DigestV4, ...] = (),
        revoked_nonces: tuple[str, ...] = (),
    ) -> None:
        if type(policy) is not TrustPolicyV4:
            _fail("TRUST_INPUT_TYPE", "policy must be TrustPolicyV4")
        if type(keys) is not tuple or any(type(key) is not TrustKeyV4 for key in keys):
            _fail("TRUST_KEY_CONFIG", "keys must be a tuple of TrustKeyV4")
        if target_environment not in {"test", "production"}:
            _fail("TRUST_ENVIRONMENT", "target_environment must be test or production")
        if type(revoked_subject_digests) is not tuple or any(
            type(item) is not DigestV4 for item in revoked_subject_digests
        ):
            _fail("TRUST_REVOCATION_CONFIG", "revoked subjects must be DigestV4 values")
        if type(revoked_nonces) is not tuple or any(
            type(item) is not str or not item for item in revoked_nonces
        ):
            _fail("TRUST_REVOCATION_CONFIG", "revoked nonces must be non-empty strings")
        by_id = {key.key_id: key for key in keys}
        if len(by_id) != len(keys):
            _fail("TRUST_KEY_CONFIG", "key_id must be unique")

        self.policy = policy
        self.target_environment = target_environment
        self._keys = by_id
        self._revoked_subjects = frozenset(revoked_subject_digests)
        self._revoked_nonces = frozenset(revoked_nonces)
        self._seen_nonces: set[tuple[str, str]] = set()
        self._nonce_lock = Lock()

    def verify(
        self,
        envelope: SignatureEnvelopeV4,
        *,
        expected_subject_digest: DigestV4,
        expected_payload_digest: DigestV4,
        required_role: str,
        required_scope: str,
        required_artifact_kind: str,
        expected_status: str,
        now: CanonicalTimeV4,
        separation_from_principals: tuple[str, ...],
    ) -> str:
        if type(envelope) is not SignatureEnvelopeV4:
            _fail("TRUST_INPUT_TYPE", "envelope must be SignatureEnvelopeV4")
        if type(expected_subject_digest) is not DigestV4 or type(expected_payload_digest) is not DigestV4:
            _fail("TRUST_INPUT_TYPE", "expected digests must be DigestV4")
        if type(now) is not CanonicalTimeV4:
            _fail("TRUST_INPUT_TYPE", "now must be CanonicalTimeV4")
        required_role = _nonempty(required_role, "required_role")
        required_scope = _nonempty(required_scope, "required_scope")
        required_artifact_kind = _nonempty(required_artifact_kind, "required_artifact_kind")
        expected_status = _nonempty(expected_status, "expected_status")
        if type(separation_from_principals) is not tuple or any(
            type(item) is not str or not item for item in separation_from_principals
        ):
            _fail("TRUST_INPUT_TYPE", "separation principals must be non-empty strings")

        profile = TRUST_PROFILES_V4.get(required_scope)
        if profile != (required_role, required_artifact_kind):
            _fail("TRUST_PROFILE_MISMATCH", "required scope, role, and artifact kind disagree")
        policy = self.policy
        if now < policy.valid_from or (policy.valid_to is not None and not now < policy.valid_to):
            _fail("TRUST_POLICY_INACTIVE", "trust policy is not active at the verification time")
        if envelope.policy_digest != policy.policy_digest:
            _fail("TRUST_POLICY_MISMATCH", "signature does not bind the active trust policy")
        if envelope.subject_digest != expected_subject_digest:
            _fail("TRUST_SUBJECT_MISMATCH", "signature subject does not match expectation")
        if envelope.payload_digest != expected_payload_digest:
            _fail("TRUST_PAYLOAD_MISMATCH", "signature payload does not match expectation")
        if envelope.role != required_role:
            _fail("TRUST_ROLE_MISMATCH", "signature role does not match expectation")
        if envelope.scope != required_scope:
            _fail("TRUST_SCOPE_MISMATCH", "signature scope does not match expectation")
        if envelope.kind != required_artifact_kind:
            _fail("TRUST_KIND_MISMATCH", "signature artifact kind does not match expectation")
        if envelope.status != expected_status:
            _fail("TRUST_STATUS_MISMATCH", "signature status does not match expectation")
        if envelope.algorithm != "Ed25519" or envelope.algorithm not in policy.allowed_algorithms:
            _fail("TRUST_ALGORITHM", "signature algorithm is not allowed")

        if envelope.key_id in policy.revoked_key_ids:
            _fail("TRUST_KEY_REVOKED", "signature key is revoked")
        if envelope.key_id not in policy.trusted_key_ids:
            _fail("TRUST_KEY_NOT_TRUSTED", "signature key is not trusted")
        key = self._keys.get(envelope.key_id)
        if key is None:
            _fail("TRUST_KEY_UNKNOWN", "signature key is not registered")
        if self.target_environment == "production" and not key.production_allowed:
            _fail("TRUST_TEST_KEY_FORBIDDEN", "test-only key cannot authorize production")
        if envelope.issuer != key.issuer or envelope.issuer not in policy.allowed_issuers:
            _fail("TRUST_ISSUER_MISMATCH", "signature issuer is not allowed for the key")
        if required_role not in key.roles or required_role not in policy.allowed_roles:
            _fail("TRUST_ROLE_MISMATCH", "signature role is outside the key or policy scope")
        if required_scope not in key.scopes or required_scope not in policy.allowed_scopes:
            _fail("TRUST_SCOPE_MISMATCH", "signature scope is outside the key or policy scope")
        if (
            required_artifact_kind not in key.artifact_kinds
            or required_artifact_kind not in policy.allowed_artifact_kinds
        ):
            _fail("TRUST_KIND_MISMATCH", "artifact kind is outside the key or policy scope")
        if envelope.revocation_ref != policy.revocation_policy_ref:
            _fail("TRUST_REVOCATION_POLICY", "signature does not bind the revocation policy")

        if envelope.issued_at < policy.valid_from or now < envelope.issued_at:
            _fail("TRUST_ISSUED_TIME", "signature issued time is outside the valid interval")
        if envelope.expires_at is None or not now < envelope.expires_at:
            _fail("TRUST_SIGNATURE_EXPIRED", "signature is expired or has no expiry")
        if policy.valid_to is not None and policy.valid_to < envelope.expires_at:
            _fail("TRUST_SIGNATURE_EXPIRY", "signature outlives the trust policy")
        if envelope.subject_digest in self._revoked_subjects or envelope.nonce in self._revoked_nonces:
            _fail("TRUST_SIGNATURE_REVOKED", "signature subject or nonce is revoked")
        if key.principal_id in separation_from_principals:
            _fail("TRUST_SEPARATION_OF_DUTIES", "signer violates separation of duties")

        try:
            signature = b64decode(envelope.signature, validate=True)
        except (Base64Error, ValueError) as exc:
            raise ContractV4Error("TRUST_SIGNATURE_ENCODING", "signature must be strict base64") from exc
        if len(signature) != 64:
            _fail("TRUST_SIGNATURE_ENCODING", "Ed25519 signature must be 64 bytes")
        if b64encode(signature).decode("ascii") != envelope.signature:
            _fail("TRUST_SIGNATURE_ENCODING", "signature must use canonical padded base64")
        signed_body = envelope.to_dict()
        del signed_body["signature"]
        try:
            Ed25519PublicKey.from_public_bytes(key.public_key).verify(
                signature, canonical_bytes(signed_body)
            )
        except InvalidSignature as exc:
            raise ContractV4Error("TRUST_SIGNATURE_INVALID", "Ed25519 verification failed") from exc

        nonce_key = (envelope.key_id, envelope.nonce)
        with self._nonce_lock:
            if nonce_key in self._seen_nonces:
                _fail("TRUST_REPLAY", "signature nonce was already consumed")
            self._seen_nonces.add(nonce_key)
        return key.principal_id
