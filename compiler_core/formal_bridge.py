"""Fail-closed stdio consumer for the active local-production formal profile."""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread
from typing import Any, Mapping, Sequence

from compiler_core.canonical_serialization import DigestV4, canonical_bytes
from compiler_core.contracts import (
    CaseInputBundleV4,
    DecisionStatusV4,
    CertificateKindV4,
    MCPCapabilitiesOutputV4,
    MCPEvaluateOutputV4,
    MCPReadArtifactOutputV4,
    MCPVerifyRunOutputV4,
)


TOOLS = ("jc_capabilities", "jc_evaluate", "jc_verify_run", "jc_read_artifact")
PIN_FIELDS = (
    "schema_version", "engine_version", "engine_source_tree", "engine_build_digest",
    "wheel_digest", "package_digest", "lock_digest", "schema_digest",
    "tool_spec_digest", "active_pack_ref", "trust_policy_ref",
    "storage_capability_ref", "kernel_ready", "legal_production_ready",
)


class FormalBridgeError(RuntimeError):
    """Stable public failure; details never contain case bytes or internal paths."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FormalProfileV4:
    profile_id: str
    python: Path
    module: str
    cwd: Path
    environment: dict[str, str]
    tools_list_digest: DigestV4
    capability_pins: dict[str, object]
    page_bytes: int
    startup_timeout_seconds: int
    tool_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class FormalDeliveryV4:
    marker: str
    artifact_digest: DigestV4
    content: bytes
    profile_id: str
    generation: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "jc/formal-delivery/1.0",
            "marker": self.marker,
            "artifact_digest": str(self.artifact_digest),
            "content_base64": base64.b64encode(self.content).decode("ascii"),
            "profile_id": self.profile_id,
            "generation": self.generation,
        }


def _closed(value: object, fields: set[str], code: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise FormalBridgeError(code)
    return value


def load_active_profile(registry_path: Path) -> FormalProfileV4:
    """Load the one active profile from the deployment registry."""

    try:
        registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FormalBridgeError("PROFILE_REGISTRY_UNAVAILABLE") from exc
    registry = _closed(
        registry, {"schema_version", "active_profile", "profiles"},
        "PROFILE_REGISTRY_FIELDS",
    )
    profiles = registry["profiles"]
    active = registry["active_profile"]
    if (
        registry["schema_version"] != "jc/formal-profile-registry/1.0"
        or type(active) is not str
        or type(profiles) is not dict
        or set(profiles) != {active}
    ):
        raise FormalBridgeError("PROFILE_REGISTRY_BOUNDARY")
    profile = _closed(
        profiles[active],
        {
            "schema_version", "profile_id", "production", "loaded_by_default",
            "python", "module", "cwd", "environment", "allowed_tools",
            "tools_list_digest", "capability_pins", "page_bytes",
            "startup_timeout_seconds", "tool_timeout_seconds",
        },
        "FORMAL_PROFILE_FIELDS",
    )
    pins = profile["capability_pins"]
    environment = profile["environment"]
    python = Path(str(profile["python"]))
    cwd = Path(str(profile["cwd"]))
    if (
        profile["schema_version"] != "jc/formal-profile/1.0"
        or profile["profile_id"] != active
        or profile["production"] is not True
        or profile["loaded_by_default"] is not False
        or profile["allowed_tools"] != list(TOOLS)
        or type(environment) is not dict
        or not environment
        or any(type(key) is not str or type(value) is not str for key, value in environment.items())
        or set(pins) != set(PIN_FIELDS)
        or not python.is_absolute()
        or not python.is_file()
        or not cwd.is_absolute()
        or not cwd.is_dir()
        or type(profile["module"]) is not str
        or not profile["module"]
        or type(profile["page_bytes"]) is not int
        or profile["page_bytes"] <= 0
        or type(profile["startup_timeout_seconds"]) is not int
        or profile["startup_timeout_seconds"] <= 0
        or type(profile["tool_timeout_seconds"]) is not int
        or profile["tool_timeout_seconds"] <= 0
    ):
        raise FormalBridgeError("FORMAL_PROFILE_BOUNDARY")
    try:
        tools_digest = DigestV4.parse(profile["tools_list_digest"])
        for field in (
            "engine_build_digest", "wheel_digest", "package_digest", "lock_digest",
            "schema_digest", "tool_spec_digest",
        ):
            DigestV4.parse(pins[field])
    except (TypeError, ValueError) as exc:
        raise FormalBridgeError("FORMAL_PROFILE_PINS") from exc
    return FormalProfileV4(
        active, python, profile["module"], cwd, dict(environment), tools_digest,
        dict(pins), profile["page_bytes"], profile["startup_timeout_seconds"],
        profile["tool_timeout_seconds"],
    )


class StdioSessionV4:
    """One generation of a pinned MCP subprocess session."""

    def __init__(self, profile: FormalProfileV4, generation: int = 0) -> None:
        self.profile = profile
        self.generation = generation
        self._request_id = 0
        self._responses: Queue[object] = Queue()
        env = {
            key: value for key, value in os.environ.items()
            if key.upper() not in {"PYTHONPATH", "PYTHONHOME", "JC_PROFILE_REGISTRY"}
        }
        env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        env.update(profile.environment)
        try:
            self._process = subprocess.Popen(
                [str(profile.python), "-B", "-m", profile.module],
                cwd=str(profile.cwd), env=env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="strict", bufsize=1,
            )
        except OSError as exc:
            raise FormalBridgeError("MCP_STARTUP_FAILED") from exc
        Thread(target=self._read_stdout, daemon=True).start()
        try:
            self._activate()
        except Exception:
            self.close()
            raise

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        try:
            for line in self._process.stdout:
                try:
                    self._responses.put(json.loads(line))
                except json.JSONDecodeError:
                    self._responses.put(FormalBridgeError("MCP_INVALID_JSON"))
                    return
        except (OSError, UnicodeError):
            pass
        self._responses.put(FormalBridgeError("MCP_PROCESS_CLOSED"))

    def _rpc(self, method: str, params: Mapping[str, object] | None = None) -> dict[str, Any]:
        if self._process.poll() is not None or self._process.stdin is None:
            raise FormalBridgeError("MCP_PROCESS_CLOSED")
        self._request_id += 1
        request: dict[str, object] = {
            "jsonrpc": "2.0", "id": self._request_id, "method": method,
        }
        if params is not None:
            request["params"] = dict(params)
        try:
            self._process.stdin.write(canonical_bytes(request).decode("utf-8") + "\n")
            self._process.stdin.flush()
            timeout = (
                self.profile.startup_timeout_seconds
                if method in {"initialize", "tools/list"}
                else self.profile.tool_timeout_seconds
            )
            response = self._responses.get(timeout=timeout)
        except (BrokenPipeError, OSError) as exc:
            raise FormalBridgeError("MCP_PROCESS_CLOSED") from exc
        except Empty as exc:
            raise FormalBridgeError("MCP_TIMEOUT") from exc
        if isinstance(response, FormalBridgeError):
            raise response
        if (
            type(response) is not dict
            or response.get("jsonrpc") != "2.0"
            or response.get("id") != self._request_id
            or set(response) not in ({"jsonrpc", "id", "result"}, {"jsonrpc", "id", "error"})
        ):
            raise FormalBridgeError("MCP_RESPONSE_BINDING")
        if "error" in response:
            raise FormalBridgeError("MCP_RPC_ERROR")
        result = response["result"]
        if type(result) is not dict:
            raise FormalBridgeError("MCP_RESPONSE_SHAPE")
        return result

    def _call_tool(self, name: str, arguments: Mapping[str, object]) -> dict[str, Any]:
        result = self._rpc("tools/call", {"name": name, "arguments": dict(arguments)})
        if set(result) != {"content", "structuredContent", "isError"}:
            raise FormalBridgeError("MCP_TOOL_RESULT_FIELDS")
        if type(result["isError"]) is not bool or result["isError"]:
            structured = result.get("structuredContent")
            error = structured.get("error") if type(structured) is dict else None
            detail = str(error.get("code", "UNKNOWN")) if type(error) is dict else "UNKNOWN"
            raise FormalBridgeError("MCP_TOOL_ERROR", detail)
        structured = result["structuredContent"]
        if type(structured) is not dict:
            raise FormalBridgeError("MCP_TOOL_RESULT_SHAPE")
        return structured

    def _activate(self) -> None:
        initialized = self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "jc-formal", "version": "1"},
            },
        )
        if type(initialized.get("protocolVersion")) is not str:
            raise FormalBridgeError("MCP_INITIALIZE_DRIFT")
        publication = self._rpc("tools/list")
        tools = publication.get("tools")
        if (
            type(tools) is not list
            or [item.get("name") for item in tools if type(item) is dict] != list(TOOLS)
            or DigestV4.from_bytes(canonical_bytes(publication)) != self.profile.tools_list_digest
        ):
            raise FormalBridgeError("MCP_TOOL_LIST_DRIFT")
        try:
            capabilities = MCPCapabilitiesOutputV4.from_dict(
                self._call_tool("jc_capabilities", {})
            )
        except (TypeError, ValueError) as exc:
            raise FormalBridgeError("MCP_CAPABILITY_INVALID") from exc
        actual = capabilities.to_dict()
        if any(actual[field] != value for field, value in self.profile.capability_pins.items()):
            raise FormalBridgeError("MCP_CAPABILITY_DRIFT")
        if not capabilities.kernel_ready or not capabilities.legal_production_ready:
            raise FormalBridgeError("MCP_NOT_PRODUCTION_READY")

    def deliver(self, bundle: CaseInputBundleV4) -> FormalDeliveryV4:
        try:
            evaluated = MCPEvaluateOutputV4.from_dict(
                self._call_tool("jc_evaluate", {"case_bundle": bundle.to_dict()})
            )
        except (TypeError, ValueError) as exc:
            raise FormalBridgeError("MCP_EVALUATE_INVALID") from exc
        if (
            evaluated.result.decision_status is not DecisionStatusV4.ACCEPTED_FORMAL_RESULT
            or evaluated.result.certificate_kind is not CertificateKindV4.FORMAL_VERIFIED
        ):
            raise FormalBridgeError("FORMAL_RESULT_REQUIRED")
        if (
            evaluated.run_handle.run_identity_ref != evaluated.result.run_identity_ref
            or evaluated.certificate_handle.run_identity_ref != evaluated.result.run_identity_ref
        ):
            raise FormalBridgeError("FORMAL_RUN_BINDING")
        try:
            verified = MCPVerifyRunOutputV4.from_dict(self._call_tool(
                "jc_verify_run",
                {"run_handle": evaluated.run_handle.to_dict(), "offline_replay": False},
            ))
        except (TypeError, ValueError) as exc:
            raise FormalBridgeError("MCP_VERIFY_INVALID") from exc
        if (
            verified.verification.status != "VERIFIED"
            or verified.verification.run_identity_ref != evaluated.result.run_identity_ref
            or verified.verification.certificate_ref != evaluated.certificate_handle.content_ref
        ):
            raise FormalBridgeError("FORMAL_VERIFICATION_REQUIRED")
        content = bytearray()
        handle = evaluated.certificate_handle
        offset = 0
        while offset < handle.size_bytes:
            length = min(self.profile.page_bytes, handle.size_bytes - offset)
            try:
                page = MCPReadArtifactOutputV4.from_dict(self._call_tool(
                    "jc_read_artifact",
                    {"artifact_handle": handle.to_dict(), "offset": offset, "length": length},
                ))
                chunk = base64.b64decode(page.content_base64, validate=True)
            except (TypeError, ValueError) as exc:
                raise FormalBridgeError("MCP_READ_INVALID") from exc
            if (
                page.artifact_handle != handle
                or page.offset != offset
                or page.length != len(chunk)
                or page.chunk_digest != DigestV4.from_bytes(chunk)
                or page.artifact_digest != handle.content_ref.digest
                or page.eof != (offset + len(chunk) == handle.size_bytes)
                or page.next_offset != (None if page.eof else offset + len(chunk))
                or not chunk
            ):
                raise FormalBridgeError("FORMAL_PAGE_BINDING")
            content.extend(chunk)
            offset += len(chunk)
        artifact_digest = DigestV4.from_bytes(content)
        if offset != handle.size_bytes or artifact_digest != handle.content_ref.digest:
            raise FormalBridgeError("FORMAL_ARTIFACT_BYTES")
        return FormalDeliveryV4(
            "JC_FORMAL_VERIFIED", artifact_digest, bytes(content),
            self.profile.profile_id, self.generation,
        )

    def close(self) -> None:
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except OSError:
                pass
        try:
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()

    def __enter__(self) -> StdioSessionV4:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class FormalBridgeV4:
    def __init__(self, profile: FormalProfileV4) -> None:
        self.profile = profile
        self.generation = -1
        self.session: StdioSessionV4 | None = None

    def connect(self) -> StdioSessionV4:
        if self.session is not None:
            self.session.close()
        self.generation += 1
        self.session = StdioSessionV4(self.profile, self.generation)
        return self.session

    def deliver(self, bundle: CaseInputBundleV4) -> FormalDeliveryV4:
        session = self.session or self.connect()
        return session.deliver(bundle)

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None

    def __enter__(self) -> FormalBridgeV4:
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deliver one verified JC formal certificate")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--registry", type=Path,
        default=Path(os.environ.get("JC_PROFILE_REGISTRY", "deployment/profile-registry.json")),
    )
    args = parser.parse_args(argv)
    try:
        bundle = CaseInputBundleV4.from_json_bytes(args.input.read_bytes())
        profile = load_active_profile(args.registry.resolve())
        with FormalBridgeV4(profile) as bridge:
            delivery = bridge.deliver(bundle)
        sys.stdout.buffer.write(canonical_bytes(delivery.to_dict()) + b"\n")
        return 0
    except (OSError, TypeError, ValueError, FormalBridgeError) as exc:
        code = exc.code if isinstance(exc, FormalBridgeError) else "FORMAL_INPUT_INVALID"
        print(code, file=sys.stderr)
        return 1


__all__ = (
    "FormalBridgeError", "FormalProfileV4", "FormalDeliveryV4", "StdioSessionV4",
    "FormalBridgeV4", "load_active_profile", "main",
)
