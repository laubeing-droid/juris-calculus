"""Phase C2 incremental grounded extension tests."""

from compiler_core.argumentation import grounded_extension
from compiler_core.incremental_grounded import (
    incremental_grounded_add_argument,
    incremental_grounded_add_attack,
)


def _c(id_):
    return {"id": id_}


def _same_labelling(left, right):
    return (
        set(left["accepted"]) == set(right["accepted"])
        and set(left["rejected"]) == set(right["rejected"])
        and set(left["undecided"]) == set(right["undecided"])
    )


def test_add_argument_no_attackers():
    claims = [_c("A")]
    attacks = [("A", "A")]  # A self-attacks, undecided
    current = grounded_extension(claims, attacks)
    result = incremental_grounded_add_argument(claims, attacks, _c("B"), [], current)
    full = grounded_extension(claims + [_c("B")], attacks)
    assert result["incremental"] is True
    assert "B" in result["accepted"]
    assert _same_labelling(result, full)


def test_add_attack_single_scc_matches_full_recompute():
    claims = [_c("A"), _c("B")]
    attacks = [("A", "B"), ("B", "A")]
    current = grounded_extension(claims, attacks)
    result = incremental_grounded_add_attack(claims, attacks, ("A", "A"), current)
    full = grounded_extension(claims, attacks + [("A", "A")])
    assert result["incremental"] is True
    assert result["fallback_reason"] == ""
    assert _same_labelling(result, full)


def test_add_attack_source_scc_bug_regression_falls_back_to_full():
    claims = [_c("E"), _c("A"), _c("B")]
    attacks = [("A", "B")]
    current = grounded_extension(claims, attacks)
    result = incremental_grounded_add_attack(claims, attacks, ("E", "A"), current)
    full = grounded_extension(claims, attacks + [("E", "A")])
    assert result["incremental"] is False
    assert "MVM boundary exceeded" in result["fallback_reason"]
    assert _same_labelling(result, full)
    assert set(result["accepted"]) == {"B", "E"}


def test_add_attack_external_attacker_falls_back_to_full():
    claims = [_c("A"), _c("B"), _c("C")]
    attacks = [("A", "B")]
    current = grounded_extension(claims, attacks)
    result = incremental_grounded_add_attack(claims, attacks, ("C", "B"), current)
    full = grounded_extension(claims, attacks + [("C", "B")])
    assert result["incremental"] is False
    assert result["fallback_reason"] != ""
    assert _same_labelling(result, full)


def test_add_argument_external_attacker_falls_back_to_full():
    claims = [_c("A"), _c("B")]
    attacks = [("A", "B")]
    current = grounded_extension(claims, attacks)
    new_argument = _c("C")
    new_attacks = [("C", "A")]
    result = incremental_grounded_add_argument(claims, attacks, new_argument, new_attacks, current)
    full = grounded_extension(claims + [new_argument], attacks + new_attacks)
    assert result["incremental"] is False
    assert _same_labelling(result, full)
