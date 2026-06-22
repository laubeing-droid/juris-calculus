"""B6 engineering capability tests: SCC witness, label reasons, proof trace."""
from compiler_core.argumentation import (
    grounded_extension, scc_decomposition, find_cycles, label_reasons, proof_trace
)

def _c(id_): return {"id": id_}

def test_scc_decomposition_empty():
    assert scc_decomposition([], []) == []

def test_scc_decomposition_dag():
    sccs = scc_decomposition([_c("A"),_c("B"),_c("C")], [("A","B"),("B","C")])
    assert len(sccs) == 3  # each node is its own SCC

def test_scc_decomposition_cycle():
    sccs = scc_decomposition([_c("A"),_c("B"),_c("C")], [("A","B"),("B","C"),("C","A")])
    assert len(sccs) == 1  # one SCC containing all three

def test_find_cycles():
    cycles = find_cycles([_c("A"),_c("B")], [("A","B"),("B","A")])
    assert len(cycles) == 1  # bidirectional cycle

def test_find_cycles_self_attack():
    cycles = find_cycles([_c("A")], [("A","A")])
    assert len(cycles) == 1

def test_label_reasons():
    result = grounded_extension([_c("A"),_c("B")], [("A","B")])
    reasons = label_reasons([_c("A"),_c("B")], [("A","B")], result)
    assert reasons["A"]["label"] == "IN"
    assert reasons["B"]["label"] == "OUT"
    assert reasons["A"]["reason"] == "no attackers"

def test_label_reasons_undecided():
    result = grounded_extension([_c("A"),_c("B")], [("A","B"),("B","A")])
    reasons = label_reasons([_c("A"),_c("B")], [("A","B"),("B","A")], result)
    assert reasons["A"]["label"] == "UNDEC"
    assert reasons["B"]["label"] == "UNDEC"

def test_proof_trace():
    trace = proof_trace([_c("A"),_c("B")], [("A","B")])
    assert trace["convergent"] is True
    assert len(trace["iteration_history"]) >= 1
    assert "sccs" in trace
    assert "cycles" in trace
    assert "labels" in trace
