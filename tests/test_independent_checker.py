"""Tests for independent_grounded_checker.py — 10 tests covering empty AAF,
single argument, self-attack, even cycle, odd cycle, and JC evaluator cross-check."""

import pytest
from compiler_core.canonical_serialization import serialize_aaf
from compiler_core.independent_grounded_checker import check_grounded
from compiler_core.argumentation import grounded_extension


THEOREM_REFS = ["Lean.Dung1995.Grounded.unique", "Lean.Dung1995.Grounded.lfp"]


def _claim(id_):
    return {"id": id_}


# ---------------------------------------------------------------------------
# Test 1: Empty AAF — everything trivially valid
# ---------------------------------------------------------------------------
def test_empty_aaf():
    j = serialize_aaf([], [])
    result = check_grounded(j, {}, THEOREM_REFS)
    assert result["valid"] is True
    assert result["violations"] == []


# ---------------------------------------------------------------------------
# Test 2: Single argument, no attacks → IN
# ---------------------------------------------------------------------------
def test_single_argument():
    j = serialize_aaf([_claim("A")], [])
    result = check_grounded(j, {"A": "IN"}, THEOREM_REFS)
    assert result["valid"] is True


# ---------------------------------------------------------------------------
# Test 3: Single argument, self-attack → UNDEC
# ---------------------------------------------------------------------------
def test_self_attack():
    j = serialize_aaf([_claim("A")], [("A", "A")])
    result = check_grounded(j, {"A": "UNDEC"}, THEOREM_REFS)
    assert result["valid"] is True


# ---------------------------------------------------------------------------
# Test 4: Two arguments, unidirectional attack → one IN, one OUT
# ---------------------------------------------------------------------------
def test_unidirectional():
    j = serialize_aaf([_claim("A"), _claim("B")], [("A", "B")])
    result = check_grounded(j, {"A": "IN", "B": "OUT"}, THEOREM_REFS)
    assert result["valid"] is True


# ---------------------------------------------------------------------------
# Test 5: Even cycle (4 nodes) → all UNDEC
# ---------------------------------------------------------------------------
def test_even_cycle():
    j = serialize_aaf(
        [_claim("A"), _claim("B"), _claim("C"), _claim("D")],
        [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")],
    )
    result = check_grounded(
        j,
        {"A": "UNDEC", "B": "UNDEC", "C": "UNDEC", "D": "UNDEC"},
        THEOREM_REFS,
    )
    assert result["valid"] is True


# ---------------------------------------------------------------------------
# Test 6: Odd cycle (3 nodes) → all UNDEC
# ---------------------------------------------------------------------------
def test_odd_cycle():
    j = serialize_aaf(
        [_claim("X"), _claim("Y"), _claim("Z")],
        [("X", "Y"), ("Y", "Z"), ("Z", "X")],
    )
    result = check_grounded(
        j, {"X": "UNDEC", "Y": "UNDEC", "Z": "UNDEC"}, THEOREM_REFS
    )
    assert result["valid"] is True


# ---------------------------------------------------------------------------
# Test 7: Wrong label — flag as violation
# ---------------------------------------------------------------------------
def test_wrong_label_detected():
    j = serialize_aaf([_claim("A")], [])
    # Claim A is OUT but it should be IN (no attackers)
    result = check_grounded(j, {"A": "OUT"}, THEOREM_REFS)
    assert result["valid"] is False
    assert any("A" in v for v in result["violations"])


# ---------------------------------------------------------------------------
# Test 8: Cross-check against JC grounded_extension full set
# ---------------------------------------------------------------------------
def test_cross_check_jc_evaluator():
    """Recompute labels via check_grounded and compare with JC grounded_extension."""
    claims = [_claim("A"), _claim("B"), _claim("C"), _claim("D")]
    attacks = [("A", "B"), ("B", "C"), ("D", "C")]

    # Ground truth from JC
    jc_result = grounded_extension(claims, attacks)
    # Derive labels
    claimed: dict[str, str] = {}
    for cid in jc_result["accepted"]:
        claimed[cid] = "IN"
    for cid in jc_result["rejected"]:
        claimed[cid] = "OUT"
    for cid in jc_result["undecided"]:
        claimed[cid] = "UNDEC"

    j = serialize_aaf(claims, attacks)
    result = check_grounded(j, claimed, THEOREM_REFS)
    assert result["valid"] is True


# ---------------------------------------------------------------------------
# Test 9: More complex graph cross-check
# ---------------------------------------------------------------------------
def test_complex_graph_cross_check():
    """A more elaborate AAF: multiple SCCs, defended arguments."""
    claims = [_claim(f"N{i}") for i in range(8)]
    attacks = [
        ("N0", "N1"), ("N1", "N2"), ("N2", "N0"),  # 3-cycle
        ("N3", "N4"), ("N4", "N5"),  # chain
        ("N5", "N6"), ("N5", "N7"),  # N5 attacks two
    ]
    jc_result = grounded_extension(claims, attacks)
    claimed: dict[str, str] = {}
    for cid in jc_result["accepted"]:
        claimed[cid] = "IN"
    for cid in jc_result["rejected"]:
        claimed[cid] = "OUT"
    for cid in jc_result["undecided"]:
        claimed[cid] = "UNDEC"

    j = serialize_aaf(claims, attacks)
    result = check_grounded(j, claimed, THEOREM_REFS)
    assert result["valid"] is True


# ---------------------------------------------------------------------------
# Test 10: Empty theorem_refs is reported as violation
# ---------------------------------------------------------------------------
def test_empty_theorem_refs_violation():
    j = serialize_aaf([_claim("A")], [])
    result = check_grounded(j, {"A": "IN"}, [])
    assert result["valid"] is False
    assert any("theorem_refs" in v for v in result["violations"])
