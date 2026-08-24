"""Public Python facade over the sole V4 application and audit authorities."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
import importlib
import os
from pathlib import Path
import re
from typing import Any

from compiler_core.application import ApplicationV4
from compiler_core.audit_bundle import (
    AuditBundleStoreV4,
    ReplayExecutionV4,
    RunCapabilityV4,
    VerifiedAuditBundleV4,
)
from compiler_core.contracts import (
    ArtifactHandleV4,
    CanonicalTimeV4,
    CaseInputBundleV4,
    CaseRequestV4,
    ContentRefV4,
    EvaluationEnvelopeV4,
    MCPCapabilitiesOutputV4,
    MCPEvaluateInputV4,
    MCPEvaluateOutputV4,
    MCPReadArtifactOutputV4,
    MCPVerifyRunOutputV4,
    ReplayResultV4,
    ResourceLimitsV4,
)
from compiler_core.canonical_serialization import parse_json_document
from compiler_core.rendering import RenderOutputV4, render_verified_bundle


EvaluationContextV4 = Callable[
    [CaseInputBundleV4], AbstractContextManager[tuple[ContentRefV4, ContentRefV4, str]]
]
ReplayExecutorV4 = Callable[[object], ReplayExecutionV4]
MCPOutputFactoryV4 = Callable[[EvaluationEnvelopeV4], MCPEvaluateOutputV4]


def _environment_capabilities() -> MCPCapabilitiesOutputV4 | None:
    manifest = os.environ.get("JC_RUNTIME_MANIFEST", "").strip()
    if not manifest:
        return None
    try:
        document = parse_json_document(Path(manifest).read_bytes())
        if not isinstance(document, dict) or set(document) != {
            "schema_version", "capabilities",
        } or document["schema_version"] != "jc/runtime-manifest/1.0":
            raise ValueError("runtime manifest fields are invalid")
        return MCPCapabilitiesOutputV4.from_dict(document["capabilities"])
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        raise ClientV4Error(
            "RUNTIME_MANIFEST_INVALID",
            "V4 runtime manifest is unavailable or invalid",
            stage="runtime",
        ) from exc


class ClientV4Error(RuntimeError):
    """Stable public error without filesystem paths or internal object reprs."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        stage: str = "client",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.retryable = retryable


class JCClient:
    """Thin V4 facade; runtime materials are injected, never caller-asserted."""

    def __init__(
        self,
        application: ApplicationV4 | None = None,
        audit_store: AuditBundleStoreV4 | None = None,
        *,
        clock: Callable[[], CanonicalTimeV4] | None = None,
        evaluation_context: EvaluationContextV4 | None = None,
        replay_executor: ReplayExecutorV4 | None = None,
        capabilities: MCPCapabilitiesOutputV4 | None = None,
        mcp_output_factory: MCPOutputFactoryV4 | None = None,
    ) -> None:
        if application is not None and type(application) is not ApplicationV4:
            raise ClientV4Error("CLIENT_RUNTIME_TYPE", "application must be ApplicationV4")
        if audit_store is not None and type(audit_store) is not AuditBundleStoreV4:
            raise ClientV4Error("CLIENT_RUNTIME_TYPE", "audit_store must be AuditBundleStoreV4")
        for value, name in (
            (clock, "clock"),
            (evaluation_context, "evaluation_context"),
            (replay_executor, "replay_executor"),
            (mcp_output_factory, "mcp_output_factory"),
        ):
            if value is not None and not callable(value):
                raise ClientV4Error("CLIENT_RUNTIME_TYPE", f"{name} must be callable")
        if capabilities is not None and type(capabilities) is not MCPCapabilitiesOutputV4:
            raise ClientV4Error(
                "CLIENT_RUNTIME_TYPE", "capabilities must be MCPCapabilitiesOutputV4"
            )
        self._application = application
        self._audit_store = audit_store
        self._clock = clock
        self._evaluation_context = evaluation_context
        self._replay_executor = replay_executor
        self._capabilities = capabilities or _environment_capabilities()
        self._mcp_output_factory = mcp_output_factory

    @staticmethod
    def validate_request(payload: Mapping[str, Any] | bytes | str) -> CaseRequestV4:
        if type(payload) is bytes:
            return CaseRequestV4.from_json_bytes(payload)
        if type(payload) is str:
            return CaseRequestV4.from_json_bytes(payload.encode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ClientV4Error("INVALID_CASE_REQUEST", "request must be a JSON object")
        return CaseRequestV4.from_dict(dict(payload))

    @staticmethod
    def validate_bundle(
        payload: CaseInputBundleV4 | Mapping[str, Any] | bytes | str,
    ) -> CaseInputBundleV4:
        if type(payload) is CaseInputBundleV4:
            return payload
        if type(payload) is bytes:
            return CaseInputBundleV4.from_json_bytes(payload)
        if type(payload) is str:
            return CaseInputBundleV4.from_json_bytes(payload.encode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ClientV4Error("INVALID_CASE_BUNDLE", "case bundle must be a JSON object")
        return CaseInputBundleV4.from_dict(dict(payload))

    def _now(self) -> CanonicalTimeV4:
        if self._clock is None:
            raise ClientV4Error(
                "RUNTIME_NOT_CONFIGURED", "V4 runtime clock is not configured", stage="runtime"
            )
        now = self._clock()
        if type(now) is not CanonicalTimeV4:
            raise ClientV4Error("RUNTIME_CLOCK", "runtime clock returned an invalid value")
        return now

    def capabilities(self) -> MCPCapabilitiesOutputV4:
        if self._capabilities is None:
            raise ClientV4Error(
                "RUNTIME_NOT_CONFIGURED",
                "V4 runtime identity and trust material are not configured",
                stage="runtime",
            )
        return self._capabilities

    def evaluate(
        self,
        case_bundle: CaseInputBundleV4 | Mapping[str, Any] | bytes | str,
        *,
        limits: ResourceLimitsV4 | None = None,
        seed: int = 0,
    ) -> EvaluationEnvelopeV4:
        if self._application is None or self._evaluation_context is None:
            raise ClientV4Error(
                "RUNTIME_NOT_CONFIGURED",
                "V4 application and derived runtime context are not configured",
                stage="runtime",
            )
        admitted = self.validate_bundle(case_bundle)
        with self._evaluation_context(admitted) as context:
            request_ref, run_identity_ref, case_scope = context
            if (
                type(request_ref) is not ContentRefV4
                or type(run_identity_ref) is not ContentRefV4
                or type(case_scope) is not str
                or not case_scope
            ):
                raise ClientV4Error(
                    "RUNTIME_CONTEXT", "derived evaluation context is invalid", stage="runtime"
                )
            return self._application.evaluate(
                request_ref,
                run_identity_ref,
                case_scope=case_scope,
                limits=limits,
                seed=seed,
            )

    def evaluate_for_mcp(self, request: MCPEvaluateInputV4) -> MCPEvaluateOutputV4:
        if self._mcp_output_factory is None:
            raise ClientV4Error(
                "RUNTIME_NOT_CONFIGURED",
                "MCP artifact-handle issuer is not configured",
                stage="runtime",
            )
        return self._mcp_output_factory(self.evaluate(request.case_bundle))

    def _store(self) -> AuditBundleStoreV4:
        if self._audit_store is None:
            raise ClientV4Error(
                "RUNTIME_NOT_CONFIGURED", "V4 audit store is not configured", stage="runtime"
            )
        return self._audit_store

    def verify_run(
        self,
        capability: RunCapabilityV4 | ArtifactHandleV4,
    ) -> VerifiedAuditBundleV4:
        store = self._store()
        now = self._now()
        if type(capability) is ArtifactHandleV4:
            store.read_artifact(capability, offset=0, length=1, now=now)
            run_capability = store.capability_for(capability.run_identity_ref)
        elif type(capability) is RunCapabilityV4:
            run_capability = capability
        else:
            raise ClientV4Error("INVALID_RUN_CAPABILITY", "run capability has a wrong type")
        return store.verify_run(run_capability, now=now)

    def verify_for_mcp(
        self,
        handle: ArtifactHandleV4,
        *,
        offline_replay: bool,
    ) -> MCPVerifyRunOutputV4:
        store = self._store()
        verified = self.verify_run(handle)
        replay: ReplayResultV4 | None = None
        if offline_replay:
            if self._replay_executor is None:
                raise ClientV4Error(
                    "REPLAY_NOT_CONFIGURED", "offline replay executor is not configured"
                )
            replay = store.replay_run(
                store.capability_for(handle.run_identity_ref),
                now=self._now(),
                executor=self._replay_executor,
            )
        return MCPVerifyRunOutputV4(verified.verification, replay)

    def read_artifact(
        self,
        handle: ArtifactHandleV4,
        *,
        offset: int,
        length: int,
    ) -> MCPReadArtifactOutputV4:
        return self._store().read_artifact(
            handle,
            offset=offset,
            length=length,
            now=self._now(),
        )

    def render(
        self,
        capability: RunCapabilityV4 | ArtifactHandleV4,
        *,
        output_format: str = "markdown",
        audience: str = "agent",
    ) -> RenderOutputV4:
        return render_verified_bundle(
            self.verify_run(capability),
            output_format=output_format,
            audience=audience,
        )


def runtime_client() -> JCClient:
    """Load the host-installed runtime factory or retain the fail-closed client."""

    module_name = os.environ.get("JC_RUNTIME_FACTORY", "").strip()
    if not module_name:
        return JCClient()
    if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", module_name) is None:
        raise ClientV4Error(
            "RUNTIME_FACTORY_INVALID",
            "runtime factory must be an installed Python module",
            stage="runtime",
        )
    try:
        factory = getattr(importlib.import_module(module_name), "create_client")
        client = factory()
    except (AttributeError, ImportError, TypeError) as exc:
        raise ClientV4Error(
            "RUNTIME_FACTORY_INVALID",
            "runtime factory is unavailable or invalid",
            stage="runtime",
        ) from exc
    if type(client) is not JCClient:
        raise ClientV4Error(
            "RUNTIME_FACTORY_INVALID",
            "runtime factory returned an invalid client",
            stage="runtime",
        )
    return client


__all__ = ("ClientV4Error", "EvaluationContextV4", "JCClient", "runtime_client")
