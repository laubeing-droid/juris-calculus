#!/usr/bin/env python3
"""Zero-dependency independent grounded extension checker.

Design constraint: this module imports NO juris-calculus internal modules.
It receives a canonical AAF JSON string (produced by canonical_serialization),
recomputes the grounded extension using its own implementation, and compares
the result against claimed labels.

Lean theorem refs are enumerated for audit trail but the checker itself
does not call Lean; it verifies algorithmic consistency only.
"""
from __future__ import annotations

import json
from typing import Any


def _recompute_grounded(
    claims: list[dict[str, Any]], attacks: list[tuple[str, str]]
) -> dict[str, str]:
    """Re-implementation of Dung (1995) grounded extension labelling.

    Characteristic function F(S) = {a | all attackers of a are attacked by S}.
    Iterate from empty set until fixed point, then assign IN/OUT/UNDEC labels.

    Returns dict mapping argument ID to "IN" | "OUT" | "UNDEC".
    """
    cids: set[str] = {c["id"] for c in claims}

    # Build attacker index: for each target, which sources attack it
    attackers_of: dict[str, set[str]] = {}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)

    # Fixed-point iteration from empty set
    accepted: set[str] = set()
    n = len(cids)
    max_iter = n + 1  # at most |AR| steps, +1 for convergence check
    iteration = 0

    while iteration < max_iter:
        iteration += 1
        defended: set[str] = set()
        for cid in cids:
            atts = attackers_of.get(cid, set())
            if not atts:
                # No attackers → always IN
                defended.add(cid)
            else:
                # An argument is defended if all its attackers are attacked by accepted
                all_defeated = True
                for a in atts:
                    a_atts = attackers_of.get(a, set())
                    if not (a_atts & accepted):
                        all_defeated = False
                        break
                if all_defeated:
                    defended.add(cid)

        if defended == accepted:
            # Fixed point reached
            break
        accepted = defended

    # Assign labels
    labels: dict[str, str] = {}
    for cid in cids:
        if cid in accepted:
            labels[cid] = "IN"
        else:
            atts = attackers_of.get(cid, set())
            if atts & accepted:
                labels[cid] = "OUT"
            else:
                labels[cid] = "UNDEC"

    return labels


def check_grounded(
    serialized_aaf: str,
    claimed_labels: dict[str, str],
    theorem_refs: list[str],
) -> dict[str, Any]:
    """Validate claimed grounded-extension labels against an independent recomputation.

    Args:
        serialized_aaf: Canonical AAF JSON from serialize_aaf.
        claimed_labels: dict mapping argument ID → "IN" | "OUT" | "UNDEC".
        theorem_refs: Lean theorem references (e.g. "Grounded.unique").
            Non-empty list signals that formal backing exists. The checker
            validates algorithmic consistency only; Lean verification is
            deferred to the theorem-prover bridge.

    Returns:
        {"valid": bool, "violations": list[str]}
        Where violations lists argument IDs with mismatched labels and
        additional consistency errors.
    """
    violations: list[str] = []

    # Theorem-ref validation: if refs are empty, flag a violation
    if not theorem_refs:
        violations.append("theorem_refs is empty: no Lean formal backing provided")

    # Attempt deserialization
    try:
        data = json.loads(serialized_aaf)
    except json.JSONDecodeError as e:
        violations.append(f"serialized_aaf is not valid JSON: {e}")
        return {"valid": False, "violations": violations}

    claims_raw = data.get("claims", [])
    attacks_raw = data.get("attacks", [])
    if not isinstance(claims_raw, list):
        violations.append("claims field missing or not a list")
        return {"valid": False, "violations": violations}
    if not isinstance(attacks_raw, list):
        violations.append("attacks field missing or not a list")
        return {"valid": False, "violations": violations}

    # Convert attacks back to tuple form
    attacks: list[tuple[str, str]] = []
    for a in attacks_raw:
        if isinstance(a, (list, tuple)) and len(a) == 2:
            attacks.append((str(a[0]), str(a[1])))
        else:
            violations.append(f"malformed attack entry: {a}")

    claims: list[dict[str, Any]] = claims_raw

    # Recompute grounded labels
    try:
        recomputed = _recompute_grounded(claims, attacks)
    except Exception as e:
        violations.append(f"grounded recomputation failed: {e}")
        return {"valid": False, "violations": violations}

    # Collect all argument IDs from both claims and claimed_labels
    claim_ids = {c["id"] for c in claims}
    label_ids = set(claimed_labels.keys())
    all_ids = claim_ids | label_ids

    for arg_id in sorted(all_ids):
        expected = claimed_labels.get(arg_id)
        actual = recomputed.get(arg_id)
        if expected is None:
            violations.append(
                f"argument '{arg_id}' has no claimed label"
            )
        elif actual is None:
            violations.append(
                f"argument '{arg_id}' claimed as '{expected}' but not in claim set"
            )
        elif expected != actual:
            violations.append(
                f"argument '{arg_id}' claimed '{expected}' but recomputed as '{actual}'"
            )

    # Also check for claims not in claimed_labels
    for arg_id in sorted(claim_ids - label_ids):
        violations.append(
            f"argument '{arg_id}' in AAF but missing from claimed_labels"
        )

    return {"valid": len(violations) == 0, "violations": violations}
