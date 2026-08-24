"""Negative replacements for legacy V3/compat acceptance tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from compiler_core import contracts, mcp


REPO = Path(__file__).resolve().parents[2]
VECTORS = json.loads(
    (REPO / "tests" / "contract" / "v4-contract-vectors.json").read_text(
        encoding="utf-8"
    )
)


def test_engine_3_payload_fails() -> None:
    payload = deepcopy(VECTORS["objects"]["MCPCapabilitiesOutputV4"])
    payload["engine_version"] = "3.0.2"

    with pytest.raises(contracts.ContractV4Error) as direct:
        contracts.MCPCapabilitiesOutputV4.from_dict(payload)
    assert direct.value.code == "ENGINE_VERSION_MISMATCH"

    with pytest.raises(contracts.ContractV4Error) as public_codec:
        mcp.decode_tool_payload("jc_capabilities", "output", payload)
    assert public_codec.value.code == "ENGINE_VERSION_MISMATCH"


def test_v3_payload_has_no_upgrade_path() -> None:
    payload = deepcopy(VECTORS["objects"]["MCPEvaluateInputV4"])
    payload["case_bundle"]["request"]["schema_version"] = "jc/3.0"

    with pytest.raises(contracts.ContractV4Error) as rejected:
        mcp.decode_tool_payload("jc_evaluate", "input", payload)
    assert rejected.value.code == "SCHEMA_VERSION"
    assert not hasattr(contracts, "migrate_v3_request")
    assert not hasattr(mcp, "migrate_v3_request")


def test_only_v4_schema_is_generated() -> None:
    schema = mcp.schema_document()
    encoded = mcp.schema_bytes()

    assert schema["$id"] == "https://juris-calculus.local/schemas/jc-v4.schema.json"
    assert set(schema["$defs"]) == set(contracts.V4_TYPE_REGISTRY)
    assert encoded == (REPO / "schemas" / "jc-v4.schema.json").read_bytes()
    assert b"jc/3.0" not in encoded
    assert b"compat_v3_v4" not in encoded
