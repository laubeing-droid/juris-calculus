from compiler_core.io_contracts import IORegistry, ModuleIOContract, validate_mcp_machine_status
from mcp_server import MCPServer


def test_pipeline_step_cannot_read_undeclared_fact():
    contract = ModuleIOContract(module_id="step.a", consumed_keys=frozenset({"fact.a"}))

    contract.validate_read("fact.a")
    try:
        contract.validate_read("fact.b")
    except ValueError as exc:
        assert "undeclared fact key" in str(exc)
    else:
        raise AssertionError("undeclared read should fail")


def test_pipeline_step_cannot_output_undeclared_final_conclusion():
    contract = ModuleIOContract(module_id="step.a", produced_keys=frozenset({"packet.a"}))

    contract.validate_output("packet.a")
    try:
        contract.validate_output("final_legal_opinion")
    except ValueError as exc:
        assert "undeclared output key" in str(exc)
    else:
        raise AssertionError("undeclared output should fail")


def test_output_key_ownership_collision_is_blocked():
    registry = IORegistry()
    registry.claim_outputs(ModuleIOContract("step.a", produced_keys=frozenset({"packet"})))

    try:
        registry.claim_outputs(ModuleIOContract("step.b", produced_keys=frozenset({"packet"})))
    except ValueError as exc:
        assert "collision" in str(exc)
    else:
        raise AssertionError("output collision should fail")


def test_mcp_api_returns_machine_readable_lsc_status():
    result = MCPServer()._call_tool("search_rules", {"query": "合同"})

    assert validate_mcp_machine_status(result["payload"])
    assert "result_status" in result["payload"]["lsc_boundary"]

