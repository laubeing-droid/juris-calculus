from __future__ import annotations

import copy

import pytest

from compiler_core.mcp import runtime_tools_list
from tests.dsh_formal.conftest import capabilities, event
from tests.dsh_formal.jc_formal_adapter import (
    FormalAdapterError,
    _event_content,
    activate,
)


def test_client_policy_is_fail_closed_and_evaluate_is_not_retried(profile) -> None:
    policy = profile["client_policy"]
    assert profile["fail_on_startup_error"] is True
    assert policy["evaluate_retryable"] is False
    assert policy["cancel_is_terminal"] is True
    assert policy["reconnect_revalidates"] is True
    assert policy["private_registry_required"] is True
    assert policy["retry_limit"] == 1


@pytest.mark.parametrize(
    "mutation",
    (
        "missing-is-error", "error-flip", "wrong-session", "old-generation",
        "wrong-tool", "oversized-output",
    ),
)
def test_tool_result_mutations_fail_closed(profile, session, mutation: str) -> None:
    candidate = event("jc_verify_run", {"verification": {"status": "VERIFIED"}})
    if mutation == "missing-is-error":
        del candidate["result"]["isError"]
    elif mutation == "error-flip":
        candidate["result"]["isError"] = True
    elif mutation == "wrong-session":
        candidate["session_id"] = "historical-session"
    elif mutation == "old-generation":
        candidate["generation"] = 2
    elif mutation == "wrong-tool":
        candidate["tool"] = "jc_evaluate"
    else:
        candidate["result"]["content"][0]["text"] = "x" * (
            profile["client_policy"]["max_output_bytes"] + 1
        )
    with pytest.raises(FormalAdapterError):
        _event_content(session, profile, candidate, "jc_verify_run")


def test_reconnect_revalidates_tools_and_invalidates_old_generation(profile) -> None:
    tools = runtime_tools_list()
    reconnected = activate(
        profile,
        tools,
        event(
            "jc_capabilities", capabilities(profile),
            session_id="session-1", generation=1,
        ),
        session_id="session-1",
        generation=1,
    )
    old_event = event("jc_verify_run", {}, generation=0)
    with pytest.raises(FormalAdapterError, match="SESSION_OR_TOOL_BINDING"):
        _event_content(reconnected, profile, old_event, "jc_verify_run")

    drifted = copy.deepcopy(tools)
    drifted["tools"][0]["outputSchema"]["x-reconnect-drift"] = True
    with pytest.raises(FormalAdapterError, match="MCP_TOOL_LIST_DRIFT"):
        activate(
            profile,
            drifted,
            event(
                "jc_capabilities", capabilities(profile),
                session_id="session-1", generation=2,
            ),
            session_id="session-1",
            generation=2,
        )
