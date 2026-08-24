from __future__ import annotations

import copy
import json

import pytest

from compiler_core.mcp import runtime_tools_list
from tests.dsh_formal.conftest import capabilities, event
from tests.dsh_formal.jc_formal_adapter import (
    FormalAdapterError,
    activate,
    assert_production_deployment_allowed,
    load_profile,
    production_boundary_problems,
)


def test_profile_is_test_local_and_general_dsh_is_unchanged(profile) -> None:
    assert profile["profile_id"] == "jc-formal-test-local"
    assert profile["scope"] == "test-local"
    assert profile["production_allowed"] is False
    assert profile["loaded_by_default"] is False
    assert profile["general_profile_unchanged"] is True
    assert profile["deployment_boundary"]["approval_gate"] == "H9-00"


def test_exact_tools_and_pinned_capabilities_activate_one_test_session(profile) -> None:
    session = activate(
        profile,
        runtime_tools_list(),
        event("jc_capabilities", capabilities(profile), session_id="fresh-session"),
        session_id="fresh-session",
    )
    assert session.session_id == "fresh-session"
    assert session.scope == "test-local"
    assert session.production_allowed is False


@pytest.mark.parametrize(
    "mutation",
    (
        "server-unavailable", "tool-hidden", "tool-renamed", "schema-drift",
        "v3-capability", "build-digest", "kernel-not-ready", "capability-error",
    ),
)
def test_startup_mutations_fail_closed(profile, mutation: str) -> None:
    tools = copy.deepcopy(runtime_tools_list())
    cap_event = event("jc_capabilities", capabilities(profile))
    available = True
    if mutation == "server-unavailable":
        available = False
    elif mutation == "tool-hidden":
        tools["tools"].pop()
    elif mutation == "tool-renamed":
        tools["tools"][1]["name"] = "jc_evaluate_unpinned"
    elif mutation == "schema-drift":
        tools["tools"][1]["inputSchema"]["x-drift"] = True
    elif mutation == "v3-capability":
        cap_event["result"]["structuredContent"]["schema_version"] = "jc/3.0"
    elif mutation == "build-digest":
        cap_event["result"]["structuredContent"]["engine_build_digest"] = "sha256:" + "f" * 64
    elif mutation == "kernel-not-ready":
        cap_event["result"]["structuredContent"]["kernel_ready"] = False
    else:
        cap_event["result"]["isError"] = True
    with pytest.raises(FormalAdapterError):
        activate(
            profile, tools, cap_event,
            session_id="session-1", server_available=available,
        )
    if mutation == "schema-drift":
        tools = runtime_tools_list()
        cap_event = event("jc_capabilities", capabilities(profile))
        cap_event["result"]["structuredContent"]["tool_specs"][0]["description"] += " drift"
        with pytest.raises(FormalAdapterError, match="MCP_CAPABILITY_TOOL_DRIFT"):
            activate(profile, tools, cap_event, session_id="session-1")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("dsh_pin_approved", False),
        ("independent_service_identity", False),
        ("authenticated_private_transport", False),
        ("dsh_can_write_jc_state", True),
        ("global_tool_registry_used", True),
    ),
)
def test_unsafe_production_topology_is_explicit(field: str, value: bool) -> None:
    boundary = {
        "dsh_pin_approved": True,
        "independent_service_identity": True,
        "authenticated_private_transport": True,
        "dsh_can_write_jc_state": False,
        "global_tool_registry_used": False,
    }
    boundary[field] = value
    assert production_boundary_problems(boundary) == [f"{field}={value!r}"]


def test_even_safe_shape_requires_external_h9_00_approval(profile) -> None:
    safe = {
        "dsh_pin_approved": True,
        "independent_service_identity": True,
        "authenticated_private_transport": True,
        "dsh_can_write_jc_state": False,
        "global_tool_registry_used": False,
    }
    assert production_boundary_problems(safe) == []
    with pytest.raises(FormalAdapterError, match="H9_00_APPROVAL_REQUIRED"):
        assert_production_deployment_allowed(profile, safe)


def test_profile_parser_rejects_unknown_fields(tmp_path) -> None:
    profile = load_profile()
    profile["production_endpoint"] = "invented"
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(FormalAdapterError, match="PROFILE_FIELDS"):
        load_profile(path)
