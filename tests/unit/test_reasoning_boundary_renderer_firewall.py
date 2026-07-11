from compiler_core.output_firewall import renderer_firewall_metadata, validate_output_contract


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


def test_renderer_recursively_rejects_protected_and_final_fields_without_mutation():
    payload = {
        "sections": [
            {"analysis": {"final_conclusion": "certain"}},
            {"machine_override": {"result_status": "accepted_formal_result"}},
        ]
    }

    result = validate_output_contract(payload, result_status="review_only_result")

    assert not result["ok"]
    assert "$.sections[0].analysis.final_conclusion" in result["errors"][0]
    assert "$.sections[1].machine_override.result_status" in result["errors"][0]
    assert payload["sections"][0]["analysis"]["final_conclusion"] == "certain"


def test_renderer_rejects_nested_assertive_conclusion_phrases():
    result = validate_output_contract(
        {"sections": [{"analysis": "法院必然支持该请求"}]},
        result_status="review_only_result",
    )

    assert not result["ok"]
    assert "$.sections[0].analysis" in result["errors"][0]

