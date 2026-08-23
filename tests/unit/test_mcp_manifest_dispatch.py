"""W5-03 boundary for the retired pre-cutover WorkBuddy adapter."""

from __future__ import annotations

from pathlib import Path

from addons.workbuddy_mcp import TOOL_NAMES, WorkBuddyAdapter, manifest_document, run_smoke


ROOT = Path(__file__).resolve().parents[2]


def test_workbuddy_tombstone_exposes_no_tools_or_resources() -> None:
    manifest = manifest_document(ROOT / "mcp_manifest.json")

    assert TOOL_NAMES == ()
    assert manifest["tools"] == {}
    assert manifest["resources"] == {}
    assert manifest["protocol_version"] == "2024-11-05"


def test_retired_advisory_tool_fails_closed() -> None:
    result = WorkBuddyAdapter().call_tool("jc_analyze_strategy", {"run_id": "old"})

    assert result["status"] == "error"
    assert result["error"]["code"] == "UNKNOWN_TOOL"


def test_tombstone_smoke_never_claims_readiness(capsys) -> None:
    assert run_smoke(ROOT / "mcp_manifest.json") == 0
    output = capsys.readouterr().out
    assert '"readiness_claimed": false' in output
    assert '"tool_count": 0' in output


def test_default_distribution_does_not_register_workbuddy() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "jc-workbuddy" not in pyproject
    assert "addons.workbuddy_mcp" not in pyproject
