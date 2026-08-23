"""Executable CLI, Python client, and MCP parity over the V4 state matrix."""

from __future__ import annotations

from dataclasses import dataclass
import errno
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

import compiler_core.application as application_module
from compiler_core import cli
from compiler_core.application import ApplicationV4, ApplicationV4Error
from compiler_core.audit_bundle import AuditBundleStoreV4
from compiler_core.backend_router import BackendV4Error
from compiler_core.canonical_serialization import DigestV4
from compiler_core.client import JCClient
from compiler_core.contracts import (
    CanonicalTimeV4,
    CaseRequestV4,
    CertificateKindV4,
    ContentRefV4,
    ContractV4Error,
    DecisionStatusV4,
    ExecutionStatusV4,
    LegalContextV4,
    MCPEvaluateInputV4,
    MCPEvaluateOutputV4,
)
from compiler_core.mcp import MCPServerV4, run_stdio
from tests.contract.test_application import (
    _application,
    _nonformal_attestation,
    _register_request_and_run,
    _rule_ref,
)
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


ROOT = Path(__file__).resolve().parents[2]
HANDLE_EXPIRY = CanonicalTimeV4("2027-01-01T00:00:00Z")
PRIVATE_CANARY = r"D:\private\client\case.txt SECRET_W5_06"


@dataclass(frozen=True)
class _Scenario:
    harness: _ChainHarness
    application: ApplicationV4
    store: AuditBundleStoreV4
    request: CaseRequestV4
    request_ref: ContentRefV4
    run_ref: ContentRefV4


def _scenario(
    tmp_path: Path,
    case: str,
    monkeypatch: pytest.MonkeyPatch,
) -> _Scenario:
    harness = _ChainHarness()
    request = harness.request
    request_ref = harness.request_ref
    run_ref = harness.run_identity_ref

    if case in {"hypothetical", "review"}:
        expected = (
            DecisionStatusV4.HYPOTHETICAL_RESULT
            if case == "hypothetical"
            else DecisionStatusV4.REVIEW_ONLY_RESULT
        )
        attestation_ref = _nonformal_attestation(
            harness,
            dispute_state="UNDISPUTED" if case == "hypothetical" else "DISPUTED",
            assumption_state="USER_ASSUMED" if case == "hypothetical" else "NONE",
            label=expected.value,
        )
        request, request_ref, _, run_ref = _register_request_and_run(
            harness,
            attestation_refs=(attestation_ref,),
        )
    elif case == "missing":
        request, request_ref, _, run_ref = _register_request_and_run(
            harness,
            attestation_refs=(),
            proposal_refs=(_rule_ref(harness, "synthetic-missing-disputed"),),
        )
    elif case == "unknown":
        request, request_ref, _, run_ref = _register_request_and_run(
            harness,
            attestation_refs=(),
        )
    elif case == "admission_blocked":
        request, request_ref, _, run_ref = _register_request_and_run(
            harness,
            attestation_refs=(),
            legal_context=LegalContextV4("TEST", "not-the-signed-law"),
        )

    application, store, router = _application(tmp_path, harness)
    if case == "conflict":
        def conflict(_execution, checked):
            return application_module._ArgumentOutcome(
                "disputed",
                (),
                (checked.receipt.argument_graph_ref,),
                (ContentRefV4("attack-v4", DigestV4.from_bytes(b"w5-06-conflict")),),
                (),
                (),
            )

        monkeypatch.setattr(application, "_argument_outcome", conflict)
    elif case in {"resource_exhausted", "engine_error"}:
        code = (
            "BACKEND_RESOURCE_EXHAUSTED"
            if case == "resource_exhausted"
            else "BACKEND_W5_06_FAULT"
        )

        def fail(*_args, **_kwargs):
            raise BackendV4Error(code, PRIVATE_CANARY)

        monkeypatch.setattr(router, "execute", fail)
    elif case == "cancelled":
        cancelled = application.evaluate(
            request_ref,
            run_ref,
            case_scope=CASE_SCOPE,
            cancel_check=lambda: True,
        )
        monkeypatch.setattr(application, "evaluate", lambda *_args, **_kwargs: cancelled)

    return _Scenario(harness, application, store, request, request_ref, run_ref)


def _client(scenario: _Scenario) -> JCClient:
    def context(request: CaseRequestV4):
        assert request.canonical_digest() == scenario.request.canonical_digest()
        return scenario.request_ref, scenario.run_ref, CASE_SCOPE

    def mcp_output(envelope) -> MCPEvaluateOutputV4:
        capability = scenario.store.capability_for(envelope.result.run_identity_ref)
        verified = scenario.store.verify_run(capability, now=scenario.harness.now)

        def handle(name: str):
            return scenario.store.issue_artifact_handle(
                capability,
                name,
                now=scenario.harness.now,
                expires_at=HANDLE_EXPIRY,
                max_bytes=len(verified.files[name]),
                signer=scenario.harness._sign_receipt,
            )

        return MCPEvaluateOutputV4(
            envelope.result,
            handle("certificate.json"),
            handle("manifest.json"),
            (handle("result.json"),),
        )

    return JCClient(
        scenario.application,
        scenario.store,
        clock=lambda: scenario.harness.now,
        evaluation_context=context,
        mcp_output_factory=mcp_output,
    )


def _stdio_tool(
    monkeypatch: pytest.MonkeyPatch,
    server: MCPServerV4,
    name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    requests = (
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    stdin = io.StringIO("".join(json.dumps(item) + "\n" for item in requests))
    stdout = io.StringIO()
    with monkeypatch.context() as transport:
        transport.setattr(sys, "stdin", stdin)
        transport.setattr(sys, "stdout", stdout)
        run_stdio(server)
    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["id"] == 1
    assert responses[1]["id"] == 2
    return responses[1]["result"]


@pytest.mark.parametrize(
    ("case", "decision", "execution", "exit_code", "certificate_kind"),
    (
        ("formal", DecisionStatusV4.ACCEPTED_FORMAL_RESULT, ExecutionStatusV4.COMPLETED, 0, CertificateKindV4.FORMAL_VERIFIED),
        ("hypothetical", DecisionStatusV4.HYPOTHETICAL_RESULT, ExecutionStatusV4.COMPLETED, 0, CertificateKindV4.NONE),
        ("review", DecisionStatusV4.REVIEW_ONLY_RESULT, ExecutionStatusV4.COMPLETED, 0, CertificateKindV4.NONE),
        ("missing", DecisionStatusV4.MISSING_REQUIRED_FACT, ExecutionStatusV4.COMPLETED, 0, CertificateKindV4.NONE),
        ("conflict", DecisionStatusV4.CONFLICT_CERTIFICATE, ExecutionStatusV4.COMPLETED, 0, CertificateKindV4.CONFLICT_VERIFIED),
        ("unknown", DecisionStatusV4.UNKNOWN, ExecutionStatusV4.COMPLETED, 0, CertificateKindV4.NONE),
        ("admission_blocked", DecisionStatusV4.BLOCKED, ExecutionStatusV4.ADMISSION_BLOCKED, 3, CertificateKindV4.NONE),
        ("resource_exhausted", DecisionStatusV4.BLOCKED, ExecutionStatusV4.RESOURCE_EXHAUSTED, 3, CertificateKindV4.NONE),
        ("cancelled", DecisionStatusV4.BLOCKED, ExecutionStatusV4.CANCELLED, 3, CertificateKindV4.NONE),
        ("engine_error", DecisionStatusV4.ENGINE_ERROR, ExecutionStatusV4.ENGINE_ERROR, 4, CertificateKindV4.NONE),
    ),
)
def test_canonical_result_matrix_across_cli_client_and_stdio_mcp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: str,
    decision: DecisionStatusV4,
    execution: ExecutionStatusV4,
    exit_code: int,
    certificate_kind: CertificateKindV4,
) -> None:
    scenario = _scenario(tmp_path, case, monkeypatch)
    client = _client(scenario)
    envelope = client.evaluate(scenario.request)
    assert envelope.result.decision_status is decision
    assert envelope.result.execution_status is execution
    assert envelope.certificate.kind is certificate_kind
    assert PRIVATE_CANARY not in envelope.canonical_bytes().decode("utf-8")

    capability = scenario.store.capability_for(envelope.result.run_identity_ref)
    assert client.verify_run(capability).result == envelope.result
    monkeypatch.setattr(client, "evaluate", lambda *_args, **_kwargs: envelope)

    input_path = tmp_path / "request.json"
    input_path.write_bytes(scenario.request.canonical_bytes())
    assert cli.main(
        ["evaluate", "--input", str(input_path), "--json"], client=client,
    ) == exit_code
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result["result"] == envelope.result.to_dict()
    assert cli_result["certificate"]["kind"] == certificate_kind.value

    server = MCPServerV4(client)
    evaluated = _stdio_tool(
        monkeypatch,
        server,
        "jc_evaluate",
        MCPEvaluateInputV4(scenario.request, None).to_dict(),
    )
    assert evaluated["isError"] is (decision in {DecisionStatusV4.BLOCKED, DecisionStatusV4.ENGINE_ERROR})
    structured = evaluated["structuredContent"]
    assert structured["result"] == envelope.result.to_dict()
    for handle in (
        structured["certificate_handle"],
        structured["run_handle"],
        *structured["artifact_handles"],
    ):
        assert 0 < handle["max_bytes"] <= handle["size_bytes"]
        assert "path" not in json.dumps(handle).lower()

    verified = _stdio_tool(
        monkeypatch,
        server,
        "jc_verify_run",
        {"run_handle": structured["run_handle"], "offline_replay": False},
    )
    assert verified["isError"] is False
    assert verified["structuredContent"]["verification"]["status"] == "VERIFIED"

    handle_path = tmp_path / "run-handle.json"
    handle_path.write_text(json.dumps(structured["run_handle"]), encoding="utf-8")
    assert cli.main(
        ["verify", "--input", str(handle_path), "--json"], client=client,
    ) == 0
    assert json.loads(capsys.readouterr().out)["verification"]["status"] == "VERIFIED"


def test_contract_error_code_is_identical_across_entrypoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenario = _scenario(tmp_path, "formal", monkeypatch)
    client = _client(scenario)
    with pytest.raises(ContractV4Error) as caught:
        client.evaluate({})

    input_path = tmp_path / "invalid.json"
    input_path.write_text("{}", encoding="utf-8")
    assert cli.main(
        ["evaluate", "--input", str(input_path), "--json"], client=client,
    ) == cli.EXIT_INPUT_ERROR
    cli_error = json.loads(capsys.readouterr().err)
    mcp_error = _stdio_tool(
        monkeypatch,
        MCPServerV4(client),
        "jc_evaluate",
        {"request": {}, "request_handle": None},
    )
    assert mcp_error["isError"] is True
    assert cli_error["code"] == caught.value.code
    assert mcp_error["structuredContent"]["error"]["code"] == caught.value.code


def test_storage_error_is_typed_retryable_redacted_and_uncommitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenario = _scenario(tmp_path, "formal", monkeypatch)
    client = _client(scenario)

    def fail(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, PRIVATE_CANARY)

    monkeypatch.setattr(scenario.store, "_write_file", fail)
    with pytest.raises(ApplicationV4Error) as caught:
        client.evaluate(scenario.request)
    failure = caught.value
    assert (failure.code, failure.stage, failure.retryable) == (
        "STORAGE_CAPACITY", "audit", True,
    )
    assert PRIVATE_CANARY not in str(failure)
    assert not list((tmp_path / "state").rglob("COMPLETE"))
    assert not list((tmp_path / "state").rglob("certificate.json"))

    def raise_failure(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(client, "evaluate", raise_failure)
    input_path = tmp_path / "request.json"
    input_path.write_bytes(scenario.request.canonical_bytes())
    assert cli.main(
        ["evaluate", "--input", str(input_path), "--json"], client=client,
    ) == cli.EXIT_ENGINE_ERROR
    cli_error = json.loads(capsys.readouterr().err)
    mcp_error = _stdio_tool(
        monkeypatch,
        MCPServerV4(client),
        "jc_evaluate",
        MCPEvaluateInputV4(scenario.request, None).to_dict(),
    )
    assert (cli_error["code"], cli_error["stage"], cli_error["retryable"]) == (
        "STORAGE_CAPACITY", "audit", True,
    )
    assert mcp_error["isError"] is True
    assert (
        mcp_error["structuredContent"]["error"]["code"],
        mcp_error["structuredContent"]["error"]["stage"],
        mcp_error["structuredContent"]["error"]["retryable"],
    ) == ("STORAGE_CAPACITY", "audit", True)
    wire = json.dumps((cli_error, mcp_error), ensure_ascii=False)
    assert PRIVATE_CANARY not in wire
    assert str(tmp_path.resolve()) not in wire


def test_source_tree_stdio_launcher_returns_typed_pathless_runtime_error() -> None:
    request = _ChainHarness().request
    messages = (
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "jc_evaluate",
                "arguments": MCPEvaluateInputV4(request, None).to_dict(),
            },
        },
    )
    completed = subprocess.run(
        [sys.executable, "-B", "mcp_server.py"],
        cwd=ROOT,
        input="".join(json.dumps(item) + "\n" for item in messages),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    tool = responses[1]["result"]
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert tool["isError"] is True
    assert tool["structuredContent"]["error"]["code"] == "RUNTIME_NOT_CONFIGURED"
    wire = json.dumps(tool).lower()
    assert "input_path" not in wire
    assert "audit_out" not in wire
    assert str(ROOT).lower() not in wire
