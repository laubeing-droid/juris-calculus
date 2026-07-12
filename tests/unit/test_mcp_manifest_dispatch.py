"""四项WorkBuddy工具的manifest、分发和审计边界测试。"""

from __future__ import annotations

import json
from pathlib import Path

from addons.workbuddy_mcp import TOOL_NAMES, WorkBuddyAdapter, manifest_document
from tests.unit.test_audit_bundle import _fixture


ROOT = Path(__file__).resolve().parents[2]
CASE_INDEX = ROOT / "tests" / "fixtures" / "synthetic_case_index.json"


def _adapter_run(tmp_path: Path):
    """构造development pack并通过MCP薄层产生一个完整审计run。"""

    _, request = _fixture(tmp_path / "configs")
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(request.to_dict(), ensure_ascii=False), encoding="utf-8")
    adapter = WorkBuddyAdapter(
        config_root=tmp_path / "configs",
        development=True,
        state_root=tmp_path / "state",
    )
    result = adapter.call_tool("jc_evaluate", {"input_path": str(input_path)})
    return adapter, result


def test_manifest_exposes_exactly_four_versioned_tools_and_no_resources() -> None:
    """旧工具面与整库resources不得重新进入生产manifest。"""

    manifest = manifest_document(ROOT / "mcp_manifest.json")

    assert tuple(manifest["tools"]) == TOOL_NAMES
    assert manifest["resources"] == {}
    assert manifest["version"]
    assert manifest["protocol_version"] == "2024-11-05"
    assert all("inputSchema" in tool and "outputSchema" in tool for tool in manifest["tools"].values())


def test_four_tools_share_existing_application_and_return_logical_refs(tmp_path) -> None:
    """四工具返回紧凑结果，不回显本地路径、events或traceback。"""

    adapter, evaluated = _adapter_run(tmp_path)
    run_id = evaluated["run_id"]
    looked_up = adapter.call_tool("jc_lookup_rule", {"pack_id": "fixture-official", "rule_id": "R-ANCHORED"})
    strategy = adapter.call_tool("jc_analyze_strategy", {"run_id": run_id})
    similar = adapter.call_tool(
        "jc_analyze_similar_cases",
        {"run_id": run_id, "index_path": str(CASE_INDEX), "limit": 2},
    )

    assert evaluated["status"] == "ok"
    assert evaluated["result_status"] == "accepted_formal_result"
    assert evaluated["review_required"] is False
    assert evaluated["formal_kernel_used"] is True
    assert looked_up["results"][0]["rule_id"] == "R-ANCHORED"
    assert strategy["analysis_status"] == "ADVISORY" and strategy["review_required"] is True
    assert similar["analysis_status"] == "ADVISORY" and similar["review_required"] is True
    for payload in (evaluated, looked_up, strategy, similar):
        serialized = json.dumps(payload, ensure_ascii=False)
        assert str(tmp_path) not in serialized
        assert "traceback" not in serialized.casefold()
        assert "events.jsonl" not in serialized or payload is evaluated
    assert all(ref.startswith("run://") for ref in evaluated["artifact_refs"])


def test_unknown_or_schema_invalid_tool_fails_closed(tmp_path) -> None:
    """未知工具和多余参数只返回机器错误，不进入业务服务。"""

    adapter, _ = _adapter_run(tmp_path)

    unknown = adapter.call_tool("trirail_collide", {})
    invalid = adapter.call_tool("jc_evaluate", {"input_path": "x", "facts": {}})

    assert unknown["error"]["code"] == "UNKNOWN_TOOL"
    assert invalid["error"]["code"] == "INVALID_TOOL_INPUT"
