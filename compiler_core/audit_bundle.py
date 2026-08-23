"""Atomic, independently verified V4 audit bundles and offline replay."""

from __future__ import annotations

from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from collections.abc import Callable
from dataclasses import dataclass
import errno
from functools import wraps
import hashlib
import hmac
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
import uuid

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.audit import AuditEventV4, EVENT_SCHEMA_V4
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.certificates import (
    CertificateArtifactV4,
    CertificateContextV4,
    CertificateV4Error,
    CertificateVerifierV4,
    _verified_certificate_context,
)
from compiler_core.contracts import (
    ArtifactHandleV4,
    AuditBundleIndexV4,
    AuditManifestV4,
    CanonicalTimeV4,
    CaseRequestV4,
    CertificateEnvelopeV4,
    CertificateKindV4,
    ContentRefV4,
    ContractV4Error,
    MCPReadArtifactOutputV4,
    ReplayResultV4,
    RunIdentityV4,
    SemanticResultV4,
    SignatureEnvelopeV4,
    TrustPolicyV4,
    VerificationResultV4,
)
from compiler_core.independent_checker import (
    CHECKER_RECEIPT_KIND,
    CHECKER_SCOPE,
    IndependentCheckerV4,
    IndependentCheckerV4Error,
)
from compiler_core.storage import (
    StorageV4Error,
    V4TransactionStore,
    _file_id,
    _flush_directory,
    _flush_file,
    _harden_windows,
    _mkdir,
    _open_exact,
    _verify_security,
    _write_all,
)
from compiler_core.trust import TrustKeyV4, TrustVerifierV4


BUNDLE_SCHEMA_V4 = "jc/audit-bundle/4.0"
ARTIFACT_SET_SCHEMA_V4 = "jc/audit-artifact-set/4.0"
INPUT_SCHEMA_V4 = "jc/audit-input/4.0"
CERTIFICATE_BINDING_SCHEMA_V4 = "jc/audit-certificate-binding/4.0"
COMPLETE_SCHEMA_V4 = "jc/audit-complete/4.0"
CAPABILITY_SCHEMA_V4 = "jc/audit-run-capability/4.0"
AUDIT_SCOPE_V4 = "audit-read"

CORE_FILES_V4 = (
    "input.json",
    "source-index.json",
    "fact-admission.json",
    "rule-pack.json",
    "translation-receipts.json",
    "backend-receipts.json",
    "checker-receipts.json",
    "events.jsonl",
    "graph.json",
    "result.json",
)
DATA_FILES_V4 = (*CORE_FILES_V4, "certificate.json", "manifest.json")
BUNDLE_FILES_V4 = (*DATA_FILES_V4, "checksums.sha256", "COMPLETE")
REPLAY_INPUT_FILES_V4 = (
    "input.json",
    "source-index.json",
    "fact-admission.json",
    "rule-pack.json",
)
MAX_BUNDLE_BYTES_V4 = 64 * 1024 * 1024
MAX_ARTIFACT_BYTES_V4 = 8 * 1024 * 1024

_ARTIFACT_GROUPS = {
    "source-index.json": "source_artifacts",
    "fact-admission.json": "fact_artifacts",
    "rule-pack.json": "rule_pack_artifacts",
    "translation-receipts.json": "translation_artifacts",
    "backend-receipts.json": "backend_artifacts",
    "checker-receipts.json": "checker_artifacts",
    "graph.json": "graph_artifacts",
}
_CONTENT_KINDS = {
    "input.json": "audit-input",
    "source-index.json": "audit-source-index",
    "fact-admission.json": "audit-fact-admission",
    "rule-pack.json": "audit-rule-pack",
    "translation-receipts.json": "audit-translation-receipts",
    "backend-receipts.json": "audit-backend-receipts",
    "checker-receipts.json": "audit-checker-receipts",
    "events.jsonl": "audit-events",
    "graph.json": "audit-graph",
    "result.json": "audit-result",
    "certificate.json": "audit-certificate-binding",
    "manifest.json": "audit-manifest",
    "checksums.sha256": "audit-checksums",
    "COMPLETE": "audit-complete",
}
_MEDIA_TYPES = {
    **{name: "application/json" for name in BUNDLE_FILES_V4},
    "events.jsonl": "application/x-ndjson",
    "checksums.sha256": "text/plain",
}
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_TOKEN = re.compile(r"[0-9a-f]{64}\Z")


class AuditBundleV4Error(RuntimeError):
    """Stable fail-closed error without host path disclosure."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise AuditBundleV4Error(code, detail)


def _storage_code(exc: StorageV4Error | OSError) -> str:
    code = getattr(exc, "code", None)
    if type(code) is str and code.startswith("STORAGE_"):
        return code
    if isinstance(exc, OSError):
        if exc.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)}:
            return "STORAGE_CAPACITY"
        if exc.errno in {errno.EACCES, errno.EPERM, errno.EROFS}:
            return "STORAGE_PERMISSION"
    return "STORAGE_IO"


def _storage_boundary(method: Callable[..., object]) -> Callable[..., object]:
    @wraps(method)
    def guarded(*args: object, **kwargs: object) -> object:
        try:
            return method(*args, **kwargs)
        except (StorageV4Error, OSError) as exc:
            raise AuditBundleV4Error(
                _storage_code(exc), "private audit storage operation failed"
            ) from None

    return guarded


def _identifier(value: object, field: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        _fail("AUDIT_IDENTIFIER", f"{field} is not a logical identifier")
    return value


def _canonical_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = parse_json_document(raw)
    except (TypeError, ValueError) as exc:
        raise AuditBundleV4Error("AUDIT_JSON", f"{label} is not strict JSON") from exc
    if type(value) is not dict or raw != canonical_bytes(value):
        _fail("AUDIT_NONCANONICAL", f"{label} is not canonical JSON")
    return value


def _content_ref(name: str, raw: bytes) -> ContentRefV4:
    return ContentRefV4(_CONTENT_KINDS[name], DigestV4.from_bytes(raw))


@dataclass(frozen=True, slots=True)
class AuditArtifactV4:
    """One immutable resolver record sealed inside a fixed bundle file."""

    artifact_id: str
    content_ref: ContentRefV4
    artifact_kind: str
    media_type: str
    scope: str
    content: bytes

    def __post_init__(self) -> None:
        _identifier(self.artifact_id, "artifact_id")
        _identifier(self.artifact_kind, "artifact_kind")
        _identifier(self.scope, "scope")
        if type(self.content_ref) is not ContentRefV4 or type(self.content) is not bytes:
            _fail("AUDIT_ARTIFACT", "artifact reference and bytes must be exact V4 values")
        if len(self.content) > MAX_ARTIFACT_BYTES_V4:
            _fail("AUDIT_ARTIFACT_TOO_LARGE", "artifact exceeds the fixed bundle bound")
        if DigestV4.from_bytes(self.content) != self.content_ref.digest:
            _fail("AUDIT_ARTIFACT_DIGEST", "artifact bytes differ from content_ref")

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return self.artifact_kind, self.content_ref.digest.hex, self.artifact_id

    def to_wire(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "content_ref": self.content_ref.to_dict(),
            "artifact_kind": self.artifact_kind,
            "media_type": self.media_type,
            "scope": self.scope,
            "content_base64": b64encode(self.content).decode("ascii"),
        }

    @classmethod
    def from_wire(cls, value: object) -> AuditArtifactV4:
        if type(value) is not dict or set(value) != {
            "artifact_id", "content_ref", "artifact_kind", "media_type", "scope",
            "content_base64",
        }:
            _fail("AUDIT_ARTIFACT_SCHEMA", "artifact record is not closed")
        encoded = value["content_base64"]
        if type(encoded) is not str:
            _fail("AUDIT_ARTIFACT_SCHEMA", "artifact content must be base64 text")
        try:
            content = b64decode(encoded, validate=True)
        except (Base64Error, ValueError) as exc:
            raise AuditBundleV4Error(
                "AUDIT_ARTIFACT_ENCODING", "artifact content is not strict base64"
            ) from exc
        if b64encode(content).decode("ascii") != encoded:
            _fail("AUDIT_ARTIFACT_ENCODING", "artifact base64 is not canonical")
        try:
            reference = ContentRefV4.from_dict(value["content_ref"])
        except (ContractV4Error, TypeError, ValueError) as exc:
            raise AuditBundleV4Error(
                "AUDIT_ARTIFACT_SCHEMA", "artifact content_ref is invalid"
            ) from exc
        return cls(
            value["artifact_id"], reference, value["artifact_kind"],
            value["media_type"], value["scope"], content,
        )


@dataclass(frozen=True, slots=True)
class AuditTrustMaterialV4:
    """Public trust and revocation bytes required for independent offline checks."""

    policy: TrustPolicyV4
    keys: tuple[TrustKeyV4, ...]
    target_environment: str
    revoked_subject_digests: tuple[DigestV4, ...] = ()
    revoked_nonces: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.policy) is not TrustPolicyV4:
            _fail("AUDIT_TRUST", "trust policy must be TrustPolicyV4")
        if type(self.keys) is not tuple or any(type(key) is not TrustKeyV4 for key in self.keys):
            _fail("AUDIT_TRUST", "trust keys must be an exact tuple")
        if tuple(sorted(self.keys, key=lambda key: key.key_id)) != self.keys:
            _fail("AUDIT_TRUST_ORDER", "trust keys must be sorted by key_id")
        if self.target_environment not in {"test", "production"}:
            _fail("AUDIT_TRUST", "target environment is invalid")
        if type(self.revoked_subject_digests) is not tuple or any(
            type(item) is not DigestV4 for item in self.revoked_subject_digests
        ):
            _fail("AUDIT_TRUST", "revoked subjects must be DigestV4 values")
        if type(self.revoked_nonces) is not tuple or any(
            type(item) is not str or not item for item in self.revoked_nonces
        ):
            _fail("AUDIT_TRUST", "revoked nonces must be non-empty strings")

    def verifier(self) -> TrustVerifierV4:
        return TrustVerifierV4(
            policy=self.policy,
            keys=self.keys,
            target_environment=self.target_environment,
            revoked_subject_digests=self.revoked_subject_digests,
            revoked_nonces=self.revoked_nonces,
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "policy": self.policy.to_dict(),
            "keys": [
                {
                    "key_id": key.key_id,
                    "issuer": key.issuer,
                    "principal_id": key.principal_id,
                    "roles": list(key.roles),
                    "scopes": list(key.scopes),
                    "artifact_kinds": list(key.artifact_kinds),
                    "public_key_base64": b64encode(key.public_key).decode("ascii"),
                    "production_allowed": key.production_allowed,
                }
                for key in self.keys
            ],
            "target_environment": self.target_environment,
            "revoked_subject_digests": [str(item) for item in self.revoked_subject_digests],
            "revoked_nonces": list(self.revoked_nonces),
        }

    @classmethod
    def from_wire(cls, value: object) -> AuditTrustMaterialV4:
        if type(value) is not dict or set(value) != {
            "policy", "keys", "target_environment", "revoked_subject_digests",
            "revoked_nonces",
        }:
            _fail("AUDIT_TRUST_SCHEMA", "sealed trust material is not closed")
        if type(value["keys"]) is not list:
            _fail("AUDIT_TRUST_SCHEMA", "sealed trust keys must be an array")
        keys: list[TrustKeyV4] = []
        for row in value["keys"]:
            if type(row) is not dict or set(row) != {
                "key_id", "issuer", "principal_id", "roles", "scopes",
                "artifact_kinds", "public_key_base64", "production_allowed",
            }:
                _fail("AUDIT_TRUST_SCHEMA", "sealed trust key is not closed")
            try:
                public_key = b64decode(row["public_key_base64"], validate=True)
            except (Base64Error, TypeError, ValueError) as exc:
                raise AuditBundleV4Error(
                    "AUDIT_TRUST_SCHEMA", "sealed public key is not strict base64"
                ) from exc
            keys.append(TrustKeyV4(
                key_id=row["key_id"],
                issuer=row["issuer"],
                principal_id=row["principal_id"],
                roles=tuple(row["roles"]),
                scopes=tuple(row["scopes"]),
                artifact_kinds=tuple(row["artifact_kinds"]),
                public_key=public_key,
                production_allowed=row["production_allowed"],
            ))
        try:
            return cls(
                TrustPolicyV4.from_dict(value["policy"]),
                tuple(keys),
                value["target_environment"],
                tuple(DigestV4.parse(item) for item in value["revoked_subject_digests"]),
                tuple(value["revoked_nonces"]),
            )
        except (ContractV4Error, TypeError, ValueError) as exc:
            raise AuditBundleV4Error(
                "AUDIT_TRUST_SCHEMA", "sealed trust material is invalid"
            ) from exc


@dataclass(frozen=True, slots=True)
class AuditBundleMaterialsV4:
    request: CaseRequestV4
    run_identity: RunIdentityV4
    replay_policy_ref: ContentRefV4
    result: SemanticResultV4
    source_artifacts: tuple[AuditArtifactV4, ...]
    fact_artifacts: tuple[AuditArtifactV4, ...]
    rule_pack_artifacts: tuple[AuditArtifactV4, ...]
    translation_artifacts: tuple[AuditArtifactV4, ...]
    backend_artifacts: tuple[AuditArtifactV4, ...]
    checker_artifacts: tuple[AuditArtifactV4, ...]
    graph_artifacts: tuple[AuditArtifactV4, ...]
    events: tuple[AuditEventV4, ...]

    def __post_init__(self) -> None:
        if (
            type(self.request) is not CaseRequestV4
            or type(self.run_identity) is not RunIdentityV4
            or type(self.replay_policy_ref) is not ContentRefV4
            or type(self.result) is not SemanticResultV4
        ):
            _fail("AUDIT_MATERIALS", "bundle requires exact V4 contracts")
        for field_name in _ARTIFACT_GROUPS.values():
            values = getattr(self, field_name)
            if type(values) is not tuple or any(type(item) is not AuditArtifactV4 for item in values):
                _fail("AUDIT_MATERIALS", f"{field_name} must be an exact artifact tuple")
            if tuple(sorted(values, key=lambda item: item.sort_key)) != values:
                _fail("AUDIT_ARTIFACT_ORDER", f"{field_name} is not canonical")
        if type(self.events) is not tuple or not self.events:
            _fail("AUDIT_EVENTS_REQUIRED", "every run requires at least one audit event")
        if tuple(event.sequence for event in self.events) != tuple(range(len(self.events))):
            _fail("AUDIT_EVENT_ORDER", "event sequence must be contiguous from zero")


@dataclass(frozen=True, slots=True)
class RunCapabilityV4:
    token: str
    run_identity_ref: ContentRefV4

    def __post_init__(self) -> None:
        if type(self.token) is not str or _TOKEN.fullmatch(self.token) is None:
            _fail("AUDIT_CAPABILITY", "run capability token is malformed")
        if type(self.run_identity_ref) is not ContentRefV4 or self.run_identity_ref.kind != "run-identity":
            _fail("AUDIT_CAPABILITY", "run capability must bind a V4 run identity")


@dataclass(frozen=True, slots=True)
class VerifiedAuditBundleV4:
    request: CaseRequestV4
    run_identity: RunIdentityV4
    result: SemanticResultV4
    certificate: CertificateEnvelopeV4
    manifest: AuditManifestV4
    bundle_index: AuditBundleIndexV4
    verification: VerificationResultV4
    checker_receipt_refs: tuple[ContentRefV4, ...]
    files: MappingProxyType


@dataclass(frozen=True, slots=True)
class SealedReplayInputsV4:
    original_run_identity_ref: ContentRefV4
    replay_policy_ref: ContentRefV4
    files: tuple[tuple[str, bytes], ...]

    def read(self, name: str) -> bytes:
        for candidate, raw in self.files:
            if candidate == name:
                return raw
        _fail("REPLAY_MATERIAL_MISSING", "requested sealed replay material is absent")


CertificateFactoryV4 = Callable[[CertificateContextV4], CertificateEnvelopeV4]


@dataclass(frozen=True, slots=True)
class ReplayExecutionV4:
    materials: AuditBundleMaterialsV4
    certificate_factory: CertificateFactoryV4 | None = None


@dataclass(frozen=True, slots=True)
class _DecodedCoreV4:
    request: CaseRequestV4
    run_identity: RunIdentityV4
    replay_policy_ref: ContentRefV4
    result: SemanticResultV4
    resolver: ArtifactResolverV4
    artifacts: tuple[AuditArtifactV4, ...]
    artifact_refs: tuple[ContentRefV4, ...]
    checker_receipt_refs: tuple[ContentRefV4, ...]
    refs: MappingProxyType
    core_digest: DigestV4


class AuditBundleStoreV4:
    """Write, verify, page and replay immutable bundles under V4 storage authority."""

    def __init__(
        self,
        store: V4TransactionStore,
        *,
        trust_material: AuditTrustMaterialV4,
        current_engine_build_digest: DigestV4,
        checker_receipt_issuer: str,
    ) -> None:
        if type(store) is not V4TransactionStore:
            _fail("AUDIT_STORAGE", "store must be V4TransactionStore")
        if type(trust_material) is not AuditTrustMaterialV4:
            _fail("AUDIT_TRUST", "trust_material must be AuditTrustMaterialV4")
        if type(current_engine_build_digest) is not DigestV4:
            _fail("AUDIT_BUILD", "current build must be DigestV4")
        _identifier(checker_receipt_issuer, "checker_receipt_issuer")
        self._store = store
        self._trust_material = trust_material
        self._current_engine_build_digest = current_engine_build_digest
        self._checker_receipt_issuer = checker_receipt_issuer
        self._initialize_layout()

    def _initialize_layout(self) -> None:
        with self._store._lock():
            for name in ("audit-staging", "audit-bundles", "audit-quarantine"):
                path = self._store.root / name
                if not path.exists() and not path.is_symlink():
                    _mkdir(path)
                    if os.name == "nt":
                        _harden_windows(path)
            key_path = self._store.root / "audit.capability-key"
            if not key_path.exists() and not key_path.is_symlink():
                descriptor = _open_exact(key_path, write=True, create=True)
                try:
                    _write_all(descriptor, os.urandom(32))
                    _flush_file(descriptor)
                finally:
                    os.close(descriptor)
                if os.name == "nt":
                    _harden_windows(key_path)
            _flush_directory(self._store.root)
            self._audit_directory_ids = {
                name: _file_id(self._store.root / name)
                for name in ("audit-staging", "audit-bundles", "audit-quarantine")
            }
            self._capability_key_id = _file_id(key_path)
            self._capability_key = self._store._read_path(key_path, expected_digest=None)
            if len(self._capability_key) != 32:
                _fail("AUDIT_CAPABILITY", "capability key has the wrong size")
            self._verify_audit_layout_locked()

    def _verify_audit_layout_locked(self) -> None:
        self._store._verify_layout()
        for name, expected in self._audit_directory_ids.items():
            path = self._store.root / name
            if _file_id(path) != expected:
                _fail("AUDIT_TOCTOU", "audit directory identity changed")
            _verify_security(path)
        key_path = self._store.root / "audit.capability-key"
        if _file_id(key_path) != self._capability_key_id:
            _fail("AUDIT_TOCTOU", "capability key identity changed")
        _verify_security(key_path, file=True)
        if not hmac.compare_digest(
            self._store._read_path(key_path, expected_digest=None), self._capability_key
        ):
            _fail("AUDIT_CAPABILITY", "capability key changed after open")

    def _token_for(self, run_identity_ref: ContentRefV4) -> str:
        body = canonical_bytes({
            "schema_version": CAPABILITY_SCHEMA_V4,
            "run_identity_ref": run_identity_ref.to_dict(),
        })
        return hmac.new(self._capability_key, body, hashlib.sha256).hexdigest()

    @_storage_boundary
    def capability_for(self, run_identity_ref: ContentRefV4) -> RunCapabilityV4:
        if type(run_identity_ref) is not ContentRefV4 or run_identity_ref.kind != "run-identity":
            _fail("AUDIT_CAPABILITY", "capability requires a run-identity reference")
        with self._store._lock():
            self._verify_audit_layout_locked()
            return RunCapabilityV4(self._token_for(run_identity_ref), run_identity_ref)

    def _validate_capability(self, capability: object) -> RunCapabilityV4:
        if type(capability) is not RunCapabilityV4:
            _fail("AUDIT_CAPABILITY", "run reference must be an opaque capability")
        expected = self._token_for(capability.run_identity_ref)
        if not hmac.compare_digest(capability.token, expected):
            _fail("AUDIT_CAPABILITY", "run capability authentication failed")
        return capability

    def _core_files(self, materials: AuditBundleMaterialsV4) -> dict[str, bytes]:
        run_ref = ContentRefV4("run-identity", materials.run_identity.canonical_digest())
        request_ref = ContentRefV4("case-request", materials.request.canonical_digest())
        if (
            materials.run_identity.request_ref != request_ref
            or materials.result.request_ref != request_ref
            or materials.result.run_identity_ref != run_ref
            or materials.replay_policy_ref != self._trust_material.policy.replay_policy_ref
        ):
            _fail("AUDIT_RUN_BINDING", "request, run, result, or replay policy differs")
        files = {
            "input.json": canonical_bytes({
                "schema_version": INPUT_SCHEMA_V4,
                "request": materials.request.to_dict(),
                "run_identity": materials.run_identity.to_dict(),
                "replay_policy_ref": materials.replay_policy_ref.to_dict(),
            }),
            "result.json": materials.result.canonical_bytes(),
        }
        for name, field_name in _ARTIFACT_GROUPS.items():
            payload: dict[str, object] = {
                "schema_version": ARTIFACT_SET_SCHEMA_V4,
                "artifacts": [item.to_wire() for item in getattr(materials, field_name)],
            }
            if name == "rule-pack.json":
                payload["trust_material"] = self._trust_material.to_wire()
            files[name] = canonical_bytes(payload)
        files["events.jsonl"] = b"".join(
            canonical_bytes(event.to_wire(run_ref)) + b"\n" for event in materials.events
        )
        if sum(map(len, files.values())) > MAX_BUNDLE_BYTES_V4:
            _fail("AUDIT_BUNDLE_TOO_LARGE", "bundle core exceeds the fixed byte bound")
        return {name: files[name] for name in CORE_FILES_V4}

    @staticmethod
    def _decode_artifacts(raw: bytes, name: str) -> tuple[AuditArtifactV4, ...]:
        payload = _canonical_object(raw, name)
        expected = {"schema_version", "artifacts"}
        if name == "rule-pack.json":
            expected.add("trust_material")
        if set(payload) != expected or payload.get("schema_version") != ARTIFACT_SET_SCHEMA_V4:
            _fail("AUDIT_FILE_SCHEMA", f"{name} is not a closed V4 artifact set")
        rows = payload["artifacts"]
        if type(rows) is not list:
            _fail("AUDIT_FILE_SCHEMA", f"{name} artifacts must be an array")
        artifacts = tuple(AuditArtifactV4.from_wire(row) for row in rows)
        if tuple(sorted(artifacts, key=lambda item: item.sort_key)) != artifacts:
            _fail("AUDIT_ARTIFACT_ORDER", f"{name} artifact order differs")
        return artifacts

    @staticmethod
    def _decode_events(
        raw: bytes,
        run_ref: ContentRefV4,
        known_refs: frozenset[ContentRefV4],
    ) -> tuple[AuditEventV4, ...]:
        if not raw or not raw.endswith(b"\n"):
            _fail("AUDIT_EVENT_STREAM", "events.jsonl must be non-empty and newline terminated")
        events: list[AuditEventV4] = []
        for line in raw.splitlines():
            payload = _canonical_object(line, "events.jsonl entry")
            if set(payload) != {
                "schema_version", "sequence", "stage", "run_identity_ref", "artifact_ref",
            } or payload.get("schema_version") != EVENT_SCHEMA_V4:
                _fail("AUDIT_EVENT_STREAM", "event entry is not closed")
            try:
                event_run = ContentRefV4.from_dict(payload["run_identity_ref"])
                event_ref = ContentRefV4.from_dict(payload["artifact_ref"])
                event = AuditEventV4(payload["sequence"], payload["stage"], event_ref)
            except (ContractV4Error, TypeError, ValueError) as exc:
                raise AuditBundleV4Error(
                    "AUDIT_EVENT_STREAM", "event reference is invalid"
                ) from exc
            if event_run != run_ref or event.artifact_ref not in known_refs:
                _fail("AUDIT_EVENT_BINDING", "event differs from the sealed run artifacts")
            events.append(event)
        if tuple(event.sequence for event in events) != tuple(range(len(events))):
            _fail("AUDIT_EVENT_ORDER", "event sequence was missing, duplicated, or reordered")
        return tuple(events)

    def _verify_core(self, files: dict[str, bytes], *, now: CanonicalTimeV4) -> _DecodedCoreV4:
        if set(files) != set(CORE_FILES_V4):
            _fail("AUDIT_FILE_SET", "bundle core file set differs")
        if type(now) is not CanonicalTimeV4:
            _fail("AUDIT_TIME", "verification time must be CanonicalTimeV4")
        input_payload = _canonical_object(files["input.json"], "input.json")
        if set(input_payload) != {
            "schema_version", "request", "run_identity", "replay_policy_ref",
        } or input_payload.get("schema_version") != INPUT_SCHEMA_V4:
            _fail("AUDIT_FILE_SCHEMA", "input.json is not the closed V4 input envelope")
        try:
            request = CaseRequestV4.from_dict(input_payload["request"])
            run = RunIdentityV4.from_dict(input_payload["run_identity"])
            replay_policy_ref = ContentRefV4.from_dict(input_payload["replay_policy_ref"])
        except (ContractV4Error, TypeError, ValueError) as exc:
            raise AuditBundleV4Error(
                "AUDIT_INPUT_CONTRACT", "input.json violates a frozen V4 contract"
            ) from exc
        request_ref = ContentRefV4("case-request", request.canonical_digest())
        run_ref = ContentRefV4("run-identity", run.canonical_digest())
        if (
            run.request_ref != request_ref
            or run.engine_build_digest != self._current_engine_build_digest
            or run.trust_policy_ref
            != ContentRefV4("trust-policy", self._trust_material.policy.canonical_digest())
            or replay_policy_ref != self._trust_material.policy.replay_policy_ref
        ):
            _fail("AUDIT_BUILD_BINDING", "run uses a different request, build, or trust policy")

        result_file_ref = _content_ref("result.json", files["result.json"])
        result_body = _canonical_object(files["result.json"], "result.json")
        try:
            result = SemanticResultV4.from_dict(result_body)
        except (ContractV4Error, TypeError, ValueError) as exc:
            raise AuditBundleV4Error(
                "AUDIT_RESULT_CONTRACT", "result.json violates SemanticResultV4"
            ) from exc
        profile = result.runtime_profile
        if (
            result.request_ref != request_ref
            or result.run_identity_ref != run_ref
            or profile.engine_version != run.engine_version
            or profile.engine_build_digest != run.engine_build_digest
            or profile.trust_policy_ref != run.trust_policy_ref
            or profile.storage_capability_ref != run.storage_capability_ref
        ):
            _fail("AUDIT_RESULT_BINDING", "result does not bind the sealed run identity")

        groups = {
            name: self._decode_artifacts(files[name], name) for name in _ARTIFACT_GROUPS
        }
        rule_payload = _canonical_object(files["rule-pack.json"], "rule-pack.json")
        sealed_trust = AuditTrustMaterialV4.from_wire(rule_payload["trust_material"])
        if sealed_trust != self._trust_material:
            _fail("AUDIT_TRUST_BINDING", "sealed trust material differs from current authority")

        resolver = ArtifactResolverV4(max_artifact_bytes=MAX_ARTIFACT_BYTES_V4)
        auto_records = (
            AuditArtifactV4(
                f"case-request-{request_ref.digest.hex}", request_ref, "case-request",
                "application/json", "request", request.canonical_bytes(),
            ),
            AuditArtifactV4(
                f"run-identity-{run_ref.digest.hex}", run_ref, "run-identity",
                "application/json", "run", canonical_bytes(run.digest_body()),
            ),
        )
        all_artifacts = tuple(
            item for name in _ARTIFACT_GROUPS for item in groups[name]
        )
        combined = (*auto_records, *all_artifacts)
        if len({item.artifact_id for item in combined}) != len(combined):
            _fail("AUDIT_ARTIFACT_COLLISION", "artifact_id is not unique across the bundle")
        if len({item.content_ref for item in combined}) != len(combined):
            _fail("AUDIT_ARTIFACT_COLLISION", "content_ref repeats across the bundle")
        for item in combined:
            resolver.register_bytes(
                artifact_id=item.artifact_id,
                content_ref=item.content_ref,
                artifact_kind=item.artifact_kind,
                media_type=item.media_type,
                scope=item.scope,
                content=item.content,
            )
        artifact_refs = tuple(sorted(
            (item.content_ref for item in all_artifacts),
            key=lambda ref: (ref.kind, ref.digest.hex),
        ))
        checker_refs = tuple(
            item.content_ref
            for item in groups["checker-receipts.json"]
            if item.artifact_kind == CHECKER_RECEIPT_KIND
            and item.scope == CHECKER_SCOPE
        )
        checker = IndependentCheckerV4(
            resolver,
            self._trust_material.verifier(),
            receipt_issuer=self._checker_receipt_issuer,
            receipt_signer=lambda *_args: _fail(
                "AUDIT_SIGNING_FORBIDDEN", "verification has no signing authority"
            ),
        )
        try:
            for reference in checker_refs:
                checker.verify_receipt(reference, now=now)
        except (ContractV4Error, IndependentCheckerV4Error) as exc:
            raise AuditBundleV4Error(
                "AUDIT_RECEIPT_DAG", f"independent receipt verification failed: {exc.code}"
            ) from exc
        if result.runtime_profile.formal_kernel and not checker_refs:
            _fail("AUDIT_CHECKER_REQUIRED", "formal-kernel result has no verified checker receipt")

        result_ref = ContentRefV4("semantic-result", result.canonical_digest())
        known_refs = frozenset((
            request_ref, run_ref, result_ref, result_file_ref, *artifact_refs,
        ))
        self._decode_events(files["events.jsonl"], run_ref, known_refs)
        refs = MappingProxyType({name: _content_ref(name, files[name]) for name in CORE_FILES_V4})
        core_digest = digest_value({
            "schema_version": BUNDLE_SCHEMA_V4,
            "files": [
                {"name": name, "content_ref": refs[name].to_dict()}
                for name in CORE_FILES_V4
            ],
        })
        return _DecodedCoreV4(
            request, run, replay_policy_ref, result, resolver,
            tuple(sorted(all_artifacts, key=lambda item: item.sort_key)), artifact_refs,
            checker_refs, refs, core_digest,
        )

    @staticmethod
    def _certificate_context(
        core: _DecodedCoreV4,
        *,
        now: CanonicalTimeV4,
    ) -> CertificateContextV4:
        return _verified_certificate_context(
            request=core.request,
            run_identity=core.run_identity,
            result=core.result,
            bundle_core_digest=core.core_digest,
            artifacts=tuple(
                CertificateArtifactV4(
                    item.content_ref,
                    item.artifact_kind,
                    item.media_type,
                    item.scope,
                    item.content,
                )
                for item in core.artifacts
            ),
            verified_checker_receipt_refs=core.checker_receipt_refs,
            now=now,
        )

    def _certificate_bytes(
        self,
        core: _DecodedCoreV4,
        certificate: CertificateEnvelopeV4,
        *,
        now: CanonicalTimeV4,
    ) -> bytes:
        if type(certificate) is not CertificateEnvelopeV4:
            _fail("AUDIT_CERTIFICATE", "certificate factory returned the wrong type")
        context = self._certificate_context(core, now=now)
        try:
            CertificateVerifierV4(
                self._trust_material.verifier(),
                current_engine_build_digest=self._current_engine_build_digest,
            ).verify(context, certificate)
        except CertificateV4Error as exc:
            raise AuditBundleV4Error(
                "AUDIT_CERTIFICATE_VERIFY", f"certificate verification failed: {exc.code}"
            ) from exc
        if certificate.kind is not core.result.certificate_kind:
            _fail("AUDIT_CERTIFICATE_KIND", "certificate kind differs from result state")
        selected = certificate.formal or certificate.conflict
        if selected is None:
            if certificate.kind is not CertificateKindV4.NONE:
                _fail("AUDIT_CERTIFICATE", "issued certificate body is missing")
        else:
            if (
                selected.request_ref != context.request_ref
                or selected.result_ref != context.result_ref
                or selected.run_identity_ref != context.run_identity_ref
                or selected.bundle_core_digest != context.bundle_core_digest
                or certificate.service_signature is None
            ):
                _fail("AUDIT_CERTIFICATE_BINDING", "certificate differs from the verified bundle core")
            certificate_refs = tuple(
                reference
                for field_name in (
                    "source_receipt_refs", "evidence_receipt_refs",
                    "fact_admission_receipt_refs", "rule_promotion_receipt_refs",
                    "translation_receipt_refs", "solver_receipt_refs",
                    "proof_receipt_refs", "checker_receipt_refs",
                )
                for reference in getattr(selected, field_name)
            )
            known = frozenset(core.artifact_refs)
            if any(reference not in known for reference in certificate_refs):
                _fail("AUDIT_CERTIFICATE_DAG", "certificate references an unsealed receipt")
            if any(
                reference not in core.checker_receipt_refs
                for reference in selected.checker_receipt_refs
            ):
                _fail("AUDIT_CERTIFICATE_DAG", "certificate checker receipt was not recomputed")
            signature = certificate.service_signature
            unsigned = certificate.to_dict()
            del unsigned["service_signature"]
            if not frozenset(certificate_refs) <= frozenset(signature.evidence_refs):
                _fail("AUDIT_CERTIFICATE_EVIDENCE", "certificate signature omits receipt evidence")
            try:
                self._trust_material.verifier().verify(
                    signature,
                    expected_subject_digest=selected.certificate_digest,
                    expected_payload_digest=digest_value(unsigned),
                    required_role="service_signer",
                    required_scope="service-certificate",
                    required_artifact_kind="service-certificate",
                    expected_status="APPROVED",
                    now=now,
                    separation_from_principals=(),
                )
            except ContractV4Error as exc:
                raise AuditBundleV4Error(
                    "AUDIT_CERTIFICATE_SIGNATURE", f"certificate signature failed: {exc.code}"
                ) from exc
        return canonical_bytes({
            "schema_version": CERTIFICATE_BINDING_SCHEMA_V4,
            "run_identity_ref": context.run_identity_ref.to_dict(),
            "bundle_core_digest": str(context.bundle_core_digest),
            "certificate": certificate.to_dict(),
        })

    def _decode_certificate(
        self,
        raw: bytes,
        core: _DecodedCoreV4,
        *,
        now: CanonicalTimeV4,
    ) -> CertificateEnvelopeV4:
        payload = _canonical_object(raw, "certificate.json")
        if set(payload) != {
            "schema_version", "run_identity_ref", "bundle_core_digest", "certificate",
        } or payload.get("schema_version") != CERTIFICATE_BINDING_SCHEMA_V4:
            _fail("AUDIT_CERTIFICATE_SCHEMA", "certificate.json is not closed")
        try:
            run_ref = ContentRefV4.from_dict(payload["run_identity_ref"])
            core_digest = DigestV4.parse(payload["bundle_core_digest"])
            certificate = CertificateEnvelopeV4.from_dict(payload["certificate"])
        except (ContractV4Error, TypeError, ValueError) as exc:
            raise AuditBundleV4Error(
                "AUDIT_CERTIFICATE_SCHEMA", "certificate.json violates a V4 contract"
            ) from exc
        context = self._certificate_context(core, now=now)
        if run_ref != context.run_identity_ref or core_digest != context.bundle_core_digest:
            _fail("AUDIT_CERTIFICATE_BINDING", "certificate wrapper differs from bundle core")
        if self._certificate_bytes(core, certificate, now=now) != raw:
            _fail("AUDIT_CERTIFICATE_BINDING", "certificate wrapper bytes differ")
        return certificate

    @staticmethod
    def _manifest(core: _DecodedCoreV4, certificate_raw: bytes) -> AuditManifestV4:
        certificate_ref = _content_ref("certificate.json", certificate_raw)
        body = {
            "run_identity_ref": ContentRefV4(
                "run-identity", core.run_identity.canonical_digest()
            ).to_dict(),
            "request_ref": ContentRefV4(
                "case-request", core.request.canonical_digest()
            ).to_dict(),
            "input_ref": core.refs["input.json"].to_dict(),
            "source_index_ref": core.refs["source-index.json"].to_dict(),
            "fact_admission_ref": core.refs["fact-admission.json"].to_dict(),
            "rule_pack_ref": core.refs["rule-pack.json"].to_dict(),
            "translation_receipts_ref": core.refs["translation-receipts.json"].to_dict(),
            "backend_receipts_ref": core.refs["backend-receipts.json"].to_dict(),
            "checker_receipts_ref": core.refs["checker-receipts.json"].to_dict(),
            "events_ref": core.refs["events.jsonl"].to_dict(),
            "graph_ref": core.refs["graph.json"].to_dict(),
            "result_ref": core.refs["result.json"].to_dict(),
            "certificate_ref": certificate_ref.to_dict(),
            "bundle_core_digest": str(core.core_digest),
        }
        return AuditManifestV4.from_dict({
            **body, "manifest_digest": str(digest_value(body)),
        })

    @staticmethod
    def _checksums(files: dict[str, bytes]) -> bytes:
        return b"".join(
            f"{DigestV4.from_bytes(files[name]).hex}  {name}\n".encode("ascii")
            for name in DATA_FILES_V4
        )

    @staticmethod
    def _complete(
        refs: dict[str, ContentRefV4],
        manifest_ref: ContentRefV4,
        checksums_ref: ContentRefV4,
        run_ref: ContentRefV4,
    ) -> bytes:
        projection = digest_value({
            "schema_version": BUNDLE_SCHEMA_V4,
            "files": [
                {"name": name, "content_ref": refs[name].to_dict()}
                for name in DATA_FILES_V4
            ],
            "checksums_ref": checksums_ref.to_dict(),
        })
        return canonical_bytes({
            "schema_version": COMPLETE_SCHEMA_V4,
            "run_identity_ref": run_ref.to_dict(),
            "manifest_ref": manifest_ref.to_dict(),
            "checksums_ref": checksums_ref.to_dict(),
            "bundle_projection_digest": str(projection),
        })

    @staticmethod
    def _bundle_index(files: dict[str, bytes]) -> AuditBundleIndexV4:
        refs = {name: _content_ref(name, raw) for name, raw in files.items()}
        body = {
            "manifest_ref": refs["manifest.json"].to_dict(),
            "checksums_ref": refs["checksums.sha256"].to_dict(),
            "complete_marker_ref": refs["COMPLETE"].to_dict(),
            "entries": [refs[name].to_dict() for name in (*DATA_FILES_V4, "checksums.sha256")],
        }
        return AuditBundleIndexV4.from_dict({
            **body, "bundle_digest": str(digest_value(body)),
        })

    def _decode_files(
        self,
        files: dict[str, bytes],
        *,
        now: CanonicalTimeV4,
        require_complete: bool,
    ) -> VerifiedAuditBundleV4:
        expected = set(DATA_FILES_V4) | {"checksums.sha256"}
        if require_complete:
            expected.add("COMPLETE")
        if set(files) != expected:
            _fail("AUDIT_FILE_SET", "bundle has a missing or extra file")
        core = self._verify_core(
            {name: files[name] for name in CORE_FILES_V4}, now=now
        )
        certificate = self._decode_certificate(files["certificate.json"], core, now=now)
        expected_manifest = self._manifest(core, files["certificate.json"])
        manifest_ref = _content_ref("manifest.json", files["manifest.json"])
        manifest_body = _canonical_object(files["manifest.json"], "manifest.json")
        if "manifest_digest" in manifest_body:
            _fail("AUDIT_MANIFEST_DIGEST", "manifest stores a recursive digest field")
        try:
            manifest = AuditManifestV4.from_dict({
                **manifest_body, "manifest_digest": str(manifest_ref.digest),
            })
        except (ContractV4Error, TypeError, ValueError) as exc:
            raise AuditBundleV4Error(
                "AUDIT_MANIFEST_CONTRACT", "manifest violates AuditManifestV4"
            ) from exc
        if manifest != expected_manifest or files["manifest.json"] != canonical_bytes(
            expected_manifest.digest_body()
        ):
            _fail("AUDIT_MANIFEST_MISMATCH", "manifest differs from all sealed files")
        if files["checksums.sha256"] != self._checksums(files):
            _fail("AUDIT_CHECKSUM_MISMATCH", "checksums are missing, reordered, or stale")
        checksums_ref = _content_ref("checksums.sha256", files["checksums.sha256"])
        run_ref = ContentRefV4("run-identity", core.run_identity.canonical_digest())
        refs = {name: _content_ref(name, files[name]) for name in DATA_FILES_V4}
        if require_complete:
            expected_complete = self._complete(
                refs, manifest_ref, checksums_ref, run_ref,
            )
            if files["COMPLETE"] != expected_complete:
                _fail("AUDIT_COMPLETE_MISMATCH", "COMPLETE does not bind the verified bundle")
        else:
            files = {**files, "COMPLETE": self._complete(
                refs, manifest_ref, checksums_ref, run_ref,
            )}
        index = self._bundle_index(files)
        bundle_ref = ContentRefV4("audit-bundle-index", index.bundle_digest)
        verification = VerificationResultV4(
            run_identity_ref=run_ref,
            status="VERIFIED",
            certificate_ref=manifest.certificate_ref,
            audit_manifest_ref=manifest_ref,
            audit_bundle_ref=bundle_ref,
            verified_artifact_refs=tuple(
                _content_ref(name, files[name])
                for name in (*DATA_FILES_V4, "checksums.sha256", "COMPLETE")
            ),
            failed_artifact_refs=(),
            checker_receipt_refs=core.checker_receipt_refs,
            verification_receipt_refs=(),
            error_codes=(),
        )
        return VerifiedAuditBundleV4(
            core.request,
            core.run_identity,
            core.result,
            certificate,
            manifest,
            index,
            verification,
            core.checker_receipt_refs,
            MappingProxyType(dict(files)),
        )

    def _write_file(self, directory: Path, name: str, raw: bytes) -> None:
        descriptor = _open_exact(directory / name, write=True, create=True)
        try:
            _write_all(descriptor, raw)
            _flush_file(descriptor)
        finally:
            os.close(descriptor)
        if os.name == "nt":
            _harden_windows(directory / name)
        _verify_security(directory / name, file=True)

    @staticmethod
    def _move_directory(source: Path, target: Path) -> None:
        if target.exists() or target.is_symlink():
            _fail("RUN_ID_COLLISION", "audit run target already exists")
        try:
            if os.name == "nt":
                import ctypes

                move = ctypes.windll.kernel32.MoveFileExW
                if not move(str(source), str(target), 0x8):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                source.rename(target)
        except OSError as exc:
            raise AuditBundleV4Error(
                "AUDIT_IO", "atomic audit directory publication failed"
            ) from exc

    def _recover_staging_locked(self) -> int:
        staging = self._store.root / "audit-staging"
        quarantine = self._store.root / "audit-quarantine"
        recovered = 0
        for path in sorted(staging.iterdir(), key=lambda item: item.name):
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                _fail("AUDIT_LAYOUT", "audit staging contains a non-directory entry")
            _verify_security(path)
            target = quarantine / f"{path.name}.{uuid.uuid4().hex}.orphan"
            self._move_directory(path, target)
            recovered += 1
        if recovered:
            _flush_directory(staging)
            _flush_directory(quarantine)
        return recovered

    @_storage_boundary
    def recover(self) -> int:
        with self._store._lock():
            self._verify_audit_layout_locked()
            return self._recover_staging_locked()

    def _directory_bytes(
        self,
        directory: Path,
        *,
        require_complete: bool,
    ) -> dict[str, bytes]:
        _verify_security(directory)
        before = _file_id(directory)
        expected = set(DATA_FILES_V4) | {"checksums.sha256"}
        if require_complete:
            expected.add("COMPLETE")
        children = {path.name for path in directory.iterdir()}
        if children != expected:
            _fail("AUDIT_FILE_SET", "bundle directory has a missing or extra file")
        files = {
            name: self._store._read_path(directory / name, expected_digest=None)
            for name in expected
        }
        if _file_id(directory) != before:
            _fail("AUDIT_TOCTOU", "bundle directory identity changed during read")
        return files

    def _read_locked(
        self,
        capability: RunCapabilityV4,
        *,
        now: CanonicalTimeV4,
    ) -> VerifiedAuditBundleV4:
        self._verify_audit_layout_locked()
        target = self._store.root / "audit-bundles" / capability.token
        if not target.is_dir():
            _fail("AUDIT_NOT_FOUND", "run capability has no completed bundle")
        verified = self._decode_files(
            self._directory_bytes(target, require_complete=True),
            now=now,
            require_complete=True,
        )
        if verified.verification.run_identity_ref != capability.run_identity_ref:
            _fail("AUDIT_CAPABILITY_BINDING", "bundle belongs to another run capability")
        return verified

    @_storage_boundary
    def verify_run(
        self,
        capability: RunCapabilityV4,
        *,
        now: CanonicalTimeV4,
    ) -> VerifiedAuditBundleV4:
        capability = self._validate_capability(capability)
        with self._store._lock():
            return self._read_locked(capability, now=now)

    def _audit_usage_locked(self) -> int:
        total = 0
        for root_name in ("audit-staging", "audit-bundles", "audit-quarantine"):
            pending = [self._store.root / root_name]
            while pending:
                directory = pending.pop()
                _verify_security(directory)
                for path in directory.iterdir():
                    info = path.lstat()
                    if stat.S_ISLNK(info.st_mode):
                        _fail("AUDIT_REPARSE", "reparse points are forbidden in audit state")
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(path)
                    elif stat.S_ISREG(info.st_mode):
                        _verify_security(path, file=True)
                        total += info.st_size
                    else:
                        _fail("AUDIT_LAYOUT", "audit state contains an unsupported node")
        return total

    @_storage_boundary
    def write_run(
        self,
        capability: RunCapabilityV4,
        materials: AuditBundleMaterialsV4,
        *,
        now: CanonicalTimeV4,
        certificate_factory: CertificateFactoryV4 | None = None,
    ) -> VerifiedAuditBundleV4:
        capability = self._validate_capability(capability)
        if type(materials) is not AuditBundleMaterialsV4:
            _fail("AUDIT_MATERIALS", "write_run requires AuditBundleMaterialsV4")
        core_files = self._core_files(materials)
        core = self._verify_core(core_files, now=now)
        if (
            ContentRefV4("run-identity", core.run_identity.canonical_digest())
            != capability.run_identity_ref
        ):
            _fail("AUDIT_CAPABILITY_BINDING", "capability and materials bind different runs")

        with self._store._lock():
            self._verify_audit_layout_locked()
            self._recover_staging_locked()
            target = self._store.root / "audit-bundles" / capability.token
            if target.exists() or target.is_symlink():
                existing = self._read_locked(capability, now=now)
                if any(existing.files[name] != core_files[name] for name in CORE_FILES_V4):
                    _fail("RUN_ID_COLLISION", "existing COMPLETE bundle has different core bytes")
                return existing

            if core.result.certificate_kind is CertificateKindV4.NONE:
                if certificate_factory is not None:
                    _fail("AUDIT_CERTIFICATE_AUTHORITY", "none result cannot invoke an issuer")
                certificate = CertificateEnvelopeV4(
                    CertificateKindV4.NONE, None, None, None
                )
            else:
                if not callable(certificate_factory):
                    _fail("AUDIT_CERTIFICATE_AUTHORITY", "issued result requires a certificate issuer")
                certificate = certificate_factory(self._certificate_context(core, now=now))
            certificate_raw = self._certificate_bytes(core, certificate, now=now)
            manifest = self._manifest(core, certificate_raw)
            files = {
                **core_files,
                "certificate.json": certificate_raw,
                "manifest.json": canonical_bytes(manifest.digest_body()),
            }
            files["checksums.sha256"] = self._checksums(files)
            refs = {name: _content_ref(name, files[name]) for name in DATA_FILES_V4}
            run_ref = ContentRefV4("run-identity", core.run_identity.canonical_digest())
            files["COMPLETE"] = self._complete(
                refs,
                refs["manifest.json"],
                _content_ref("checksums.sha256", files["checksums.sha256"]),
                run_ref,
            )
            total = sum(map(len, files.values()))
            if total > MAX_BUNDLE_BYTES_V4:
                _fail("AUDIT_BUNDLE_TOO_LARGE", "completed bundle exceeds the fixed bound")
            if self._store._usage() + self._audit_usage_locked() + total > self._store.quota_bytes:
                _fail("AUDIT_QUOTA", "V4 state quota would be exceeded")

            stage = self._store.root / "audit-staging" / (
                f"{capability.token}.{os.getpid()}.{uuid.uuid4().hex}"
            )
            _mkdir(stage)
            if os.name == "nt":
                _harden_windows(stage)
            for name in (*DATA_FILES_V4, "checksums.sha256"):
                self._write_file(stage, name, files[name])
            _flush_directory(stage)
            self._decode_files(
                self._directory_bytes(stage, require_complete=False),
                now=now,
                require_complete=False,
            )
            self._write_file(stage, "COMPLETE", files["COMPLETE"])
            _flush_directory(stage)
            self._decode_files(
                self._directory_bytes(stage, require_complete=True),
                now=now,
                require_complete=True,
            )
            self._move_directory(stage, target)
            _flush_directory(self._store.root / "audit-staging")
            _flush_directory(self._store.root / "audit-bundles")
            return self._read_locked(capability, now=now)

    @_storage_boundary
    def issue_artifact_handle(
        self,
        capability: RunCapabilityV4,
        name: str,
        *,
        now: CanonicalTimeV4,
        expires_at: CanonicalTimeV4,
        max_bytes: int,
        signer: Callable[
            [DigestV4, DigestV4, tuple[ContentRefV4, ...], ContentRefV4, CanonicalTimeV4],
            SignatureEnvelopeV4,
        ],
    ) -> ArtifactHandleV4:
        capability = self._validate_capability(capability)
        if name not in BUNDLE_FILES_V4:
            _fail("AUDIT_ARTIFACT_NAME", "artifact name is outside the fixed bundle set")
        if type(expires_at) is not CanonicalTimeV4 or not now < expires_at:
            _fail("AUDIT_HANDLE_EXPIRY", "artifact handle expiry must be in the future")
        verified = self.verify_run(capability, now=now)
        raw = verified.files[name]
        if type(max_bytes) is not int or max_bytes <= 0 or max_bytes > len(raw):
            _fail("AUDIT_HANDLE_BOUNDS", "artifact handle max_bytes is outside the file")
        reference = _content_ref(name, raw)
        body = {
            "artifact_id": f"audit-{name.lower().replace('.', '-')}-{reference.digest.hex[:24]}",
            "kind": reference.kind,
            "content_ref": reference.to_dict(),
            "run_identity_ref": capability.run_identity_ref.to_dict(),
            "scope": AUDIT_SCOPE_V4,
            "media_type": _MEDIA_TYPES[name],
            "size_bytes": len(raw),
            "expires_at": expires_at.to_dict(),
            "max_bytes": max_bytes,
        }
        signature = signer(
            reference.digest,
            digest_value(body),
            (capability.run_identity_ref,),
            capability.run_identity_ref,
            now,
        )
        if type(signature) is not SignatureEnvelopeV4:
            _fail("AUDIT_HANDLE_SIGNATURE", "handle signer returned the wrong type")
        try:
            handle = ArtifactHandleV4.from_dict({**body, "signature": signature.to_dict()})
        except (ContractV4Error, TypeError, ValueError) as exc:
            raise AuditBundleV4Error(
                "AUDIT_HANDLE_SIGNATURE", "handle signature does not bind its body"
            ) from exc
        if (
            signature.run_identity_ref != capability.run_identity_ref
            or signature.evidence_refs != (capability.run_identity_ref,)
            or signature.expires_at is None
            or signature.expires_at < expires_at
        ):
            _fail("AUDIT_HANDLE_SIGNATURE", "handle signature context differs")
        return handle

    @_storage_boundary
    def read_artifact(
        self,
        handle: ArtifactHandleV4,
        *,
        offset: int,
        length: int,
        now: CanonicalTimeV4,
    ) -> MCPReadArtifactOutputV4:
        if type(handle) is not ArtifactHandleV4:
            _fail("AUDIT_HANDLE", "read requires ArtifactHandleV4")
        capability = self.capability_for(handle.run_identity_ref)
        if not now < handle.expires_at:
            _fail("AUDIT_HANDLE_EXPIRED", "artifact handle has expired")
        if (
            type(offset) is not int
            or type(length) is not int
            or offset < 0
            or length <= 0
            or offset + length > handle.max_bytes
            or offset + length > handle.size_bytes
        ):
            _fail("AUDIT_HANDLE_RANGE", "artifact page exceeds the signed bound")
        if handle.signature.evidence_refs != (handle.run_identity_ref,):
            _fail("AUDIT_HANDLE_SIGNATURE", "handle signature omits its run evidence")
        try:
            self._trust_material.verifier().verify(
                handle.signature,
                expected_subject_digest=handle.content_ref.digest,
                expected_payload_digest=digest_value(handle.signature_body()),
                required_role="service_signer",
                required_scope="service-certificate",
                required_artifact_kind="service-certificate",
                expected_status="APPROVED",
                now=now,
                separation_from_principals=(),
            )
        except ContractV4Error as exc:
            raise AuditBundleV4Error(
                "AUDIT_HANDLE_SIGNATURE", f"handle signature failed: {exc.code}"
            ) from exc
        verified = self.verify_run(capability, now=now)
        matches = [
            (name, raw)
            for name, raw in verified.files.items()
            if _content_ref(name, raw) == handle.content_ref
            and _CONTENT_KINDS[name] == handle.kind
            and _MEDIA_TYPES[name] == handle.media_type
        ]
        if len(matches) != 1:
            _fail("AUDIT_HANDLE_BINDING", "handle does not identify one sealed bundle file")
        _, raw = matches[0]
        if len(raw) != handle.size_bytes or handle.scope != AUDIT_SCOPE_V4:
            _fail("AUDIT_HANDLE_BINDING", "handle metadata differs from the sealed file")
        chunk = raw[offset:offset + length]
        end = offset + len(chunk)
        bound = min(handle.size_bytes, handle.max_bytes)
        eof = end == bound
        return MCPReadArtifactOutputV4(
            artifact_handle=handle,
            offset=offset,
            length=len(chunk),
            next_offset=None if eof else end,
            content_base64=b64encode(chunk).decode("ascii"),
            chunk_digest=DigestV4.from_bytes(chunk),
            artifact_digest=handle.content_ref.digest,
            content_type=handle.media_type,
            eof=eof,
        )

    @_storage_boundary
    def replay_run(
        self,
        capability: RunCapabilityV4,
        *,
        now: CanonicalTimeV4,
        executor: Callable[[SealedReplayInputsV4], ReplayExecutionV4],
    ) -> ReplayResultV4:
        capability = self._validate_capability(capability)
        original = self.verify_run(capability, now=now)
        original_snapshot = tuple(
            (name, original.files[name]) for name in BUNDLE_FILES_V4
        )
        sealed = SealedReplayInputsV4(
            capability.run_identity_ref,
            self._trust_material.policy.replay_policy_ref,
            tuple((name, original.files[name]) for name in REPLAY_INPUT_FILES_V4),
        )
        execution = executor(sealed)
        if type(execution) is not ReplayExecutionV4:
            _fail("REPLAY_EXECUTOR", "offline executor returned the wrong type")
        if execution.materials.request.canonical_bytes() != original.request.canonical_bytes():
            _fail("REPLAY_REQUEST_MISMATCH", "replay changed the sealed request")
        replay_ref = ContentRefV4(
            "run-identity", execution.materials.run_identity.canonical_digest()
        )
        if replay_ref == capability.run_identity_ref:
            _fail("REPLAY_RUN_COLLISION", "replay must use a distinct run identity")
        replay_capability = self.capability_for(replay_ref)
        replayed = self.write_run(
            replay_capability,
            execution.materials,
            now=now,
            certificate_factory=execution.certificate_factory,
        )
        unchanged = self.verify_run(capability, now=now)
        if tuple((name, unchanged.files[name]) for name in BUNDLE_FILES_V4) != original_snapshot:
            _fail("REPLAY_ORIGINAL_MUTATED", "offline replay modified the original run")
        original_wire = original.result.to_dict()
        replay_wire = replayed.result.to_dict()
        exact_equal = original.result.canonical_bytes() == replayed.result.canonical_bytes()
        semantic_original = _replay_semantic_projection(original.result)
        semantic_replay = _replay_semantic_projection(replayed.result)
        semantic_equal = semantic_original == semantic_replay
        differing_paths = tuple(_differing_paths(original_wire, replay_wire))
        return ReplayResultV4(
            run_identity_ref=capability.run_identity_ref,
            replay_run_identity_ref=replay_ref,
            status="MATCH" if semantic_equal else "MISMATCH",
            replay_policy_ref=self._trust_material.policy.replay_policy_ref,
            original_result_ref=ContentRefV4("semantic-result", original.result.canonical_digest()),
            replay_result_ref=ContentRefV4("semantic-result", replayed.result.canonical_digest()),
            original_bundle_ref=ContentRefV4(
                "audit-bundle-index", original.bundle_index.bundle_digest
            ),
            replay_bundle_ref=ContentRefV4(
                "audit-bundle-index", replayed.bundle_index.bundle_digest
            ),
            exact_equal=exact_equal,
            semantic_equal=semantic_equal,
            differing_paths=differing_paths,
        )


def _replay_semantic_projection(result: SemanticResultV4) -> dict[str, object]:
    """Keep legal outcomes and stable inputs while erasing run-issued artifact identities."""

    body = result.digest_body()
    body.pop("run_identity_ref")

    def kinds(references: object) -> list[str]:
        return [reference["kind"] for reference in references]

    runtime = body["runtime_profile"]
    if runtime["backend_invocation_ref"] is not None:
        runtime["backend_invocation_ref"] = runtime["backend_invocation_ref"]["kind"]
    for field in (
        "admitted_fact_refs",
        "rejected_fact_refs",
        "argument_refs",
        "attack_refs",
        "exception_resolution_refs",
        "permission_resolution_refs",
        "priority_resolution_refs",
        "temporal_result_refs",
        "numeric_result_refs",
    ):
        body[field] = kinds(body[field])
    for claim in body["claims"]:
        claim["argument_refs"] = kinds(claim["argument_refs"])
        claim["fact_refs"] = kinds(claim["fact_refs"])
    for branch in body["branches"]:
        branch["assumption_refs"] = kinds(branch["assumption_refs"])
    review = body["review_state"]
    review["unresolved_item_refs"] = kinds(review["unresolved_item_refs"])
    review["release_condition_refs"] = kinds(review["release_condition_refs"])
    if review["review_receipt_ref"] is not None:
        review["review_receipt_ref"] = review["review_receipt_ref"]["kind"]
    return body


def _differing_paths(left: object, right: object, path: str = "$") -> list[str]:
    if type(left) is not type(right):
        return [path]
    if type(left) is dict:
        paths: list[str] = []
        keys = sorted(set(left) | set(right))
        for key in keys:
            if key not in left or key not in right:
                paths.append(f"{path}.{key}")
            else:
                paths.extend(_differing_paths(left[key], right[key], f"{path}.{key}"))
        return paths
    if type(left) is list:
        paths = []
        if len(left) != len(right):
            paths.append(f"{path}.length")
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=False)):
            paths.extend(_differing_paths(left_item, right_item, f"{path}[{index}]"))
        return paths
    return [] if left == right else [path]


__all__ = [
    "AUDIT_SCOPE_V4",
    "BUNDLE_FILES_V4",
    "AuditArtifactV4",
    "AuditBundleMaterialsV4",
    "AuditBundleStoreV4",
    "AuditBundleV4Error",
    "AuditEventV4",
    "AuditTrustMaterialV4",
    "ReplayExecutionV4",
    "RunCapabilityV4",
    "SealedReplayInputsV4",
    "VerifiedAuditBundleV4",
]
