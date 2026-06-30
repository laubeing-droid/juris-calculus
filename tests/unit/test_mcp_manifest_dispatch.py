import json
from pathlib import Path

from mcp_server import MCPServer, MCP_ENVELOPE_KEYS


ROOT = Path(__file__).resolve().parents[2]


SAMPLE_ARGS = {
    "trirail_collide": {"facts": {"contract_exists": 1.0}},
    "check_threat": {"facts": ["Alter-Ego liability"]},
    "generate_memo": {"case_id": "toy", "trirail_result": {}},
    "route_state": {"raw_fact": "CA_BP_17200", "state_code": "CA"},
    "get_citation": {"rule_id": "toy-rule"},
    "get_operator_schemas": {},
    "generate_task_schema": {},
    "rule_router": {"fact_texts": ["合同违约"]},
    "stratified_evaluate": {"facts": {"contract_exists": "contract exists"}},
    "neural_leaf_status": {},
    "search_rules": {"query": "合同"},
    "evaluate_facts": {"fact_items": {"contract_exists": "contract exists"}},
    "calculate_damages": {"principal": 1000, "lpr_rate": 3.45, "interest_days": 30},
    "analyze_strategy": {"fact_text": "合同违约"},
    "extract_elements": {"fact_text": "合同成立"},
    "evaluate_facts_llm": {"fact_text": "candidate"},
    "align_concepts_llm": {"cn_concept": "合同", "us_concept": "contract"},
    "generate_nlni_llm": {"case_description": "candidate"},
    "evaluate": {},
    "route": {"concept": "unknown", "source": "CN", "target": "HK"},
    "trace": {"graph_kind": "cycle"},
    "check": {"malformed_certificate": True},
    "batch": {"count": 1},
    "render": {},
    "diff": {"spec_root": str(ROOT.parent / "数学证明" / "legal-math-modeling")},
    "governance": {},
    "impact": {"rule_id": "rule::delivery_obligation"},
    "ingest_candidate": {"raw_text": "candidate only"},
}


def test_manifest_tools_all_return_public_envelope():
    manifest = json.loads((ROOT / "mcp_manifest.json").read_text(encoding="utf-8"))
    server = MCPServer()

    assert set(SAMPLE_ARGS) == set(manifest["tools"])
    for tool_name in manifest["tools"]:
        result = server._call_tool(tool_name, SAMPLE_ARGS[tool_name])
        assert MCP_ENVELOPE_KEYS <= set(result), tool_name
        assert "MISSING_HANDLER" not in result["risk_labels"], tool_name
        assert "TOOL_EXCEPTION" not in result["risk_labels"], tool_name


def test_unknown_tool_fails_closed():
    result = MCPServer()._call_tool("not_registered", {})

    assert result["status"] == "error"
    assert "UNKNOWN_TOOL" in result["risk_labels"]
