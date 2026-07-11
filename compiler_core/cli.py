"""JC默认agent CLI；只注册已经实现并可验证的命令。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

import yaml

from compiler_core.resources import configs_root, neutral_profile_path, schemas_root
from compiler_core.rule_packs import RulePackError, RulePackRegistry
from compiler_core.audit_bundle import (
    AuditBundleError,
    default_state_root,
    evaluate_registered_case,
    replay_audit_bundle,
    state_root_diagnostics,
)
from compiler_core.contracts import CaseRequest, ResultStatus
from compiler_core.analysis import AnalysisError, analyze_similar_cases, analyze_strategy
from compiler_core.rendering import RendererError, render_run
from compiler_core.rule_governance import audit_pack, write_governance_report
from compiler_core.training import export_corpus_pack
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
    audit = rule_commands.add_parser("audit", help="audit a versioned rule corpus without promoting candidates")
    audit.add_argument("pack_id")
    audit.add_argument("--tests-root", metavar="PATH", help="explicit tests directory for rule-ID coverage")
    audit.add_argument("--audit-out", metavar="PATH", help="state root for the complete governance artifact")
    audit.add_argument("--include-candidate-ids", action="store_true")
    _add_pack_root_options(audit)
    audit.add_argument("--json", action="store_true", dest="json_output")
    audit.set_defaults(handler=_handle_rules_audit)

    doctor = commands.add_parser("doctor", help="check the installed core resources")
    doctor.add_argument("--audit-out", metavar="PATH", help="explicit state root to diagnose")
    doctor.add_argument("--json", action="store_true", dest="json_output")
    doctor.set_defaults(handler=_handle_doctor)

    packs = commands.add_parser("packs", help="inspect and verify versioned rule packs")
    pack_commands = packs.add_subparsers(dest="packs_command", required=True)
    list_packs = pack_commands.add_parser("list", help="list installed pack manifests")
    _add_pack_root_options(list_packs)
    list_packs.add_argument("--json", action="store_true", dest="json_output")
    list_packs.set_defaults(handler=_handle_packs_list)
    verify = pack_commands.add_parser("verify", help="verify pack files, digest, inventory, and admission")
    selection = verify.add_mutually_exclusive_group()
    selection.add_argument("pack_id", nargs="?", help="pack ID; defaults to all installed packs")
    selection.add_argument("--all", action="store_true", dest="verify_all")
    _add_pack_root_options(verify)
    verify.add_argument("--json", action="store_true", dest="json_output")
    verify.set_defaults(handler=_handle_packs_verify)

    evaluate = commands.add_parser("evaluate", help="evaluate a CaseRequest and write a complete audit bundle")
    evaluate.add_argument("--input", required=True, metavar="PATH", help="CaseRequest JSON path or '-' for stdin")
    evaluate.add_argument("--audit-out", metavar="PATH", help="explicit state root; defaults to the user state directory")
    _add_pack_root_options(evaluate)
    evaluate.add_argument("--json", action="store_true", dest="json_output")
    evaluate.set_defaults(handler=_handle_evaluate)

    replay = commands.add_parser("replay", help="verify and semantically replay a completed run")
    replay.add_argument("run_id")
    replay.add_argument("--audit-out", metavar="PATH", help="state root containing runs/ and packs/")
    replay.add_argument("--json", action="store_true", dest="json_output")
    replay.set_defaults(handler=_handle_replay)

    render = commands.add_parser("render", help="render an existing audited run without re-evaluation")
    render.add_argument("run_id")
    render.add_argument("--audit-out", metavar="PATH", help="state root containing the completed run")
    render.add_argument("--format", choices=("markdown", "mermaid", "html"), default="markdown")
    render.add_argument("--audience", choices=("agent", "lawyer"), default="agent")
    render.add_argument("--profile", metavar="PATH", help="explicit declarative profile; defaults to neutral")
    render.add_argument("--json", action="store_true", dest="json_output")
    render.set_defaults(handler=_handle_render)

    training = commands.add_parser("training", help="export governed candidate rule corpora")
    training_commands = training.add_subparsers(dest="training_command", required=True)
    training_export = training_commands.add_parser("export", help="export a verified corpus manifest to JSONL splits")
    training_export.add_argument("pack_id")
    training_export.add_argument("--out", required=True, metavar="DIR")
    training_export.add_argument("--seed", type=int, default=42)
    _add_pack_root_options(training_export)
    training_export.add_argument("--json", action="store_true", dest="json_output")
    training_export.set_defaults(handler=_handle_training_export)

    analyze = commands.add_parser("analyze", help="derive advisory artifacts from a completed audit run")
    analyze_commands = analyze.add_subparsers(dest="analyze_command", required=True)
    strategy = analyze_commands.add_parser("strategy", help="derive machine litigation strategy paths")
    strategy.add_argument("--run", required=True, dest="run_id")
    strategy.add_argument("--audit-out", metavar="PATH")
    strategy.add_argument("--json", action="store_true", dest="json_output")
    strategy.set_defaults(handler=_handle_analyze_strategy)
    similar = analyze_commands.add_parser("similar-cases", help="compare a run to a verified structural case index")
    similar.add_argument("--run", required=True, dest="run_id")
    similar.add_argument("--index", required=True, metavar="PATH")
    similar.add_argument("--limit", type=int, default=10)
    similar.add_argument("--audit-out", metavar="PATH")
    similar.add_argument("--json", action="store_true", dest="json_output")
    similar.set_defaults(handler=_handle_analyze_similar_cases)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """解析并执行CLI；预期错误不向stdout泄漏traceback。"""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        payload = args.handler(args)
        exit_code = int(payload.pop("_exit_code", EXIT_OK))
        _write_success(payload, json_output=bool(getattr(args, "json_output", False)))
        return exit_code
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


def _handle_doctor(args: argparse.Namespace) -> dict[str, Any]:
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
    official = RulePackRegistry(configs_root()).verify("cn-official")
    checks["cn_official"] = {
        "present": official.integrity_valid,
        "reasoning_ready": official.reasoning_ready,
        "resource": "configs/packs/cn-official/manifest.yaml",
    }
    state = state_root_diagnostics(Path(args.audit_out) if args.audit_out else None)
    checks["audit_state"] = {
        "present": state["writable"] and not state["in_repository"] and not state["dangerous_permissions"],
        "resource": state["resource"],
        **{key: value for key, value in state.items() if key != "resource"},
    }
    healthy = all(check["present"] for check in checks.values()) and official.reasoning_ready
    return {
        "command": "doctor",
        "status": "ok" if healthy else "blocked",
        "version": __version__,
        "python_supported": (3, 11) <= sys.version_info[:2] < (3, 13),
        "checks": checks,
        "_exit_code": EXIT_OK if healthy else EXIT_ADMISSION_BLOCKED,
    }


def _handle_packs_list(args: argparse.Namespace) -> dict[str, Any]:
    """列出已安装manifest声明；完整hash验证只由packs verify执行。"""

    registry = _pack_registry(args)
    packs = list(registry.list_installed())
    return {
        "command": "packs.list",
        "status": "ok",
        "pack_count": len(packs),
        "development_override": registry.development_override,
        "packs": packs,
    }


def _handle_packs_verify(args: argparse.Namespace) -> dict[str, Any]:
    """验证指定或全部pack；任何完整性或正式准入问题返回退出码3。"""

    registry = _pack_registry(args)
    try:
        results = registry.verify_all() if args.verify_all or not args.pack_id else (registry.verify(args.pack_id),)
    except RulePackError as exc:
        exit_code = EXIT_OPTIONAL_COMPONENT_MISSING if exc.code == "PACK_NOT_INSTALLED" else EXIT_ADMISSION_BLOCKED
        raise CLIError(exc.code, str(exc), exit_code=exit_code) from exc
    passed = all(result.integrity_valid and (result.kind != "official" or result.reasoning_ready) for result in results)
    return {
        "command": "packs.verify",
        "status": "ok" if passed else "blocked",
        "development_override": registry.development_override,
        "results": [result.to_dict() for result in results],
        "_exit_code": EXIT_OK if passed else EXIT_ADMISSION_BLOCKED,
    }


def _handle_rules_audit(args: argparse.Namespace) -> dict[str, Any]:
    """执行完整规则治理并把大候选列表写入artifact。"""

    registry = _pack_registry(args)
    try:
        report = audit_pack(
            registry,
            args.pack_id,
            tests_root=Path(args.tests_root).resolve() if args.tests_root else None,
        )
    except RulePackError as exc:
        raise CLIError(exc.code, str(exc), exit_code=EXIT_ADMISSION_BLOCKED) from exc
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise CLIError("RULE_GOVERNANCE_FAILED", str(exc), exit_code=EXIT_INPUT_ERROR) from exc
    root = Path(args.audit_out).resolve() if args.audit_out else default_state_root()
    diagnostics = state_root_diagnostics(root)
    if diagnostics["in_repository"]:
        raise CLIError("AUDIT_PATH_IN_REPOSITORY", "governance artifacts cannot be written inside a Git worktree")
    relative = Path("governance") / report["pack_digest"] / "audit.json"
    report_hash = write_governance_report(report, root / relative)
    payload = {
        "command": "rules.audit",
        "status": report["status"].lower(),
        "pack_id": report["pack_id"],
        "pack_version": report["pack_version"],
        "pack_digest": report["pack_digest"],
        "inventory": report["inventory"],
        "candidate_rule_count": len(report["candidate_rule_ids"]),
        "duplicate_rule_ids": report["duplicate_rule_ids"],
        "finding_count": report["finding_count"],
        "blocking_count": report["blocking_count"],
        "promotion_blocking_count": report["promotion_blocking_count"],
        "test_coverage": report["test_coverage"],
        "automatic_promotion": False,
        "artifact_ref": relative.as_posix(),
        "artifact_sha256": report_hash,
        "_exit_code": EXIT_OK if report["status"] == "PASS" else EXIT_ADMISSION_BLOCKED,
    }
    if args.include_candidate_ids:
        payload["candidate_rule_ids"] = report["candidate_rule_ids"]
    return payload


def _handle_training_export(args: argparse.Namespace) -> dict[str, Any]:
    """导出candidate训练语料，禁止写回pack配置目录。"""

    registry = _pack_registry(args)
    try:
        report = export_corpus_pack(registry, args.pack_id, Path(args.out), seed=args.seed)
    except RulePackError as exc:
        raise CLIError(exc.code, str(exc), exit_code=EXIT_ADMISSION_BLOCKED) from exc
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise CLIError("TRAINING_EXPORT_FAILED", str(exc), exit_code=EXIT_INPUT_ERROR) from exc
    return {
        "command": "training.export",
        "status": "ok",
        "pack_id": report["pack_id"],
        "pack_version": report["pack_version"],
        "pack_digest": report["pack_digest"],
        "inventory": {
            "corpus_total": report["corpus_total"],
            "reasoning_eligible_total": report["reasoning_eligible_total"],
            "candidate_only_total": report["candidate_only_total"],
        },
        "splits": report["splits"],
        "split_seed": report["split_seed"],
        "dataset_hash": report["dataset_hash"],
        "artifact_files": report["artifact_files"],
        "manifest_sha256": report["manifest_sha256"],
        "private_case_facts_included": False,
        "automatic_promotion": False,
    }


def _handle_evaluate(args: argparse.Namespace) -> dict[str, Any]:
    """从显式JSON输入运行正式application并强制生成审计包。"""

    request_payload = _read_json_input(args.input)
    try:
        request = CaseRequest.from_dict(request_payload)
    except (TypeError, ValueError) as exc:
        raise CLIError("INVALID_CASE_REQUEST", str(exc), exit_code=EXIT_INPUT_ERROR) from exc
    registry = _pack_registry(args)
    try:
        bundle = evaluate_registered_case(
            request,
            registry,
            state_root=Path(args.audit_out) if args.audit_out else None,
        )
    except RulePackError as exc:
        exit_code = EXIT_OPTIONAL_COMPONENT_MISSING if exc.code == "PACK_NOT_INSTALLED" else EXIT_ADMISSION_BLOCKED
        raise CLIError(exc.code, str(exc), exit_code=exit_code) from exc
    except AuditBundleError as exc:
        exit_code = (
            EXIT_INPUT_ERROR
            if exc.code in {"AUDIT_PRIVACY_VIOLATION", "AUDIT_PATH_IN_REPOSITORY", "INVALID_RUN_ID"}
            else EXIT_ENGINE_ERROR
        )
        raise CLIError(exc.code, str(exc), exit_code=exit_code) from exc
    payload = {
        "command": "evaluate",
        "status": "engine_error" if bundle.result.semantic.result_status is ResultStatus.ENGINE_ERROR else "ok",
        **bundle.public_dict(),
        "_exit_code": EXIT_ENGINE_ERROR if bundle.result.semantic.result_status is ResultStatus.ENGINE_ERROR else EXIT_OK,
    }
    return payload


def _handle_replay(args: argparse.Namespace) -> dict[str, Any]:
    """验证并离线重放一个COMPLETE审计包。"""

    try:
        replayed = replay_audit_bundle(
            Path(args.audit_out).resolve() if args.audit_out else default_state_root(),
            args.run_id,
        )
    except AuditBundleError as exc:
        exit_code = EXIT_OPTIONAL_COMPONENT_MISSING if exc.code == "REPLAY_MATERIAL_MISSING" else EXIT_REPLAY_MISMATCH
        raise CLIError(exc.code, str(exc), exit_code=exit_code) from exc
    return {"command": "replay", **replayed}


def _handle_render(args: argparse.Namespace) -> dict[str, Any]:
    """只从已验证审计run生成按需展示文件和绑定元数据。"""

    try:
        output = render_run(
            args.run_id,
            state_root=Path(args.audit_out).resolve() if args.audit_out else None,
            output_format=args.format,
            audience=args.audience,
            profile_path=Path(args.profile).resolve() if args.profile else None,
        )
    except AuditBundleError as exc:
        raise CLIError(exc.code, str(exc), exit_code=EXIT_REPLAY_MISMATCH) from exc
    except RendererError as exc:
        input_codes = {
            "INVALID_RENDERER_PROFILE",
            "PROFILE_HASH_MISMATCH",
            "PROFILE_UNAVAILABLE",
            "INVALID_RENDER_FORMAT",
            "INVALID_AUDIENCE",
        }
        raise CLIError(
            exc.code,
            str(exc),
            exit_code=EXIT_INPUT_ERROR if exc.code in input_codes else EXIT_ENGINE_ERROR,
        ) from exc
    return {"command": "render", "status": "ok", **output.public_dict()}


def _handle_analyze_strategy(args: argparse.Namespace) -> dict[str, Any]:
    """从审计run生成紧凑策略ADVISORY引用。"""

    report = _run_analysis(
        lambda: analyze_strategy(
            args.run_id,
            state_root=Path(args.audit_out).resolve() if args.audit_out else None,
        )
    )
    return {
        "command": "analyze.strategy",
        "status": "ok",
        "analysis_status": report["analysis_status"],
        "run_id": report["run_id"],
        "result_digest": report["result_digest"],
        "review_required": report["review_required"],
        "path_count": len(report["paths"]),
        "risk_labels": report["basis"]["risk_labels"],
        "artifact_ref": report["artifact_ref"],
        "artifact_sha256": report["artifact_sha256"],
    }


def _handle_analyze_similar_cases(args: argparse.Namespace) -> dict[str, Any]:
    """从显式index生成紧凑类案ADVISORY引用。"""

    report = _run_analysis(
        lambda: analyze_similar_cases(
            args.run_id,
            Path(args.index),
            state_root=Path(args.audit_out).resolve() if args.audit_out else None,
            limit=args.limit,
        )
    )
    return {
        "command": "analyze.similar-cases",
        "status": "ok",
        "analysis_status": report["analysis_status"],
        "quality_status": report["quality_status"],
        "run_id": report["run_id"],
        "result_digest": report["result_digest"],
        "review_required": report["review_required"],
        "match_count": len(report["matches"]),
        "artifact_ref": report["artifact_ref"],
        "artifact_sha256": report["artifact_sha256"],
        "limitations": report["limitations"],
    }


def _run_analysis(callback) -> dict[str, Any]:
    """统一分析错误到CLI退出码，禁止traceback和绝对路径泄漏。"""

    try:
        return callback()
    except AuditBundleError as exc:
        raise CLIError(exc.code, str(exc), exit_code=EXIT_REPLAY_MISMATCH) from exc
    except AnalysisError as exc:
        input_codes = {"INVALID_LIMIT", "CASE_INDEX_UNAVAILABLE", "INVALID_CASE_INDEX", "CASE_INDEX_DIGEST_MISMATCH"}
        raise CLIError(exc.code, str(exc), exit_code=EXIT_INPUT_ERROR if exc.code in input_codes else EXIT_ENGINE_ERROR) from exc


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
            ready = check.get("reasoning_ready", check["present"])
            print(f"- {name}: {'PASS' if check['present'] and ready else 'BLOCKED'}")
    elif payload["command"] == "packs.list":
        for item in payload["packs"]:
            print(f"- {item['pack_id']} {item['version']}: {item['declared_status']} (not verified)")
    elif payload["command"] == "packs.verify":
        for item in payload["results"]:
            state = "PASS" if item["integrity_valid"] and (item["kind"] != "official" or item["reasoning_ready"]) else "BLOCKED"
            print(f"- {item['pack_id']}: {state}")
    elif payload["command"] == "evaluate":
        print(f"- run_id: {payload['run_id']}")
        print(f"- result_status: {payload['canonical_result']['semantic']['result_status']}")
        print(f"- bundle_digest: {payload['bundle_digest']}")
    elif payload["command"] == "replay":
        print(f"- run_id: {payload['run_id']}")
        print(f"- replay: {payload['status']}")
    elif payload["command"] == "render":
        print(f"- format: {payload['format']}")
        print(f"- artifact_ref: {payload['artifact_ref']}")
        print(f"- content_sha256: {payload['content_sha256']}")
    elif payload["command"] == "rules.audit":
        print(f"- pack_id: {payload['pack_id']}")
        print(f"- candidate_rule_count: {payload['candidate_rule_count']}")
        print(f"- artifact_ref: {payload['artifact_ref']}")
    elif payload["command"] == "training.export":
        print(f"- pack_id: {payload['pack_id']}")
        print(f"- dataset_hash: {payload['dataset_hash']}")
    elif payload["command"] in {"analyze.strategy", "analyze.similar-cases"}:
        print(f"- run_id: {payload['run_id']}")
        print(f"- analysis_status: {payload['analysis_status']}")
        print(f"- artifact_ref: {payload['artifact_ref']}")


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


def _add_pack_root_options(parser: argparse.ArgumentParser) -> None:
    """为pack命令增加显式development override参数。"""

    parser.add_argument("--development", action="store_true", help="allow an explicit non-bundled config root")
    parser.add_argument("--config-root", help="development configs root; requires --development")


def _pack_registry(args: argparse.Namespace) -> RulePackRegistry:
    """构造pack registry；环境变量本身永远不能静默换包。"""

    development = bool(getattr(args, "development", False))
    explicit_root = getattr(args, "config_root", None)
    if explicit_root and not development:
        raise CLIError("DEVELOPMENT_FLAG_REQUIRED", "--config-root requires --development")
    if development:
        selected = explicit_root or os.environ.get("JURIS_CONFIG_DIR")
        if not selected:
            raise CLIError("DEVELOPMENT_ROOT_REQUIRED", "development mode requires --config-root")
        root = Path(selected)
        if not root.is_dir():
            raise CLIError("DEVELOPMENT_ROOT_NOT_FOUND", "development config root does not exist")
        return RulePackRegistry(root, development_override=True)
    return RulePackRegistry(configs_root())


def _read_json_input(input_path: str) -> dict[str, Any]:
    """从stdin或显式UTF-8文件读取单一JSON对象。"""

    try:
        text = sys.stdin.read() if input_path == "-" else Path(input_path).read_text(encoding="utf-8")
        payload = json.loads(text)
    except OSError as exc:
        raise CLIError("INPUT_READ_ERROR", "input JSON cannot be read", details={"error_type": type(exc).__name__}) from exc
    except json.JSONDecodeError as exc:
        raise CLIError("INVALID_JSON", "input is not valid JSON", details={"line": exc.lineno, "column": exc.colno}) from exc
    if not isinstance(payload, dict):
        raise CLIError("INVALID_JSON", "input JSON must be an object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
