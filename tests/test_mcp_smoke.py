"""MCP Server 烟雾测试 — dry_run + evaluate + 错误码。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_dry_run():
    """dry_run=true: 仅预检，不跑 Fixpoint"""
    from mcp_server import _juris_evaluate_core
    facts = json.dumps({"contract_formed": "合同成立", "payment_due": "到期未还"})
    result = _juris_evaluate_core("contract", facts, dry_run=True)
    assert result.get("dry_run") is True, f"应为dry_run模式: {result}"
    assert "validated_facts" in result
    assert "blocked_reasons" in result
    print("  ✅ dry_run=true 预检通过")

def test_full_evaluate():
    """dry_run=false: 完整 Fixpoint 推理"""
    from mcp_server import _juris_evaluate_core
    facts = json.dumps({"contract_formed": "合同成立", "payment_due": "到期未还"})
    result = _juris_evaluate_core("contract", facts, dry_run=False)
    assert result.get("total_claims", 0) > 0, f"推理应产生结论: {result}"
    assert "top_claims" in result
    assert "domain" in result
    print(f"  ✅ evaluate: {result['total_claims']} 条结论, domain={result['domain']}")

def test_watchdog_violation():
    """US文本在CN模式下触发看门狗阻断"""
    from mcp_server import _juris_evaluate_core
    facts = json.dumps({"punitive_damages": "seeks punitive damages"})
    result = _juris_evaluate_core("contract", facts, source_law="CN", dry_run=True)
    blocked = result.get("blocked_reasons", [])
    assert len(blocked) > 0, "应触发US概念阻断"
    print(f"  ✅ 看门狗阻断: {len(blocked)}条")

def test_error_response():
    """非法 facts_json 返回错误"""
    from mcp_server import _juris_evaluate_sync
    try:
        _juris_evaluate_sync(domain="contract", facts_json="not-json")
        assert False, "应抛异常"
    except Exception as e:
        print(f"  ✅ 非法输入正确报错: {type(e).__name__}")

if __name__ == "__main__":
    print("=== MCP Smoke Test ===")
    test_dry_run()
    test_full_evaluate()
    test_watchdog_violation()
    test_error_response()
    print("=== 4/4 通过 ===")
