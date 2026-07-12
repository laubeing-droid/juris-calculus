"""G9A test suite: 18 graph types for grounded extension correctness."""
import pytest
from compiler_core.argumentation import grounded_extension

def _claim(id_): return {"id": id_}

def test_empty_graph():
    r = grounded_extension([], [])
    assert r["accepted"] == []; assert r["convergent"] is True; assert r["derived_bound"] == 1

def test_single_node():
    r = grounded_extension([_claim("A")], [])
    assert r["accepted"] == ["A"]; assert r["convergent"] is True

def test_self_attack():
    r = grounded_extension([_claim("A")], [("A","A")])
    assert r["accepted"] == []; assert r["undecided"] == ["A"]; assert r["convergent"] is True

def test_unidirectional():
    r = grounded_extension([_claim("A"),_claim("B")], [("A","B")])
    assert r["accepted"] == ["A"]; assert r["rejected"] == ["B"]

def test_bidirectional():
    r = grounded_extension([_claim("A"),_claim("B")], [("A","B"),("B","A")])
    assert r["accepted"] == []; assert r["undecided"] == ["A","B"]

def test_odd_cycle_triangle():
    r = grounded_extension([_claim("A"),_claim("B"),_claim("C")], [("A","B"),("B","C"),("C","A")])
    assert r["accepted"] == []; assert r["undecided"] == ["A","B","C"]

def test_even_cycle():
    r = grounded_extension([_claim("A"),_claim("B"),_claim("C"),_claim("D")], [("A","B"),("B","C"),("C","D"),("D","A")])
    assert r["accepted"] == []; assert r["undecided"] == ["A","B","C","D"]

def test_chorded_cycle():
    r = grounded_extension([_claim("A"),_claim("B"),_claim("C")], [("A","B"),("B","C"),("C","A"),("A","C")])
    assert r["accepted"] == []; assert set(r["undecided"]) == {"A","B","C"}

def test_multiple_sccs():
    r = grounded_extension([_claim("A"),_claim("B"),_claim("C"),_claim("D")], [("A","B"),("B","A"),("C","D")])
    assert r["accepted"] == ["C"]; assert r["rejected"] == ["D"]; assert set(r["undecided"]) == {"A","B"}

def test_scc_to_dag():
    r = grounded_extension([_claim("A"),_claim("B"),_claim("C"),_claim("D")], [("A","B"),("B","A"),("A","C"),("C","D")])
    assert set(r["undecided"]) == {"A","B","C","D"}

def test_dag_to_scc():
    r = grounded_extension([_claim("A"),_claim("B"),_claim("C")], [("C","A"),("A","B"),("B","A")])
    assert set(r["accepted"]) == {"B","C"}; assert set(r["rejected"]) == {"A"}; assert r["undecided"] == []

def test_multiple_attackers():
    r = grounded_extension([_claim("A"),_claim("B"),_claim("C"),_claim("D")], [("B","A"),("C","A"),("D","A")])
    assert r["accepted"] == ["B","C","D"]; assert r["rejected"] == ["A"]

def test_long_defense_chain():
    n = 50; claims = [_claim(f"A{i}") for i in range(n)]
    attacks = [(f"A{i}",f"A{i+1}") for i in range(n-1)]
    r = grounded_extension(claims, attacks)
    assert len(r["accepted"]) == (n+1)//2; assert r["convergent"] is True

def test_large_graph():
    n = 150; claims = [_claim(f"N{i}") for i in range(n)]
    attacks = [(f"N{i}",f"N{i+1}") for i in range(n-1)]
    r = grounded_extension(claims, attacks)
    assert r["iterations"] <= r["derived_bound"]; assert r["convergent"] is True

def test_order_permutation():
    ra = grounded_extension([_claim("A"),_claim("B"),_claim("C"),_claim("D")], [("A","B"),("B","C")])
    rb = grounded_extension([_claim("D"),_claim("C"),_claim("A"),_claim("B")], [("A","B"),("B","C")])
    assert ra["accepted"] == rb["accepted"]; assert ra["undecided"] == rb["undecided"]

def test_duplicate_edges():
    r = grounded_extension([_claim("A"),_claim("B")], [("A","B"),("A","B")])
    assert r["accepted"] == ["A"]; assert r["rejected"] == ["B"]

def test_orphan_endpoints():
    r = grounded_extension([_claim("A")], [("X","A"),("A","Y")])
    assert r["accepted"] == ["A"]; assert r["convergent"] is True

def test_disconnected_components():
    r = grounded_extension([_claim("A"),_claim("B"),_claim("C"),_claim("D")], [("A","B")])
    assert sorted(r["accepted"]) == ["A","C","D"]; assert r["rejected"] == ["B"]

def test_derived_bound_respected():
    n = 10; claims = [_claim(f"A{i}") for i in range(n)]
    attacks = [(f"A{i}",f"A{i+1}") for i in range(n-1)]
    r = grounded_extension(claims, attacks)
    assert r["derived_bound"] == n + 1; assert r["iterations"] <= n + 1; assert r["convergent"] is True; assert r["truncated"] is False

def test_truncated_when_insufficient_max_iter():
    n = 10; claims = [_claim(f"A{i}") for i in range(n)]
    attacks = [(f"A{i}",f"A{i+1}") for i in range(n-1)]
    r = grounded_extension(claims, attacks, max_iter=2)
    assert r["truncated"] is True; assert r["convergent"] is False
