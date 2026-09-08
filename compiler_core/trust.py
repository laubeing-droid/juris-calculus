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
    LOCAL_RECORD_ALGORITHM_V4,
    LOCAL_RECORD_STATUS_V4,
    CanonicalTimeV4,
    ContractV4Error,
    LocalRecordV4,
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

TRUST_ENVIRONMENTS_V4 = frozenset({"test", "production", "local"})


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

    expected_status = "APPROVED"

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
        if len({key.public_key for key in keys}) != len(keys):
            _fail("TRUST_KEY_CONFIG", "public key must bind exactly one key identity")

        self.policy = policy
        self.target_environment = target_environment
        self._keys = by_id
        self._revoked_subjects = frozenset(revoked_subject_digests)
        self._revoked_nonces = frozenset(revoked_nonces)
        self._seen_nonces: set[tuple[str, str]] = set()
        self._nonce_lock = Lock()

    def _fresh_without_replay(self) -> "TrustVerifierV4":
        """Copy current trust configuration without reusing the live nonce ledger."""

        return self.fresh_copy()

    def fresh_copy(self) -> "TrustVerifierV4":
        """Polymorphic copy without the live nonce ledger."""

        return TrustVerifierV4(
            policy=self.policy,
            keys=tuple(key for _, key in sorted(self._keys.items())),
            target_environment=self.target_environment,
            revoked_subject_digests=tuple(sorted(self._revoked_subjects, key=str)),
            revoked_nonces=tuple(sorted(self._revoked_nonces)),
        )

    def state_fingerprint(self) -> tuple[object, ...]:
        """Comparable snapshot of this authority's configuration."""

        return (
            self.target_environment,
            self.policy.canonical_bytes(),
            tuple(
                (
                    key_id,
                    key.issuer,
                    key.principal_id,
                    key.roles,
                    key.scopes,
                    key.artifact_kinds,
                    key.public_key,
                    key.production_allowed,
                )
                for key_id, key in sorted(self._keys.items())
            ),
            tuple(sorted(str(digest) for digest in self._revoked_subjects)),
            tuple(sorted(self._revoked_nonces)),
        )

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


class LocalRecordTrustV4:
    """Local-record trust authority: content binding without any key material.

    This is the explicit local provenance mode. It verifies exactly the same
    structural bindings as :class:`TrustVerifierV4` (subject, payload,
    evidence, role, scope, kind, status, time windows, policy, revocation,
    replay, separation of duties) over :class:`LocalRecordV4` documents —
    but it verifies no signature, holds no keys, and asserts no external
    principal. A signed envelope reaching this authority is a hard error so
    the old key-based procedure can never silently run in local mode.
    """

    expected_status = LOCAL_RECORD_STATUS_V4

    def __init__(
        self,
        *,
        policy: TrustPolicyV4,
        revoked_subject_digests: tuple[DigestV4, ...] = (),
        revoked_nonces: tuple[str, ...] = (),
    ) -> None:
        if type(policy) is not TrustPolicyV4:
            _fail("TRUST_INPUT_TYPE", "policy must be TrustPolicyV4")
        if type(revoked_subject_digests) is not tuple or any(
            type(item) is not DigestV4 for item in revoked_subject_digests
        ):
            _fail("TRUST_REVOCATION_CONFIG", "revoked subjects must be DigestV4 values")
        if type(revoked_nonces) is not tuple or any(
            type(item) is not str or not item for item in revoked_nonces
        ):
            _fail("TRUST_REVOCATION_CONFIG", "revoked nonces must be non-empty strings")
        self.policy = policy
        self.target_environment = "local"
        self._keys: dict[str, TrustKeyV4] = {}
        self._revoked_subjects = frozenset(revoked_subject_digests)
        self._revoked_nonces = frozenset(revoked_nonces)
        self._seen_nonces: set[tuple[str, str]] = set()
        self._nonce_lock = Lock()

    def _fresh_without_replay(self) -> "LocalRecordTrustV4":
        return self.fresh_copy()

    def fresh_copy(self) -> "LocalRecordTrustV4":
        return LocalRecordTrustV4(
            policy=self.policy,
            revoked_subject_digests=tuple(sorted(self._revoked_subjects, key=str)),
            revoked_nonces=tuple(sorted(self._revoked_nonces)),
        )

    def state_fingerprint(self) -> tuple[object, ...]:
        return (
            self.target_environment,
            self.policy.canonical_bytes(),
            (),
            tuple(sorted(str(digest) for digest in self._revoked_subjects)),
            tuple(sorted(self._revoked_nonces)),
        )

    def verify(
        self,
        record: LocalRecordV4,
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
        if type(record) is not LocalRecordV4:
            _fail(
                "TRUST_INPUT_TYPE",
                "local trust verifies only LocalRecordV4 records; "
                "signed envelopes are not part of the local path",
            )
        if type(expected_subject_digest) is not DigestV4 or type(expected_payload_digest) is not DigestV4:
            _fail("TRUST_INPUT_TYPE", "expected digests must be DigestV4")
        if type(now) is not CanonicalTimeV4:
            _fail("TRUST_INPUT_TYPE", "now must be CanonicalTimeV4")
        required_role = _nonempty(required_role, "required_role")
        required_scope = _nonempty(required_scope, "required_scope")
        required_artifact_kind = _nonempty(required_artifact_kind, "required_artifact_kind")
        expected_status = _nonempty(expected_status, "expected_status")
        if type(separation_from_principals) is not tuple or any(
            type(item) is not str for item in separation_from_principals
        ):
            _fail("TRUST_INPUT_TYPE", "separation principals must be non-empty strings")

        profile = TRUST_PROFILES_V4.get(required_scope)
        if profile != (required_role, required_artifact_kind):
            _fail("TRUST_PROFILE_MISMATCH", "required scope, role, and artifact kind disagree")
        policy = self.policy
        if now < policy.valid_from or (policy.valid_to is not None and not now < policy.valid_to):
            _fail("TRUST_POLICY_INACTIVE", "trust policy is not active at the verification time")
        if record.policy_digest != policy.policy_digest:
            _fail("TRUST_POLICY_MISMATCH", "record does not bind the active trust policy")
        if record.subject_digest != expected_subject_digest:
            _fail("TRUST_SUBJECT_MISMATCH", "record subject does not match expectation")
        if record.payload_digest != expected_payload_digest:
            _fail("TRUST_PAYLOAD_MISMATCH", "record payload does not match expectation")
        if record.role != required_role:
            _fail("TRUST_ROLE_MISMATCH", "record role does not match expectation")
        if record.scope != required_scope:
            _fail("TRUST_SCOPE_MISMATCH", "record scope does not match expectation")
        if record.kind != required_artifact_kind:
            _fail("TRUST_KIND_MISMATCH", "record artifact kind does not match expectation")
        if record.status != expected_status:
            _fail("TRUST_STATUS_MISMATCH", "record status does not match expectation")
        if record.issuer not in policy.allowed_issuers:
            _fail("TRUST_ISSUER_MISMATCH", "record issuer is not allowed by the policy")
        if required_role not in policy.allowed_roles:
            _fail("TRUST_ROLE_MISMATCH", "record role is outside the policy scope")
        if required_scope not in policy.allowed_scopes:
            _fail("TRUST_SCOPE_MISMATCH", "record scope is outside the policy scope")
        if required_artifact_kind not in policy.allowed_artifact_kinds:
            _fail("TRUST_KIND_MISMATCH", "artifact kind is outside the policy scope")
        if record.revocation_ref != policy.revocation_policy_ref:
            _fail("TRUST_REVOCATION_POLICY", "record does not bind the revocation policy")
        if record.issued_at < policy.valid_from or now < record.issued_at:
            _fail("TRUST_ISSUED_TIME", "record issued time is outside the valid interval")
        if record.expires_at is None or not now < record.expires_at:
            _fail("TRUST_SIGNATURE_EXPIRED", "record is expired or has no expiry")
        if policy.valid_to is not None and policy.valid_to < record.expires_at:
            _fail("TRUST_SIGNATURE_EXPIRY", "record outlives the trust policy")
        if record.subject_digest in self._revoked_subjects or record.nonce in self._revoked_nonces:
            _fail("TRUST_SIGNATURE_REVOKED", "record subject or nonce is revoked")
        if record.issuer in separation_from_principals:
            _fail("TRUST_SEPARATION_OF_DUTIES", "record issuer violates separation of duties")

        nonce_key = (record.issuer, record.nonce)
        with self._nonce_lock:
            if nonce_key in self._seen_nonces:
                _fail("TRUST_REPLAY", "record nonce was already consumed")
            self._seen_nonces.add(nonce_key)
        return record.issuer
