"""The pre-cutover MCP lookup fails closed for the retired exact pack ID."""

from __future__ import annotations

import importlib
import io
import json
import sys
import types


def _load_adapter(monkeypatch):
    analysis = types.ModuleType("compiler_core.analysis")
    analysis.AnalysisError = type("AnalysisError", (RuntimeError,), {})
    analysis.analyze_similar_cases = lambda *args, **kwargs: None
    analysis.analyze_strategy = lambda *args, **kwargs: None
    audit = types.ModuleType("compiler_core.audit_bundle")
    audit.AuditBundleError = type("AuditBundleError", (RuntimeError,), {})
    audit.default_state_root = lambda: None
    audit.evaluate_registered_case = lambda *args, **kwargs: None
    contracts = types.ModuleType("compiler_core.contracts")
    contracts.CaseRequest = type("CaseRequest", (), {})
    monkeypatch.setitem(sys.modules, "compiler_core.analysis", analysis)
    monkeypatch.setitem(sys.modules, "compiler_core.audit_bundle", audit)
    monkeypatch.setitem(sys.modules, "compiler_core.contracts", contracts)
    monkeypatch.delitem(sys.modules, "addons.workbuddy_mcp", raising=False)
    return importlib.import_module("addons.workbuddy_mcp")


def test_retired_pack_lookup_sets_protocol_is_error(monkeypatch, tmp_path) -> None:
    module = _load_adapter(monkeypatch)
    config_root = tmp_path / "configs"
    config_root.mkdir()
    adapter = module.WorkBuddyAdapter(
        config_root=config_root,
        development=True,
        state_root=tmp_path / "state",
    )
    retired_id = "cn-" + "legacy-corpus"
    messages = (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "jc_lookup_rule",
                "arguments": {"pack_id": retired_id, "query": "anything"},
            },
        },
    )
    stdin = io.StringIO("".join(json.dumps(item) + "\n" for item in messages))
    stdout = io.StringIO()
    monkeypatch.setattr(module.sys, "stdin", stdin)
    monkeypatch.setattr(module.sys, "stdout", stdout)
    module.run_stdio(adapter)

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    result = next(item["result"] for item in responses if item.get("id") == 2)
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "PACK_NOT_INSTALLED"
