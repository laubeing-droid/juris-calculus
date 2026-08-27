"""Test/local reference for an out-of-tree DSH formal adapter and delivery guard."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any


PROFILE_PATH = Path(__file__).with_name("jc-formal-profile.json")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
PROFILE_FIELDS = {
    "schema_version", "profile_id", "scope", "production_allowed",
    "loaded_by_default", "general_profile_unchanged", "fail_on_startup_error",
    "allowed_tools", "tools_list_digest", "capability_pins", "client_policy",
    "deployment_boundary",
}
CAPABILITY_FIELDS = {
    "schema_version", "engine_version", "engine_source_tree", "engine_build_digest",
    "wheel_digest", "package_digest", "lock_digest", "schema_digest",
    "tool_spec_digest", "active_pack_ref", "trust_policy_ref",
    "storage_capability_ref", "kernel_ready", "legal_production_ready",
}
CLIENT_POLICY_FIELDS = {
    "startup_timeout_ms", "tool_timeout_ms", "max_output_bytes", "retry_limit",
    "evaluate_retryable", "cancel_is_terminal", "reconnect_revalidates",
    "private_registry_required",
}
DEPLOYMENT_FIELDS = {
    "production_deployment_claimed", "dsh_pin_approved",
    "independent_service_identity_verified", "authenticated_transport_verified",
    "dsh_state_write_allowed", "approval_gate",
}
EVENT_FIELDS = {"session_id", "generation", "tool", "result"}
RESULT_FIELDS = {"content", "structuredContent", "isError"}


class FormalAdapterError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FormalSession:
    session_id: str
    generation: int
    tools_list_digest: str
    capability_digest: str
    scope: str = "test-local"
    production_allowed: bool = False


@dataclass(frozen=True, slots=True)
class FormalDelivery:
    marker: str
    artifact_digest: str
    content: bytes
    session_id: str
    generation: int


def _fail(code: str) -> None:
    raise FormalAdapterError(code)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _closed(value: object, fields: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(code)
    return value


def _content_ref(value: object, code: str) -> dict[str, str]:
    ref = _closed(value, {"kind", "digest"}, code)
    if not isinstance(ref["kind"], str) or not ref["kind"] or not DIGEST.fullmatch(ref["digest"]):
        _fail(code)
    return ref


def load_profile(path: Path = PROFILE_PATH) -> dict[str, Any]:
    try:
        profile = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FormalAdapterError("PROFILE_UNAVAILABLE") from exc
    profile = _closed(profile, PROFILE_FIELDS, "PROFILE_FIELDS")
    tools = profile["allowed_tools"]
    pins = _closed(profile["capability_pins"], CAPABILITY_FIELDS, "CAPABILITY_FIELDS")
    policy = _closed(profile["client_policy"], CLIENT_POLICY_FIELDS, "CLIENT_POLICY_FIELDS")
    boundary = _closed(
        profile["deployment_boundary"], DEPLOYMENT_FIELDS, "DEPLOYMENT_FIELDS",
    )
    for field in ("active_pack_ref", "trust_policy_ref", "storage_capability_ref"):
        _content_ref(pins[field], "CAPABILITY_REF")
    if (
        profile["schema_version"] != "jc/dsh-formal-profile/1.0"
        or profile["profile_id"] != "jc-formal-test-local"
        or profile["scope"] != "test-local"
        or profile["production_allowed"] is not False
        or profile["loaded_by_default"] is not False
        or profile["general_profile_unchanged"] is not True
        or profile["fail_on_startup_error"] is not True
        or tools != [
            "jc_capabilities", "jc_evaluate", "jc_verify_run", "jc_read_artifact",
        ]
        or not DIGEST.fullmatch(profile["tools_list_digest"])
        or set(pins) != CAPABILITY_FIELDS
        or pins["schema_version"] != "jc/4.0"
        or not str(pins["engine_version"]).startswith("4.")
        or pins["kernel_ready"] is not True
        or pins["legal_production_ready"] is not False
        or any(
            not DIGEST.fullmatch(pins[field])
            for field in (
                "engine_build_digest", "wheel_digest", "package_digest", "lock_digest",
                "schema_digest", "tool_spec_digest",
            )
        )
        or any(type(policy[field]) is not int or policy[field] <= 0 for field in (
            "startup_timeout_ms", "tool_timeout_ms", "max_output_bytes", "retry_limit",
        ))
        or policy["evaluate_retryable"] is not False
        or policy["cancel_is_terminal"] is not True
        or policy["reconnect_revalidates"] is not True
        or policy["private_registry_required"] is not True
        or boundary != {
            "production_deployment_claimed": False,
            "dsh_pin_approved": False,
            "independent_service_identity_verified": False,
            "authenticated_transport_verified": False,
            "dsh_state_write_allowed": False,
            "approval_gate": "H9-00",
        }
    ):
        _fail("PROFILE_BOUNDARY")
    return profile


def _event_content(
    session: FormalSession,
    profile: dict[str, Any],
    event: object,
    tool: str,
) -> dict[str, Any]:
    event = _closed(event, EVENT_FIELDS, "EVENT_FIELDS")
    if (
        event["session_id"] != session.session_id
        or event["generation"] != session.generation
        or event["tool"] != tool
        or tool not in profile["allowed_tools"]
    ):
        _fail("SESSION_OR_TOOL_BINDING")
    result = _closed(event["result"], RESULT_FIELDS, "MCP_RESULT_FIELDS")
    if type(result["isError"]) is not bool or result["isError"]:
        _fail("MCP_TOOL_ERROR")
    if len(_canonical(result)) > profile["client_policy"]["max_output_bytes"]:
        _fail("MCP_OUTPUT_LIMIT")
    content = result["structuredContent"]
    if not isinstance(content, dict):
        _fail("MCP_STRUCTURED_CONTENT")
    return content


def activate(
    profile: dict[str, Any],
    tools_publication: object,
    capabilities_event: object,
    *,
    session_id: str,
    generation: int = 0,
    server_available: bool = True,
) -> FormalSession:
    if not server_available:
        _fail("MCP_STARTUP_UNAVAILABLE")
    if not isinstance(session_id, str) or not session_id or type(generation) is not int or generation < 0:
        _fail("SESSION_IDENTITY")
    publication = _closed(tools_publication, {"tools"}, "TOOLS_PUBLICATION")
    tools = publication["tools"]
    if (
        not isinstance(tools, list)
        or [item.get("name") for item in tools if isinstance(item, dict)]
        != profile["allowed_tools"]
        or _digest(publication) != profile["tools_list_digest"]
    ):
        _fail("MCP_TOOL_LIST_DRIFT")
    provisional = FormalSession(
        session_id, generation, profile["tools_list_digest"], "",
    )
    capabilities = _event_content(
        provisional, profile, capabilities_event, "jc_capabilities",
    )
    pins = profile["capability_pins"]
    if any(capabilities.get(field) != value for field, value in pins.items()):
        _fail("MCP_CAPABILITY_DRIFT")
    if capabilities.get("tool_spec_digest") != pins["tool_spec_digest"]:
        _fail("MCP_TOOL_SPEC_DRIFT")
    tool_specs = capabilities.get("tool_specs")
    if (
        not isinstance(tool_specs, list)
        or [item.get("name") for item in tool_specs if isinstance(item, dict)]
        != profile["allowed_tools"]
        or _digest(tool_specs) != pins["tool_spec_digest"]
    ):
        _fail("MCP_CAPABILITY_TOOL_DRIFT")
    return FormalSession(
        session_id, generation, profile["tools_list_digest"], _digest(pins),
    )


def guard_delivery(
    session: FormalSession,
    profile: dict[str, Any],
    evaluate_event: object,
    verify_event: object,
    read_event: object,
    delivered_bytes: bytes,
) -> FormalDelivery:
    evaluated = _event_content(session, profile, evaluate_event, "jc_evaluate")
    verified = _event_content(session, profile, verify_event, "jc_verify_run")
    read = _event_content(session, profile, read_event, "jc_read_artifact")
    result = evaluated.get("result", {})
    certificate_handle = evaluated.get("certificate_handle")
    run_handle = evaluated.get("run_handle")
    verification = verified.get("verification", {})
    if (
        not isinstance(result, dict)
        or result.get("decision_status") != "ACCEPTED_FORMAL_RESULT"
        or result.get("certificate_kind") != "FORMAL_VERIFIED"
        or not isinstance(certificate_handle, dict)
        or not isinstance(run_handle, dict)
        or verification.get("status") != "VERIFIED"
        or result.get("run_identity_ref") != verification.get("run_identity_ref")
        or run_handle.get("content_ref") != result.get("run_identity_ref")
        or certificate_handle.get("content_ref") != verification.get("certificate_ref")
        or read.get("artifact_handle") != certificate_handle
        or read.get("artifact_digest") != certificate_handle.get("content_ref", {}).get("digest")
        or read.get("offset") != 0
        or read.get("next_offset") is not None
        or read.get("eof") is not True
    ):
        _fail("FORMAL_CHAIN_BINDING")
    try:
        content = base64.b64decode(read["content_base64"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalAdapterError("FORMAL_ARTIFACT_ENCODING") from exc
    artifact_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if (
        read.get("length") != len(content)
        or read.get("chunk_digest") != artifact_digest
        or read.get("artifact_digest") != artifact_digest
        or type(delivered_bytes) is not bytes
        or delivered_bytes != content
    ):
        _fail("FORMAL_ARTIFACT_BYTES")
    return FormalDelivery(
        "JC_FORMAL_VERIFIED", artifact_digest, content,
        session.session_id, session.generation,
    )


def production_boundary_problems(boundary: object) -> list[str]:
    if not isinstance(boundary, dict):
        return ["boundary must be an object"]
    required = {
        "dsh_pin_approved": True,
        "independent_service_identity": True,
        "authenticated_private_transport": True,
        "dsh_can_write_jc_state": False,
        "global_tool_registry_used": False,
    }
    return [
        f"{field}={boundary.get(field)!r}"
        for field, expected in required.items() if boundary.get(field) is not expected
    ]


def assert_production_deployment_allowed(
    profile: dict[str, Any], boundary: object,
) -> None:
    problems = production_boundary_problems(boundary)
    if problems:
        _fail("UNSAFE_PRODUCTION_TOPOLOGY")
    if profile["deployment_boundary"]["production_deployment_claimed"] is not True:
        _fail("H9_00_APPROVAL_REQUIRED")
