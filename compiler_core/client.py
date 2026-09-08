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
from compiler_core.canonical_serialization import DigestV4, parse_json_document
from compiler_core.harness_contract import (
    HARNESS_CONTRACT_VERSION,
    HarnessQueryInput,
    HarnessRunRequest,
)
from compiler_core.rendering import RenderOutputV4, render_verified_bundle


HARNESS_LOCAL_CONTRACT_VERSION = "jc-harness-local/1"


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
        default_limits: ResourceLimitsV4 | None = None,
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
        if default_limits is not None and type(default_limits) is not ResourceLimitsV4:
            raise ClientV4Error(
                "CLIENT_RUNTIME_TYPE", "default_limits must be ResourceLimitsV4"
            )
        self._default_limits = default_limits
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
                limits=self._default_limits if limits is None else limits,
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

    # ------------------------------------------------------------------
    # Local keyless surface (jc-harness-local/1)
    # ------------------------------------------------------------------

    def _local(self):
        from compiler_core.local_runtime import local_handle_of

        try:
            return local_handle_of(self)
        except Exception as exc:
            raise ClientV4Error(
                "RUNTIME_NOT_CONFIGURED",
                "this client was not created by create_local_client",
                stage="runtime",
            ) from exc

    def local_pack(self) -> dict[str, Any]:
        """Describe the locally loaded rule pack (claims for query building)."""

        handle = self._local()
        return {
            "pack_ref": handle.pack.pack_ref.to_dict(),
            "sources": [
                {
                    "source_id": snapshot.source_id,
                    "jurisdiction": snapshot.jurisdiction,
                    "title": snapshot.title,
                    "effective_from": snapshot.effective_from.to_dict(),
                    "effective_to": (
                        None if snapshot.effective_to is None
                        else snapshot.effective_to.to_dict()
                    ),
                }
                for _ref, snapshot in handle.pack.sources
            ],
            "rules": list(handle.pack.rule_claims),
        }

    def local_case_bundle(self, **kwargs: Any) -> CaseInputBundleV4:
        """Build a complete local case bundle (public serialization help)."""

        handle = self._local()
        return handle.builder.build_bundle(**kwargs)

    def evaluate_harness_bundle(
        self,
        case_bundle: CaseInputBundleV4 | Mapping[str, Any] | bytes | str,
        *,
        case_id: str,
        issue_queries: Any,
    ) -> dict[str, Any]:
        """One closed local call: full input handling, one evaluation, projection.

        Returns a plain JSON-serializable object speaking
        ``jc-harness-local/1``: every ``HarnessRunResultV5`` business field,
        plus ``execution_mode="local"`` and ``signature_status="not_used"``.
        """

        from compiler_core.harness_contract import (
            HarnessQueryInput,
            project_harness_result,
        )

        handle = self._local()
        if type(case_id) is not str or not case_id:
            raise ClientV4Error("INVALID_CASE_ID", "case_id must be a non-empty string")
        queries: list[HarnessQueryInput] = []
        for index, item in enumerate(issue_queries):
            if isinstance(item, Mapping):
                try:
                    queries.append(HarnessQueryInput(
                        issue_id=item["issue_id"], claim=item["claim"],
                        profile=item["profile"],
                        excluded_branch_reasons=dict(
                            item.get("excluded_branch_reasons") or {}),
                    ))
                except (KeyError, TypeError) as exc:
                    raise ClientV4Error(
                        "INVALID_ISSUE_QUERY",
                        f"issue_queries[{index}] needs issue_id, claim, profile",
                    ) from exc
            else:
                queries.append(item)
        admitted = self.validate_bundle(case_bundle)
        request = admitted.request

        kernel_queries = request.profile_queries_v5
        kernel_by_id = {query.query_id: query for query in kernel_queries}
        issue_by_id = {query.issue_id: query for query in queries}
        if len(issue_by_id) != len(queries):
            raise ClientV4Error(
                "INVALID_ISSUE_QUERY", "issue_queries repeats an issue_id"
            )
        missing = sorted(set(kernel_by_id) - set(issue_by_id))
        extra = sorted(set(issue_by_id) - set(kernel_by_id))
        if missing or extra:
            raise ClientV4Error(
                "HARNESS_QUERY_MAPPING",
                "issue_queries and the kernel request disagree: "
                f"missing_issues={missing} unknown_issues={extra}",
            )
        for issue_id, issue in sorted(issue_by_id.items()):
            kernel = kernel_by_id[issue_id]
            if issue.claim != kernel.claim:
                raise ClientV4Error(
                    "HARNESS_QUERY_MAPPING",
                    f"issue {issue_id!r} claim differs from the kernel query claim",
                )
            if issue.profile != kernel.profile:
                raise ClientV4Error(
                    "HARNESS_QUERY_MAPPING",
                    f"issue {issue_id!r} profile differs from the kernel query profile",
                )

        if self._application is None or self._evaluation_context is None:
            raise ClientV4Error(
                "RUNTIME_NOT_CONFIGURED",
                "V4 application and derived runtime context are not configured",
                stage="runtime",
            )
        evaluations = {"count": 0}
        original_evaluate = self._application.evaluate

        def counted_evaluate(*args: Any, **kwargs: Any):
            evaluations["count"] += 1
            return original_evaluate(*args, **kwargs)

        self._application.evaluate = counted_evaluate  # type: ignore[method-assign]
        try:
            with self._evaluation_context(admitted) as context:
                request_ref, run_ref, case_scope = context
                if (
                    type(request_ref) is not ContentRefV4
                    or type(run_ref) is not ContentRefV4
                    or type(case_scope) is not str
                    or not case_scope
                ):
                    raise ClientV4Error(
                        "RUNTIME_CONTEXT",
                        "derived evaluation context is invalid",
                        stage="runtime",
                    )
                if case_scope != case_id:
                    raise ClientV4Error(
                        "HARNESS_CASE_SCOPE_MISMATCH",
                        f"case_id {case_id!r} differs from the bundle case scope "
                        f"{case_scope!r}",
                    )
                envelope = self._application.evaluate(
                    request_ref,
                    run_ref,
                    case_scope=case_scope,
                    limits=self._default_limits,
                )
        finally:
            try:
                del self._application.evaluate  # type: ignore[attr-defined]
            except AttributeError:
                self._application.evaluate = original_evaluate  # type: ignore[method-assign]
        if evaluations["count"] != 1:
            raise ClientV4Error(
                "EVALUATION_COUNT", "the local call evaluated more than once"
            )

        run_request = HarnessRunRequest(
            case_id=case_id,
            request=request,
            queries=tuple(
                HarnessQueryInput(
                    issue_id=kernel.query_id, claim=kernel.claim,
                    profile=kernel.profile,
                )
                for kernel in kernel_queries
            ),
            refutations=tuple(request.query_refutations_v5),
            gates=tuple(request.query_gates_v5),
            procedural=request.procedural_input_v5,
            incremental_parent=request.incremental_parent_v5,
        )
        projected = project_harness_result(self._application, run_request, envelope=envelope)
        payload = projected.to_dict()
        payload["harness_contract_version"] = HARNESS_LOCAL_CONTRACT_VERSION
        payload["execution_mode"] = "local"
        payload["signature_status"] = "not_used"
        payload["evaluation_count"] = evaluations["count"]
        payload["run_identity_ref"] = run_ref.to_dict()
        return payload

    def local_read_run(self, run_identity_ref: Any) -> dict[str, Any]:
        """Read one sealed local run through public methods, no capability key."""

        from compiler_core.canonical_serialization import parse_json_document

        handle = self._local()
        reference = _as_run_ref(run_identity_ref)
        store = self._store()
        capability = store.capability_for(reference)
        verified = store.verify_run(capability, now=self._now())
        files: dict[str, Any] = {}
        for name in sorted(verified.files):
            try:
                files[name] = parse_json_document(verified.files[name])
            except (TypeError, ValueError):
                files[name] = {"media": "opaque", "size_bytes": len(verified.files[name])}
        return {
            "run_identity_ref": reference.to_dict(),
            "request_id": verified.request.request_id,
            "decision_status": verified.result.decision_status.value,
            "completeness": verified.result.completeness_state.value,
            "certificate_kind": verified.certificate.kind.value,
            "signature_status": "not_used",
            "execution_mode": "local",
            "files": files,
        }

    def local_horn_subject_state(self, run_identity_ref: Any) -> dict[str, Any]:
        """Return one run's sealed Horn state and ready-made parent refs.

        The returned ``parent_run_ref``/``parent_state_ref``/
        ``parent_subject_digest`` triple feeds ``IncrementalParentV5``
        directly for the add-only incremental path of a follow-up run.
        """

        from base64 import b64decode

        from compiler_core.application import HORN_SUBJECT_STATE_KIND_V5
        from compiler_core.canonical_serialization import parse_json_document

        self._local()
        reference = _as_run_ref(run_identity_ref)
        store = self._store()
        capability = store.capability_for(reference)
        verified = store.verify_run(capability, now=self._now())
        payload = parse_json_document(verified.files["checker-receipts.json"])
        for item in payload.get("artifacts", []):
            if item.get("artifact_kind") != HORN_SUBJECT_STATE_KIND_V5:
                continue
            document = parse_json_document(
                b64decode(item["content_base64"], validate=True)
            )
            return {
                "parent_run_ref": reference.to_dict(),
                "parent_state_ref": {
                    key: value for key, value in item["content_ref"].items()
                },
                "parent_subject_digest": str(document["subject_digest"]),
                "document": document,
            }
        raise ClientV4Error(
            "LOCAL_HORN_STATE_MISSING",
            "this run has no sealed Horn subject state",
        )


def _as_run_ref(value: object) -> ContentRefV4:
    """Coerce a run identity (ContentRefV4, digest string, or dict) to a ref."""

    if type(value) is ContentRefV4:
        if value.kind != "run-identity":
            raise ClientV4Error("INVALID_RUN_REF", "run ref kind must be run-identity")
        return value
    if type(value) is str:
        return ContentRefV4("run-identity", DigestV4.parse(value))
    if isinstance(value, Mapping) and value.get("kind") == "run-identity":
        return ContentRefV4.from_dict(dict(value))
    raise ClientV4Error(
        "INVALID_RUN_REF",
        "run_identity_ref must be a run-identity ContentRefV4 or digest string",
    )


def create_local_client(state_root, rule_roots=(), *, clock=None, quota_bytes=None):
    """Create the local keyless JC client (see :mod:`compiler_core.local_runtime`).

    ``create_local_client(state_root, rule_roots)`` assembles the existing
    formal spine over local record endorsements: no service key, trust
    bundle, signed pack, broker, probe, activation ledger, or generated key
    is required or created. Returns a :class:`JCClient` carrying the local
    surface (``local_pack``, ``local_case_bundle``, ``evaluate_harness_bundle``,
    ``local_read_run``, ``local_horn_subject_state``).
    """

    from compiler_core.local_runtime import create_local_client as _create

    return _create(
        state_root,
        rule_roots,
        clock=clock,
        quota_bytes=quota_bytes,
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


__all__ = (
    "ClientV4Error",
    "EvaluationContextV4",
    "HARNESS_CONTRACT_VERSION",
    "HARNESS_LOCAL_CONTRACT_VERSION",
    "JCClient",
    "create_local_client",
    "runtime_client",
)
