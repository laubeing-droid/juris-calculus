"""Pre-cutover WorkBuddy tombstone; no business or advisory tools remain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from compiler_core.version import MCP_PROTOCOL_VERSION, SERVER_NAME, __version__


TOOL_NAMES: tuple[str, ...] = ()
_MANIFEST = {
    "schema_version": "1.0",
    "description": "Retired WorkBuddy adapter; use the V4 MCP entrypoint after cutover.",
    "resources": {},
    "tools": {},
}


class WorkBuddyAdapter:
    """Stable zero-tool shell kept only until the atomic V4 launcher cutover."""

    def __init__(
        self,
        *,
        manifest_path: Path | None = None,
        config_root: Path | None = None,
        development: bool = False,
        state_root: Path | None = None,
    ) -> None:
        del manifest_path, config_root, development, state_root
        self.manifest = {**_MANIFEST, "resources": {}, "tools": {}}

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        del name, arguments
        return _tool_error("UNKNOWN_TOOL", "the pre-cutover WorkBuddy tool surface is retired")


def manifest_document(manifest_path: Path | None = None) -> dict[str, Any]:
    del manifest_path
    return {
        "name": SERVER_NAME,
        "version": __version__,
        "protocol_version": MCP_PROTOCOL_VERSION,
        **_MANIFEST,
    }


def run_stdio(adapter: WorkBuddyAdapter) -> None:
    """Serve a silent zero-tool MCP lifecycle until the V4 cutover replaces it."""

    initialized = False
    for raw_line in sys.stdin:
        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError:
            _write_response(_rpc_error(None, -32700, "Parse error"))
            continue
        if not _valid_rpc_shape(request):
            request_id = request.get("id") if isinstance(request, dict) else None
            _write_response(_rpc_error(request_id, -32600, "Invalid Request"))
            continue
        if "id" not in request:
            continue
        request_id = request["id"]
        method = request["method"]
        params = request.get("params", {})
        if method == "initialize":
            if initialized:
                _write_response(_rpc_error(request_id, -32600, "Initialize already completed"))
                continue
            initialized = True
            _write_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": __version__},
                },
            })
            continue
        if not initialized:
            _write_response(_rpc_error(request_id, -32002, "Server not initialized"))
            continue
        if method == "ping":
            result: dict[str, Any] = {}
        elif method == "tools/list":
            result = {"tools": []}
        elif method == "resources/list":
            result = {"resources": []}
        elif method == "tools/call":
            if not isinstance(params, dict) or not isinstance(params.get("arguments", {}), dict):
                _write_response(_rpc_error(request_id, -32602, "Invalid params"))
                continue
            output = adapter.call_tool(str(params.get("name", "")), params.get("arguments", {}))
            result = {
                "content": [{
                    "type": "text",
                    "text": json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                }],
                "structuredContent": output,
                "isError": True,
            }
        else:
            _write_response(_rpc_error(request_id, -32601, "Method not found"))
            continue
        _write_response({"jsonrpc": "2.0", "id": request_id, "result": result})


def run_smoke(manifest_path: Path | None = None) -> int:
    document = manifest_document(manifest_path)
    print(json.dumps({
        "name": document["name"],
        "version": document["version"],
        "tool_count": 0,
        "readiness_claimed": False,
        "status": "retired_pre_cutover",
    }, ensure_ascii=False, sort_keys=True))
    return 0


def _tool_error(code: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "status": "error",
        "error": {"code": code, "message": message, "retryable": False},
    }


def _valid_rpc_shape(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("jsonrpc") == "2.0"
        and isinstance(value.get("method"), str)
        and isinstance(value.get("params", {}), dict)
    )


def _rpc_error(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _write_response(value: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jc-workbuddy")
    parser.add_argument("--manifest")
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--config-root")
    parser.add_argument("--audit-out")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)
    if args.smoke:
        return run_smoke(Path(args.manifest) if args.manifest else None)
    run_stdio(WorkBuddyAdapter())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
