"""Formal MCP surface that becomes green only after the V4 server restart cutover."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
V4_TOOLS = (
    "jc_capabilities",
    "jc_evaluate",
    "jc_verify_run",
    "jc_read_artifact",
)


def _run_server(*requests: dict[str, object]) -> dict[int, dict[str, object]]:
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "w5-red", "version": "1"},
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        },
        *requests,
    ]
    completed = subprocess.run(
        [sys.executable, "-B", "mcp_server.py"],
        cwd=ROOT,
        input="".join(json.dumps(message, separators=(",", ":")) + "\n" for message in messages),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert responses and responses[0].get("id") == 1
    return {
        int(response["id"]): response
        for response in responses
        if isinstance(response.get("id"), int)
    }


def _request(request_id: int, method: str) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {},
    }


def _tools(request_id: int) -> list[dict[str, object]]:
    response = _run_server(_request(request_id, "tools/list"))[request_id]
    return response["result"]["tools"]  # type: ignore[index,return-value]


def test_tools_list_is_exact_v4_with_output_schemas() -> None:
    tools = _tools(10)
    assert tuple(tool["name"] for tool in tools) == V4_TOOLS
    for tool in tools:
        assert set(tool) >= {
            "name", "description", "inputSchema", "outputSchema", "x-jc-errorSchema",
        }


def test_verify_and_read_capabilities_are_public_and_pathless() -> None:
    by_name = {tool["name"]: tool for tool in _tools(11)}
    assert {"jc_verify_run", "jc_read_artifact"} <= set(by_name)
    for name in ("jc_verify_run", "jc_read_artifact"):
        wire = json.dumps(by_name[name]["inputSchema"], sort_keys=True)
        assert "path" not in wire.lower()


def test_blocked_and_engine_error_are_protocol_errors() -> None:
    source = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("compiler_core/mcp.py", "mcp_server.py")
    )
    assert "DecisionStatusV4.BLOCKED" in source
    assert "DecisionStatusV4.ENGINE_ERROR" in source
    assert "isError" in source


def test_formal_mcp_rejects_os_paths_before_read() -> None:
    by_name = {tool["name"]: tool for tool in _tools(12)}
    assert set(V4_TOOLS) == set(by_name)
    evaluate_schema = json.dumps(by_name["jc_evaluate"]["inputSchema"], sort_keys=True)
    assert "input_path" not in evaluate_schema
    assert "audit_out" not in evaluate_schema
    assert "config_root" not in evaluate_schema


def test_resources_are_empty_and_v3_tools_are_unavailable() -> None:
    responses = _run_server(
        _request(13, "resources/list"),
        _request(14, "tools/list"),
    )
    assert responses[13].get("result") == {"resources": []}
    names = {tool["name"] for tool in responses[14]["result"]["tools"]}  # type: ignore[index]
    assert names.isdisjoint({
        "jc_lookup_rule", "jc_analyze_strategy", "jc_analyze_similar_cases",
    })
