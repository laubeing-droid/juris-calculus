"""V4 MCP ToolSpec authority, typed codecs, and deterministic publications.

Runtime code builds tool metadata from the in-wheel typed contracts below.  It
does not read ``mcp_manifest.json`` or a repository path.  The committed Schema
and manifest are byte-for-byte publications of these pure functions.
"""
from __future__ import annotations

from dataclasses import MISSING, fields
from enum import Enum
import json
import re
import sys
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

import compiler_core.contracts as _contracts
from compiler_core.application import ApplicationV4Error
from compiler_core.audit_bundle import AuditBundleV4Error
from compiler_core.canonical_serialization import (
    DIGEST_PATTERN,
    SAFE_INTEGER_MAX,
    SAFE_INTEGER_MIN,
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    DecisionStatusV4,
    ErrorV4,
    MCPCapabilitiesErrorV4,
    MCPEvaluateErrorV4,
    MCPEvaluateInputV4,
    MCPReadArtifactErrorV4,
    MCPReadArtifactInputV4,
    MCPVerifyRunErrorV4,
    MCPVerifyRunInputV4,
    ContractV4Error,
    ToolSpecV4,
    V4Contract,
    V4_OBJECT_REGISTRY,
    V4_TYPE_REGISTRY,
)
from compiler_core.client import ClientV4Error, JCClient
from compiler_core.version import MCP_PROTOCOL_VERSION, SERVER_NAME, __version__


JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
JSON_SCHEMA_ID = "https://juris-calculus.local/schemas/jc-v4.schema.json"

TOOL_SPECS: tuple[ToolSpecV4, ...] = (
    ToolSpecV4(
        name="jc_capabilities",
        description=(
            "Return host-neutral V4 build, contract, pack, trust, storage, "
            "and readiness metadata."
        ),
        input_type="MCPCapabilitiesInputV4",
        output_type="MCPCapabilitiesOutputV4",
        error_type="MCPCapabilitiesErrorV4",
    ),
    ToolSpecV4(
        name="jc_evaluate",
        description="Evaluate one complete bounded V4 case input bundle.",
        input_type="MCPEvaluateInputV4",
        output_type="MCPEvaluateOutputV4",
        error_type="MCPEvaluateErrorV4",
    ),
    ToolSpecV4(
        name="jc_verify_run",
        description="Verify a signed run capability and optionally replay it offline.",
        input_type="MCPVerifyRunInputV4",
        output_type="MCPVerifyRunOutputV4",
        error_type="MCPVerifyRunErrorV4",
    ),
    ToolSpecV4(
        name="jc_read_artifact",
        description="Read a bounded byte range through a signed artifact capability.",
        input_type="MCPReadArtifactInputV4",
        output_type="MCPReadArtifactOutputV4",
        error_type="MCPReadArtifactErrorV4",
    ),
)


def _validate_tool_specs() -> None:
    names: set[str] = set()
    for spec in TOOL_SPECS:
        if not spec.name or not spec.description or spec.name in names:
            raise ContractV4Error("MCP_TOOL_SPEC", "tool names and descriptions must be unique")
        names.add(spec.name)
        for type_name in (spec.input_type, spec.output_type, spec.error_type):
            if type_name not in V4_OBJECT_REGISTRY:
                raise ContractV4Error(
                    "MCP_TOOL_SPEC",
                    f"{spec.name} references unknown object contract {type_name!r}",
                )


_validate_tool_specs()


def _tool_spec(tool_name: str) -> ToolSpecV4:
    if type(tool_name) is not str:
        raise ContractV4Error("MCP_TOOL", "tool name must be a string")
    for spec in TOOL_SPECS:
        if spec.name == tool_name:
            return spec
    raise ContractV4Error("MCP_TOOL", f"unknown V4 MCP tool {tool_name!r}")


def _channel_type(spec: ToolSpecV4, channel: str) -> str:
    if channel == "input":
        return spec.input_type
    if channel == "output":
        return spec.output_type
    if channel == "error":
        return spec.error_type
    raise ContractV4Error("MCP_CHANNEL", "channel must be input, output, or error")


def decode_tool_payload(tool_name: str, channel: str, payload: object) -> V4Contract:
    """Decode one MCP payload through the class named by the sole ToolSpec."""

    contract_type = V4_OBJECT_REGISTRY[_channel_type(_tool_spec(tool_name), channel)]
    if type(payload) is not dict:
        raise ContractV4Error("TYPE_MISMATCH", "MCP payload must be an object")
    return contract_type.from_dict(payload)


def decode_tool_json(
    tool_name: str,
    channel: str,
    raw_json: str | bytes | bytearray,
) -> V4Contract:
    """Strictly parse raw JSON before applying the ToolSpec-selected codec."""

    return decode_tool_payload(tool_name, channel, parse_json_document(raw_json))


def _json_schema_pattern(pattern: str) -> str:
    translated = re.sub(r"\(\?P<[^>]+>", "(?:", pattern)
    if translated.endswith(r"\Z"):
        translated = translated[:-2] + "$"
    if not translated.startswith("^"):
        translated = "^" + translated
    return translated


def _annotation_schema(annotation: object) -> dict[str, object]:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        choices = get_args(annotation)
        non_null = tuple(choice for choice in choices if choice is not type(None))
        if len(non_null) != 1 or type(None) not in choices:
            raise TypeError(f"unsupported V4 schema union {annotation!r}")
        return {"anyOf": [_annotation_schema(non_null[0]), {"type": "null"}]}
    if origin is tuple:
        args = get_args(annotation)
        if len(args) != 2 or args[1] is not Ellipsis:
            raise TypeError(f"unsupported V4 tuple annotation {annotation!r}")
        return {"type": "array", "items": _annotation_schema(args[0])}
    if annotation is DigestV4:
        return {"$ref": "#/$defs/DigestV4"}
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return {"$ref": f"#/$defs/{annotation.__name__}"}
    if isinstance(annotation, type) and issubclass(annotation, V4Contract):
        return {"$ref": f"#/$defs/{annotation.__name__}"}
    if annotation is str:
        return {"type": "string"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is int:
        return {
            "type": "integer",
            "minimum": SAFE_INTEGER_MIN,
            "maximum": SAFE_INTEGER_MAX,
            "x-jc-integer-token": True,
        }
    raise TypeError(f"unsupported V4 schema annotation {annotation!r}")


def _field_schema(
    contract_type: type[V4Contract],
    field_name: str,
    annotation: object,
    default: object,
) -> dict[str, object]:
    schema = _annotation_schema(annotation)
    if contract_type is _contracts.CanonicalTimeV4 and field_name == "wire":
        schema = {
            "type": "string",
            "pattern": _json_schema_pattern(_contracts._TIME_SYNTAX_RE.pattern),
            "format": "jc-canonical-time",
            "not": {"pattern": r"\.[0-9]*0Z$"},
        }
    elif contract_type is _contracts.CaseInputBundleV4 and field_name == "schema_version":
        schema = {"type": "string", "const": _contracts.CASE_INPUT_BUNDLE_SCHEMA_V4}
    elif field_name == "schema_version" and annotation is str:
        schema = {"type": "string", "const": _contracts.SCHEMA_VERSION_V4}
    elif contract_type is _contracts.CaseArtifactV4 and field_name == "content_base64":
        schema = {"type": "string", "maxLength": 1_398_104}
    elif field_name == "engine_version" and annotation is str:
        schema = {
            "type": "string",
            "pattern": _json_schema_pattern(_contracts._ENGINE_VERSION_RE.pattern),
        }
    elif contract_type is _contracts.ReviewStateV4 and field_name == "status":
        schema = {"type": "string", "enum": sorted(_contracts._REVIEW_STATES)}
    elif contract_type is _contracts.TransportOutcomeV4 and field_name == "status":
        schema = {"type": "string", "enum": sorted(_contracts._TRANSPORT_STATES)}
    elif contract_type is _contracts.AttackV4 and field_name == "attack_type":
        schema = {"type": "string", "enum": sorted(_contracts._ATTACK_TYPES_V4)}
    elif contract_type is _contracts.AttackV4 and field_name == "target_aspect":
        schema = {
            "type": "string",
            "enum": sorted(_contracts._ATTACK_TARGET_ASPECTS_V4),
        }
    elif contract_type is _contracts.ResourceLimitsV4:
        configured_default, hard_maximum = _contracts.ENGINE_LIMITS_V4[field_name]
        if hard_maximum is None:
            schema = {"type": "null", "const": None}
        else:
            schema = {
                "type": "integer",
                "minimum": 1,
                "maximum": hard_maximum,
                "x-jc-integer-token": True,
            }
        if default != configured_default:
            raise TypeError(f"ResourceLimitsV4.{field_name} default drifted from authority")
    if contract_type is _contracts.CaseRequestV4 and field_name in {
        "fact_attestation_refs",
        "proposal_refs",
    }:
        schema = {
            **schema,
            "maxItems": _contracts.DEFAULT_RESOURCE_LIMITS_V4[f"max_{field_name}"],
            "uniqueItems": True,
        }
    if default is not MISSING:
        if default is not None and type(default) not in (str, bool, int):
            raise TypeError(
                f"unsupported schema default for {contract_type.__name__}.{field_name}"
            )
        schema = {**schema, "default": default}
    return schema


def _object_definition(contract_type: type[V4Contract]) -> dict[str, object]:
    hints = get_type_hints(contract_type)
    properties: dict[str, object] = {}
    required: list[str] = []
    for item in fields(contract_type):
        default = item.default if item.default is not MISSING else MISSING
        if item.default is MISSING and item.default_factory is MISSING:
            required.append(item.name)
        properties[item.name] = _field_schema(
            contract_type,
            item.name,
            hints[item.name],
            default,
        )
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _type_definition(type_name: str, contract_type: type[object]) -> dict[str, object]:
    if type_name == "DigestV4":
        return {
            "type": "string",
            "pattern": _json_schema_pattern(DIGEST_PATTERN.pattern),
        }
    if isinstance(contract_type, type) and issubclass(contract_type, Enum):
        return {
            "type": "string",
            "enum": [item.value for item in contract_type],
        }
    if isinstance(contract_type, type) and issubclass(contract_type, V4Contract):
        return _object_definition(contract_type)
    raise TypeError(f"unsupported V4 registry type {type_name!r}")


def schema_document() -> dict[str, object]:
    """Generate the complete closed V4 JSON Schema from the typed registry."""

    definitions = {
        type_name: _type_definition(type_name, contract_type)
        for type_name, contract_type in V4_TYPE_REGISTRY.items()
    }
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": JSON_SCHEMA_ID,
        "title": "Juris Calculus V4 public contracts",
        "description": (
            "Structural Draft 2020-12 publication of "
            "compiler_core.contracts.V4_TYPE_REGISTRY. Strict raw-JSON token "
            "admission and typed codecs remain the full runtime authority."
        ),
        "$defs": definitions,
    }


def _referenced_definitions(value: object) -> set[str]:
    found: set[str] = set()
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            reference = current.get("$ref")
            if type(reference) is str and reference.startswith("#/$defs/"):
                found.add(reference.removeprefix("#/$defs/"))
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)
    return found


def standalone_type_schema(type_name: str) -> dict[str, object]:
    """Return one self-contained schema closure suitable for MCP tools/list."""

    document = schema_document()
    definitions = document["$defs"]
    if type(type_name) is not str or type_name not in definitions:
        raise ContractV4Error("MCP_TOOL_SPEC", f"unknown V4 schema type {type_name!r}")
    reachable = {type_name}
    pending = [type_name]
    while pending:
        current = pending.pop()
        for dependency in _referenced_definitions(definitions[current]):
            if dependency not in definitions:
                raise TypeError(f"schema definition {current} has unknown ref {dependency}")
            if dependency not in reachable:
                reachable.add(dependency)
                pending.append(dependency)
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "$ref": f"#/$defs/{type_name}",
        "$defs": {
            name: definitions[name]
            for name in V4_TYPE_REGISTRY
            if name in reachable
        },
    }


def runtime_tools_list() -> dict[str, object]:
    """Build the exact MCP tools/list publication without repository I/O."""

    return {
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "inputSchema": standalone_type_schema(spec.input_type),
                "outputSchema": standalone_type_schema(spec.output_type),
                "x-jc-errorSchema": standalone_type_schema(spec.error_type),
            }
            for spec in TOOL_SPECS
        ]
    }


def runtime_resources_list() -> dict[str, object]:
    """V4 formal MCP publishes no resources."""

    return {"resources": []}


def tool_spec_digest() -> DigestV4:
    return digest_value([spec.to_dict() for spec in TOOL_SPECS])


def schema_bytes() -> bytes:
    return canonical_bytes(schema_document())


def manifest_bytes() -> bytes:
    return canonical_bytes(runtime_tools_list())


def _error_value(exc: Exception) -> ErrorV4:
    code = str(getattr(exc, "code", "MCP_INTERNAL_ERROR"))
    stage = str(getattr(exc, "stage", "mcp"))
    retryable = bool(getattr(exc, "retryable", False))
    if not isinstance(
        exc,
        (ClientV4Error, ContractV4Error, ApplicationV4Error, AuditBundleV4Error),
    ):
        code, stage, retryable = "MCP_INTERNAL_ERROR", "mcp", False
    return ErrorV4(
        code=code,
        message="V4 tool failed",
        stage=stage,
        retryable=retryable,
        correlation_id=digest_value({"code": code, "stage": stage}).hex[:24],
        field_path=(),
    )


def _tool_error(tool_name: str, exc: Exception) -> dict[str, object]:
    error = _error_value(exc)
    if tool_name == "jc_capabilities":
        return MCPCapabilitiesErrorV4(error).to_dict()
    if tool_name == "jc_evaluate":
        return MCPEvaluateErrorV4(error, None, None, ()).to_dict()
    if tool_name == "jc_verify_run":
        return MCPVerifyRunErrorV4(error, None, None, None).to_dict()
    if tool_name == "jc_read_artifact":
        return MCPReadArtifactErrorV4(error, None).to_dict()
    return {"error": error.to_dict()}


class MCPServerV4:
    """Exact four-tool JSON-RPC adapter over one JCClient V4 facade."""

    def __init__(self, client: JCClient | None = None) -> None:
        if client is not None and type(client) is not JCClient:
            raise TypeError("client must be JCClient")
        self.client = client or JCClient()

    def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> tuple[dict[str, object], bool]:
        if name not in {spec.name for spec in TOOL_SPECS}:
            return _tool_error(name, ContractV4Error("MCP_TOOL", "unknown V4 tool")), True
        try:
            decoded = decode_tool_payload(name, "input", arguments)
            if name == "jc_capabilities":
                output = self.client.capabilities()
                return output.to_dict(), False
            if name == "jc_evaluate":
                if type(decoded) is not MCPEvaluateInputV4:
                    raise ContractV4Error("MCP_TOOL", "evaluate input type drifted")
                output = self.client.evaluate_for_mcp(decoded)
                is_error = output.result.decision_status in {
                    DecisionStatusV4.BLOCKED,
                    DecisionStatusV4.ENGINE_ERROR,
                }
                return output.to_dict(), is_error
            if name == "jc_verify_run":
                if type(decoded) is not MCPVerifyRunInputV4:
                    raise ContractV4Error("MCP_TOOL", "verify input type drifted")
                output = self.client.verify_for_mcp(
                    decoded.run_handle,
                    offline_replay=decoded.offline_replay,
                )
                return output.to_dict(), False
            if type(decoded) is not MCPReadArtifactInputV4:
                raise ContractV4Error("MCP_TOOL", "read input type drifted")
            output = self.client.read_artifact(
                decoded.artifact_handle,
                offset=decoded.offset,
                length=decoded.length,
            )
            return output.to_dict(), False
        except Exception as exc:
            return _tool_error(name, exc), True


def _rpc_error(request_id: object, code: int, message: str) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _write_response(value: dict[str, object]) -> None:
    sys.stdout.write(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    )
    sys.stdout.flush()


def run_stdio(server: MCPServerV4 | None = None) -> None:
    """Run a silent MCP stdio lifecycle; one tool error never kills the server."""

    service = server or MCPServerV4()
    initialized = False
    for raw_line in sys.stdin:
        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError:
            _write_response(_rpc_error(None, -32700, "Parse error"))
            continue
        if (
            type(request) is not dict
            or request.get("jsonrpc") != "2.0"
            or type(request.get("method")) is not str
            or type(request.get("params", {})) is not dict
        ):
            request_id = request.get("id") if type(request) is dict else None
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
            result: dict[str, object] = {}
        elif method == "tools/list":
            result = runtime_tools_list()
        elif method == "resources/list":
            result = runtime_resources_list()
        elif method == "resources/templates/list":
            result = {"resourceTemplates": []}
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if type(name) is not str or type(arguments) is not dict:
                _write_response(_rpc_error(request_id, -32602, "Invalid params"))
                continue
            structured, is_error = service.call_tool(name, arguments)
            result = {
                "content": [{
                    "type": "text",
                    "text": json.dumps(
                        structured,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }],
                "structuredContent": structured,
                "isError": is_error,
            }
        else:
            _write_response(_rpc_error(request_id, -32601, "Method not found"))
            continue
        _write_response({"jsonrpc": "2.0", "id": request_id, "result": result})


def main() -> int:
    run_stdio(MCPServerV4())
    return 0


__all__ = [
    "JSON_SCHEMA_DIALECT",
    "JSON_SCHEMA_ID",
    "TOOL_SPECS",
    "decode_tool_payload",
    "decode_tool_json",
    "schema_document",
    "standalone_type_schema",
    "runtime_tools_list",
    "runtime_resources_list",
    "tool_spec_digest",
    "schema_bytes",
    "manifest_bytes",
    "MCPServerV4",
    "run_stdio",
    "main",
]
