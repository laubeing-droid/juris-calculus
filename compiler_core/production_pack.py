"""Strict local-production pack, trust, and service-key loader."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import DigestV4, canonical_bytes, parse_json_document
from compiler_core.contracts import CanonicalTimeV4, ContentRefV4, ContractV4Error, TrustPolicyV4
from compiler_core.rule_packs import RulePackVerifierV4, VerifiedRulePackV4
from compiler_core.source_service import SourceServiceV4
from compiler_core.trust import TrustKeyV4, TrustVerifierV4


PACK_FIELDS = {
    "schema_version", "scope", "production_allowed", "signing_mode",
    "independent_human_review", "observation_required", "pack_ref",
    "formal_rule_ids", "artifacts",
}
TRUST_FIELDS = {
    "schema_version", "scope", "production_allowed", "signing_mode",
    "independent_human_review", "verification_time", "runtime_identity",
    "trust_policy", "trust_keys",
}
ARTIFACT_FIELDS = {
    "artifact_id", "content_ref", "artifact_kind", "media_type", "scope",
    "content_base64",
}
KEY_FIELDS = {
    "key_id", "issuer", "principal_id", "roles", "scopes", "artifact_kinds",
    "public_key_base64", "production_allowed",
}
IDENTITY_FIELDS = {
    "engine_api", "compiler_build_digest", "source_tree_digest", "schema_digest",
}
SERVICE_KEY_FIELDS = {
    "schema_version", "key_id", "issuer", "principal_id", "private_seed_base64",
    "public_key_base64",
}


def _fail(code: str, detail: str) -> None:
    raise ContractV4Error(code, detail)


def _object(value: object, fields: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        _fail("PRODUCTION_DOCUMENT_SCHEMA", f"{label} fields are not exact")
    return value


def _read_canonical(path: Path, fields: set[str], label: str) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        value = _object(parse_json_document(raw), fields, label)
    except OSError as exc:
        raise ContractV4Error("PRODUCTION_FILE_READ", f"cannot read {label}") from exc
    if raw != canonical_bytes(value):
        _fail("PRODUCTION_NONCANONICAL_JSON", f"{label} is not canonical JSON")
    return value


def current_utc_time() -> CanonicalTimeV4:
    return CanonicalTimeV4(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


@dataclass(frozen=True, slots=True)
class ProductionIdentityPinsV4:
    engine_api: str
    compiler_build_digest: DigestV4
    source_tree_digest: DigestV4
    schema_digest: DigestV4

    @classmethod
    def from_dict(cls, value: object) -> "ProductionIdentityPinsV4":
        row = _object(value, IDENTITY_FIELDS, "runtime_identity")
        if type(row["engine_api"]) is not str:
            _fail("PRODUCTION_IDENTITY", "engine_api must be a string")
        return cls(
            row["engine_api"], DigestV4(row["compiler_build_digest"]),
            DigestV4(row["source_tree_digest"]), DigestV4(row["schema_digest"]),
        )


@dataclass(frozen=True, slots=True)
class ProductionServiceKeyV4:
    key_id: str
    issuer: str
    principal_id: str
    private_key: Ed25519PrivateKey
    public_key: bytes


@dataclass(frozen=True, slots=True)
class LoadedProductionPackV4:
    resolver: ArtifactResolverV4
    policy: TrustPolicyV4
    keys: tuple[TrustKeyV4, ...]
    trust: TrustVerifierV4
    source_service: SourceServiceV4
    pack_verifier: RulePackVerifierV4
    verified_pack: VerifiedRulePackV4
    pack_ref: ContentRefV4
    identity: ProductionIdentityPinsV4
    service_key: ProductionServiceKeyV4
    formal_rule_ids: tuple[str, ...]
    verified_at: CanonicalTimeV4


def _trust_keys(value: object) -> tuple[TrustKeyV4, ...]:
    if type(value) is not list or not value:
        _fail("PRODUCTION_TRUST_KEYS", "trust_keys must be a non-empty array")
    keys = []
    for item in value:
        row = _object(item, KEY_FIELDS, "trust_key")
        try:
            public_key = b64decode(row["public_key_base64"], validate=True)
        except (Base64Error, TypeError, ValueError) as exc:
            raise ContractV4Error("PRODUCTION_KEY_ENCODING", "trust key is not strict base64") from exc
        keys.append(TrustKeyV4(
            key_id=row["key_id"], issuer=row["issuer"], principal_id=row["principal_id"],
            roles=tuple(row["roles"]), scopes=tuple(row["scopes"]),
            artifact_kinds=tuple(row["artifact_kinds"]), public_key=public_key,
            production_allowed=row["production_allowed"],
        ))
    return tuple(keys)


def _service_key(path: Path, keys: tuple[TrustKeyV4, ...]) -> ProductionServiceKeyV4:
    row = _read_canonical(path, SERVICE_KEY_FIELDS, "service_runtime_key")
    if row["schema_version"] != "jc/local-production-service-key/1.0":
        _fail("PRODUCTION_SERVICE_KEY", "service key schema is unsupported")
    try:
        seed = b64decode(row["private_seed_base64"], validate=True)
        declared_public = b64decode(row["public_key_base64"], validate=True)
        private_key = Ed25519PrivateKey.from_private_bytes(seed)
    except (Base64Error, TypeError, ValueError) as exc:
        raise ContractV4Error("PRODUCTION_SERVICE_KEY", "service key bytes are invalid") from exc
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    trusted = next((key for key in keys if key.key_id == row["key_id"]), None)
    if (
        declared_public != public_key
        or trusted is None
        or trusted.public_key != public_key
        or trusted.issuer != row["issuer"]
        or trusted.principal_id != row["principal_id"]
        or "service_signer" not in trusted.roles
        or not trusted.production_allowed
    ):
        _fail("PRODUCTION_SERVICE_KEY_MISMATCH", "service key does not match production trust")
    return ProductionServiceKeyV4(
        row["key_id"], row["issuer"], row["principal_id"], private_key, public_key,
    )


def load_production_pack(
    pack_path: Path,
    trust_path: Path,
    service_key_path: Path,
    *,
    now: CanonicalTimeV4 | None = None,
    expected_identity: ProductionIdentityPinsV4 | None = None,
) -> LoadedProductionPackV4:
    """Load exact bytes and verify the whole pack at the caller's current UTC time."""

    pack = _read_canonical(pack_path, PACK_FIELDS, "production_pack")
    trust_document = _read_canonical(trust_path, TRUST_FIELDS, "production_trust")
    if (
        pack["schema_version"] != "jc/local-production-pack/1.0"
        or trust_document["schema_version"] != "jc/local-production-trust/1.0"
        or pack["scope"] != "local-production"
        or trust_document["scope"] != "local-production"
        or pack["production_allowed"] is not True
        or trust_document["production_allowed"] is not True
        or pack["signing_mode"] != "LOCAL_AUTOMATED_OWNER"
        or trust_document["signing_mode"] != "LOCAL_AUTOMATED_OWNER"
        or pack["independent_human_review"] is not False
        or trust_document["independent_human_review"] is not False
        or pack["observation_required"] is not True
    ):
        _fail("PRODUCTION_PROFILE", "pack and trust are not the approved local profile")
    identity = ProductionIdentityPinsV4.from_dict(trust_document["runtime_identity"])
    if expected_identity is not None and identity != expected_identity:
        _fail("PRODUCTION_IDENTITY_DRIFT", "installed identity pins differ from trust")
    policy = TrustPolicyV4.from_dict(trust_document["trust_policy"])
    keys = _trust_keys(trust_document["trust_keys"])
    service_key = _service_key(service_key_path, keys)
    resolver = ArtifactResolverV4(max_artifact_bytes=1_048_576)
    artifacts = pack["artifacts"]
    if type(artifacts) is not list or not artifacts:
        _fail("PRODUCTION_ARTIFACTS", "artifacts must be a non-empty array")
    for item in artifacts:
        row = _object(item, ARTIFACT_FIELDS, "pack_artifact")
        try:
            content = b64decode(row["content_base64"], validate=True)
        except (Base64Error, TypeError, ValueError) as exc:
            raise ContractV4Error("PRODUCTION_ARTIFACT_ENCODING", "artifact is not strict base64") from exc
        resolver.register_bytes(
            artifact_id=row["artifact_id"],
            content_ref=ContentRefV4.from_dict(row["content_ref"]),
            artifact_kind=row["artifact_kind"], media_type=row["media_type"],
            scope=row["scope"], content=content,
        )
    trust = TrustVerifierV4(policy=policy, keys=keys, target_environment="production")
    source_service = SourceServiceV4(resolver, trust)
    verifier = RulePackVerifierV4(
        resolver, source_service, trust,
        expected_engine_api=identity.engine_api,
        expected_compiler_build_digest=identity.compiler_build_digest,
        expected_source_tree_digest=identity.source_tree_digest,
        expected_schema_digest=identity.schema_digest,
    )
    verified_at = current_utc_time() if now is None else now
    if type(verified_at) is not CanonicalTimeV4:
        _fail("PRODUCTION_CURRENT_TIME", "now must be CanonicalTimeV4")
    pack_ref = ContentRefV4.from_dict(pack["pack_ref"])
    verified = verifier.verify(pack_ref, now=verified_at)
    declared_rules = pack["formal_rule_ids"]
    if type(declared_rules) is not list or any(type(item) is not str for item in declared_rules):
        _fail("PRODUCTION_RULE_SET", "formal_rule_ids must be strings")
    verified_rule_ids = tuple(rule.rule_id for rule in verified.rules)
    formal_rule_ids = tuple(declared_rules)
    if (
        len(formal_rule_ids) != 6
        or len(set(formal_rule_ids)) != 6
        or set(formal_rule_ids) != set(verified_rule_ids)
    ):
        _fail("PRODUCTION_RULE_SET", "verified formal rules differ from declared six-rule scope")
    return LoadedProductionPackV4(
        resolver, policy, keys, trust, source_service, verifier, verified, pack_ref,
        identity, service_key, formal_rule_ids, verified_at,
    )


__all__ = (
    "LoadedProductionPackV4", "ProductionIdentityPinsV4", "ProductionServiceKeyV4",
    "current_utc_time", "load_production_pack",
)
