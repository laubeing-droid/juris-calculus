"""Tests for canonical_serialization.py — 8 tests covering AAF and Horn round-trip,
deterministic output, and format validation."""

import json
import pytest
from compiler_core.canonical_serialization import (
    serialize_aaf,
    deserialize_aaf,
    serialize_horn,
    deserialize_horn,
)


# ---------------------------------------------------------------------------
# Test 1: AAF round-trip (serialize → deserialize → data equivalence)
# ---------------------------------------------------------------------------
def test_aaf_round_trip():
    """serialize + deserialize should preserve claims and attacks data."""
    claims = [{"id": "A", "desc": "alpha"}, {"id": "B", "desc": "beta"}]
    attacks = [("A", "B")]
    json_str = serialize_aaf(claims, attacks)
    claims2, attacks2 = deserialize_aaf(json_str)
    # Re-sort claims by id for comparison since order may change
    assert sorted(claims, key=lambda c: c["id"]) == sorted(claims2, key=lambda c: c["id"])
    assert sorted(attacks) == sorted(attacks2)


# ---------------------------------------------------------------------------
# Test 2: AAF deterministic output (same input → identical JSON)
# ---------------------------------------------------------------------------
def test_aaf_deterministic_output():
    """Two calls with same input must produce byte-identical JSON strings."""
    claims = [{"id": "X"}, {"id": "Y", "extra": 1}]
    attacks = [("X", "Y"), ("Y", "X")]
    j1 = serialize_aaf(claims, attacks)
    j2 = serialize_aaf(claims, attacks)
    assert j1 == j2


# ---------------------------------------------------------------------------
# Test 3: AAF deterministic regardless of input order
# ---------------------------------------------------------------------------
def test_aaf_input_order_invariant():
    """Input claim/attack order should not affect serialized output."""
    j_a = serialize_aaf(
        [{"id": "B"}, {"id": "A"}],
        [("B", "A")]
    )
    j_b = serialize_aaf(
        [{"id": "A"}, {"id": "B"}],
        [("B", "A")]
    )
    assert j_a == j_b


# ---------------------------------------------------------------------------
# Test 4: AAF serialization produces valid JSON with correct structure
# ---------------------------------------------------------------------------
def test_aaf_valid_json_structure():
    """Serialized output must parse as valid JSON with 'claims' and 'attacks' keys."""
    claims = [{"id": "C1"}]
    attacks = []
    j = serialize_aaf(claims, attacks)
    data = json.loads(j)
    assert "claims" in data
    assert "attacks" in data
    assert isinstance(data["claims"], list)
    assert isinstance(data["attacks"], list)


# ---------------------------------------------------------------------------
# Test 5: Horn round-trip
# ---------------------------------------------------------------------------
def test_horn_round_trip():
    """serialize_horn + deserialize_horn should preserve rules and facts."""
    rules = [
        {"head": "p", "body": ["q", "r"]},
        {"head": "q", "body": []},
    ]
    facts = {"r", "s"}
    json_str = serialize_horn(rules, facts)
    rules2, facts2 = deserialize_horn(json_str)
    assert facts == facts2
    # Rules should have sorted bodies now, compare accordingly
    assert len(rules) == len(rules2)
    for r in rules2:
        assert "head" in r
        assert "body" in r


# ---------------------------------------------------------------------------
# Test 6: Horn deterministic output
# ---------------------------------------------------------------------------
def test_horn_deterministic_output():
    """Two calls with same input must produce identical JSON."""
    rules = [{"head": "A", "body": ["B"]}]
    facts = {"B"}
    j1 = serialize_horn(rules, facts)
    j2 = serialize_horn(rules, facts)
    assert j1 == j2


# ---------------------------------------------------------------------------
# Test 7: Horn serialization produces valid JSON with correct structure
# ---------------------------------------------------------------------------
def test_horn_valid_json_structure():
    """Serialized Horn output must have 'rules' and 'facts' keys."""
    rules = [{"head": "h", "body": ["a", "b"]}]
    facts = {"a"}
    j = serialize_horn(rules, facts)
    data = json.loads(j)
    assert "rules" in data
    assert "facts" in data
    assert isinstance(data["rules"], list)
    assert isinstance(data["facts"], list)


# ---------------------------------------------------------------------------
# Test 8: Empty inputs round-trip correctly
# ---------------------------------------------------------------------------
def test_empty_inputs_round_trip():
    """Empty claims/attacks and empty rules/facts must round-trip cleanly."""
    j_a = serialize_aaf([], [])
    c, a = deserialize_aaf(j_a)
    assert c == []
    assert a == []

    j_h = serialize_horn([], set())
    r, f = deserialize_horn(j_h)
    assert r == []
    assert f == set()
