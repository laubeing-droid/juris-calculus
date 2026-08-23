from __future__ import annotations

from base64 import b64encode
from dataclasses import replace
import multiprocessing
from typing import Callable

import pytest

import compiler_core.backend_router as backend_module
from compiler_core.backend_router import (
    BACKEND_PROBLEM_KIND,
    BackendRouterV4,
    BackendV4Error,
)
from compiler_core.backends import (
    HORN_PROVIDER_ID,
    PROVIDER_VERSION,
    ProviderRunV4,
    provider_runtime_identity,
)
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    CanonicalTimeV4,
    ContentRefV4,
    ContractV4Error,
    ResourceLimitsV4,
    RunIdentityV4,
    SignatureEnvelopeV4,
)
from compiler_core.fact_admission import (
    FACT_ADMISSION_RECEIPT_KIND,
    RUN_IDENTITY_KIND,
    RUN_IDENTITY_SCOPE,
)
from compiler_core.legal_ir import LegalIRCompilerV4
from compiler_core.rule_packs import RULE_COMPONENT_SCOPE, RULE_PREMISE_KIND
from tests.integration.test_trust_chain import _ChainHarness, _ref


def _error_code(call: Callable[[], object]) -> str:
    with pytest.raises((BackendV4Error, ContractV4Error)) as caught:
        call()
    return caught.value.code


def _backend(rule_ids: tuple[str, ...] = ("synthetic-positive",)):
    harness = _ChainHarness()
    fact_receipt_ref, fact_ref = harness.admit_fact()
    pack = harness.verify_pack()
    compiler = LegalIRCompilerV4(
        harness.pack_verifier,
        receipt_issuer="synthetic-service-issuer",
        receipt_signer=harness._sign_receipt,
    )
    compilations = tuple(
        compiler.compile_rule(
            pack,
            rule_ref=next(
                reference
                for reference, rule in zip(pack.manifest.rule_refs, pack.rules)
                if rule.rule_id == rule_id
            ),
            run_identity_ref=harness.run_identity_ref,
            now=harness.now,
        )
        for rule_id in rule_ids
    )
    router = BackendRouterV4(
        compiler,
        harness.fact_service,
        receipt_signer=harness._sign_receipt,
    )
    return harness, compiler, router, compilations, fact_receipt_ref, fact_ref


def _execute(
    router: BackendRouterV4,
    harness: _ChainHarness,
    compilations: tuple[object, ...],
    fact_receipt_ref: ContentRefV4,
    **overrides: object,
):
    values = {
        "run_identity_ref": harness.run_identity_ref,
        "fact_admission_receipt_refs": (fact_receipt_ref,),
        "limits": ResourceLimitsV4(),
        "now": harness.now,
    }
    values.update(overrides)
    return router.execute(compilations, **values)


def _completed_run(
    provider_id: str,
    input_digest: DigestV4,
    *,
    provider_version: str = PROVIDER_VERSION,
    output: str = "baseline",
) -> ProviderRunV4:
    result = {
        "schema_version": "jc/backend-result/1.0",
        "provider_id": provider_id,
        "provider_version": provider_version,
        "input_digest": str(input_digest),
        "status": "COMPLETED",
        "outcome": "FIXPOINT",
        "outputs": {"case": output},
    }
    result_bytes = canonical_bytes(result)
    proof_bytes = canonical_bytes({
        "schema_version": "jc/backend-proof/1.0",
        "provider_id": provider_id,
        "provider_version": provider_version,
        "input_digest": str(input_digest),
        "result_digest": str(DigestV4.from_bytes(result_bytes)),
        "witness": {"case": output},
    })
    return ProviderRunV4(
        provider_id,
        provider_version,
        input_digest,
        "COMPLETED",
        0,
        result_bytes,
        proof_bytes,
    )


def _fake_completed(
    provider_id: str,
    problem_bytes: bytes,
    input_digest: DigestV4,
    *,
    deadline_ms: int,
    cancel_check: Callable[[], bool] | None,
    expected_runtime_identity: dict[str, object] | None = None,
) -> ProviderRunV4:
    del problem_bytes, deadline_ms, cancel_check, expected_runtime_identity
    return _completed_run(provider_id, input_digest)


def _alternate_run(harness: _ChainHarness) -> tuple[RunIdentityV4, ContentRefV4]:
    body = harness.run.digest_body()
    body["engine_source_commit"] = "c" * 40
    run = RunIdentityV4.from_dict({
        **body,
        "run_digest": str(digest_value(body)),
    })
    return run, harness._digest_contract(
        RUN_IDENTITY_KIND,
        RUN_IDENTITY_SCOPE,
        run,
    )


def _caller_field_is_rejected(forged_field: str) -> None:
    harness, _, router, compilations, receipt_ref, _ = _backend()
    with pytest.raises(TypeError):
        _execute(
            router,
            harness,
            compilations,
            receipt_ref,
            **{forged_field: {"status": "COMPLETED"}},
        )


def test_caller_cannot_supply_backend_features() -> None:
    _caller_field_is_rejected("features")


def test_caller_cannot_override_request_time_or_omit_verified_facts() -> None:
    harness, _, router, compilations, receipt_ref, _ = _backend()
    with pytest.raises(TypeError):
        _execute(
            router,
            harness,
            compilations,
            receipt_ref,
            decision_time=CanonicalTimeV4.parse("2030-01-01T00:00:00Z"),
        )
    assert _error_code(
        lambda: router.execute(
            compilations,
            run_identity_ref=harness.run_identity_ref,
            fact_admission_receipt_refs=(),
            limits=ResourceLimitsV4(),
            now=harness.now,
        )
    ) == "BACKEND_FACT_BINDING"


def test_caller_solver_receipt_is_rejected() -> None:
    _caller_field_is_rejected("receipt")


@pytest.mark.parametrize("origin", ("bare-copy", "foreign-compiler"))
def test_router_rejects_nonissued_or_foreign_compilation_handles(origin: str) -> None:
    harness, _, router, compilations, receipt_ref, _ = _backend()
    if origin == "bare-copy":
        supplied = (replace(compilations[0]),)
    else:
        _, _, _, supplied, _, _ = _backend()

    assert _error_code(
        lambda: _execute(router, harness, supplied, receipt_ref)
    ) == "IR_COMPILATION_HANDLE"


@pytest.mark.parametrize("origin", ("admitted-fact", "unregistered-receipt"))
def test_router_rejects_bare_or_foreign_fact_references(origin: str) -> None:
    harness, _, router, compilations, receipt_ref, fact_ref = _backend()
    supplied = (
        fact_ref
        if origin == "admitted-fact"
        else _ref(FACT_ADMISSION_RECEIPT_KIND, "foreign-receipt")
    )
    expected = "BACKEND_REF_KIND" if origin == "admitted-fact" else "ARTIFACT_NOT_FOUND"

    assert _error_code(
        lambda: _execute(router, harness, compilations, supplied)
    ) == expected


def test_translation_receipts_cannot_cross_run_identity() -> None:
    harness, _, router, compilations, receipt_ref, _ = _backend()
    _, alternate_ref = _alternate_run(harness)

    assert _error_code(
        lambda: _execute(
            router,
            harness,
            compilations,
            receipt_ref,
            run_identity_ref=alternate_ref,
        )
    ) == "BACKEND_IR_HANDLE"


def test_fact_receipt_cannot_cross_run_identity() -> None:
    harness = _ChainHarness()
    fact_receipt_ref, _ = harness.admit_fact()
    pack = harness.verify_pack()
    _, alternate_ref = _alternate_run(harness)
    compiler = LegalIRCompilerV4(
        harness.pack_verifier,
        receipt_issuer="synthetic-service-issuer",
        receipt_signer=harness._sign_receipt,
    )
    rule_ref = next(
        reference
        for reference, rule in zip(pack.manifest.rule_refs, pack.rules)
        if rule.rule_id == "synthetic-positive"
    )
    compilation = compiler.compile_rule(
        pack,
        rule_ref=rule_ref,
        run_identity_ref=alternate_ref,
        now=harness.now,
    )
    router = BackendRouterV4(
        compiler,
        harness.fact_service,
        receipt_signer=harness._sign_receipt,
    )

    assert _error_code(
        lambda: _execute(
            router,
            harness,
            (compilation,),
            fact_receipt_ref,
            run_identity_ref=alternate_ref,
        )
    ) == "FACT_RECEIPT_SCOPE"


@pytest.mark.parametrize(
    ("signer_kind", "expected"),
    (
        ("wrong-role", "TRUST_ROLE_MISMATCH"),
        ("unbound", "BACKEND_RECEIPT_SIGNATURE"),
    ),
)
def test_solver_receipt_rejects_wrong_or_unbound_signer(
    monkeypatch: pytest.MonkeyPatch,
    signer_kind: str,
    expected: str,
) -> None:
    harness, compiler, router, compilations, receipt_ref, _ = _backend()

    def signer(
        subject_digest: DigestV4,
        payload_digest: DigestV4,
        evidence_refs: tuple[ContentRefV4, ...],
        run_identity_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> SignatureEnvelopeV4:
        if signer_kind == "wrong-role":
            return harness._signature(
                "legal",
                subject_digest=subject_digest,
                payload_digest=payload_digest,
                evidence_refs=evidence_refs,
                nonce=f"wrong-backend-role-{subject_digest.hex}",
                issued_at=now,
                run_identity_ref=run_identity_ref,
            )
        return harness._sign_receipt(
            subject_digest,
            payload_digest,
            (),
            run_identity_ref,
            now,
        )

    router = BackendRouterV4(
        compiler,
        harness.fact_service,
        receipt_signer=signer,
    )
    monkeypatch.setattr(router, "_invoke_provider", _fake_completed)
    assert _error_code(
        lambda: _execute(router, harness, compilations, receipt_ref)
    ) == expected


@pytest.mark.parametrize(
    ("drift", "expected"),
    (
        ("provider", "BACKEND_PROVIDER_IDENTITY"),
        ("version", "BACKEND_PROVIDER_IDENTITY"),
        ("input", "BACKEND_PROVIDER_IDENTITY"),
        ("result", "BACKEND_PROVIDER_RESULT"),
        ("proof", "BACKEND_PROVIDER_PROOF"),
    ),
)
def test_provider_output_must_bind_identity_result_and_proof(
    drift: str,
    expected: str,
) -> None:
    problem_ref = ContentRefV4(BACKEND_PROBLEM_KIND, digest_value({"problem": "exact"}))
    run = _completed_run(HORN_PROVIDER_ID, problem_ref.digest)
    if drift == "provider":
        run = replace(run, provider_id="caller-provider")
    elif drift == "version":
        run = replace(run, provider_version="0.0.0")
    elif drift == "input":
        run = replace(run, input_digest=digest_value({"problem": "other"}))
    elif drift == "result":
        result = parse_json_document(run.result_bytes)
        assert isinstance(result, dict)
        run = replace(run, result_bytes=canonical_bytes({**result, "status": "UNKNOWN"}))
    else:
        proof = parse_json_document(run.proof_bytes)
        assert isinstance(proof, dict)
        run = replace(
            run,
            proof_bytes=canonical_bytes({
                **proof,
                "result_digest": str(digest_value({"result": "other"})),
            }),
        )

    assert _error_code(
        lambda: BackendRouterV4._validate_run(run, HORN_PROVIDER_ID, problem_ref)
    ) == expected


@pytest.mark.parametrize(
    "status",
    ("CRASHED", "UNKNOWN", "UNSUPPORTED_SEMANTICS"),
)
def test_provider_failure_status_never_becomes_completed_or_formal(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    harness, _, router, compilations, receipt_ref, _ = _backend()

    def failure(
        provider_id: str,
        problem_bytes: bytes,
        input_digest: DigestV4,
        *,
        deadline_ms: int,
        cancel_check: Callable[[], bool] | None,
        expected_runtime_identity: dict[str, object] | None = None,
    ) -> ProviderRunV4:
        del problem_bytes, deadline_ms, cancel_check, expected_runtime_identity
        return router._failure_run(provider_id, input_digest, status)

    monkeypatch.setattr(router, "_invoke_provider", failure)
    execution = _execute(router, harness, compilations, receipt_ref)[0]

    assert execution.receipt.status == status
    assert execution.receipt.exit_status != 0
    assert execution.receipt.proof_ref is None
    assert execution.completed is False
    assert getattr(execution, "formal", False) is False


def test_router_rejects_unknown_component_semantics() -> None:
    harness, _, router, _, _, _ = _backend()
    reference = harness._json(
        RULE_PREMISE_KIND,
        RULE_COMPONENT_SCOPE,
        {
            "schema_version": "jc/rule-premise/1.0",
            "rule_id": "synthetic-positive",
            "fact_key": "synthetic-positive.required-fact",
            "required": True,
            "negated": True,
        },
    )

    assert _error_code(
        lambda: router._component(
            reference,
            expected_kind=RULE_PREMISE_KIND,
            owner_rule_id="synthetic-positive",
            selected_rule_ids={"synthetic-positive"},
        )
    ) == "BACKEND_COMPONENT_SCHEMA"


def test_router_rejects_fact_receipts_from_multiple_case_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, _, router, compilations, receipt_ref, _ = _backend()
    foreign_ref = _ref(FACT_ADMISSION_RECEIPT_KIND, "other-case")
    original = router._fact

    def fact(
        reference: ContentRefV4,
        run: RunIdentityV4,
        run_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> dict[str, object]:
        row = original(receipt_ref, run, run_ref, now)
        if reference == foreign_ref:
            row = {**row, "case_scope": "other-case"}
        return row

    monkeypatch.setattr(router, "_fact", fact)
    assert _error_code(
        lambda: _execute(
            router,
            harness,
            compilations,
            receipt_ref,
            fact_admission_receipt_refs=(receipt_ref, foreign_ref),
        )
    ) == "BACKEND_FACT_BINDING"


def _minimal_horn_problem() -> bytes:
    def ref(kind: str, label: str) -> dict[str, str]:
        return _ref(kind, label).to_dict()

    return canonical_bytes({
        "schema_version": "jc/backend-problem/1.0",
        "provider_id": HORN_PROVIDER_ID,
        "run_identity_ref": ref("run-identity-v4", "security-run"),
        "request_ref": ref("case-request-v4", "security-request"),
        "case_scope": "security-case",
        "limits_ref": ref("backend-limits-v4", "security-limits"),
        "decision_time": "2026-08-22T11:00:00Z",
        "seed": 0,
        "features": {
            "conflict_structure": False,
            "temporal_constraints": False,
            "numeric_constraints": False,
        },
        "facts": [],
        "clauses": [{
            "ivl_id": "security-probe",
            "ivl_ref": ref("legal-ivl-v4", "security-probe"),
            "rule_ref": ref("rule-v4", "security-probe"),
            "translation_receipt_refs": [
                ref("rule-to-spec-receipt", "security-probe"),
                ref("spec-to-ivl-receipt", "security-probe"),
            ],
            "premise_refs": [],
            "premises": [],
            "conclusion_ref": ref("rule-conclusion", "security-probe"),
            "conclusion": {
                "schema_version": "jc/rule-conclusion/1.0",
                "rule_id": "security-probe",
                "fact_key": "security-probe",
            },
            "derivation_refs": [
                ref("legal-ir-proof-obligation", "security-probe")
            ],
            "modality": "CONSTITUTIVE",
            "effective_from": "2022-01-01T00:00:00Z",
            "effective_to": None,
            "relations": [],
            "temporal_constraints": [],
            "numeric_constraints": [],
        }],
    })


def _new_child_pids(before: set[int | None]) -> set[int | None]:
    return {
        child.pid
        for child in multiprocessing.active_children()
        if child.pid not in before and child.is_alive()
    }


def _runtime_identity() -> dict[str, object]:
    binary, package, inputs = provider_runtime_identity()
    return {
        "provider_binary_digest": str(binary),
        "provider_package_digest": str(package),
        "provider_build_inputs": inputs,
    }


def _provider_wire(run: ProviderRunV4, identity: dict[str, object]) -> bytes:
    return canonical_bytes({
        "schema_version": "jc/backend-provider-wire/1.0",
        "outcome": "completed",
        "runtime_identity": identity,
        "run": {
            "provider_id": run.provider_id,
            "provider_version": run.provider_version,
            "input_digest": str(run.input_digest),
            "status": run.status,
            "exit_status": run.exit_status,
            "result_base64": b64encode(run.result_bytes).decode("ascii"),
            "proof_base64": (
                None
                if run.proof_bytes is None
                else b64encode(run.proof_bytes).decode("ascii")
            ),
        },
        "error_code": None,
    })


class _FakePipeEnd:
    def __init__(self, raw: bytes | None = None, error: OSError | None = None) -> None:
        self.raw = raw
        self.error = error
        self.closed = False

    def poll(self, timeout: float) -> bool:
        del timeout
        return True

    def recv_bytes(self, maxlength: int) -> bytes:
        if self.error is not None:
            raise self.error
        assert self.raw is not None and len(self.raw) <= maxlength
        return self.raw

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, *, resist_kill: bool = False) -> None:
        self.pid: int | None = None
        self.alive = False
        self.resist_kill = resist_kill
        self.killed = False
        self.joined = False

    def start(self) -> None:
        self.pid = 4242
        self.alive = True

    def is_alive(self) -> bool:
        return self.alive

    def kill(self) -> None:
        self.killed = True
        if not self.resist_kill:
            self.alive = False

    def join(self, timeout: float) -> None:
        del timeout
        self.joined = True


class _FakeContext:
    def __init__(self, receiver: _FakePipeEnd, process: _FakeProcess) -> None:
        self.receiver = receiver
        self.sender = _FakePipeEnd()
        self.process = process

    def Pipe(self, *, duplex: bool):
        assert duplex is False
        return self.receiver, self.sender

    def Process(self, *, target, args, daemon: bool):
        del target, args
        assert daemon is True
        return self.process


def test_actual_provider_timeout_terminates_child_and_fails_closed() -> None:
    _, _, router, _, _, _ = _backend()
    problem = _minimal_horn_problem()
    before = {child.pid for child in multiprocessing.active_children()}

    run = router._invoke_provider(
        HORN_PROVIDER_ID,
        problem,
        DigestV4.from_bytes(problem),
        deadline_ms=1,
        cancel_check=None,
    )

    assert run.status == "TIMEOUT" and run.exit_status == 124
    assert run.proof_bytes is None
    assert _new_child_pids(before) == set()


def test_actual_provider_cancellation_terminates_child_and_fails_closed() -> None:
    _, _, router, _, _, _ = _backend()
    problem = _minimal_horn_problem()
    checks = 0

    def cancel_after_spawn() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    before = {child.pid for child in multiprocessing.active_children()}
    run = router._invoke_provider(
        HORN_PROVIDER_ID,
        problem,
        DigestV4.from_bytes(problem),
        deadline_ms=1_000,
        cancel_check=cancel_after_spawn,
    )

    assert checks >= 2
    assert run.status == "CANCELLED" and run.exit_status == 130
    assert run.proof_bytes is None
    assert _new_child_pids(before) == set()


def test_provider_child_runtime_identity_drift_fails_closed_and_cleans_up() -> None:
    _, _, router, _, _, _ = _backend()
    problem = _minimal_horn_problem()
    before = {child.pid for child in multiprocessing.active_children()}

    run = router._invoke_provider(
        HORN_PROVIDER_ID,
        problem,
        DigestV4.from_bytes(problem),
        deadline_ms=10_000,
        cancel_check=None,
        expected_runtime_identity={
            "provider_binary_digest": str(digest_value({"wrong": "binary"})),
            "provider_package_digest": str(digest_value({"wrong": "package"})),
            "provider_build_inputs": {},
        },
    )

    assert run.status == "CRASHED" and run.proof_bytes is None
    assert _new_child_pids(before) == set()


def test_oversized_provider_message_fails_closed_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, router, _, _, _ = _backend()
    process = _FakeProcess()
    context = _FakeContext(
        _FakePipeEnd(error=OSError("message exceeds maxlength")), process
    )
    monkeypatch.setattr(
        backend_module.multiprocessing, "get_context", lambda method: context
    )
    problem = _minimal_horn_problem()

    run = router._invoke_provider(
        HORN_PROVIDER_ID,
        problem,
        DigestV4.from_bytes(problem),
        deadline_ms=1_000,
        cancel_check=None,
        expected_runtime_identity=_runtime_identity(),
    )

    assert run.status == "CRASHED" and run.proof_bytes is None
    assert process.killed and process.joined and not process.is_alive()


def test_provider_result_received_after_deadline_is_not_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, router, _, _, _ = _backend()
    problem = _minimal_horn_problem()
    input_digest = DigestV4.from_bytes(problem)
    identity = _runtime_identity()
    process = _FakeProcess()
    context = _FakeContext(
        _FakePipeEnd(_provider_wire(_completed_run(HORN_PROVIDER_ID, input_digest), identity)),
        process,
    )
    ticks = iter((0, 0, 1_000_000))
    monkeypatch.setattr(
        backend_module.multiprocessing, "get_context", lambda method: context
    )
    monkeypatch.setattr(backend_module.time, "monotonic_ns", lambda: next(ticks))

    run = router._invoke_provider(
        HORN_PROVIDER_ID,
        problem,
        input_digest,
        deadline_ms=1,
        cancel_check=None,
        expected_runtime_identity=identity,
    )

    assert run.status == "TIMEOUT" and run.proof_bytes is None
    assert process.killed and process.joined and not process.is_alive()


def test_provider_cleanup_postcheck_overrides_a_completed_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, router, _, _, _ = _backend()
    problem = _minimal_horn_problem()
    input_digest = DigestV4.from_bytes(problem)
    identity = _runtime_identity()
    process = _FakeProcess(resist_kill=True)
    context = _FakeContext(
        _FakePipeEnd(_provider_wire(_completed_run(HORN_PROVIDER_ID, input_digest), identity)),
        process,
    )
    monkeypatch.setattr(
        backend_module.multiprocessing, "get_context", lambda method: context
    )

    run = router._invoke_provider(
        HORN_PROVIDER_ID,
        problem,
        input_digest,
        deadline_ms=1_000,
        cancel_check=None,
        expected_runtime_identity=identity,
    )

    assert run.status == "CRASHED" and run.proof_bytes is None
    assert process.killed and process.joined and process.is_alive()


def test_replay_rejects_semantically_different_provider_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, _, router, compilations, receipt_ref, _ = _backend()
    monkeypatch.setattr(router, "_invoke_provider", _fake_completed)
    execution = _execute(router, harness, compilations, receipt_ref)[0]

    def changed(
        provider_id: str,
        problem_bytes: bytes,
        input_digest: DigestV4,
        *,
        deadline_ms: int,
        cancel_check: Callable[[], bool] | None,
        expected_runtime_identity: dict[str, object] | None = None,
    ) -> ProviderRunV4:
        del problem_bytes, deadline_ms, cancel_check, expected_runtime_identity
        return _completed_run(provider_id, input_digest, output="changed")

    monkeypatch.setattr(router, "_invoke_provider", changed)
    assert _error_code(
        lambda: router.replay(execution, now=harness.now)
    ) == "BACKEND_REPLAY_MISMATCH"


def test_replay_rechecks_the_exact_solver_signature_evidence_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, _, router, compilations, receipt_ref, _ = _backend()
    monkeypatch.setattr(router, "_invoke_provider", _fake_completed)
    execution = _execute(router, harness, compilations, receipt_ref)[0]
    signature = execution.receipt.signature
    forged_signature = replace(
        signature,
        evidence_refs=signature.evidence_refs[:-1],
    )
    forged_receipt = replace(execution.receipt, signature=forged_signature)
    forged_execution = replace(execution, receipt=forged_receipt)
    original_resolve = router._resolve_json

    def resolve(
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
    ) -> dict[str, object]:
        if reference == forged_execution.receipt_ref:
            return forged_receipt.to_dict()
        return original_resolve(reference, kind=kind, scope=scope)

    monkeypatch.setattr(router, "_resolve_json", resolve)
    assert _error_code(
        lambda: router.replay(forged_execution, now=harness.now)
    ) == "BACKEND_RECEIPT_SIGNATURE"


def test_replay_rejects_current_provider_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, _, router, compilations, receipt_ref, _ = _backend()
    monkeypatch.setattr(router, "_invoke_provider", _fake_completed)
    execution = _execute(router, harness, compilations, receipt_ref)[0]
    _, package_digest, build_inputs = backend_module.provider_runtime_identity()
    monkeypatch.setattr(
        backend_module,
        "provider_runtime_identity",
        lambda: (digest_value({"binary": "drift"}), package_digest, build_inputs),
    )

    assert _error_code(
        lambda: router.replay(execution, now=harness.now)
    ) == "BACKEND_PROVIDER_IDENTITY"
