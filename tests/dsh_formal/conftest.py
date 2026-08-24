from __future__ import annotations

import base64
import copy
import hashlib

import pytest

from compiler_core.mcp import TOOL_SPECS, runtime_tools_list
from tests.dsh_formal.jc_formal_adapter import activate, load_profile


def event(
    tool: str,
    content: dict[str, object],
    *,
    session_id: str = "session-1",
    generation: int = 0,
    is_error: bool = False,
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "generation": generation,
        "tool": tool,
        "result": {
            "content": [{"type": "text", "text": "structured"}],
            "structuredContent": content,
            "isError": is_error,
        },
    }


def capabilities(profile: dict[str, object]) -> dict[str, object]:
    return {
        **copy.deepcopy(profile["capability_pins"]),
        "tool_specs": [item.to_dict() for item in TOOL_SPECS],
        "resource_limits": {},
    }


@pytest.fixture
def profile() -> dict[str, object]:
    return load_profile()


@pytest.fixture
def session(profile):
    return activate(
        profile,
        runtime_tools_list(),
        event("jc_capabilities", capabilities(profile)),
        session_id="session-1",
    )


@pytest.fixture
def delivery_chain() -> dict[str, object]:
    run_ref = {"kind": "run-identity-v4", "digest": "sha256:" + "a" * 64}
    certificate_bytes = b'{"certificate":"exact-jc-bytes"}\n'
    certificate_digest = "sha256:" + hashlib.sha256(certificate_bytes).hexdigest()
    certificate_ref = {"kind": "formal-certificate-v4", "digest": certificate_digest}
    run_handle = {"content_ref": run_ref, "artifact_id": "run"}
    certificate_handle = {
        "content_ref": certificate_ref,
        "run_identity_ref": run_ref,
        "artifact_id": "certificate",
    }
    return {
        "bytes": certificate_bytes,
        "evaluate": event("jc_evaluate", {
            "result": {
                "decision_status": "ACCEPTED_FORMAL_RESULT",
                "certificate_kind": "FORMAL_VERIFIED",
                "run_identity_ref": run_ref,
            },
            "certificate_handle": certificate_handle,
            "run_handle": run_handle,
            "artifact_handles": [],
        }),
        "verify": event("jc_verify_run", {
            "verification": {
                "status": "VERIFIED",
                "run_identity_ref": run_ref,
                "certificate_ref": certificate_ref,
            },
            "replay": None,
        }),
        "read": event("jc_read_artifact", {
            "artifact_handle": certificate_handle,
            "offset": 0,
            "length": len(certificate_bytes),
            "next_offset": None,
            "content_base64": base64.b64encode(certificate_bytes).decode("ascii"),
            "chunk_digest": certificate_digest,
            "artifact_digest": certificate_digest,
            "content_type": "application/json",
            "eof": True,
        }),
    }
