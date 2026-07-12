"""正式 application 使用的 argumentation certificate 回归测试。"""

from compiler_core.argumentation import grounded_extension
from compiler_core.litigation_engineering import generate_certificate


def _claim(claim_id: str) -> dict[str, str]:
    return {"id": claim_id}


def test_certificate_is_verifiable_for_accepted_argument() -> None:
    claims = [_claim("A"), _claim("B")]
    result = grounded_extension(claims, [("A", "B")])

    certificate = generate_certificate("A", claims, [("A", "B")], result)

    assert certificate.label == "IN"
    assert certificate.verifiable is True
    assert certificate.attackers == []


def test_certificate_minimizes_shared_defender() -> None:
    claims = [_claim(claim_id) for claim_id in ("A", "B", "C", "D")]
    attacks = [("B", "A"), ("C", "A"), ("D", "B"), ("D", "C")]
    result = grounded_extension(claims, attacks)

    certificate = generate_certificate("A", claims, attacks, result)

    assert certificate.label == "IN"
    assert certificate.minimal_witnesses == ["D"]
    assert certificate.defense_paths == [
        {"target": "A", "attacker": "B", "defenders": ["D"]},
        {"target": "A", "attacker": "C", "defenders": ["D"]},
    ]


def test_certificate_records_undecided_dependency() -> None:
    claims = [_claim(claim_id) for claim_id in ("A", "B", "C")]
    attacks = [("A", "B"), ("B", "A"), ("B", "C")]
    result = grounded_extension(claims, attacks)

    certificate = generate_certificate("C", claims, attacks, result)

    assert certificate.label == "UNDEC"
    assert certificate.attackers == ["B"]
    assert certificate.witnesses == ["B"]
