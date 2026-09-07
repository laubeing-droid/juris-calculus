"""G03: V5 profile requests expose the same semantics from every entry.

Python client, executable CLI and stdio MCP share one ApplicationV4 spine;
this test proves the V5 completeness semantics (complete answers versus
mapping-blocked partial answers) surface identically from all three with no
bypass. The CLI and MCP legs reuse the sealed envelope of the Python leg, so
the comparison covers the adapters, not a re-run of the admission chain.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from compiler_core import cli
from compiler_core.canonical_serialization import digest_value
from compiler_core.client import JCClient
from compiler_core.contracts import (
    CanonicalTimeV4,
    CaseInputBundleV4,
    MCPEvaluateInputV4,
)
from compiler_core.mcp import MCPServerV4, run_stdio

from tests.contract.test_v5_profile_chain import (
    EXCEPTION_FACTS,
    _application,
    _seed_with_v5,
    _v5_inputs,
)
from tests.contract.test_v5_final_remediation import PRIORITY_CONDITION_FACT
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness

HANDLE_EXPIRY = CanonicalTimeV4("2027-01-01T00:00:00Z")


def _v5_bundle(request) -> CaseInputBundleV4:
    body = {
        "schema_version": "jc/case-input-bundle/1.0",
        "bundle_id": f"v5-{request.request_id}",
        "request": request.to_dict(),
        "artifacts": [],
    }
    return CaseInputBundleV4.from_dict({
        **body, "bundle_digest": str(digest_value(body)),
    })


def _scenario(tmp_path: Path, extra_facts: tuple[str, ...]):
    harness = _ChainHarness()
    policy, queries, _claim = _v5_inputs(harness, profiles=("grounded",))
    seed, request_ref, _, run_ref = _seed_with_v5(
        harness, policy=policy, queries=queries, extra_fact_keys=extra_facts,
    )
    application, store = _application(tmp_path, harness)

    from contextlib import contextmanager

    @contextmanager
    def evaluation_context(bundle: CaseInputBundleV4):
        application._resolver.validate_case_bundle(bundle)
        yield request_ref, run_ref, CASE_SCOPE

    def mcp_output(envelope):
        capability = store.capability_for(envelope.result.run_identity_ref)
        verified = store.verify_run(capability, now=harness.now)

        def handle(name: str):
            return store.issue_artifact_handle(
                capability,
                name,
                now=harness.now,
                expires_at=HANDLE_EXPIRY,
                max_bytes=len(verified.files[name]),
                signer=harness._sign_receipt,
            )

        from compiler_core.contracts import MCPEvaluateOutputV4

        return MCPEvaluateOutputV4(
            envelope.result,
            handle("certificate.json"),
            handle("manifest.json"),
            (handle("result.json"),),
        )

    client = JCClient(
        application,
        store,
        clock=lambda: harness.now,
        evaluation_context=evaluation_context,
        mcp_output_factory=mcp_output,
    )
    return seed, client


def _stdio_tool(monkeypatch, server, name, arguments) -> dict:
    requests = (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": name, "arguments": arguments}},
    )
    stdin = io.StringIO("".join(json.dumps(item) + "\n" for item in requests))
    stdout = io.StringIO()
    with monkeypatch.context() as transport:
        transport.setattr(sys, "stdin", stdin)
        transport.setattr(sys, "stdout", stdout)
        run_stdio(server)
    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[1]["id"] == 2
    return responses[1]["result"]


@pytest.mark.parametrize(
    ("fact_keys", "expected_completeness", "expected_reason"),
    (
        (EXCEPTION_FACTS, "complete", ()),
        (
            EXCEPTION_FACTS + (PRIORITY_CONDITION_FACT,),
            "partial",
            ("v5_mapping_incomplete",),
        ),
    ),
)
def test_v5_semantics_are_identical_across_three_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fact_keys: tuple[str, ...],
    expected_completeness: str,
    expected_reason: tuple[str, ...],
) -> None:
    seed, client = _scenario(tmp_path, fact_keys)
    bundle = _v5_bundle(seed)

    envelope = client.evaluate(bundle)
    assert envelope.transport_outcome.status == "success"
    assert envelope.result.completeness_state.value == expected_completeness
    assert expected_reason <= tuple(envelope.result.decision_reason_codes)

    # CLI leg: same bundle, same sealed answer.
    input_path = tmp_path / "request.json"
    input_path.write_bytes(bundle.canonical_bytes())
    monkeypatch.setattr(client, "evaluate", lambda *_a, **_k: envelope)
    assert cli.main(
        ["evaluate", "--input", str(input_path), "--json"], client=client,
    ) == 0
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result["result"]["completeness_state"] == expected_completeness
    assert cli_result["result"]["decision_reason_codes"] == (
        list(envelope.result.decision_reason_codes)
    )

    # MCP leg: the structured content carries the identical result.
    server = MCPServerV4(client)
    evaluated = _stdio_tool(
        monkeypatch, server, "jc_evaluate", MCPEvaluateInputV4(bundle).to_dict(),
    )
    assert evaluated["isError"] is False
    structured = evaluated["structuredContent"]
    assert structured["result"]["completeness_state"] == expected_completeness
    assert structured["result"]["decision_reason_codes"] == (
        list(envelope.result.decision_reason_codes)
    )
    assert structured["result"]["decision_status"] == (
        envelope.result.decision_status.value
    )
