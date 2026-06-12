from tools.agent_protocol_auditor import audit_protocol


def test_agent_protocol_enforces_superpowers_review_order():
    report = audit_protocol("configs/agent_collaboration_protocol.yaml")

    assert report["status"] == "PASS"
    assert report["issues"] == []
