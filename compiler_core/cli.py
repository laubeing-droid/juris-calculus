"""JC默认agent CLI；只注册已经实现并可验证的命令。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import yaml

from compiler_core.resources import configs_root, neutral_profile_path, schemas_root
from compiler_core.types import build_rule_inventory, normalize_rule_admission
from compiler_core.version import __version__


EXIT_OK = 0
EXIT_INPUT_ERROR = 2
EXIT_ADMISSION_BLOCKED = 3
EXIT_ENGINE_ERROR = 4
EXIT_REPLAY_MISMATCH = 5
EXIT_OPTIONAL_COMPONENT_MISSING = 6


class CLIError(RuntimeError):
    """携带稳定机器错误字段和进程退出码的CLI边界异常。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int = EXIT_INPUT_ERROR,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.details = dict(details or {})
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        """返回固定机器错误schema，不暴露traceback或对象repr。"""

        return {
            "code": self.code,
            "message": str(self),
            "details": self.details,
            "retryable": self.retryable,
        }


class JCArgumentParser(argparse.ArgumentParser):
    """在JSON模式下把argparse错误也约束为机器错误schema。"""

    def error(self, message: str) -> None:
        json_mode = "--json" in sys.argv[1:]
        if json_mode:
            payload = {
                "code": "CLI_USAGE_ERROR",
                "message": message,
                "details": {},
                "retryable": False,
            }
            self._print_message(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", sys.stderr)
        else:
            super().error(message)
        raise SystemExit(EXIT_INPUT_ERROR)


def build_parser() -> argparse.ArgumentParser:
    """构造仅含当前真实实现的命令树。"""

    parser = JCArgumentParser(prog="jc", description="Auditable formal legal reasoning kernel")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    rules = commands.add_parser("rules", help="inspect published rule corpora")
    rule_commands = rules.add_subparsers(dest="rules_command", required=True)
    lookup = rule_commands.add_parser("lookup", help="search the CN legacy candidate corpus")
    source = lookup.add_mutually_exclusive_group(required=True)
    source.add_argument("query", nargs="?", help="literal search text")
    source.add_argument("--input", metavar="PATH", help="read search text from PATH or '-' for stdin")
    lookup.add_argument("--limit", type=int, default=10)
    lookup.add_argument("--json", action="store_true", dest="json_output")
    lookup.set_defaults(handler=_handle_rules_lookup)

    doctor = commands.add_parser("doctor", help="check the installed core resources")
    doctor.add_argument("--json", action="store_true", dest="json_output")
    doctor.set_defaults(handler=_handle_doctor)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """解析并执行CLI；预期错误不向stdout泄漏traceback。"""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        payload = args.handler(args)
        _write_success(payload, json_output=bool(getattr(args, "json_output", False)))
        return EXIT_OK
    except CLIError as exc:
        _write_error(exc, json_output=bool(getattr(args, "json_output", False)))
        return exc.exit_code
    except Exception:
        error = CLIError(
            "CLI_INTERNAL_ERROR",
            "command failed inside the JC runtime",
            exit_code=EXIT_ENGINE_ERROR,
        )
        _write_error(error, json_output=bool(getattr(args, "json_output", False)))
        return error.exit_code


def _handle_rules_lookup(args: argparse.Namespace) -> dict[str, Any]:
    """在legacy candidate corpus中确定性检索，不把命中项晋升为正式规则。"""

    query = _read_query(args.query, args.input)
    if args.limit < 1 or args.limit > 100:
        raise CLIError("INVALID_LIMIT", "--limit must be between 1 and 100")
    rules_path = configs_root() / "zh_CN" / "rules.yaml"
    try:
        document = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise CLIError(
            "RULE_CORPUS_UNAVAILABLE",
            "published CN candidate corpus cannot be read",
            exit_code=EXIT_OPTIONAL_COMPONENT_MISSING,
            details={"resource": "configs/zh_CN/rules.yaml", "error_type": type(exc).__name__},
        ) from exc
    rules = document.get("rules", []) if isinstance(document, dict) else []
    if not isinstance(rules, list):
        raise CLIError("INVALID_RULE_CORPUS", "rules must be an array", exit_code=EXIT_ADMISSION_BLOCKED)
    needle = query.casefold()
    matches: list[dict[str, Any]] = []
    for raw_rule in rules:
        if not isinstance(raw_rule, dict):
            continue
        normalized = normalize_rule_admission(raw_rule)
        searchable = "\n".join(
            str(normalized.get(field, ""))
            for field in ("id", "head_claim", "description", "legal_basis", "citation")
        ).casefold()
        if needle in searchable:
            matches.append({
                "rule_id": str(normalized.get("id", "")),
                "head_claim": str(normalized.get("head_claim", "")),
                "source_anchor": str(normalized.get("source_anchor", "")),
                "admission": "reasoning_eligible" if normalized.get("source_anchor") else "candidate_only",
            })
    matches.sort(key=lambda item: (item["rule_id"], item["head_claim"]))
    return {
        "command": "rules.lookup",
        "status": "ok",
        "pack_id": "cn-legacy-corpus",
        "query": query,
        "inventory": build_rule_inventory(rules),
        "match_count": len(matches),
        "results": matches[: args.limit],
    }


def _handle_doctor(_args: argparse.Namespace) -> dict[str, Any]:
    """检查独立安装所需的核心schema、profile和候选语料。"""

    resources = {
        "schema": schemas_root() / "jc-v3.schema.json",
        "neutral_profile": neutral_profile_path(),
        "cn_legacy_corpus": configs_root() / "zh_CN" / "rules.yaml",
    }
    checks = {
        name: {"present": path.is_file(), "resource": _public_resource_name(path)}
        for name, path in resources.items()
    }
    healthy = all(check["present"] for check in checks.values())
    return {
        "command": "doctor",
        "status": "ok" if healthy else "blocked",
        "version": __version__,
        "python_supported": (3, 11) <= sys.version_info[:2] < (3, 13),
        "checks": checks,
    }


def _read_query(query: str | None, input_path: str | None) -> str:
    """从显式文本、stdin或UTF-8文件读取非空查询。"""

    try:
        value = sys.stdin.read() if input_path == "-" else Path(input_path).read_text(encoding="utf-8") if input_path else query
    except OSError as exc:
        raise CLIError(
            "INPUT_READ_ERROR",
            "query input cannot be read",
            details={"error_type": type(exc).__name__},
        ) from exc
    value = str(value or "").strip()
    if not value:
        raise CLIError("EMPTY_QUERY", "query cannot be empty")
    return value


def _write_success(payload: dict[str, Any], *, json_output: bool) -> None:
    """成功时stdout只写一种明确格式。"""

    if json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return
    print(f"{payload['command']}: {payload['status']}")
    if payload["command"] == "rules.lookup":
        print(f"matches: {payload['match_count']}")
        for item in payload["results"]:
            print(f"- {item['rule_id']}: {item['head_claim']} [{item['admission']}]")
    elif payload["command"] == "doctor":
        for name, check in sorted(payload["checks"].items()):
            print(f"- {name}: {'PASS' if check['present'] else 'BLOCKED'}")


def _write_error(error: CLIError, *, json_output: bool) -> None:
    """错误只写stderr；JSON和文本都不含traceback。"""

    if json_output:
        print(json.dumps(error.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")), file=sys.stderr)
    else:
        print(f"{error.code}: {error}", file=sys.stderr)


def _public_resource_name(path: Path) -> str:
    """仅返回包内逻辑资源名，禁止doctor泄漏绝对机器路径。"""

    parts = path.parts
    for marker in ("configs", "schemas"):
        if marker in parts:
            return "/".join(parts[parts.index(marker):])
    return path.name


if __name__ == "__main__":
    raise SystemExit(main())
