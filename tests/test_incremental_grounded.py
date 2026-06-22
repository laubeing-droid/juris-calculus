"""Phase C2 incremental grounded extension tests."""
from compiler_core.incremental_grounded import (
    incremental_grounded_add_argument, incremental_grounded_add_attack
)
from compiler_core.argumentation import grounded_extension

def _c(id_): return {"id": id_}

def test_add_argument_no_attackers():
    claims = [_c("A")]
    attacks = [("A","A")]  # A self-attacks, undecided
    cur = grounded_extension(claims, attacks)
    r = incremental_grounded_add_argument(claims, attacks, _c("B"), [], cur)
    assert r["incremental"] is True
    assert "B" in r["accepted"]

def test_add_attack_single_scc():
    claims = [_c("A"),_c("B"),_c("C")]
    attacks = [("A","B")]
    cur = grounded_extension(claims, attacks)
    r = incremental_grounded_add_attack(claims, attacks, ("B","C"), cur)
    assert "incremental" in r
