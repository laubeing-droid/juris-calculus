from __future__ import annotations

import copy

import pytest

from tests.dsh_formal.jc_formal_adapter import FormalAdapterError, guard_delivery


def test_exact_current_session_certificate_bytes_receive_formal_marker(
    profile, session, delivery_chain,
) -> None:
    delivery = guard_delivery(
        session,
        profile,
        delivery_chain["evaluate"],
        delivery_chain["verify"],
        delivery_chain["read"],
        delivery_chain["bytes"],
    )
    assert delivery.marker == "JC_FORMAL_VERIFIED"
    assert delivery.content == delivery_chain["bytes"]
    assert delivery.session_id == session.session_id


@pytest.mark.parametrize(
    "mutation",
    (
        "blocked-evaluate", "certificate-kind", "verify-status", "run-swap",
        "certificate-swap", "read-handle", "artifact-byte", "historical-session",
        "is-error-flip", "model-rewrite",
    ),
)
def test_delivery_chain_mutations_cannot_keep_formal_identity(
    profile, session, delivery_chain, mutation: str,
) -> None:
    chain = copy.deepcopy(delivery_chain)
    delivered = chain["bytes"]
    if mutation == "blocked-evaluate":
        chain["evaluate"]["result"]["structuredContent"]["result"]["decision_status"] = "BLOCKED"
    elif mutation == "certificate-kind":
        chain["evaluate"]["result"]["structuredContent"]["result"]["certificate_kind"] = "NONE"
    elif mutation == "verify-status":
        chain["verify"]["result"]["structuredContent"]["verification"]["status"] = "FAILED"
    elif mutation == "run-swap":
        chain["verify"]["result"]["structuredContent"]["verification"]["run_identity_ref"] = {
            "kind": "run-identity-v4", "digest": "sha256:" + "b" * 64,
        }
    elif mutation == "certificate-swap":
        chain["verify"]["result"]["structuredContent"]["verification"]["certificate_ref"] = {
            "kind": "formal-certificate-v4", "digest": "sha256:" + "c" * 64,
        }
    elif mutation == "read-handle":
        handle = chain["read"]["result"]["structuredContent"]["artifact_handle"]
        chain["read"]["result"]["structuredContent"]["artifact_handle"] = {
            **handle, "artifact_id": "other",
        }
    elif mutation == "artifact-byte":
        chain["read"]["result"]["structuredContent"]["content_base64"] = "eA=="
    elif mutation == "historical-session":
        chain["verify"]["session_id"] = "historical-session"
    elif mutation == "is-error-flip":
        chain["evaluate"]["result"]["isError"] = True
    else:
        delivered = chain["bytes"] + b"model summary"
    with pytest.raises(FormalAdapterError):
        guard_delivery(
            session, profile, chain["evaluate"], chain["verify"], chain["read"], delivered,
        )


def test_dsh_formal_bypass_and_tool_hiding_are_blocked(
    profile, session, delivery_chain,
) -> None:
    hidden_verify = copy.deepcopy(delivery_chain["verify"])
    hidden_verify["tool"] = "model_claimed_verify"
    with pytest.raises(FormalAdapterError, match="SESSION_OR_TOOL_BINDING"):
        guard_delivery(
            session,
            profile,
            delivery_chain["evaluate"],
            hidden_verify,
            delivery_chain["read"],
            delivery_chain["bytes"],
        )

    fake = copy.deepcopy(delivery_chain)
    fake["evaluate"]["result"]["structuredContent"]["natural_language"] = "verified"
    fake["verify"]["result"]["isError"] = True
    with pytest.raises(FormalAdapterError, match="MCP_TOOL_ERROR"):
        guard_delivery(
            session, profile, fake["evaluate"], fake["verify"], fake["read"], fake["bytes"],
        )
