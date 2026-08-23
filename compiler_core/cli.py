"""Strict V4 command-line adapter backed by JCClient."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from compiler_core.application import ApplicationV4Error
from compiler_core.audit_bundle import AuditBundleV4Error
from compiler_core.client import ClientV4Error, JCClient
from compiler_core.contracts import (
    ArtifactHandleV4,
    CaseRequestV4,
    ContractV4Error,
    DecisionStatusV4,
    MCPReadArtifactInputV4,
)
from compiler_core.rendering import RendererV4Error
from compiler_core.version import __version__


EXIT_OK = 0
EXIT_INPUT_ERROR = 2
EXIT_ADMISSION_BLOCKED = 3
EXIT_ENGINE_ERROR = 4
EXIT_REPLAY_MISMATCH = 5
EXIT_OPTIONAL_COMPONENT_MISSING = 6


class CLIError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int = EXIT_INPUT_ERROR,
        stage: str = "cli",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.stage = stage
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "stage": self.stage,
            "retryable": self.retryable,
        }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIError("CLI_USAGE_ERROR", message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="jc", description="Juris Calculus V4 formal runtime")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    capabilities = commands.add_parser("capabilities")
    capabilities.add_argument("--json", action="store_true", dest="json_output")

    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--input", required=True)
    evaluate.add_argument("--json", action="store_true", dest="json_output")

    verify = commands.add_parser("verify")
    verify.add_argument("--input", required=True)
    verify.add_argument("--json", action="store_true", dest="json_output")

    replay = commands.add_parser("replay")
    replay.add_argument("--input", required=True)
    replay.add_argument("--json", action="store_true", dest="json_output")

    read = commands.add_parser("read-artifact")
    read.add_argument("--input", required=True)
    read.add_argument("--json", action="store_true", dest="json_output")

    render = commands.add_parser("render")
    render.add_argument("--input", required=True)
    render.add_argument("--format", choices=("markdown", "mermaid", "html"), default="markdown")
    render.add_argument("--audience", choices=("agent", "lawyer"), default="agent")
    render.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _read(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read()
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise CLIError("INPUT_UNAVAILABLE", type(exc).__name__) from exc


def _json_object(path: str) -> dict[str, Any]:
    try:
        value = json.loads(_read(path))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CLIError("INVALID_JSON", type(exc).__name__) from exc
    if type(value) is not dict:
        raise CLIError("INVALID_JSON", "input must be one JSON object")
    return value


def _execute(args: argparse.Namespace, client: JCClient) -> tuple[dict[str, Any], int]:
    if args.command == "capabilities":
        return {"command": "capabilities", **client.capabilities().to_dict()}, EXIT_OK
    if args.command == "evaluate":
        request = CaseRequestV4.from_json_bytes(_read(args.input))
        envelope = client.evaluate(request)
        status = envelope.result.decision_status
        exit_code = (
            EXIT_ADMISSION_BLOCKED
            if status is DecisionStatusV4.BLOCKED
            else EXIT_ENGINE_ERROR
            if status is DecisionStatusV4.ENGINE_ERROR
            else EXIT_OK
        )
        return {"command": "evaluate", **envelope.to_dict()}, exit_code
    if args.command in {"verify", "replay", "render"}:
        handle = ArtifactHandleV4.from_dict(_json_object(args.input))
        if args.command == "verify":
            verified = client.verify_run(handle)
            return {
                "command": "verify",
                "verification": verified.verification.to_dict(),
            }, EXIT_OK
        if args.command == "replay":
            output = client.verify_for_mcp(handle, offline_replay=True)
            replay = output.replay
            exit_code = EXIT_OK if replay is not None and replay.semantic_equal else EXIT_REPLAY_MISMATCH
            return {"command": "replay", **output.to_dict()}, exit_code
        rendered = client.render(
            handle,
            output_format=args.format,
            audience=args.audience,
        )
        return {
            "command": "render",
            **rendered.to_dict(include_content=not args.json_output),
        }, EXIT_OK
    request = MCPReadArtifactInputV4.from_dict(_json_object(args.input))
    output = client.read_artifact(
        request.artifact_handle,
        offset=request.offset,
        length=request.length,
    )
    return {"command": "read-artifact", **output.to_dict()}, EXIT_OK


def _mapped_error(exc: Exception) -> CLIError:
    if isinstance(exc, ClientV4Error):
        exit_code = (
            EXIT_OPTIONAL_COMPONENT_MISSING
            if exc.code in {"RUNTIME_NOT_CONFIGURED", "REPLAY_NOT_CONFIGURED"}
            else EXIT_INPUT_ERROR
        )
        return CLIError(
            exc.code,
            str(exc),
            exit_code=exit_code,
            stage=exc.stage,
            retryable=exc.retryable,
        )
    code = str(getattr(exc, "code", "CLI_INTERNAL_ERROR"))
    stage = str(getattr(exc, "stage", "runtime"))
    if isinstance(exc, ContractV4Error):
        exit_code = EXIT_INPUT_ERROR
    elif isinstance(exc, AuditBundleV4Error):
        exit_code = EXIT_REPLAY_MISMATCH
    elif isinstance(exc, RendererV4Error):
        exit_code = EXIT_INPUT_ERROR
    elif isinstance(exc, ApplicationV4Error):
        exit_code = EXIT_ENGINE_ERROR
    else:
        code = "CLI_INTERNAL_ERROR"
        exit_code = EXIT_ENGINE_ERROR
    return CLIError(
        code,
        "V4 command failed",
        exit_code=exit_code,
        stage=stage,
        retryable=bool(getattr(exc, "retryable", False)),
    )


def _write(document: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        command = document.pop("command", "jc")
        print(f"{command}: ok")
        print(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2))


def main(argv: Sequence[str] | None = None, *, client: JCClient | None = None) -> int:
    try:
        args = build_parser().parse_args(list(argv) if argv is not None else None)
        document, exit_code = _execute(args, client or JCClient())
        _write(document, json_output=bool(getattr(args, "json_output", False)))
        return exit_code
    except CLIError as exc:
        print(json.dumps(exc.to_dict(), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        error = _mapped_error(exc)
        print(json.dumps(error.to_dict(), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
