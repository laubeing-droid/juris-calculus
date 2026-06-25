#!/usr/bin/env python3
"""Canonical JSON serialization for AAF (Dung abstract argumentation) and Horn clauses.

Purpose: deterministic, hash-comparable JSON output so that independent
verification agents receive identical byte strings.
- All keys sorted (json.dumps sort_keys=True)
- All list elements sorted where semantics permit
- Round-trip fidelity: serialize → deserialize → serialize produces identical output
"""
from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# AAF: claims + attacks → deterministic JSON
# ---------------------------------------------------------------------------

def _make_aaf_canonical(
    claims: list[dict[str, Any]], attacks: list[tuple[str, str]]
) -> dict[str, Any]:
    """Build the canonical AAF dict with sorted internal ordering."""
    # Sort claims by 'id' for deterministic output
    sorted_claims = sorted(claims, key=lambda c: c.get("id", ""))
    # Sort attacks lexicographically
    sorted_attacks = sorted(attacks, key=lambda t: (t[0], t[1]))
    return {"claims": sorted_claims, "attacks": sorted_attacks}


def serialize_aaf(claims: list[dict[str, Any]], attacks: list[tuple[str, str]]) -> str:
    """Serialize an AAF to a deterministic JSON string.

    Args:
        claims: List of claim dicts, each with at least an 'id' key.
        attacks: List of (source_id, target_id) tuples.

    Returns:
        Deterministic JSON string (sorted keys, sorted lists).
        Same claims+attacks always produce identical output.
    """
    canonical = _make_aaf_canonical(claims, attacks)
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deserialize_aaf(json_str: str) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Deserialize a canonical AAF JSON string back to (claims, attacks).

    Args:
        json_str: Output of serialize_aaf.

    Returns:
        Tuple of (claims: list[dict], attacks: list[tuple[str, str]]).
    """
    data = json.loads(json_str)
    claims: list[dict[str, Any]] = data.get("claims", [])
    # Convert attacks back to list of tuples for consistency with the JC API
    attacks: list[tuple[str, str]] = [tuple(a) for a in data.get("attacks", [])]
    return claims, attacks


# ---------------------------------------------------------------------------
# Horn: rules + facts → deterministic JSON
# ---------------------------------------------------------------------------

def _make_horn_canonical(
    rules: list[dict[str, Any]], facts: set[str]
) -> dict[str, Any]:
    """Build the canonical Horn dict with sorted internal ordering."""
    # Sort rules by head, then by body for deterministic output
    sorted_rules = sorted(
        rules,
        key=lambda r: (r.get("head", ""), tuple(sorted(r.get("body", [])))),
    )
    # Within each rule, sort the body list
    for r in sorted_rules:
        if "body" in r:
            r["body"] = sorted(r["body"])
    # Sort facts
    sorted_facts = sorted(facts)
    return {"rules": sorted_rules, "facts": sorted_facts}


def serialize_horn(rules: list[dict[str, Any]], facts: set[str]) -> str:
    """Serialize Horn rules and facts to a deterministic JSON string.

    Args:
        rules: List of rule dicts, each with 'head' (str) and 'body' (list[str]).
        facts: Set of fact strings (ground atoms).

    Returns:
        Deterministic JSON string (sorted keys, sorted rules, sorted facts).
        Same rules+facts always produce identical output.
    """
    canonical = _make_horn_canonical(rules, facts)
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deserialize_horn(json_str: str) -> tuple[list[dict[str, Any]], set[str]]:
    """Deserialize a canonical Horn JSON string back to (rules, facts).

    Args:
        json_str: Output of serialize_horn.

    Returns:
        Tuple of (rules: list[dict], facts: set[str]).
    """
    data = json.loads(json_str)
    rules: list[dict[str, Any]] = data.get("rules", [])
    facts: set[str] = set(data.get("facts", []))
    return rules, facts
