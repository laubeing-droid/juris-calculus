from compiler_core.output_firewall import renderer_firewall_metadata, validate_output_contract
from compiler_core.proof_trace_renderer import format_boundary_result_cn
from compiler_core.post_freeze_surface import certified_litigation_report


def test_renderer_does_not_turn_hypothetical_into_final_opinion():
    result = validate_output_contract(
        {"final_conclusion": "must not appear"},
        result_status="hypothetical_result",
    )

    assert not result["ok"]
    assert result["renderer_firewall"]["formal_legal_opinion"] is False
    assert not result["renderer_firewall"]["may_render_final_conclusion"]


def test_renderer_shows_degraded_alternative_role():
    metadata = renderer_firewall_metadata("review_only_result")

    assert metadata["rendering_role"] == "review_packet"
    assert metadata["machine_state_preserved"] is True


def test_engine_error_rendering_is_not_legal_advice():
    text = format_boundary_result_cn({"result_status": "engine_error"})

    assert "不得转换为法律建议" in text


def test_mcp_render_payload_preserves_renderer_firewall():
    result = certified_litigation_report({"facts": ["candidate::unverified"]})

    assert result["payload"]["renderer_firewall"]["formal_legal_opinion"] is False
    assert result["payload"]["lsc_boundary"]["result_status"] == "review_only_result"

