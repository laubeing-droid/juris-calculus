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

CALCULATION_RECEIPT_SCHEMA_VERSION = "jc-calculation-receipt/1"
PRICING_MODEL_VERSION = "Z-v1-default"
SUPPORTED_ESTIMATOR_VERSIONS = ("theilsen-legacy-branches/1",)
DEFAULT_DEADLINE_CONFIGS = Path(__file__).resolve().parent.parent / "configs"


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

    def business_capabilities(self) -> dict[str, Any]:
        """Describe the installed jc-business-root/1 implementation.

        The list is generated from the installed code, never from a candidate
        manifest: profiles, requirement, schemas, checker version, delivery
        file names, and the declared evidence scope.
        """

        from compiler_core.contracts import (
            BUSINESS_DELIVERY_FILES_V1,
        )
        from compiler_core.business_root.codec import (
            BUSINESS_CHECKER_VERSION,
            BUSINESS_FORMAL_EVIDENCE_V1,
            BUSINESS_MODEL_BASIS_V1,
            BUSINESS_PROFILE_V1,
            BUSINESS_REQUIREMENT_V1,
            BUSINESS_ROOT_CAPABILITY,
        )
        from compiler_core.business_root.delivery_checker import SCOPE as DELIVERY_SCOPE

        self._local()
        return {
            "capability": BUSINESS_ROOT_CAPABILITY,
            "profiles": (BUSINESS_PROFILE_V1,),
            "model_bases": (BUSINESS_MODEL_BASIS_V1,),
            "requirements": (BUSINESS_REQUIREMENT_V1,),
            "delivery_files": list(BUSINESS_DELIVERY_FILES_V1),
            "checker_version": BUSINESS_CHECKER_VERSION,
            "formal_evidence": BUSINESS_FORMAL_EVIDENCE_V1,
            "semantic_scope": DELIVERY_SCOPE,
            "request_extension": "business_tasks_v1",
            "verify_method": "verify_business_delivery",
            "verify_only": True,
        }

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
        payload["business_results"] = [
            row.to_dict() for row in envelope.result.business_results_v1
        ]
        return payload

    def verify_business_delivery(
        self,
        *,
        run_identity_ref: Any,
        business_task_id: str,
        selected_input_ref: Any,
        artifacts: Any,
    ) -> dict[str, Any]:
        """Verify-only two-file delivery check against one sealed business run.

        Recovers the run's sealed I0, result, and witness through public
        verification (never re-evaluating), checks the ``selected_input_ref``
        binding clue, then strictly parses the actual txt/JSON bytes with the
        closed delivery grammar. Sealed audit bundles are never modified; a
        separate content-addressed delivery record is registered instead.
        """

        from hashlib import sha256

        from compiler_core.application import BUSINESS_INPUT_KIND_V1
        from compiler_core.business_root import wire as business_wire
        from compiler_core.business_root.delivery_checker import (
            FILES as DELIVERY_FILES,
            check_business_bundle,
        )
        from compiler_core.contracts import (
            BUSINESS_PROFILE_SYNTHETIC_PRINCIPAL_V1,
            BUSINESS_REQUIREMENT_TWO_FILES_V1,
            BusinessDeliveryBindingV5,
            BusinessDeliveryVerificationV5,
            BusinessTaskInputV1,
        )
        from compiler_core.business_root.codec import (
            BUSINESS_CHECKER_VERSION,
            BUSINESS_FORMAL_EVIDENCE_V1,
        )

        reference = _as_run_ref(run_identity_ref)
        if type(business_task_id) is not str or not business_task_id:
            raise ClientV4Error("INVALID_BUSINESS_TASK", "business_task_id must be a non-empty string")
        if isinstance(selected_input_ref, Mapping):
            raw_selection = selected_input_ref.get("digest")
        elif isinstance(selected_input_ref, str):
            raw_selection = str(selected_input_ref)
        else:
            raw_selection = None
        if type(raw_selection) is not str or not raw_selection.startswith("sha256:"):
            raise ClientV4Error(
                "INVALID_SELECTION_REF", "selected_input_ref must be a sha256 digest string"
            )
        if not isinstance(artifacts, Mapping) or set(artifacts) != set(DELIVERY_FILES):
            raise ClientV4Error(
                "INVALID_DELIVERY_ARTIFACTS",
                "artifacts must map exactly "
                f"{sorted(DELIVERY_FILES)} to actual byte strings",
            )
        if any(type(payload) is not bytes for payload in artifacts.values()):
            raise ClientV4Error(
                "INVALID_DELIVERY_ARTIFACTS", "artifact values must be bytes"
            )
        if self._application is None:
            raise ClientV4Error(
                "RUNTIME_NOT_CONFIGURED",
                "delivery verification needs the runtime application",
                stage="runtime",
            )

        store = self._store()
        verified = store.verify_run(store.capability_for(reference), now=self._now())
        rows = verified.result.business_results_v1
        row = next((item for item in rows if item.task_id == business_task_id), None)

        def verdict_payload(
            status: str, reasons: tuple[str, ...], bindings: tuple = ()
        ) -> dict[str, Any]:
            record_body: dict[str, Any] = {
                "schema_version": "jc/business-delivery-record/1.0",
                "run_identity_ref": reference.to_dict(),
                "selection_ref": raw_selection,
                "task_id": business_task_id,
                "requirement_id": BUSINESS_REQUIREMENT_TWO_FILES_V1,
                "profile": BUSINESS_PROFILE_SYNTHETIC_PRINCIPAL_V1,
                "status": status,
                "reasons": list(reasons),
                "artifact_bindings": [
                    binding.to_dict() if hasattr(binding, "to_dict") else dict(binding)
                    for binding in bindings
                ],
                "checker_version": BUSINESS_CHECKER_VERSION,
                "formal_evidence": BUSINESS_FORMAL_EVIDENCE_V1,
                "verified_at": self._now().to_dict(),
            }
            record_ref = self._application.register_business_delivery_record(record_body)
            verification = BusinessDeliveryVerificationV5(
                verification_record_ref=record_ref,
                run_identity_ref=reference,
                selection_ref=DigestV4(raw_selection),
                task_id=business_task_id,
                requirement_id=BUSINESS_REQUIREMENT_TWO_FILES_V1,
                profile=BUSINESS_PROFILE_SYNTHETIC_PRINCIPAL_V1,
                status=status,
                reasons=reasons,
                artifact_bindings=bindings,
                checker_version=BUSINESS_CHECKER_VERSION,
                formal_evidence=BUSINESS_FORMAL_EVIDENCE_V1,
            )
            payload = verification.to_dict()
            payload["verified_at"] = record_body["verified_at"]
            return payload

        if row is None:
            return verdict_payload(
                "REJECTED", ("BUSINESS_TASK_NOT_IN_RUN",)
            )
        if str(row.selection_ref) != raw_selection:
            return verdict_payload("REJECTED", ("SELECTION_REF_MISMATCH",))
        if row.completion.value != "exact_finite_scenarios":
            return verdict_payload("REJECTED", ("BUSINESS_RUN_NOT_EXACT",))

        document = self._find_sealed_artifact(verified, row.input_ref, BUSINESS_INPUT_KIND_V1)
        if document is None:
            return verdict_payload("REJECTED", ("BUSINESS_INPUT_NOT_SEALED",))
        try:
            stored_input = BusinessTaskInputV1.from_dict(document["input"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ClientV4Error(
                "BUSINESS_INPUT_CORRUPT", "the sealed business input is not decodable"
            ) from exc

        from compiler_core.business_root.analytics import check_analytics
        from compiler_core.business_root.checker import check as business_check

        spec = business_wire.spec_of(stored_input)
        model = business_wire.model_of(stored_input)
        internal_result = business_wire.result_of(row, spec)
        if not business_check(spec, internal_result):
            return verdict_payload("REJECTED", ("SEALED_RESULT_FAILED_CHECK",))
        internal_analytics = None
        if row.analytics is not None and model is not None:
            internal_analytics = business_wire.analytics_of(row.analytics, spec.context)
            if not check_analytics(spec, internal_result, model, internal_analytics):
                return verdict_payload("REJECTED", ("SEALED_ANALYTICS_FAILED_CHECK",))

        verdict = check_business_bundle(
            spec, internal_result, model, internal_analytics, dict(artifacts)
        )
        bindings = tuple(
            BusinessDeliveryBindingV5(
                name,
                sha256(artifacts[name]).hexdigest(),
                len(artifacts[name]),
            )
            for name in sorted(artifacts)
        )
        if not verdict.accepted:
            return verdict_payload("REJECTED", (verdict.reason,), bindings)
        return verdict_payload("ACCEPTED", (), bindings)

    def business_delivery_documents(
        self,
        *,
        run_identity_ref: Any,
        business_task_id: str,
    ) -> dict[str, bytes]:
        """Read-only protected file view of one sealed exact business run.

        Renders the two protected files from the run's sealed row and sealed
        I0 — never by re-evaluating. The Harness writes these bytes to disk
        and later verifies the actual files through
        :meth:`verify_business_delivery`.
        """

        from compiler_core.application import BUSINESS_INPUT_KIND_V1
        from compiler_core.business_root import wire as business_wire
        from compiler_core.business_root.delivery_checker import (
            FILES as DELIVERY_FILES,
            render_calculation_json,
            render_document,
        )
        from compiler_core.contracts import BusinessTaskInputV1

        reference = _as_run_ref(run_identity_ref)
        if type(business_task_id) is not str or not business_task_id:
            raise ClientV4Error("INVALID_BUSINESS_TASK", "business_task_id must be a non-empty string")
        store = self._store()
        verified = store.verify_run(store.capability_for(reference), now=self._now())
        row = next(
            (item for item in verified.result.business_results_v1 if item.task_id == business_task_id),
            None,
        )
        if row is None:
            raise ClientV4Error(
                "BUSINESS_TASK_NOT_IN_RUN",
                "this sealed run has no such business task result",
            )
        if row.completion.value != "exact_finite_scenarios" or row.analytics is None:
            raise ClientV4Error(
                "BUSINESS_RUN_NOT_EXACT",
                "the two-file view exists only for exact runs with analytics",
            )
        document = self._find_sealed_artifact(verified, row.input_ref, BUSINESS_INPUT_KIND_V1)
        if document is None:
            raise ClientV4Error(
                "BUSINESS_INPUT_NOT_SEALED", "the run's business input is not sealed"
            )
        stored_input = BusinessTaskInputV1.from_dict(document["input"])
        spec = business_wire.spec_of(stored_input)
        model = business_wire.model_of(stored_input)
        internal_result = business_wire.result_of(row, spec)
        internal_analytics = business_wire.analytics_of(row.analytics, spec.context)
        return {
            DELIVERY_FILES[0]: render_document(spec, internal_result).encode("utf-8"),
            DELIVERY_FILES[1]: render_calculation_json(
                spec, internal_result, model, internal_analytics
            ).encode("utf-8"),
        }

    @staticmethod
    def _find_sealed_artifact(
        verified: VerifiedAuditBundleV4,
        content_ref: ContentRefV4,
        artifact_kind: str,
    ) -> dict[str, Any] | None:
        """Recover one sealed artifact document from the verified bundle."""

        from base64 import b64decode

        from compiler_core.canonical_serialization import parse_json_document

        for name in sorted(verified.files):
            if not name.endswith(".json"):
                continue
            try:
                payload = parse_json_document(verified.files[name])
            except (TypeError, ValueError):
                continue
            if type(payload) is not dict or type(payload.get("artifacts")) is not list:
                continue
            for item in payload["artifacts"]:
                if item.get("artifact_kind") != artifact_kind:
                    continue
                ref = item.get("content_ref") or {}
                if ref.get("digest") != str(content_ref.digest):
                    continue
                return parse_json_document(
                    b64decode(item["content_base64"], validate=True)
                )
        return None

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

    # ------------------------------------------------------------------
    # Computation surface (03 card steps 4/5a and 4a; mother plan §3.3.4,
    # frozen bridge methods provider=jc). Deterministic pricing, calibration
    # and deadline computation over the same local artifact store, with
    # content-addressed calculation receipts that recompute byte-stable.
    # ------------------------------------------------------------------

    def _artifact_resolver(self):
        handle = self._local()
        return handle.builder.resolver

    def _wire_ref(self, reference: ContentRefV4, *, matter_id: str) -> dict[str, Any]:
        return {
            "owner": "jc",
            "kind": reference.kind,
            "id": reference.digest.hex,
            "version": "1",
            "matterId": matter_id,
            "digest": f"sha256:{reference.digest.hex}",
        }

    def _register_json(self, kind: str, payload: Mapping[str, Any], *, scope: str) -> ContentRefV4:
        from compiler_core.canonical_serialization import canonical_bytes

        raw = canonical_bytes(dict(payload))
        reference = ContentRefV4(kind, DigestV4.from_bytes(raw))
        resolver = self._artifact_resolver()
        resolver.register_bytes(
            artifact_id=f"jc-calc-{reference.digest.hex[:24]}",
            content_ref=reference,
            artifact_kind=kind,
            media_type="application/json",
            scope=scope,
            content=raw,
        )
        return reference

    def _resolve_json(self, ref_like: Any, *, kind: str, scope: str) -> dict[str, Any]:
        reference = self._content_ref(ref_like, kind)
        resolver = self._artifact_resolver()
        try:
            raw = resolver.resolve_content(
                reference,
                expected_artifact_kind=kind,
                expected_media_type="application/json",
                expected_scope=scope,
                max_bytes=resolver.max_artifact_bytes,
            )
        except Exception as exc:  # noqa: BLE001 - typed public error below
            raise ClientV4Error(
                "ref_not_found",
                f"no {kind} artifact for the supplied ref in this client's store",
            ) from exc
        document = parse_json_document(raw)
        if type(document) is not dict:
            raise ClientV4Error("ref_not_found", f"{kind} artifact payload is not an object")
        return document

    @staticmethod
    def _content_ref(ref_like: Any, kind: str) -> ContentRefV4:
        if type(ref_like) is ContentRefV4:
            if ref_like.kind != kind:
                raise ClientV4Error("ref_not_found", f"ref kind must be {kind}")
            return ref_like
        if isinstance(ref_like, Mapping):
            digest = ref_like.get("digest") or ref_like.get("id")
        else:
            digest = ref_like
        if type(digest) is not str or not digest:
            raise ClientV4Error("ref_not_found", f"a {kind} ref dict or digest string is required")
        text = digest if digest.startswith("sha256:") else f"sha256:{digest}"
        try:
            return ContentRefV4(kind, DigestV4.parse(text))
        except Exception as exc:  # noqa: BLE001 - typed public error below
            raise ClientV4Error("ref_not_found", f"unreadable {kind} digest") from exc

    def calibrate(self, calibration_input: Mapping[str, Any]) -> dict[str, Any]:
        """``calibrate.fit`` provider: fit one alpha from a calibration dataset.

        Accepts ``samples`` inline or a ``datasetRef`` registered in this
        client's store (kind ``calibration-dataset``). Returns the frozen
        IFC-3 CalibrationSnapshot with ``guaranteeLevel=None`` and
        ``delta=None`` always.
        """

        from compiler_core.pricing import (
            ESTIMATOR_VERSION,
            CalibrationSample,
            fit_alpha,
        )

        if not isinstance(calibration_input, Mapping):
            raise ClientV4Error("INVALID_CALIBRATION_INPUT", "calibration input must be a mapping")
        feature_version = calibration_input.get("featureDefinitionVersion")
        if type(feature_version) is not str or not feature_version:
            raise ClientV4Error("INVALID_CALIBRATION_INPUT", "featureDefinitionVersion is required")
        estimator_version = str(calibration_input.get("estimatorVersion") or ESTIMATOR_VERSION)
        if estimator_version not in SUPPORTED_ESTIMATOR_VERSIONS:
            raise ClientV4Error("estimator_version_unknown", estimator_version)
        matter_id = str(calibration_input.get("matterId") or "unscoped")

        rows: list[CalibrationSample] = []
        dataset_ref = None
        if calibration_input.get("datasetRef") is not None:
            dataset = self._resolve_json(
                calibration_input["datasetRef"], kind="calibration-dataset", scope="pricing",
            )
            if dataset.get("schema_version") != "jc-calibration-dataset/1":
                raise ClientV4Error("ref_not_found", "dataset payload schema is not jc-calibration-dataset/1")
            raw_rows = dataset.get("samples", [])
            dataset_ref = self._content_ref(calibration_input["datasetRef"], "calibration-dataset")
        else:
            raw_rows = calibration_input.get("samples") or []
        if not isinstance(raw_rows, list) or not raw_rows:
            raise ClientV4Error("insufficient_calibration_data", "no samples supplied")
        for index, row in enumerate(raw_rows):
            try:
                rows.append(CalibrationSample(
                    entry_ref=str(row["entryRef"]),
                    feature_definition_version=str(row["featureDefinitionVersion"]),
                    duration_seconds=int(row["durationSeconds"]),
                    effective_nodes=int(row["effectiveNodes"]),
                    attributed=bool(row.get("attributed", True)),
                    source_resolution_seconds=int(row.get("sourceResolutionSeconds", 1)),
                ))
            except (KeyError, TypeError, ValueError) as exc:
                raise ClientV4Error(
                    "INVALID_CALIBRATION_INPUT", f"samples[{index}] is not a usable observation",
                ) from exc

        fit = fit_alpha(rows, feature_definition_version=feature_version)
        excluded = [
            self._wire_ref(
                ContentRefV4("time-entry", DigestV4.from_bytes(row["entryRef"].encode("utf-8"))),
                matter_id=matter_id,
            )
            for row in fit["excluded"]
        ]
        snapshot = {
            "ref": None,
            "datasetRef": (
                None if dataset_ref is None
                else self._wire_ref(dataset_ref, matter_id=matter_id)
            ),
            "featureDefinitionVersion": fit["feature_definition_version"],
            "estimatorVersion": fit["estimator_version"],
            "alpha": fit["alpha"],
            "status": fit["status"],
            "samplesUsed": fit["samples_used"],
            "excludedEntryRefs": excluded,
            "guaranteeLevel": None,
            "delta": None,
        }
        reference = self._register_json("calibration", snapshot, scope="pricing")
        snapshot["ref"] = self._wire_ref(reference, matter_id=matter_id)
        return snapshot

    def price(self, pricing_input: Mapping[str, Any]) -> dict[str, Any]:
        """``pricing.estimate`` provider: one Z-v1-default QuoteSnapshot.

        ``feature``/``alpha`` carry the resolved payloads inline (a ref dict
        to a registered artifact works too). The calculation receipt is
        content-addressed and self-contained so ``recompute_price`` is
        byte-stable; amounts are integer minor, half-up on unrounded hours.
        """

        from compiler_core.pricing import estimate_default

        if not isinstance(pricing_input, Mapping):
            raise ClientV4Error("INVALID_PRICING_INPUT", "pricing input must be a mapping")
        model_version = str(pricing_input.get("modelVersion") or PRICING_MODEL_VERSION)
        if model_version != PRICING_MODEL_VERSION:
            raise ClientV4Error("model_version_unknown", model_version)
        matter_id = str(pricing_input.get("matterId") or "unscoped")
        feature = self._payload_or_ref(pricing_input.get("feature"), "pricing-features")
        alpha = self._payload_or_ref(pricing_input.get("alpha"), "calibration")
        try:
            effective_nodes = int(feature["effectiveNodes"])
            batch_position = int(pricing_input["batchPosition"])
            rate_minor = int(pricing_input["rateMinorPerHour"])
            overhead_hours = str(pricing_input["overheadHours"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ClientV4Error("INVALID_PRICING_INPUT", "feature/batch/rate fields are incomplete") from exc
        if feature.get("featureDefinitionVersion") == "legacy-dth-explicit/1" and feature.get("legacyDth") is None:
            raise ClientV4Error("INVALID_PRICING_INPUT", "legacy features must carry legacyDth counts")
        result = estimate_default(
            effective_nodes=effective_nodes,
            alpha=str(alpha["alpha"]),
            location_factor=str(pricing_input.get("locationFactor", "1.3")),
            stage_factor=str(pricing_input.get("stageFactor", "1.25")),
            overhead_hours=overhead_hours,
            batch_position=batch_position,
            rate_minor=rate_minor,
            alpha_status=str(alpha.get("status", "fitted")),
            factor_set_version=str(pricing_input.get("factorSetVersion", "zh-default/1")),
        )
        echoed_input = {
            "featureRef": feature.get("ref"),
            "alphaRef": alpha.get("ref"),
            "factorSetRef": pricing_input.get("factorSetRef"),
            "modelVersion": model_version,
            "batchGroupId": pricing_input.get("batchGroupId"),
            "batchPosition": batch_position,
            "rateMinorPerHour": rate_minor,
            "overheadHours": overhead_hours,
            "overheadPolicyRef": pricing_input.get("overheadPolicyRef"),
            # self-contained recompute basis (canonical decimal texts)
            "feature": {"effectiveNodes": effective_nodes},
            "alpha": {"alpha": str(alpha["alpha"]), "status": str(alpha.get("status", "fitted"))},
            "locationFactor": str(pricing_input.get("locationFactor", "1.3")),
            "stageFactor": str(pricing_input.get("stageFactor", "1.25")),
        }
        return self._seal_quote(echoed_input, result, matter_id=matter_id)

    def price_human_residual(self, price_input: Mapping[str, Any]) -> dict[str, Any]:
        """``jc.price`` provider: issue-human-residual/1 HumanResidualQuote.

        Zero history still quotes. ``modelVersion`` is explicit: the frozen
        default is ``issue-human-residual/1``; ``Z-v1-default`` must be
        requested through :meth:`price` and is never substituted silently.
        Params (rate/cost/direct cost) default to the frozen engineering
        initial values and stay editable; changing the rate changes only
        the quote.
        """

        from compiler_core.pricing import (
            HUMAN_RESIDUAL_DEFAULT_DIRECT_COST_MINOR,
            HUMAN_RESIDUAL_DEFAULT_INTERNAL_COST_PER_HOUR_MINOR,
            HUMAN_RESIDUAL_DEFAULT_RATE_PER_HOUR_MINOR,
            HUMAN_RESIDUAL_MODEL_VERSION,
            human_residual_quote,
        )

        if not isinstance(price_input, Mapping):
            raise ClientV4Error("INVALID_PRICING_INPUT", "price input must be a mapping")
        model_version = str(price_input.get("modelVersion") or HUMAN_RESIDUAL_MODEL_VERSION)
        if model_version == PRICING_MODEL_VERSION:
            raise ClientV4Error(
                "model_version_explicit_required",
                "Z-v1-default quotes must use the price() entry, never a silent switch",
            )
        if model_version != HUMAN_RESIDUAL_MODEL_VERSION:
            raise ClientV4Error("model_version_unknown", model_version)
        work_items = price_input.get("workItems")
        if not isinstance(work_items, list):
            raise ClientV4Error("INVALID_PRICING_INPUT", "workItems must be an array")
        params = price_input.get("params") or {}
        matter_id = str(price_input.get("matterId") or "unscoped")
        try:
            quote = human_residual_quote(
                work_items=[dict(item) for item in work_items],
                internal_cost_per_hour_minor=int(
                    params.get("internalCostPerHourMinor",
                               HUMAN_RESIDUAL_DEFAULT_INTERNAL_COST_PER_HOUR_MINOR)
                ),
                rate_minor_per_hour=int(
                    params.get("rateMinorPerHour", HUMAN_RESIDUAL_DEFAULT_RATE_PER_HOUR_MINOR)
                ),
                direct_cost_minor=int(
                    params.get("directCostMinor", HUMAN_RESIDUAL_DEFAULT_DIRECT_COST_MINOR)
                ),
            )
        except ValueError as exc:
            raise ClientV4Error("INVALID_PRICING_INPUT", str(exc)) from exc
        receipt = {
            "schema_version": CALCULATION_RECEIPT_SCHEMA_VERSION,
            "kind": "human-residual",
            "input": {
                "workItems": [dict(item) for item in work_items],
                "internalCostPerHourMinor": quote["internal_cost_per_hour_minor"],
                "rateMinorPerHour": quote["rate_minor_per_hour"],
                "directCostMinor": quote["direct_cost_minor"],
                "modelVersion": model_version,
            },
            "computed": quote,
        }
        receipt_ref = self._register_json("calculation-receipt", receipt, scope="pricing")
        quote = dict(quote)
        quote["calculationReceiptRef"] = self._wire_ref(receipt_ref, matter_id=matter_id)
        return quote

    def _payload_or_ref(self, value: Any, kind: str) -> dict[str, Any]:
        if isinstance(value, Mapping) and (value.get("digest") or value.get("id")) and not value.get("payload"):
            if kind in {"pricing-features", "calibration"} and set(value) <= {
                "owner", "kind", "id", "version", "matterId", "digest",
            }:
                return self._resolve_json(value, kind=kind, scope="pricing")
        if isinstance(value, Mapping):
            return dict(value)
        raise ClientV4Error("INVALID_PRICING_INPUT", f"{kind} payload or ref is required")

    def _seal_quote(self, echoed_input: Mapping[str, Any], result: Mapping[str, Any], *, matter_id: str) -> dict[str, Any]:
        quote_core = {
            "variableHoursUnrounded": result["variable_hours_unrounded"],
            "overheadHoursUnrounded": result["overhead_hours_unrounded"],
            "totalHoursUnrounded": result["total_hours_unrounded"],
            "displayHours": result["display_hours"],
            "amountMinor": result["amount_minor"],
            "currency": "CNY",
        }
        receipt = {
            "schema_version": CALCULATION_RECEIPT_SCHEMA_VERSION,
            "kind": "pricing",
            "input": dict(echoed_input),
            "computed": quote_core,
        }
        receipt_ref = self._register_json("calculation-receipt", receipt, scope="pricing")
        quote_ref = self._register_json("quote", {**quote_core, "input": dict(echoed_input)}, scope="pricing")
        return {
            **quote_core,
            "ref": self._wire_ref(quote_ref, matter_id=matter_id),
            "input": dict(echoed_input),
            "calculationReceiptRef": self._wire_ref(receipt_ref, matter_id=matter_id),
        }

    def recompute_price(
        self,
        calculation_receipt_ref: Any,
        *,
        model_version: str | None = None,
    ) -> dict[str, Any]:
        """``pricing.recompute`` / ``jc.recompute_price`` provider.

        Recomputes from the self-contained receipt and compares canonical
        payloads. Old receipts never change: an equal recomputation is the
        expected outcome, and a digest the store cannot resolve raises
        ``ref_not_found`` instead of guessing.
        """

        if isinstance(calculation_receipt_ref, Mapping) and "schema_version" in calculation_receipt_ref:
            receipt = dict(calculation_receipt_ref)
        else:
            receipt = self._resolve_json(
                calculation_receipt_ref, kind="calculation-receipt", scope="pricing",
            )
        if receipt.get("schema_version") != CALCULATION_RECEIPT_SCHEMA_VERSION:
            raise ClientV4Error("ref_not_found", "unknown calculation receipt schema")
        kind = str(receipt.get("kind"))
        if kind == "pricing":
            original = receipt["computed"]
            from compiler_core.pricing import estimate_default

            source = receipt["input"]
            result = estimate_default(
                effective_nodes=int(source["feature"]["effectiveNodes"]),
                alpha=str(source["alpha"]["alpha"]),
                location_factor=str(source["locationFactor"]),
                stage_factor=str(source["stageFactor"]),
                overhead_hours=str(source["overheadHours"]),
                batch_position=int(source["batchPosition"]),
                rate_minor=int(source["rateMinorPerHour"]),
                alpha_status=str(source["alpha"]["status"]),
            )
            recomputed = {
                "variableHoursUnrounded": result["variable_hours_unrounded"],
                "overheadHoursUnrounded": result["overhead_hours_unrounded"],
                "totalHoursUnrounded": result["total_hours_unrounded"],
                "displayHours": result["display_hours"],
                "amountMinor": result["amount_minor"],
                "currency": "CNY",
            }
        elif kind == "human-residual":
            from compiler_core.pricing import human_residual_quote

            original = receipt["computed"]
            recomputed = human_residual_quote(
                work_items=receipt["input"]["workItems"],
                internal_cost_per_hour_minor=int(receipt["input"]["internalCostPerHourMinor"]),
                rate_minor_per_hour=int(receipt["input"]["rateMinorPerHour"]),
                direct_cost_minor=int(receipt["input"]["directCostMinor"]),
            )
        else:
            raise ClientV4Error("ref_not_found", f"unknown receipt kind {kind!r}")
        equal = (
            original == recomputed
            and (model_version is None or str(receipt["input"].get("modelVersion")) == model_version)
        )
        return {"original": original, "recomputed": recomputed, "equal": equal}

    def calculate_deadlines(self, deadline_input: Mapping[str, Any]) -> dict[str, Any]:
        """``deadlines.calculate`` provider over the IFC-1 deadline chain.

        Resolves the procedure event from this client's store, resolves
        every rule binding against the versioned registry shipped in
        ``configs/deadline_rules*.yaml``, and computes branch-correct
        deadlines. An unreleased/ uncovered calendar surfaces the frozen
        ``calendar_coverage_missing`` error; individual results that leave
        the coverage window carry ``dueDate=null`` with the gap step.
        """

        from datetime import datetime, timezone as dt_timezone

        from compiler_core.deadlines import (
            CalendarSnapshot,
            DeadlineError,
            compute_deadline,
            load_deadline_rules,
        )

        if not isinstance(deadline_input, Mapping):
            raise ClientV4Error("INVALID_DEADLINE_INPUT", "deadline input must be a mapping")
        matter_id = str(deadline_input.get("matterId") or "unscoped")
        try:
            event = self._resolve_json(
                deadline_input["eventRef"], kind="procedure-event", scope="case",
            )
        except KeyError as exc:
            raise ClientV4Error("INVALID_DEADLINE_INPUT", "eventRef is required") from exc
        event_revision = int(deadline_input.get("eventRevision", 0) or 0)
        if int(event.get("revision", 0)) != event_revision:
            raise ClientV4Error("revision_conflict", "event revision drifted from the request")
        if str(event.get("matterId", matter_id)) != matter_id:
            raise ClientV4Error("ref_not_found", "event belongs to another matter")

        rules = deadline_input.get("rules") or []
        if not isinstance(rules, list):
            raise ClientV4Error("INVALID_DEADLINE_INPUT", "rules must be an array")
        configs_root = Path(str(deadline_input.get("configsRoot") or DEFAULT_DEADLINE_CONFIGS))
        try:
            registry = load_deadline_rules(configs_root)
        except DeadlineError as error:
            raise ClientV4Error(error.code, error.detail) from error

        binding = deadline_input.get("calendar") or {}
        overrides: dict[str, bool] = {}
        if binding.get("ref") is not None:
            calendar_payload = self._resolve_json(binding["ref"], kind="calendar", scope="calendar")
            overrides = {
                str(key): value
                for key, value in (calendar_payload.get("overrides") or {}).items()
            }
            if any(type(value) is not bool for value in overrides.values()):
                raise ClientV4Error("calendar_coverage_missing", "calendar overrides must be booleans")
        from datetime import date as date_cls

        calendar = CalendarSnapshot(
            version=str((binding.get("ref") or {}).get("id", "unversioned")),
            coverage_start=date_cls.fromisoformat(str(binding["coverageStart"])),
            coverage_end=date_cls.fromisoformat(str(binding["coverageEnd"])),
            released=bool(binding.get("released", False)),
            overrides=overrides,
        )
        if not calendar.released:
            raise ClientV4Error(
                "calendar_coverage_missing",
                "the calendar binding is not released; no deadline may be computed",
            )

        now_raw = deadline_input.get("now")
        now = (
            datetime.fromisoformat(str(now_raw)) if now_raw
            else datetime.now(dt_timezone.utc)
        )

        deadlines: list[dict[str, Any]] = []
        uncovered = 0
        for entry in rules:
            rule_id = str(entry.get("ruleId"))
            rule_version = str(entry.get("ruleVersion"))
            rule = registry.get((rule_id, rule_version))
            if rule is None:
                raise ClientV4Error("ref_not_found", f"deadline rule {rule_id}@{rule_version} is unknown")
            try:
                computed = compute_deadline(
                    rule=rule,
                    event=event,
                    calendar=calendar,
                    matter_id=matter_id,
                    event_id=str(event.get("id", "")),
                    event_revision=event_revision,
                    now=now,
                )
            except DeadlineError as error:
                if error.code == "calendar_coverage_missing":
                    raise ClientV4Error("calendar_coverage_missing", error.detail) from error
                raise ClientV4Error(error.code, error.detail) from error
            if computed["dueDate"] is None:
                uncovered += 1
            computed.pop("calculation", None)
            deadlines.append(computed)
        # 出覆盖边界的个别结果按冻结语义返回 dueDate=null + 缺口步骤；
        # 日历整体未发布/不可用才在 compute_deadline 内升级为 typed 错误。
        receipt_ref = deadlines[0]["calculationReceiptRef"] if deadlines else None
        receipt = {
            "ref": receipt_ref,
            "scope": {"kind": "matter", "matterId": matter_id, "runId": None},
            "inputRefs": [deadline_input["eventRef"]],
            "outputRefs": [row["ref"] for row in deadlines],
            "issuedAt": now.astimezone(dt_timezone.utc).isoformat(),
        }
        return {"deadlines": deadlines, "receipt": receipt}

    def register_event(self, event: Mapping[str, Any]) -> dict[str, Any]:
        """``events.register`` provider: public registration of one procedure event.

        Lightweight schema gate (non-empty ``id``/``matterId`` strings,
        integer ``revision`` >= 1), then canonical registration in this
        client's store under kind ``procedure-event`` (scope ``case``).
        Returns the frozen wire ref that ``calculate_deadlines`` consumes
        as ``eventRef``; acceptance chains go through this public surface,
        not the private registration path.
        """

        if not isinstance(event, Mapping):
            raise ClientV4Error("schema_invalid", "event must be a mapping")
        if type(event.get("id")) is not str or not event["id"]:
            raise ClientV4Error("schema_invalid", "event id must be a non-empty string")
        if type(event.get("revision")) is not int or event["revision"] < 1:
            raise ClientV4Error("schema_invalid", "event revision must be an integer >= 1")
        if type(event.get("matterId")) is not str or not event["matterId"]:
            raise ClientV4Error("schema_invalid", "event matterId must be a non-empty string")
        reference = self._register_json("procedure-event", event, scope="case")
        return self._wire_ref(reference, matter_id=str(event["matterId"]))

    def read_argument_graph(
        self,
        run_identity_ref: Any,
        *,
        case_id: str,
        issue_ids: Any = (),
        profile: str | None = None,
    ) -> dict[str, Any]:
        """``arguments.read`` provider: the sealed argument graph of one run.

        Reads exactly what an external verifier reads (the verified audit
        bundle); no re-evaluation. Horn-only runs have a trivial graph and
        are reported as ``graphKind="horn"``.
        """

        from base64 import b64decode

        from compiler_core.application import PROFILE_STAGE_KIND_V5

        reference = _as_run_ref(run_identity_ref)
        store = self._store()
        capability = store.capability_for(reference)
        verified = store.verify_run(capability, now=self._now())
        graph_document = None
        stage_document = None
        try:
            checker_payload = parse_json_document(verified.files["checker-receipts.json"])
        except (KeyError, ValueError) as exc:
            raise ClientV4Error("ref_not_found", "run has no checker receipts") from exc
        for item in checker_payload.get("artifacts", []):
            content_ref = item.get("content_ref") or {}
            if content_ref.get("kind") == "argument-graph-v4" and graph_document is None:
                graph_document = parse_json_document(
                    b64decode(item["content_base64"], validate=True)
                )
            if content_ref.get("kind") == PROFILE_STAGE_KIND_V5 and stage_document is None:
                stage_document = parse_json_document(
                    b64decode(item["content_base64"], validate=True)
                )
        if graph_document is None:
            raise ClientV4Error(
                "ref_not_found",
                "this run sealed no argument graph document",
            )
        matter_id = case_id
        graph_ref = self._wire_ref(
            ContentRefV4("argument-graph", reference.digest), matter_id=matter_id,
        )
        node_refs = [
            self._wire_ref(
                ContentRefV4(
                    "argument-node",
                    DigestV4.from_bytes(str(row.get("argument_id", index)).encode("utf-8")),
                ),
                matter_id=matter_id,
            )
            for index, row in enumerate(graph_document.get("arguments", []))
        ]
        edge_refs = [
            self._wire_ref(
                ContentRefV4(
                    "argument-edge",
                    DigestV4.from_bytes(
                        f"{row.get('attacker', '')}->{row.get('defeated', '')}".encode("utf-8"),
                    ),
                ),
                matter_id=matter_id,
            )
            for row in graph_document.get("attacks", [])
        ]
        issue_result_refs: list[dict[str, Any]] = []
        if stage_document and issue_ids:
            statuses = stage_document.get("queries") or stage_document.get("profile_queries") or {}
            wanted = [str(issue) for issue in issue_ids]
            for issue in wanted:
                row = statuses.get(issue) if isinstance(statuses, dict) else None
                if row is None:
                    continue
                issue_result_refs.append(
                    self._wire_ref(
                        ContentRefV4(
                            "issue-result",
                            DigestV4.from_bytes(f"{reference.digest.hex}:{issue}".encode("utf-8")),
                        ),
                        matter_id=matter_id,
                    )
                )
        return {
            "graphRef": graph_ref,
            "nodeRefs": node_refs,
            "edgeRefs": edge_refs,
            "branchRefs": [],
            "issueResultRefs": issue_result_refs,
        }

    # ------------------------------------------------------------------
    # Knowledge runtime surface (03 card §4b; frozen bridge methods
    # jc.predict_outcome / jc.deviation_rank / jc.terminal_state_stats /
    # jc.admit_verified_rule_pack). The case-side adapters stay on the
    # case.* public read face — no vector store or corpus access here.
    # ------------------------------------------------------------------

    def predict_outcome(self, prediction_input: Mapping[str, Any]) -> dict[str, Any]:
        """``jc.predict_outcome`` provider.

        Returns one calibrated ProbabilityPrediction computed from the
        trained checkpoint registered under the models root (env
        ``JC_PREDICTION_MODEL_ROOT`` or ``modelRoot`` in the input).
        Without a matching checkpoint the named ``model_not_available``
        error is the answer — never a fixed probability.
        """

        from compiler_core.prediction import MODEL_NOT_AVAILABLE, load_checkpoint, predict_from_checkpoint

        if not isinstance(prediction_input, Mapping):
            raise ClientV4Error("INVALID_PREDICTION_INPUT", "prediction input must be a mapping")
        event_definition = prediction_input.get("eventDefinition")
        if type(event_definition) is not str or not event_definition:
            raise ClientV4Error("INVALID_PREDICTION_INPUT", "eventDefinition is required")
        observation_point = str(prediction_input.get("observationPoint") or "")
        if not observation_point:
            raise ClientV4Error("INVALID_PREDICTION_INPUT", "observationPoint is required")
        model_root = prediction_input.get("modelRoot") or os.environ.get("JC_PREDICTION_MODEL_ROOT")
        if not model_root:
            raise ClientV4Error(MODEL_NOT_AVAILABLE, "no prediction model root is configured")
        try:
            checkpoint = load_checkpoint(
                Path(str(model_root)),
                event_definition=event_definition,
                model_version=prediction_input.get("modelVersion"),
            )
        except LookupError as exc:
            raise ClientV4Error(
                MODEL_NOT_AVAILABLE,
                f"no trained checkpoint for event {event_definition!r}",
            ) from exc
        features = prediction_input.get("features") or {}
        if not isinstance(features, Mapping) or not features:
            raise ClientV4Error(
                "INVALID_PREDICTION_INPUT",
                "features (decimal-text values keyed by the checkpoint feature order) are required",
            )
        from compiler_core.pricing import decimal_text

        try:
            parsed_features = {
                str(name): float(decimal_text(str(value)))
                for name, value in features.items()
            }
        except ValueError as exc:
            raise ClientV4Error("INVALID_PREDICTION_INPUT", str(exc)) from exc
        return predict_from_checkpoint(
            checkpoint, parsed_features, observation_point=observation_point,
        )

    def deviation_rank(self, rank_input: Mapping[str, Any]) -> dict[str, Any]:
        """``jc.deviation_rank`` provider over the case.* public read face.

        ``structureReader`` maps one candidate locator dict to that case's
        public structure DTO (``{"elements": [...], "numeric": {...}}``);
        the reader is the only sanctioned case-side dependency. Without a
        reader the frozen ``not_compiled`` status is returned — never a
        fabricated deviation, and vector distances are never presented as
        precise deviations (``measure`` stays null for structural atoms).
        """

        reader = rank_input.get("structureReader") if isinstance(rank_input, Mapping) else None
        if not isinstance(rank_input, Mapping):
            raise ClientV4Error("INVALID_RANK_INPUT", "rank input must be a mapping")
        if not callable(reader):
            return {
                "items": [],
                "ruleVersion": str(rank_input.get("baselineRuleVersion", "")),
                "status": "not_compiled",
            }
        baseline_version = str(rank_input.get("baselineRuleVersion") or "")
        if not baseline_version:
            raise ClientV4Error("INVALID_RANK_INPUT", "baselineRuleVersion is required")
        query_structure = rank_input.get("queryStructure") or {}
        candidates = rank_input.get("candidates") or []
        budget = int(rank_input.get("budget") or 0)
        if not isinstance(candidates, list):
            raise ClientV4Error("INVALID_RANK_INPUT", "candidates must be an array")
        if budget and len(candidates) > budget:
            return {"items": [], "ruleVersion": baseline_version, "status": "budget_exceeded"}
        query_elements = set(str(item) for item in query_structure.get("elements", []))
        query_numeric = {str(k): str(v) for k, v in (query_structure.get("numeric") or {}).items()}
        items: list[dict[str, Any]] = []
        for candidate in candidates:
            locator = dict(candidate)
            structure = reader(locator)
            if structure is None:
                continue
            elements = set(str(item) for item in structure.get("elements", []))
            numeric = {str(k): str(v) for k, v in (structure.get("numeric") or {}).items()}
            deviations: list[dict[str, Any]] = []
            for element in sorted(query_elements - elements):
                deviations.append({"position": element, "measure": None,
                                   "basis": "required element absent in candidate"})
            for element in sorted(elements - query_elements):
                deviations.append({"position": element, "measure": None,
                                   "basis": "candidate element absent in query"})
            for name in sorted(set(query_numeric) & set(numeric)):
                if query_numeric[name] != numeric[name]:
                    deviations.append({
                        "position": name,
                        "measure": numeric[name],
                        "basis": "candidate numeric field differs from the query",
                    })
            items.append({
                "locator": {
                    "datasetVersion": locator.get("datasetVersion"),
                    "canonicalDocId": locator.get("canonicalDocId"),
                    "month": locator.get("month"),
                    "locator": locator.get("locator"),
                },
                "deviations": deviations,
            })
        items.sort(key=lambda row: (len(row["deviations"]), str(row["locator"]["canonicalDocId"])))
        return {"items": items, "ruleVersion": baseline_version, "status": "ok"}

    def terminal_state_stats(self, stats_input: Mapping[str, Any]) -> dict[str, Any]:
        """``jc.terminal_state_stats`` provider over the case.* public read face.

        ``statsReader(datasetVersion, filters, ruleVersion)`` is the sole
        case-side dependency and must return the public stats DTO
        (``{"distribution": [...], "counts": {...}, "range": ...}``).
        Unknown dataset versions raise the frozen
        ``dataset_version_not_found`` error; JC never reads corpus files.
        """

        reader = stats_input.get("statsReader") if isinstance(stats_input, Mapping) else None
        dataset_version = stats_input.get("datasetVersion") if isinstance(stats_input, Mapping) else None
        if not callable(reader):
            raise ClientV4Error(
                "dataset_version_not_found",
                "no case statistics read face is connected for this client",
            )
        if not isinstance(stats_input, Mapping):
            raise ClientV4Error("INVALID_STATS_INPUT", "stats input must be a mapping")
        filters = stats_input.get("filters") or {}
        if not isinstance(filters, Mapping):
            raise ClientV4Error("INVALID_STATS_INPUT", "filters must be a mapping")
        stats = reader(dataset_version, dict(filters), stats_input.get("ruleVersion"))
        if stats is None:
            raise ClientV4Error(
                "dataset_version_not_found",
                f"dataset version {dataset_version!r} is not registered",
            )
        distribution = []
        for row in stats.get("distribution", []):
            distribution.append({
                "outcome": str(row["outcome"]),
                "n": int(row["n"]),
                "rate": None if row.get("rate") is None else str(row["rate"]),
            })
        return {
            "distribution": distribution,
            "counts": dict(stats.get("counts") or {}),
            "range": str(stats.get("range") or ""),
            "datasetVersion": dataset_version if dataset_version is None else str(dataset_version),
            "ruleVersion": (
                None if stats_input.get("ruleVersion") is None
                else str(stats_input.get("ruleVersion"))
            ),
        }

    def admit_verified_rule_pack(self, admit_input: Mapping[str, Any]) -> dict[str, Any]:
        """``jc.admit_verified_rule_pack`` thin provider over the real gates.

        YAML manifest packs go through ``verify_pack_manifest`` (hashes,
        uniqueness, counts, formal source admission); ``jc-local-pack.json``
        records go through canonical structural validation. The machine
        decision ref is recorded verbatim in the admission receipt — this
        entry never fabricates a human actor and never switches on a failed
        verification. Same payload replays return the same receipt.
        """

        import json as _json
        import shutil as _shutil
        from datetime import datetime as _datetime, timezone as _timezone

        import yaml as _yaml

        from compiler_core.canonical_serialization import canonical_bytes
        from compiler_core.rule_packs import verify_pack_manifest

        if not isinstance(admit_input, Mapping):
            raise ClientV4Error("INVALID_ADMIT_INPUT", "admit input must be a mapping")
        machine_decision_ref = admit_input.get("machineDecisionRef")
        if not isinstance(machine_decision_ref, Mapping) or not machine_decision_ref.get("digest"):
            raise ClientV4Error(
                "INVALID_ADMIT_INPUT",
                "a machineDecisionRef with a digest is required (actor=machine lives with 02)",
            )
        pack_uri = str(admit_input.get("packURI") or "")
        path = Path(pack_uri)
        if not path.is_file():
            raise ClientV4Error("ref_not_found", f"packURI {pack_uri} is not a readable file")
        expected_version = admit_input.get("expectedRuleVersion")
        admitted_root = Path(
            str(admit_input.get("admittedRoot") or (path.parent.parent / "admitted-packs"))
        )

        if path.suffix in {".yaml", ".yml"}:
            verification = verify_pack_manifest(path, path.parent)
            if verification.issues or not verification.integrity_valid:
                raise ClientV4Error(
                    "verification_failed",
                    "; ".join(sorted(issue.get("code", "?") for issue in verification.issues))
                    or "integrity invalid",
                )
            pack_id = verification.pack_id
            new_version = verification.version
            pack_digest = verification.content_digest
            files = [path]
            document = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for group in ("rule_files", "source_files", "config_files"):
                for entry in document.get(group) or []:
                    rel = entry.get("path") if isinstance(entry, Mapping) else None
                    if rel:
                        files.append(path.parent / str(rel))
        else:
            raw = path.read_bytes()
            document = _json.loads(raw.decode("utf-8"))
            if document.get("schema_version") != "jc/local-pack/1.0":
                raise ClientV4Error("verification_failed", "pack schema is not jc/local-pack/1.0")
            if not isinstance(document.get("rules"), list) or not document["rules"]:
                raise ClientV4Error("verification_failed", "pack carries no rules")
            if not isinstance(document.get("sources"), list) or not document["sources"]:
                raise ClientV4Error("verification_failed", "pack carries no declared sources")
            pack_id = str(document.get("pack_id") or path.stem)
            new_version = str(document.get("pack_version") or "1")
            digest = DigestV4.from_bytes(raw)
            pack_digest = f"sha256:{digest.hex}"
            files = [path]
        if expected_version is not None and str(expected_version) != new_version:
            raise ClientV4Error(
                "revision_conflict",
                f"expected version {expected_version!r} differs from pack version {new_version!r}",
            )

        current_path = admitted_root / pack_id / "CURRENT.json"
        old_version: str | None = None
        if current_path.is_file():
            current = _json.loads(current_path.read_text(encoding="utf-8"))
            old_version = current.get("version")
            if current.get("packDigest") == pack_digest:
                # Same payload: replay returns the sealed receipt unchanged.
                return {
                    "oldRuleVersion": current.get("oldRuleVersion"),
                    "newRuleVersion": new_version,
                    "admissionReceiptRef": current.get("admissionReceiptRef"),
                    "replay": True,
                }
            if old_version == new_version:
                raise ClientV4Error(
                    "revision_conflict",
                    "same version was already admitted with a different payload",
                )

        now = _datetime.now(_timezone.utc).isoformat()
        receipt_payload = {
            "schema_version": "jc-rule-admission/1",
            "packId": pack_id,
            "oldRuleVersion": old_version,
            "newRuleVersion": new_version,
            "packDigest": pack_digest,
            "machineDecisionRef": dict(machine_decision_ref),
            "sourceVerificationRef": admit_input.get("sourceVerificationRef"),
            "admittedAt": now,
        }
        receipt_bytes = canonical_bytes(receipt_payload)
        receipt_digest = DigestV4.from_bytes(receipt_bytes)
        receipt_ref = {
            "owner": "jc",
            "kind": "rule-admission",
            "id": receipt_digest.hex,
            "version": "1",
            "matterId": None,
            "digest": f"sha256:{receipt_digest.hex}",
        }
        pack_dir = admitted_root / pack_id / new_version
        pack_dir.mkdir(parents=True, exist_ok=True)
        for source_file in files:
            resolved = source_file.resolve()
            if path.parent.resolve() not in resolved.parents and resolved != path.resolve():
                raise ClientV4Error("verification_failed", "pack file escapes its config root")
            target = pack_dir / source_file.relative_to(path.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
            _shutil.copyfile(resolved, target)
        current_path.parent.mkdir(parents=True, exist_ok=True)
        current_path.write_text(_json.dumps({
            "version": new_version,
            "packDigest": pack_digest,
            "oldRuleVersion": old_version,
            "admissionReceiptRef": receipt_ref,
            "admittedAt": now,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "oldRuleVersion": old_version,
            "newRuleVersion": new_version,
            "admissionReceiptRef": receipt_ref,
            "replay": False,
        }


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
