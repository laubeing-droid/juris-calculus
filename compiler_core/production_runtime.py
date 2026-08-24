"""Complete composition root for the bounded local V4 production runtime."""

from __future__ import annotations

from base64 import b64encode
from contextlib import contextmanager
from dataclasses import dataclass, replace
import os
from pathlib import Path
import tempfile

from compiler_core.application import ApplicationV4
from compiler_core.audit_bundle import (
    AuditArtifactV4, AuditBundleStoreV4, AuditTrustMaterialV4, ReplayExecutionV4,
)
from compiler_core.backend_router import BackendRouterV4, backend_profile_digest_v4
from compiler_core.canonical_serialization import DigestV4, canonical_bytes, digest_value, parse_json_document
from compiler_core.certificates import CertificateIssuerV4
from compiler_core.client import JCClient
from compiler_core.contracts import (
    CanonicalTimeV4, CaseArtifactV4, CaseInputBundleV4, ContentRefV4,
    EvidenceManifestV4,
    MCPCapabilitiesOutputV4, MCPEvaluateOutputV4, ResourceLimitsV4,
    RunIdentityV4, SignatureEnvelopeV4, TrustPolicyV4,
)
from compiler_core.fact_admission import (
    CASE_REQUEST_KIND, CASE_REQUEST_SCOPE, RUN_IDENTITY_KIND, RUN_IDENTITY_SCOPE,
    FactAdmissionServiceV4,
)
from compiler_core.independent_checker import IndependentCheckerV4
from compiler_core.legal_ir import LegalIRCompilerV4
from compiler_core.mcp import TOOL_SPECS, tool_spec_digest
from compiler_core.production_pack import (
    LoadedProductionPackV4, current_utc_time, load_production_pack,
)
from compiler_core.rule_packs import TRUST_POLICY_KIND
from compiler_core.storage import V4TransactionStore


CONFIG_FIELDS = {
    "schema_version", "pack_path", "trust_path", "service_key_path", "state_root",
    "quota_bytes", "engine_source_commit", "wheel_digest", "package_digest",
    "lock_digest", "tool_spec_digest", "algorithm_profile_digest",
    "backend_profile_digest", "storage_capability_ref",
}


def _algorithm_profile_digest() -> DigestV4:
    return digest_value({
        "schema_version": "jc/independent-checker-profile/1.0",
        "canonical_input": "content-addressed-v4-artifacts",
        "translation": "independent-exhaustive-field-projection",
        "horn": "finite-constitutive-least-fixpoint",
        "aaf": "independent-finite-dung-grounded",
        "exact": "integer-rational-nanosecond-half-open",
        "claim_projection": "all-argument-witnesses",
    })


@dataclass(frozen=True, slots=True)
class ProductionRuntimeConfigV4:
    pack_path: Path
    trust_path: Path
    service_key_path: Path
    state_root: Path
    quota_bytes: int
    engine_source_commit: str
    wheel_digest: DigestV4
    package_digest: DigestV4
    lock_digest: DigestV4
    tool_spec_digest: DigestV4
    algorithm_profile_digest: DigestV4
    backend_profile_digest: DigestV4
    storage_capability_ref: ContentRefV4
    runtime_config_digest: DigestV4

    @classmethod
    def from_path(cls, path: Path) -> "ProductionRuntimeConfigV4":
        raw = path.read_bytes()
        value = parse_json_document(raw)
        if type(value) is not dict or set(value) != CONFIG_FIELDS:
            raise ValueError("production runtime config fields are not exact")
        if raw != canonical_bytes(value) or value["schema_version"] != "jc/production-runtime/1.0":
            raise ValueError("production runtime config is not canonical V4 JSON")
        paths = tuple(Path(value[name]) for name in (
            "pack_path", "trust_path", "service_key_path", "state_root",
        ))
        if any(not item.is_absolute() for item in paths):
            raise ValueError("production runtime paths must be absolute")
        config = cls(
            *paths,
            value["quota_bytes"], value["engine_source_commit"],
            DigestV4(value["wheel_digest"]), DigestV4(value["package_digest"]),
            DigestV4(value["lock_digest"]), DigestV4(value["tool_spec_digest"]),
            DigestV4(value["algorithm_profile_digest"]),
            DigestV4(value["backend_profile_digest"]),
            ContentRefV4.from_dict(value["storage_capability_ref"]),
            DigestV4.from_bytes(raw),
        )
        if (
            config.quota_bytes < 64 * 1024 * 1024
            or len(config.engine_source_commit) not in {40, 64}
            or config.tool_spec_digest != tool_spec_digest()
            or config.algorithm_profile_digest != _algorithm_profile_digest()
            or config.backend_profile_digest != backend_profile_digest_v4(solver_deadline_ms=2500)
        ):
            raise ValueError("production runtime identity or resource pins are invalid")
        return config


def _signer(materials: LoadedProductionPackV4):
    def sign(
        subject_digest: DigestV4,
        payload_digest: DigestV4,
        evidence_refs: tuple[ContentRefV4, ...],
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> SignatureEnvelopeV4:
        expires_at = materials.policy.valid_to
        if expires_at is None:
            raise ValueError("production service signatures require policy expiry")
        body = {
            "algorithm": "Ed25519", "key_id": materials.service_key.key_id,
            "issuer": materials.service_key.issuer, "role": "service_signer",
            "scope": "service-certificate", "kind": "service-certificate",
            "schema_version": "jc/4.0", "subject_digest": str(subject_digest),
            "run_identity_ref": run_identity_ref.to_dict(), "status": "APPROVED",
            "issued_at": now.to_dict(), "expires_at": expires_at.to_dict(),
            "nonce": f"service-{subject_digest.hex}-{payload_digest.hex}",
            "evidence_refs": [item.to_dict() for item in evidence_refs],
            "payload_digest": str(payload_digest),
            "policy_digest": str(materials.policy.policy_digest),
            "revocation_ref": materials.policy.revocation_policy_ref.to_dict(),
        }
        signature = materials.service_key.private_key.sign(canonical_bytes(body))
        return SignatureEnvelopeV4.from_dict({
            **body, "signature": b64encode(signature).decode("ascii"),
        })
    return sign


def _store(config: ProductionRuntimeConfigV4) -> V4TransactionStore:
    namespace = config.state_root / "jc-v4-state"
    transaction = (
        V4TransactionStore.open(config.state_root, quota_bytes=config.quota_bytes)
        if namespace.is_dir()
        else V4TransactionStore.create(config.state_root, quota_bytes=config.quota_bytes)
    )
    return transaction


def _case_artifact(
    artifact_id: str,
    reference: ContentRefV4,
    kind: str,
    scope: str,
    raw: bytes,
) -> CaseArtifactV4:
    return CaseArtifactV4(
        artifact_id, reference, kind, "application/json", scope,
        b64encode(raw).decode("ascii"),
    )


_REPLAY_INPUT_KINDS = frozenset({
    "source-bundle", "evidence-manifest", "evidence-item", "evidence-document",
    "evidence-custody", "fact-proposition", "fact-value", "fact-candidate",
    "fact-attestation",
})


def _bundle_from_sealed(sealed) -> CaseInputBundleV4:
    input_value = parse_json_document(sealed.read("input.json"))
    request = input_value["request"]
    artifacts: dict[ContentRefV4, CaseArtifactV4] = {}
    for name in ("source-index.json", "fact-admission.json", "rule-pack.json"):
        value = parse_json_document(sealed.read(name))
        for row in value["artifacts"]:
            item = AuditArtifactV4.from_wire(row)
            if item.artifact_kind in _REPLAY_INPUT_KINDS:
                artifacts[item.content_ref] = CaseArtifactV4(
                    item.artifact_id, item.content_ref, item.artifact_kind,
                    item.media_type, item.scope, b64encode(item.content).decode("ascii"),
                )
    body = {
        "schema_version": "jc/case-input-bundle/1.0",
        "bundle_id": f"replay-{sealed.original_run_identity_ref.digest.hex[:24]}",
        "request": request,
        "artifacts": [item.to_dict() for item in sorted(
            artifacts.values(), key=lambda item: (item.artifact_kind, item.content_ref.digest.hex)
        )],
    }
    return CaseInputBundleV4.from_dict({
        **body, "bundle_digest": str(digest_value(body)),
    })


def create_client(
    config: ProductionRuntimeConfigV4 | None = None,
    *,
    clock=None,
) -> JCClient:
    if config is None:
        config_path = os.environ.get("JC_PRODUCTION_CONFIG", "").strip()
        if not config_path:
            raise ValueError("JC_PRODUCTION_CONFIG is required")
        config = ProductionRuntimeConfigV4.from_path(Path(config_path))
    if type(config) is not ProductionRuntimeConfigV4:
        raise TypeError("config must be ProductionRuntimeConfigV4")
    runtime_clock = current_utc_time if clock is None else clock
    if not callable(runtime_clock):
        raise TypeError("clock must be callable")
    materials = load_production_pack(
        config.pack_path, config.trust_path, config.service_key_path,
        now=runtime_clock(),
    )
    signer = _signer(materials)
    fact_service = FactAdmissionServiceV4(
        materials.resolver, materials.source_service, materials.trust,
        receipt_issuer=materials.service_key.issuer, receipt_signer=signer,
    )
    compiler = LegalIRCompilerV4(
        materials.pack_verifier,
        receipt_issuer=materials.service_key.issuer, receipt_signer=signer,
    )
    router = BackendRouterV4(compiler, fact_service, receipt_signer=signer)
    checker = IndependentCheckerV4(
        materials.resolver, materials.trust,
        receipt_issuer=materials.service_key.issuer, receipt_signer=signer,
    )
    trust_material = AuditTrustMaterialV4(
        materials.policy, tuple(sorted(materials.keys, key=lambda key: key.key_id)), "production",
        tuple(sorted(materials.trust._revoked_subjects, key=str)),
        tuple(sorted(materials.trust._revoked_nonces)),
    )
    audit_store = AuditBundleStoreV4(
        _store(config), trust_material=trust_material,
        current_engine_build_digest=materials.identity.compiler_build_digest,
        checker_receipt_issuer=materials.service_key.issuer,
    )
    issuer = CertificateIssuerV4(
        materials.trust,
        current_engine_build_digest=materials.identity.compiler_build_digest,
        signer=signer,
    )
    application = ApplicationV4(
        materials.resolver, materials.trust, materials.source_service, fact_service,
        materials.pack_verifier, compiler, router, checker, audit_store, issuer,
        receipt_signer=signer, clock=runtime_clock,
    )

    @contextmanager
    def evaluation_context(bundle: CaseInputBundleV4):
        materials.resolver.validate_case_bundle(bundle)
        request = bundle.request
        manifest_artifact = next(
            item for item in bundle.artifacts
            if item.content_ref == request.evidence_manifest_ref
        )
        manifest_body = parse_json_document(manifest_artifact.content_bytes())
        manifest = EvidenceManifestV4.from_dict({
            **manifest_body, "manifest_digest": str(request.evidence_manifest_ref.digest),
        })
        request_ref = ContentRefV4(CASE_REQUEST_KIND, request.canonical_digest())
        run = RunIdentityV4.build(
            request, request_ref,
            engine_version=materials.identity.engine_api,
            engine_source_commit=config.engine_source_commit,
            engine_source_tree=materials.identity.source_tree_digest.hex,
            engine_build_digest=materials.identity.compiler_build_digest,
            wheel_digest=config.wheel_digest, package_digest=config.package_digest,
            schema_digest=materials.identity.schema_digest,
            tool_spec_digest=config.tool_spec_digest, lock_digest=config.lock_digest,
            runtime_config_digest=config.runtime_config_digest,
            algorithm_profile_digest=config.algorithm_profile_digest,
            trust_policy_ref=ContentRefV4(TRUST_POLICY_KIND, materials.policy.canonical_digest()),
            storage_capability_ref=config.storage_capability_ref,
            backend_profile_digest=config.backend_profile_digest,
        )
        run_ref = ContentRefV4(RUN_IDENTITY_KIND, run.canonical_digest())
        transient = (
            *bundle.artifacts,
            _case_artifact(
                f"request-{request_ref.digest.hex[:24]}", request_ref,
                CASE_REQUEST_KIND, CASE_REQUEST_SCOPE, request.canonical_bytes(),
            ),
            _case_artifact(
                f"run-{run_ref.digest.hex[:24]}", run_ref,
                RUN_IDENTITY_KIND, RUN_IDENTITY_SCOPE, canonical_bytes(run.digest_body()),
            ),
        )
        with materials.resolver.overlay(transient):
            yield request_ref, run_ref, manifest.case_scope

    def mcp_output(envelope) -> MCPEvaluateOutputV4:
        now = runtime_clock()
        capability = audit_store.capability_for(envelope.result.run_identity_ref)
        verified = audit_store.verify_run(capability, now=now)
        expires = materials.policy.valid_to
        if expires is None:
            raise ValueError("production handles require policy expiry")

        def handle(name: str):
            return audit_store.issue_artifact_handle(
                capability, name, now=now, expires_at=expires,
                max_bytes=len(verified.files[name]), signer=signer,
            )

        return MCPEvaluateOutputV4(
            envelope.result, handle("certificate.json"), handle("manifest.json"),
            (handle("result.json"),),
        )

    capabilities = MCPCapabilitiesOutputV4(
        "jc/4.0", materials.identity.engine_api, materials.identity.source_tree_digest.hex,
        materials.identity.compiler_build_digest, config.wheel_digest, config.package_digest,
        config.lock_digest, materials.identity.schema_digest, config.tool_spec_digest,
        TOOL_SPECS, ResourceLimitsV4(), materials.pack_ref,
        ContentRefV4(TRUST_POLICY_KIND, materials.policy.canonical_digest()),
        config.storage_capability_ref, True, True,
    )

    def replay_executor(sealed) -> ReplayExecutionV4:
        bundle = _bundle_from_sealed(sealed)
        replay_commit = "f" * 40 if config.engine_source_commit != "f" * 40 else "e" * 40
        with tempfile.TemporaryDirectory(prefix="jc-v4-replay-") as directory:
            replay_config = replace(
                config, state_root=Path(directory).resolve(),
                engine_source_commit=replay_commit,
            )
            replay_client = create_client(
                replay_config, clock=lambda: bundle.request.decision_time,
            )
            captured: list[tuple[object, object]] = []
            replay_store = replay_client._audit_store
            original_write = replay_store.write_run

            def capture(capability, replay_materials, **kwargs):
                captured.append((replay_materials, kwargs.get("certificate_factory")))
                return original_write(capability, replay_materials, **kwargs)

            replay_store.write_run = capture
            replay_client.evaluate(bundle)
            if len(captured) != 1:
                raise ValueError("offline replay did not produce one sealed run")
            replay_materials, certificate_factory = captured[0]
            return ReplayExecutionV4(replay_materials, certificate_factory)

    return JCClient(
        application, audit_store, clock=runtime_clock, evaluation_context=evaluation_context,
        replay_executor=replay_executor, capabilities=capabilities,
        mcp_output_factory=mcp_output,
    )


__all__ = ("ProductionRuntimeConfigV4", "create_client")
