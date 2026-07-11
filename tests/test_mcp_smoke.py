"""MCP旧求值入口移除与审计准入烟雾测试。"""

import mcp_server


def test_legacy_mcp_evaluation_wrappers_are_removed():
    """旧wrapper不得绕过CaseRequest、pack准入和审计包。"""

    assert not hasattr(mcp_server, "_juris_evaluate_core")
    assert not hasattr(mcp_server, "_juris_evaluate_sync")


def test_legacy_free_text_evaluation_is_rejected():
    """自由文本或裸fact_items不能被静默升级为正式推理输入。"""

    result = mcp_server.juris_query(
        "evaluate_facts",
        "合同成立",
        {"fact_items": {"f1": "合同成立"}},
    )
    assert result == {
        "error": "legacy free-text evaluation was removed; case_request is required",
        "code": "CASE_REQUEST_REQUIRED",
    }


def test_strategy_requires_an_audited_run():
    """策略只能消费审计run ID，不能重新推理自由文本。"""

    result = mcp_server.juris_query("analyze_strategy", "合同违约")
    assert result["code"] == "AUDITED_RUN_REQUIRED"
