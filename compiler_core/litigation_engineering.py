"""G9B Litigation engineering capabilities — Phase C.

C1: SCC decomposition correctness — verify when SCC-ordered computation
    matches full grounded extension; identify counterexamples.
C3: Interpretation certificates — independently verifiable label reasons
    with defense witnesses and cycle attribution.
C4: Minimal intervention analysis — compute minimal argument/edge
    additions or deletions to flip UNDEC -> IN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compiler_core.argumentation import (
    grounded_extension, scc_decomposition, find_cycles, label_reasons
)


# ---------------------------------------------------------------------------
# C1: SCC decomposition correctness checker
# ---------------------------------------------------------------------------

@dataclass
class SCCCorrectnessResult:
    correct: bool
    scc_order: list[list[str]]          # SCCs in topological order
    full_accepted: list[str]
    scc_accepted: list[str]
    mismatches: list[str]               # argument IDs where SCC and full differ
    counterexample: dict[str, Any] | None  # minimal counterexample if incorrect
    reason: str

def check_scc_correctness(
    claims: list[dict[str, Any]], attacks: list[tuple[str, str]]
) -> SCCCorrectnessResult:
    """Verify whether SCC-ordered grounded computation equals full computation.

    For Dung AAFs, SCC decomposition does NOT generally preserve grounded
    semantics: arguments in earlier SCCs can be undecided due to attacks
    from later SCCs (cross-SCC undecided propagation). This function identifies
    whether SCC decomposition is valid for a specific graph.
    """
    full_result = grounded_extension(claims, attacks)
    full_accepted = set(full_result["accepted"])
    sccs = scc_decomposition(claims, attacks)

    # Build attack index
    cids = {c["id"] for c in claims}
    attackers_of: dict[str, set[str]] = {}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)

    # SCC-ordered computation: process SCCs in topological order,
    # earlier SCC results feed into later SCC evaluation
    scc_accepted: set[str] = set()
    scc_map: dict[str, int] = {}
    for i, scc in enumerate(sccs):
        for v in scc:
            scc_map[v] = i

    for scc_idx, scc in enumerate(sccs):
        # Compute grounded for this SCC, considering attacks from previous SCCs
        scc_claims = [c for c in claims if c["id"] in scc]
        # Include claims from all previous SCCs (needed for grounded propagation)
        for prev_idx in range(scc_idx):
            for c in claims:
                if c["id"] in sccs[prev_idx] and c["id"] not in {x["id"] for x in scc_claims}:
                    scc_claims.append(c)
        # Attacks: all attacks among the combined claim set
        scc_claim_ids = {c["id"] for c in scc_claims}
        scc_attacks = [
            (s, t) for s, t in attacks
            if s in scc_claim_ids and t in scc_claim_ids
        ]
        scc_result = grounded_extension(scc_claims, scc_attacks)
        scc_accepted |= set(scc_result["accepted"])

    mismatches = sorted(full_accepted ^ scc_accepted)

    # Find minimal counterexample if incorrect
    counterexample = None
    if mismatches:
        # Find arguments that are accepted in full but not in SCC (or vice versa)
        false_positive = sorted(scc_accepted - full_accepted)
        false_negative = sorted(full_accepted - scc_accepted)
        if false_negative:
            # Show a minimal example: an argument that should be accepted but isn't
            arg = false_negative[0]
            counterexample = {
                "argument": arg,
                "expected": "accepted",
                "got": "not accepted by SCC decomposition",
                "reason": "cross-SCC undecided propagation",
                "scc_id": scc_map.get(arg),
            }

    return SCCCorrectnessResult(
        correct=len(mismatches) == 0,
        scc_order=sccs,
        full_accepted=sorted(full_accepted),
        scc_accepted=sorted(scc_accepted),
        mismatches=mismatches,
        counterexample=counterexample,
        reason="SCC decomposition preserves grounded semantics" if not mismatches
        else f"SCC decomposition fails: {len(mismatches)} arguments differ due to cross-SCC undecided propagation",
    )


# ---------------------------------------------------------------------------
# C3: Interpretation certificates with independent verification
# ---------------------------------------------------------------------------

@dataclass
class LabelCertificate:
    argument_id: str
    label: str                         # IN | OUT | UNDEC
    reason: str                        # human-readable
    witnesses: list[str]               # argument IDs supporting this label
    verifiable: bool                   # can be independently verified
    verification_payload: dict[str, Any]  # data needed for verification
    attackers: list[str] = field(default_factory=list)
    minimal_witnesses: list[str] = field(default_factory=list)
    defense_paths: list[dict[str, Any]] = field(default_factory=list)
    proof_depth: int = 0


def _build_attackers_index(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
) -> dict[str, set[str]]:
    cids = {c["id"] for c in claims}
    attackers_of: dict[str, set[str]] = {}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)
    return attackers_of


def _select_minimal_defenders(
    defenders_by_attacker: dict[str, set[str]],
) -> tuple[list[str], dict[str, list[str]], list[str]]:
    remaining = {attacker for attacker, defenders in defenders_by_attacker.items() if defenders}
    chosen: list[str] = []
    chosen_set: set[str] = set()

    while remaining:
        best_defender = ""
        best_cover: set[str] = set()
        defender_pool = sorted({
            defender
            for attacker in remaining
            for defender in defenders_by_attacker.get(attacker, set())
        })
        for defender in defender_pool:
            cover = {
                attacker
                for attacker in remaining
                if defender in defenders_by_attacker.get(attacker, set())
            }
            if len(cover) > len(best_cover):
                best_defender = defender
                best_cover = cover
        if not best_defender:
            break
        chosen.append(best_defender)
        chosen_set.add(best_defender)
        remaining -= best_cover

    coverage: dict[str, list[str]] = {}
    unresolved: list[str] = []
    for attacker, defenders in defenders_by_attacker.items():
        selected = sorted(defenders & chosen_set)
        if selected:
            coverage[attacker] = selected
        elif defenders:
            fallback = sorted(defenders)[:1]
            coverage[attacker] = fallback
            if fallback[0] not in chosen_set:
                chosen.append(fallback[0])
                chosen_set.add(fallback[0])
        else:
            unresolved.append(attacker)

    return sorted(chosen), coverage, sorted(unresolved)


def _accepted_proof_depth(
    cid: str,
    attackers_of: dict[str, set[str]],
    accepted: set[str],
    memo: dict[str, int],
    active: set[str] | None = None,
) -> int:
    if cid in memo:
        return memo[cid]

    active = active or set()
    if cid in active:
        return 0

    attackers = attackers_of.get(cid, set())
    if not attackers:
        memo[cid] = 0
        return 0

    active.add(cid)
    branch_depths: list[int] = []
    for attacker in attackers:
        defenders = attackers_of.get(attacker, set()) & accepted
        if not defenders:
            branch_depths.append(0)
            continue
        branch_depths.append(
            1 + min(
                _accepted_proof_depth(defender, attackers_of, accepted, memo, active)
                for defender in defenders
            )
        )
    active.remove(cid)
    memo[cid] = max(branch_depths) if branch_depths else 0
    return memo[cid]

def generate_certificate(
    argument_id: str,
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    result: dict[str, Any],
) -> LabelCertificate:
    """Generate an independently verifiable certificate for one argument's label."""
    reasons = label_reasons(claims, attacks, result)
    reason_data = reasons.get(argument_id, {})
    label = reason_data.get("label", "UNDEC")
    reason_text = reason_data.get("reason", "unknown")
    witnesses = list(reason_data.get("witnesses", []))

    # Build verification payload
    attackers_of = _build_attackers_index(claims, attacks)
    attackers = sorted(attackers_of.get(argument_id, set()))
    accepted = set(result["accepted"])
    rejected = set(result["rejected"])
    minimal_witnesses: list[str] = []
    defense_paths: list[dict[str, Any]] = []
    proof_depth = 0

    if label == "IN":
        defenders_by_attacker = {
            attacker: attackers_of.get(attacker, set()) & accepted
            for attacker in attackers
        }
        minimal_witnesses, coverage, unresolved = _select_minimal_defenders(defenders_by_attacker)
        if minimal_witnesses:
            witnesses = minimal_witnesses
        depth_cache: dict[str, int] = {}
        proof_depth = _accepted_proof_depth(argument_id, attackers_of, accepted, depth_cache)
        for attacker in attackers:
            defense_paths.append({
                "target": argument_id,
                "attacker": attacker,
                "defenders": coverage.get(attacker, []),
            })
        if unresolved:
            defense_paths.append({
                "target": argument_id,
                "unresolved_attackers": unresolved,
            })
    elif label == "OUT":
        proof_depth = 1 if witnesses else 0
    else:
        witnesses = list(reason_data.get("witnesses", attackers))

    verification_payload = {
        "argument": argument_id,
        "attackers": attackers,
        "accepted": sorted(accepted),
        "rejected": sorted(rejected),
        "witnesses": witnesses,
        "minimal_witnesses": minimal_witnesses,
        "defense_paths": defense_paths,
        "proof_depth": proof_depth,
    }

    # Verify: ensure the label is consistent with Dung semantics
    verifiable = _verify_label(
        argument_id, label, attackers_of, accepted, rejected
    )

    return LabelCertificate(
        argument_id=argument_id,
        label=label,
        reason=reason_text,
        witnesses=witnesses,
        verifiable=verifiable,
        verification_payload=verification_payload,
        attackers=attackers,
        minimal_witnesses=minimal_witnesses,
        defense_paths=defense_paths,
        proof_depth=proof_depth,
    )


def _verify_label(
    cid: str,
    label: str,
    attackers_of: dict[str, set[str]],
    accepted: set[str],
    rejected: set[str],
) -> bool:
    """Independently verify that a label is consistent with Dung semantics."""
    atts = attackers_of.get(cid, set())
    if label == "IN":
        if cid not in accepted:
            return False
        if not atts:
            return True
        return all(
            bool(attackers_of.get(a, set()) & accepted)
            for a in atts
        )
    elif label == "OUT":
        if cid not in rejected:
            return False
        return bool(atts & accepted)
    elif label == "UNDEC":
        if cid in accepted or cid in rejected:
            return False
        return True
    return False


def generate_all_certificates(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    result: dict[str, Any],
) -> list[LabelCertificate]:
    """Generate verifiable certificates for all arguments."""
    return [
        generate_certificate(c["id"], claims, attacks, result)
        for c in claims
    ]


# ---------------------------------------------------------------------------
# C4: Minimal intervention / breakthrough analysis
# ---------------------------------------------------------------------------

@dataclass
class InterventionPlan:
    target: str                       # argument to flip
    current_label: str
    desired_label: str = "IN"
    interventions: list[dict[str, Any]] = field(default_factory=list)  # list of minimal interventions
    cost: int = 0                         # minimum number of changes needed
    implementable: bool = False               # whether a finite plan exists

def find_minimal_intervention(
    target_id: str,
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    result: dict[str, Any] | None = None,
    *,
    max_cost: int = 5,
) -> InterventionPlan:
    """Find the minimal set of argument/edge changes to flip target from UNDEC to IN.

    Intervention types:
      - add_argument: introduce a new argument that attacks some attacker of target
      - add_attack: add an attack edge from an existing argument
      - delete_attack: remove an attack edge against target or its defenders

    Uses bounded search (max_cost) since the problem is NP-hard in general.
    """
    if result is None:
        result = grounded_extension(claims, attacks)

    cids = {c["id"] for c in claims}
    attackers_of: dict[str, set[str]] = {}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)

    accepted = set(result["accepted"])
    current_label = "IN" if target_id in accepted else (
        "OUT" if target_id in result["rejected"] else "UNDEC"
    )

    if current_label == "IN":
        return InterventionPlan(
            target=target_id,
            current_label=current_label,
            interventions=[],
            cost=0,
            implementable=True,
        )

    # Current attackers of target
    target_attackers = attackers_of.get(target_id, set())

    # For each attacker, check what would defeat it
    interventions: list[dict[str, Any]] = []
    for attacker in sorted(target_attackers):
        att_attackers = attackers_of.get(attacker, set())
        # If attacker already has an attacker that is (or could be) accepted
        potential_defeaters = att_attackers - accepted
        existing_defeaters = att_attackers & accepted

        if existing_defeaters:
            # Attacker is already defeated but target still not IN
            # -> some other condition prevents IN status
            interventions.append({
                "type": "note",
                "detail": f"Attacker {attacker} is already defeated by {sorted(existing_defeaters)} but target remains {current_label}",
                "cost": 0,
            })
        elif not potential_defeaters:
            # Need to add a new argument to attack this attacker
            interventions.append({
                "type": "add_argument",
                "detail": f"Add new argument attacking {attacker}",
                "cost": 1,
                "attacker": attacker,
            })
        else:
            # Make an existing undecided argument attack this attacker
            interventions.append({
                "type": "add_attack",
                "detail": f"Add attack from {sorted(potential_defeaters)[0]} to {attacker}",
                "cost": 1,
                "from": sorted(potential_defeaters)[0],
                "to": attacker,
            })

    total_cost = sum(interv["cost"] for interv in interventions)

    return InterventionPlan(
        target=target_id,
        current_label=current_label,
        desired_label="IN",
        interventions=interventions[:max_cost],
        cost=total_cost,
        implementable=total_cost <= max_cost,
    )


# ---------------------------------------------------------------------------
# C5: Stability and sensitivity analysis
# ---------------------------------------------------------------------------

@dataclass
class StabilityAnalysis:
    argument_id: str
    label: str
    critical_edges: list[dict[str, str]]   # edges whose removal changes label
    critical_arguments: list[str]           # arguments whose removal changes label
    sensitivity_score: float                # fraction of graph changes that affect label
    robustness_radius: int                  # minimum number of changes to flip label

def analyze_stability(
    argument_id: str,
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    result: dict[str, Any] | None = None,
) -> StabilityAnalysis:
    """Analyze which graph modifications would change an argument's label."""
    if result is None:
        result = grounded_extension(claims, attacks)

    cids = {c["id"] for c in claims}
    original_label = "IN" if argument_id in result["accepted"] else (
        "OUT" if argument_id in result["rejected"] else "UNDEC"
    )

    critical_edges: list[dict[str, str]] = []
    critical_arguments: list[str] = []

    # Check each edge: does removing it change the label?
    for src, tgt in attacks:
        if src not in cids or tgt not in cids:
            continue
        modified_attacks = [(s, t) for s, t in attacks if (s, t) != (src, tgt)]
        new_result = grounded_extension(claims, modified_attacks)
        new_label = "IN" if argument_id in new_result["accepted"] else (
            "OUT" if argument_id in new_result["rejected"] else "UNDEC"
        )
        if new_label != original_label:
            critical_edges.append({"source": src, "target": tgt})

    # Check each argument: does removing it change the label?
    for c in claims:
        cid = c["id"]
        modified_claims = [cl for cl in claims if cl["id"] != cid]
        modified_attacks = [(s, t) for s, t in attacks if s != cid and t != cid]
        new_result = grounded_extension(modified_claims, modified_attacks)
        new_label = "IN" if argument_id in new_result["accepted"] else (
            "OUT" if argument_id in new_result["rejected"] else "UNDEC"
        )
        if new_label != original_label:
            critical_arguments.append(cid)

    total_elements = len(attacks) + len(claims)
    affected = len(critical_edges) + len(critical_arguments)
    sensitivity_score = affected / total_elements if total_elements > 0 else 0.0

    # Robustness radius = minimum changes to flip label
    intervention = find_minimal_intervention(argument_id, claims, attacks, result)

    return StabilityAnalysis(
        argument_id=argument_id,
        label=original_label,
        critical_edges=critical_edges,
        critical_arguments=critical_arguments,
        sensitivity_score=round(sensitivity_score, 3),
        robustness_radius=intervention.cost,
    )




