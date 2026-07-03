from compiler_core.review_packet import ReviewPacket, build_review_packet
from compiler_core.fact_trust_envelope import FactTrustEnvelope, FactTrustStatus
from compiler_core.lsc_boundary_status import classify_boundary_result


def test_disputed_fact_generates_review_packet_with_alternative_paths():
    packet = build_review_packet(
        "disputed fact",
        fact_keys=["fact.disputed"],
        alternative_paths=[{"path": "A"}, {"path": "B"}],
    ).to_dict()

    assert packet["result_status"] == "review_only_result"
    assert packet["alternative_paths"] == [{"path": "A"}, {"path": "B"}]


def test_review_packet_does_not_enter_certificate_accepted_result():
    packet = ReviewPacket(reason="P1/P2 boundary", fact_keys=("fact.p1",)).to_dict()

    assert packet["enters_certificate_accepted_result"] is False


def test_disputed_boundary_result_contains_alternative_paths():
    result = classify_boundary_result([
        FactTrustEnvelope(
            "fact.disputed",
            None,
            FactTrustStatus.DISPUTED,
            alternatives=({"value": "A"}, {"value": "B"}),
        )
    ])

    assert result.result_status.value == "review_only_result"
    assert result.payload["alternative_paths"][0]["fact_key"] == "fact.disputed"

