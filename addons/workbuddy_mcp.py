"""WorkBuddy专用的薄MCP适配器；CLI与application仍是唯一业务入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping
from urllib.parse import quote

from compiler_core.analysis import AnalysisError, analyze_similar_cases, analyze_strategy
from compiler_core.audit_bundle import AuditBundleError, default_state_root, evaluate_registered_case
from compiler_core.contracts import CaseRequest
from compiler_core.resources import configs_root
from compiler_core.rule_lookup import lookup_rules
from compiler_core.rule_packs import RulePackError, RulePackRegistry
from compiler_core.version import MCP_PROTOCOL_VERSION, SERVER_NAME, __version__


TOOL_NAMES = (
    "jc_evaluate",
    "jc_lookup_rule",
    "jc_analyze_strategy",
    "jc_analyze_similar_cases",
)


def _object_schema(properties: Mapping[str, Any], required: tuple[str, ...]) -> dict[str, Any]:
    """生成禁止额外字段的版本化对象schema。"""

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": dict(properties),
        "required": list(required),
    }


_ERROR_SCHEMA = _object_schema(
    {
        "code": {"type": "string"},
        "message": {"type": "string"},
        "retryable": {"type": "boolean"},
    },
    ("code", "message", "retryable"),
)


DEFAULT_MANIFEST: dict[str, Any] = {
    "schema_version": "1.0",
    "description": "Optional WorkBuddy adapter for the auditable JC CLI/application core",
    "resources": {},
    "tools": {
        "jc_evaluate": {
            "description": "Evaluate an explicit CaseRequest file and return a compact audited run reference.",
            "inputSchema": _object_schema(
                {"input_path": {"type": "string", "minLength": 1}},
                ("input_path",),
            ),
            "outputSchema": _object_schema(
                {
                    "schema_version": {"const": "1.0"},
                    "status": {"type": "string"},
                    "run_id": {"type": "string"},
                    "result_status": {"type": "string"},
                    "review_required": {"type": "boolean"},
                    "formal_kernel_used": {"type": "boolean"},
                    "claim_count": {"type": "integer"},
                    "risk_labels": {"type": "array", "items": {"type": "string"}},
                    "artifact_refs": {"type": "array", "items": {"type": "string"}},
                    "error": _ERROR_SCHEMA,
                },
                ("schema_version", "status"),
            ),
        },
        "jc_lookup_rule": {
            "description": "Look up a bounded rule summary in one integrity-checked rule pack.",
            "inputSchema": _object_schema(
                {
                    "pack_id": {"type": "string", "minLength": 1},
                    "rule_id": {"type": "string", "minLength": 1},
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                },
                ("pack_id",),
            ),
            "outputSchema": _object_schema(
                {
                    "schema_version": {"const": "1.0"},
                    "status": {"type": "string"},
                    "pack_id": {"type": "string"},
                    "pack_version": {"type": "string"},
                    "pack_digest": {"type": "string"},
                    "inventory": {"type": "object"},
                    "match_count": {"type": "integer"},
                    "results": {"type": "array", "items": {"type": "object"}},
                    "error": _ERROR_SCHEMA,
                },
                ("schema_version", "status"),
            ),
        },
        "jc_analyze_strategy": {
            "description": "Create an advisory strategy artifact from a verified completed run.",
            "inputSchema": _object_schema(
                {"run_id": {"type": "string", "minLength": 1}},
                ("run_id",),
            ),
            "outputSchema": _object_schema(
                {
                    "schema_version": {"const": "1.0"},
                    "status": {"type": "string"},
                    "analysis_status": {"type": "string"},
                    "run_id": {"type": "string"},
                    "review_required": {"type": "boolean"},
                    "path_count": {"type": "integer"},
                    "risk_labels": {"type": "array", "items": {"type": "string"}},
                    "artifact_refs": {"type": "array", "items": {"type": "string"}},
                    "error": _ERROR_SCHEMA,
                },
                ("schema_version", "status"),
            ),
        },
        "jc_analyze_similar_cases": {
            "description": "Create a deterministic advisory comparison from a verified run and explicit case index.",
            "inputSchema": _object_schema(
                {
                    "run_id": {"type": "string", "minLength": 1},
                    "index_path": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                },
                ("run_id", "index_path"),
            ),
            "outputSchema": _object_schema(
                {
                    "schema_version": {"const": "1.0"},
                    "status": {"type": "string"},
                    "analysis_status": {"type": "string"},
                    "quality_status": {"type": "string"},
                    "run_id": {"type": "string"},
                    "review_required": {"type": "boolean"},
                    "match_count": {"type": "integer"},
                    "limitations": {"type": "array", "items": {"type": "string"}},
                    "artifact_refs": {"type": "array", "items": {"type": "string"}},
                    "error": _ERROR_SCHEMA,
                },
                ("schema_version", "status"),
            ),
        },
    },
}


class AdapterError(RuntimeError):
    """不会向协议层泄漏本机路径或traceback的稳定工具错误。"""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class WorkBuddyAdapter:
    """把四个MCP工具薄映射到现有application、lookup和analysis服务。"""

    def __init__(
        self,
        *,
        manifest_path: Path | None = None,
        config_root: Path | None = None,
        development: bool = False,
        state_root: Path | None = None,
    ) -> None:
        self.manifest = _load_manifest(manifest_path)
        if config_root is not None and not development:
            raise AdapterError("DEVELOPMENT_FLAG_REQUIRED", "config root requires development mode")
        selected_root = Path(config_root).resolve() if config_root is not None else configs_root()
        self.registry = RulePackRegistry(selected_root, development_override=development)
        self.state_root = Path(state_root).resolve() if state_root is not None else default_state_root()

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """验证输入后分发四项薄工具；任何失败都返回稳定机器错误。"""

        if name not in TOOL_NAMES:
            return _tool_error("UNKNOWN_TOOL", "tool is not registered")
        try:
            clean = _validate_arguments(name, arguments)
            if name == "jc_evaluate":
                return self._evaluate(clean)
            if name == "jc_lookup_rule":
                return self._lookup(clean)
            if name == "jc_analyze_strategy":
                return self._strategy(clean)
            return self._similar_cases(clean)
        except AdapterError as exc:
            return _tool_error(exc.code, str(exc), retryable=exc.retryable)
        except RulePackError as exc:
            return _tool_error(exc.code, "rule pack admission failed")
        except AuditBundleError as exc:
            return _tool_error(exc.code, "audit run is unavailable or invalid")
        except AnalysisError as exc:
            return _tool_error(exc.code, "analysis input or audited run is invalid")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return _tool_error("INVALID_TOOL_INPUT", type(exc).__name__)
        except Exception as exc:  # 协议进程必须在单次内部失败后继续存活，且不得回显traceback。
            return _tool_error("ADAPTER_INTERNAL_ERROR", type(exc).__name__)

    def _evaluate(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """读取显式CaseRequest文件并调用唯一正式审计入口。"""

        payload = _read_json_object(Path(str(arguments["input_path"])))
        try:
            request = CaseRequest.from_dict(payload)
        except (TypeError, ValueError) as exc:
            raise AdapterError("INVALID_CASE_REQUEST", str(exc)) from exc
        bundle = evaluate_registered_case(request, self.registry, state_root=self.state_root)
        result = bundle.result.semantic
        return {
            "schema_version": "1.0",
            "status": "engine_error" if result.result_status.value == "engine_error" else "ok",
            "run_id": result.run_id,
            "result_status": result.result_status.value,
            "review_required": result.review_required,
            "formal_kernel_used": result.formal_kernel_used,
            "claim_count": len(result.claims),
            "risk_labels": list(result.risk_labels),
            "artifact_refs": _logical_run_refs(result.run_id, bundle.result.artifact_refs),
        }

    def _lookup(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """复用规则包完整性门禁并限制返回规则摘要。"""

        output = lookup_rules(
            self.registry,
            str(arguments["pack_id"]),
            rule_id=arguments.get("rule_id"),
            query=arguments.get("query"),
            limit=int(arguments.get("limit", 10)),
        )
        return {"schema_version": "1.0", **output}

    def _strategy(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """只读已完成run并返回ADVISORY摘要。"""

        report = analyze_strategy(str(arguments["run_id"]), state_root=self.state_root)
        return {
            "schema_version": "1.0",
            "status": "ok",
            "analysis_status": report["analysis_status"],
            "run_id": report["run_id"],
            "review_required": report["review_required"],
            "path_count": len(report["paths"]),
            "risk_labels": report["basis"]["risk_labels"],
            "artifact_refs": [_logical_analysis_ref(report["run_id"], "strategy.json")],
        }

    def _similar_cases(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """只读显式index并返回类案ADVISORY摘要。"""

        report = analyze_similar_cases(
            str(arguments["run_id"]),
            Path(str(arguments["index_path"])),
            state_root=self.state_root,
            limit=int(arguments.get("limit", 10)),
        )
        return {
            "schema_version": "1.0",
            "status": "ok",
            "analysis_status": report["analysis_status"],
            "quality_status": report["quality_status"],
            "run_id": report["run_id"],
            "review_required": report["review_required"],
            "match_count": len(report["matches"]),
            "limitations": report["limitations"],
            "artifact_refs": [_logical_analysis_ref(report["run_id"], "similar-cases.json")],
        }


def manifest_document(manifest_path: Path | None = None) -> dict[str, Any]:
    """把包元数据注入工具manifest，避免静态版本字段漂移。"""

    document = _load_manifest(manifest_path)
    return {
        "name": SERVER_NAME,
        "version": __version__,
        "protocol_version": MCP_PROTOCOL_VERSION,
        **document,
    }


def run_stdio(adapter: WorkBuddyAdapter) -> None:
    """运行启动静默、错误后存活的单行JSON-RPC stdio生命周期。"""

    initialized = False
    for raw_line in sys.stdin:
        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError:
            _write_response(_rpc_error(None, -32700, "Parse error"))
            continue
        if not _valid_rpc_shape(request):
            _write_response(_rpc_error(request.get("id") if isinstance(request, dict) else None, -32600, "Invalid Request"))
            continue
        has_id = "id" in request
        request_id = request.get("id")
        method = request["method"]
        params = request.get("params", {})
        if not has_id:
            # MCP通知永远不产生响应，包括未知通知和initialized通知。
            continue
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
            result = {"tools": [
                {"name": name, **adapter.manifest["tools"][name]}
                for name in TOOL_NAMES
            ]}
        elif method == "tools/call":
            if not isinstance(params, dict) or not isinstance(params.get("arguments", {}), dict):
                _write_response(_rpc_error(request_id, -32602, "Invalid params"))
                continue
            tool_name = str(params.get("name", ""))
            payload = adapter.call_tool(tool_name, params.get("arguments", {}))
            is_error = payload.get("status") == "error"
            result = {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, sort_keys=True)}],
                "structuredContent": payload,
                "isError": is_error,
            }
        elif method == "resources/list":
            result = {"resources": []}
        elif method == "resources/templates/list":
            result = {"resourceTemplates": []}
        else:
            _write_response(_rpc_error(request_id, -32601, "Method not found"))
            continue
        _write_response({"jsonrpc": "2.0", "id": request_id, "result": result})


def run_smoke(manifest_path: Path | None = None) -> int:
    """执行不冒充服务就绪状态的进程内协议面smoke。"""

    manifest = manifest_document(manifest_path)
    assert tuple(manifest["tools"]) == TOOL_NAMES
    assert manifest["resources"] == {}
    print(json.dumps({
        "status": "ok",
        "smoke": "in_process_functional",
        "server": manifest["name"],
        "version": manifest["version"],
        "tool_count": len(manifest["tools"]),
        "resource_count": 0,
        "readiness_claimed": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """构造适配器启动参数；非bundled规则根必须显式development。"""

    parser = argparse.ArgumentParser(description="Optional WorkBuddy MCP adapter for juris-calculus")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--config-root", type=Path)
    parser.add_argument("--audit-out", type=Path)
    parser.add_argument("--test", action="store_true", help="run in-process functional smoke only")
    return parser


def main(argv: list[str] | None = None) -> int:
    """启动smoke或stdio；启动阶段不向协议stdout写任何说明文本。"""

    args = build_parser().parse_args(argv)
    if args.test:
        return run_smoke(args.manifest)
    try:
        adapter = WorkBuddyAdapter(
            manifest_path=args.manifest,
            config_root=args.config_root,
            development=args.development,
            state_root=args.audit_out,
        )
    except AdapterError as exc:
        print(json.dumps({"code": exc.code, "message": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    run_stdio(adapter)
    return 0


def _load_manifest(path: Path | None) -> dict[str, Any]:
    """读取默认或显式manifest，并拒绝恢复旧工具和resource表。"""

    if path is None:
        document = json.loads(json.dumps(DEFAULT_MANIFEST))
    else:
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdapterError("INVALID_MCP_MANIFEST", type(exc).__name__) from exc
    if not isinstance(document, dict):
        raise AdapterError("INVALID_MCP_MANIFEST", "manifest must be an object")
    if tuple(document.get("tools", {})) != TOOL_NAMES or document.get("resources") != {}:
        raise AdapterError("INVALID_MCP_MANIFEST", "manifest must expose exactly four tools and zero resources")
    for name in TOOL_NAMES:
        tool = document["tools"].get(name)
        if not isinstance(tool, dict) or "inputSchema" not in tool or "outputSchema" not in tool:
            raise AdapterError("INVALID_MCP_MANIFEST", "every tool requires input and output schemas")
    return document


def _validate_arguments(name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """执行适配层所需的最小确定性参数验证。"""

    if not isinstance(arguments, Mapping):
        raise AdapterError("INVALID_TOOL_INPUT", "arguments must be an object")
    schemas = DEFAULT_MANIFEST["tools"][name]["inputSchema"]
    unknown = sorted(set(arguments) - set(schemas["properties"]))
    missing = sorted(set(schemas["required"]) - set(arguments))
    if unknown or missing:
        raise AdapterError("INVALID_TOOL_INPUT", "arguments do not match the declared schema")
    clean = dict(arguments)
    for key, value in clean.items():
        expected = schemas["properties"][key].get("type")
        if expected == "string" and (not isinstance(value, str) or not value):
            raise AdapterError("INVALID_TOOL_INPUT", f"{key} must be a non-empty string")
        if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise AdapterError("INVALID_TOOL_INPUT", f"{key} must be an integer")
    if name == "jc_lookup_rule" and bool(clean.get("rule_id")) == bool(clean.get("query")):
        raise AdapterError("INVALID_TOOL_INPUT", "exactly one of rule_id or query is required")
    if "limit" in clean and not 1 <= clean["limit"] <= 100:
        raise AdapterError("INVALID_TOOL_INPUT", "limit must be between 1 and 100")
    return clean


def _read_json_object(path: Path) -> dict[str, Any]:
    """读取单一UTF-8 JSON对象；错误只暴露类型，不回显本机路径。"""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AdapterError("INPUT_READ_ERROR", type(exc).__name__) from exc
    except json.JSONDecodeError as exc:
        raise AdapterError("INVALID_JSON", f"line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(value, dict):
        raise AdapterError("INVALID_JSON", "input JSON must be an object")
    return value


def _logical_run_refs(run_id: str, refs: tuple[str, ...]) -> list[str]:
    """把相对存储引用转换为不会泄漏本机目录的逻辑run URI。"""

    encoded = quote(run_id, safe="")
    return [f"run://{encoded}/{Path(ref).name}" for ref in refs]


def _logical_analysis_ref(run_id: str, name: str) -> str:
    """生成分析artifact的逻辑引用。"""

    return f"run://{quote(run_id, safe='')}/analysis/{name}"


def _tool_error(code: str, message: str, *, retryable: bool = False) -> dict[str, Any]:
    """返回四工具共享的紧凑错误schema。"""

    return {
        "schema_version": "1.0",
        "status": "error",
        "error": {"code": code, "message": message, "retryable": retryable},
    }


def _valid_rpc_shape(value: Any) -> bool:
    """验证JSON-RPC请求基本形状，不把数组批处理或非对象当MCP请求。"""

    if not isinstance(value, dict) or value.get("jsonrpc") != "2.0" or not isinstance(value.get("method"), str):
        return False
    return "params" not in value or isinstance(value["params"], dict)


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    """构造标准JSON-RPC错误对象。"""

    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _write_response(response: Mapping[str, Any]) -> None:
    """只向stdout写单行协议JSON并立即刷新。"""

    sys.stdout.write(json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
