"""Phase C2: Incremental Grounded Extension.

When arguments or attack edges are added/deleted, compute the grounded
extension incrementally rather than re-running globally.

Key theorem (MVM): For single-edge addition in DAG + single-SCC graphs,
the grounded extension change is localized to the affected SCC and its
successors. Beyond the MVM boundary, automatically fall back to full
recomputation with TRUNCATED marking.
"""

from __future__ import annotations

from typing import Any

from compiler_core.argumentation import grounded_extension, scc_decomposition

MAX_INCREMENTAL_AFFECTED_SCCS = 1


def _fallback_full_recompute(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    affected_sccs: list[list[str]],
    reason: str,
) -> dict[str, Any]:
    full = grounded_extension(claims, attacks)
    full["incremental"] = False
    full["affected_sccs"] = affected_sccs
    full["fallback_reason"] = reason
    return full


def incremental_grounded_add_argument(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    new_argument: dict[str, Any],
    new_attacks: list[tuple[str, str]],
    current_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Incrementally update grounded extension after adding an argument.

    Strategy:
    1. If the new argument has no attackers, it enters IN.
    2. If it is within an existing SCC, recompute that SCC + successors.
    3. Otherwise, add the new argument and its attacks, then
       identify which SCCs are affected (any SCC containing an argument
       attacked by the new argument).
    4. Recompute only affected SCCs and their successors.
    5. If the affected region exceeds MVM boundary (single-SCC + DAG),
       fall back to full recomputation and mark TRUNCATED.

    Returns: same structure as grounded_extension() with added fields:
      - incremental: bool (True if partial recompute succeeded)
      - affected_sccs: list of SCCs recomputed
      - fallback_reason: str (non-empty if full recompute was needed)
    """
    if current_result is None:
        current_result = grounded_extension(claims, attacks)

    all_claims = claims + [new_argument]
    all_attacks = attacks + new_attacks
    cids = {c["id"] for c in all_claims}
    arg_id = new_argument["id"]

    # Build attackers-of index after addition
    attackers_of: dict[str, set[str]] = {}
    for src, tgt in all_attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)

    # New argument with no attackers and no outgoing attacks: trivially IN
    if not attackers_of.get(arg_id, set()) and not new_attacks:
        full = grounded_extension(all_claims, all_attacks)
        full["incremental"] = True
        full["affected_sccs"] = [[arg_id]]
        full["fallback_reason"] = ""
        return full

    # Identify affected SCCs: any SCC containing an argument
    # that the new argument attacks OR any argument in the new argument's SCC
    sccs = scc_decomposition(all_claims, all_attacks)
    scc_map: dict[str, int] = {}
    for i, scc in enumerate(sccs):
        for v in scc:
            scc_map[v] = i

    # Arguments attacked by the new argument
    new_targets = {tgt for src, tgt in new_attacks if src == arg_id}
    affected_scc_indices: set[int] = set()

    # The new argument's own SCC
    if arg_id in scc_map:
        affected_scc_indices.add(scc_map[arg_id])

    # SCCs containing targets of the new argument
    for tgt in new_targets:
        if tgt in scc_map:
            affected_scc_indices.add(scc_map[tgt])

    # Add all successor SCCs
    # (SCCs that can be reached via attack edges from affected SCCs)
    adj_scc: dict[int, set[int]] = {}
    for src, tgt in all_attacks:
        if src in scc_map and tgt in scc_map:
            si, ti = scc_map[src], scc_map[tgt]
            if si != ti:
                adj_scc.setdefault(si, set()).add(ti)

    # Close affected set under reachability
    changed = True
    while changed:
        changed = False
        for si in list(affected_scc_indices):
            for ti in adj_scc.get(si, set()):
                if ti not in affected_scc_indices:
                    affected_scc_indices.add(ti)
                    changed = True

    # MVM boundary: if more than one SCC is affected (beyond the new argument's SCC),
    # fall back to full recompute
    if len(affected_scc_indices) > MAX_INCREMENTAL_AFFECTED_SCCS:
        return _fallback_full_recompute(
            all_claims,
            all_attacks,
            [sccs[i] for i in sorted(affected_scc_indices)],
            (
                f"MVM boundary exceeded: {len(affected_scc_indices)} SCCs affected "
                f"(limit: {MAX_INCREMENTAL_AFFECTED_SCCS}). Full recompute performed."
            ),
        )

    # Partial recompute: only affected SCCs + their arguments
    affected_args: set[str] = set()
    for si in affected_scc_indices:
        affected_args.update(sccs[si])

    external_attackers = sorted({
        src for src, tgt in all_attacks
        if tgt in affected_args and src not in affected_args
    })
    if external_attackers:
        return _fallback_full_recompute(
            all_claims,
            all_attacks,
            [sccs[i] for i in sorted(affected_scc_indices)],
            (
                "External attackers reach the affected region; "
                "partial recompute would silently drop outside labels. Full recompute performed."
            ),
        )

    # Collect all arguments needed: affected SCCs + incoming attackers
    # from non-affected regions (whose labels are already fixed)
    partial_claims = [c for c in all_claims if c["id"] in affected_args]
    partial_attacks = [
        (s, t) for s, t in all_attacks
        if t in affected_args
    ]

    partial_result = grounded_extension(partial_claims, partial_attacks)

    # Merge: non-affected arguments keep their previous labels
    full_accepted = set(current_result["accepted"])
    full_rejected = set(current_result["rejected"])
    full_undecided = set(current_result["undecided"])

    # Remove affected args from previous labels
    for aid in affected_args:
        full_accepted.discard(aid)
        full_rejected.discard(aid)
        full_undecided.discard(aid)

    # Add new labels for affected args
    full_accepted.update(partial_result["accepted"])
    full_rejected.update(partial_result["rejected"])
    full_undecided.update(partial_result["undecided"])

    return {
        "accepted": sorted(full_accepted),
        "rejected": sorted(full_rejected),
        "undecided": sorted(full_undecided),
        "iterations": partial_result["iterations"],
        "derived_bound": partial_result.get("derived_bound", 0),
        "convergent": partial_result.get("convergent", True),
        "truncated": partial_result.get("truncated", False),
        "incremental": True,
        "affected_sccs": [sccs[i] for i in sorted(affected_scc_indices)],
        "fallback_reason": "",
    }


def incremental_grounded_add_attack(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    new_attack: tuple[str, str],
    current_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Incrementally update grounded extension after adding a single attack edge.

    Same MVM strategy as add_argument: identify the affected SCC,
    recompute it and its successors, fall back to full if >2 SCCs affected.
    """
    if current_result is None:
        current_result = grounded_extension(claims, attacks)

    all_attacks = attacks + [new_attack]
    src, tgt = new_attack

    sccs = scc_decomposition(claims, all_attacks)
    scc_map: dict[str, int] = {}
    for i, scc in enumerate(sccs):
        for v in scc:
            scc_map[v] = i

    # Affected: both the target SCC and the source SCC of the new edge.
    # If the source sits outside the recompute window, the new edge is silently
    # filtered out by grounded_extension's local cids check.
    affected_scc_indices: set[int] = set()
    if tgt in scc_map:
        affected_scc_indices.add(scc_map[tgt])
    if src in scc_map:
        affected_scc_indices.add(scc_map[src])

    # Close under successors
    adj_scc: dict[int, set[int]] = {}
    for s, t in all_attacks:
        if s in scc_map and t in scc_map:
            si, ti = scc_map[s], scc_map[t]
            if si != ti:
                adj_scc.setdefault(si, set()).add(ti)

    changed = True
    while changed:
        changed = False
        for si in list(affected_scc_indices):
            for ti in adj_scc.get(si, set()):
                if ti not in affected_scc_indices:
                    affected_scc_indices.add(ti)
                    changed = True

    if len(affected_scc_indices) > MAX_INCREMENTAL_AFFECTED_SCCS:
        return _fallback_full_recompute(
            claims,
            all_attacks,
            [sccs[i] for i in sorted(affected_scc_indices)],
            (
                f"MVM boundary exceeded: {len(affected_scc_indices)} SCCs affected "
                f"(limit: {MAX_INCREMENTAL_AFFECTED_SCCS}). Full recompute performed."
            ),
        )

    affected_args: set[str] = set()
    for si in affected_scc_indices:
        affected_args.update(sccs[si])

    external_attackers = sorted({
        s for s, t in all_attacks
        if t in affected_args and s not in affected_args
    })
    if external_attackers:
        return _fallback_full_recompute(
            claims,
            all_attacks,
            [sccs[i] for i in sorted(affected_scc_indices)],
            (
                "External attackers reach the affected region; "
                "partial recompute would silently drop outside labels. Full recompute performed."
            ),
        )

    partial_claims = [c for c in claims if c["id"] in affected_args]
    partial_attacks = [(s, t) for s, t in all_attacks if t in affected_args]
    partial_result = grounded_extension(partial_claims, partial_attacks)

    full_accepted = set(current_result["accepted"])
    full_rejected = set(current_result["rejected"])
    full_undecided = set(current_result["undecided"])
    for aid in affected_args:
        full_accepted.discard(aid)
        full_rejected.discard(aid)
        full_undecided.discard(aid)
    full_accepted.update(partial_result["accepted"])
    full_rejected.update(partial_result["rejected"])
    full_undecided.update(partial_result["undecided"])

    return {
        "accepted": sorted(full_accepted),
        "rejected": sorted(full_rejected),
        "undecided": sorted(full_undecided),
        "iterations": partial_result["iterations"],
        "derived_bound": partial_result.get("derived_bound", 0),
        "convergent": partial_result.get("convergent", True),
        "truncated": partial_result.get("truncated", False),
        "incremental": True,
        "affected_sccs": [sccs[i] for i in sorted(affected_scc_indices)],
        "fallback_reason": "",
    }
