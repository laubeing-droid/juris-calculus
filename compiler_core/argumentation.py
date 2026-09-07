"""v3.0 Dung AAF grounded extension — formal correctness (G9A).

Per Dung (1995):
  - Characteristic function F(S) = {a | all attackers of a are attacked by S}
  - F is monotone on the complete lattice of argument sets
  - For finite argument sets, iteration from empty set reaches the
    least fixed point (grounded extension) in at most |AR| steps
  - Grounded extension is unique

B3 fixes:
  - Iteration upper bound derived from argument count (not hardcoded 100)
  - Returns convergent/truncated status explicitly
  - Correctly handles self-attack, cycles, and arbitrary attack graphs
  - Deterministic output ordering
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Dict, List, Optional, Set, Tuple

from compiler_core.canonical_serialization import DigestV4, canonical_bytes
from compiler_core.contracts import (
    ArgumentV4,
    AttackV4,
    ContentRefV4,
    ExceptionResolutionV4,
    PermissionResolutionV4,
    PriorityEdgeV4,
)


ARGUMENT_GRAPH_KIND_V4 = "argument-graph-v4"
ARGUMENT_KIND_V4 = "argument-v4"
_ARGUMENT_LABELS_V4 = frozenset({"IN", "OUT", "UNDEC"})
_GRAPH_STATES_V4 = frozenset({"accepted", "cycle_blocked", "disputed"})


class ArgumentationV4Error(ValueError):
    """Stable fail-closed error for canonical V4 argument graphs."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _v4_fail(code: str, detail: str) -> None:
    raise ArgumentationV4Error(code, detail)


def _v4_nonempty(value: object, field_name: str) -> str:
    if type(value) is not str or not value:
        _v4_fail("ARGUMENT_GRAPH_FIELD", f"{field_name} must be a non-empty string")
    return value


def _ref_key(reference: ContentRefV4) -> tuple[str, str]:
    return reference.kind, str(reference.digest)


def _sorted_refs(references: tuple[ContentRefV4, ...]) -> tuple[ContentRefV4, ...]:
    return tuple(sorted(set(references), key=_ref_key))


def argument_ref_v4(argument: ArgumentV4) -> ContentRefV4:
    """Return the canonical content identity of an admitted V4 argument."""

    if type(argument) is not ArgumentV4:
        _v4_fail("ARGUMENT_GRAPH_TYPE", "argument must be exact ArgumentV4")
    return ContentRefV4(ARGUMENT_KIND_V4, argument.canonical_digest())


@dataclass(frozen=True, slots=True)
class PermissionRelationV4:
    """Bind a permission claim to its opposing prohibition claim."""

    permission_id: str
    permission_claim_ref: ContentRefV4
    prohibition_claim_ref: ContentRefV4 | None
    source_ref: ContentRefV4

    def __post_init__(self) -> None:
        _v4_nonempty(self.permission_id, "PermissionRelationV4.permission_id")
        if type(self.permission_claim_ref) is not ContentRefV4:
            _v4_fail("ARGUMENT_GRAPH_TYPE", "permission claim ref must be ContentRefV4")
        if (
            self.prohibition_claim_ref is not None
            and type(self.prohibition_claim_ref) is not ContentRefV4
        ):
            _v4_fail("ARGUMENT_GRAPH_TYPE", "prohibition claim ref must be ContentRefV4")
        if type(self.source_ref) is not ContentRefV4:
            _v4_fail("ARGUMENT_GRAPH_TYPE", "permission source ref must be ContentRefV4")

    def to_dict(self) -> dict[str, object]:
        return {
            "permission_id": self.permission_id,
            "permission_claim_ref": self.permission_claim_ref.to_dict(),
            "prohibition_claim_ref": (
                self.prohibition_claim_ref.to_dict()
                if self.prohibition_claim_ref is not None
                else None
            ),
            "source_ref": self.source_ref.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ArgumentLabelV4:
    argument_ref: ContentRefV4
    label: str
    witness_refs: tuple[ContentRefV4, ...]

    def __post_init__(self) -> None:
        if type(self.argument_ref) is not ContentRefV4:
            _v4_fail("ARGUMENT_GRAPH_TYPE", "label argument ref must be ContentRefV4")
        if self.label not in _ARGUMENT_LABELS_V4:
            _v4_fail("ARGUMENT_LABEL", f"unsupported label {self.label!r}")
        if (
            type(self.witness_refs) is not tuple
            or any(type(item) is not ContentRefV4 for item in self.witness_refs)
            or len(set(self.witness_refs)) != len(self.witness_refs)
        ):
            _v4_fail("ARGUMENT_WITNESS", "label witnesses must be unique ContentRefV4 values")
        object.__setattr__(self, "witness_refs", _sorted_refs(self.witness_refs))

    def to_dict(self) -> dict[str, object]:
        return {
            "argument_ref": self.argument_ref.to_dict(),
            "label": self.label,
            "witness_refs": [item.to_dict() for item in self.witness_refs],
        }


@dataclass(frozen=True, slots=True)
class ClaimProjectionV4:
    claim_ref: ContentRefV4
    argument_refs: tuple[ContentRefV4, ...]

    def __post_init__(self) -> None:
        if type(self.claim_ref) is not ContentRefV4:
            _v4_fail("ARGUMENT_GRAPH_TYPE", "claim projection key must be ContentRefV4")
        if (
            type(self.argument_refs) is not tuple
            or not self.argument_refs
            or any(type(item) is not ContentRefV4 for item in self.argument_refs)
            or len(set(self.argument_refs)) != len(self.argument_refs)
        ):
            _v4_fail(
                "ARGUMENT_WITNESS",
                "claim projection must preserve one or more unique argument witnesses",
            )
        object.__setattr__(self, "argument_refs", _sorted_refs(self.argument_refs))

    def to_dict(self) -> dict[str, object]:
        return {
            "claim_ref": self.claim_ref.to_dict(),
            "argument_refs": [item.to_dict() for item in self.argument_refs],
        }


@dataclass(frozen=True, slots=True)
class ArgumentGraphV4:
    """Canonical typed graph; an included priority edge is already applicable."""

    arguments: tuple[ArgumentV4, ...]
    attacks: tuple[AttackV4, ...] = ()
    priority_edges: tuple[PriorityEdgeV4, ...] = ()
    permission_relations: tuple[PermissionRelationV4, ...] = ()

    def __post_init__(self) -> None:
        typed_groups = (
            ("arguments", self.arguments, ArgumentV4),
            ("attacks", self.attacks, AttackV4),
            ("priority_edges", self.priority_edges, PriorityEdgeV4),
            ("permission_relations", self.permission_relations, PermissionRelationV4),
        )
        for name, values, expected_type in typed_groups:
            if type(values) is not tuple or any(type(item) is not expected_type for item in values):
                _v4_fail(
                    "ARGUMENT_GRAPH_TYPE",
                    f"ArgumentGraphV4.{name} must contain exact {expected_type.__name__} values",
                )
        if not self.arguments:
            _v4_fail("ARGUMENT_GRAPH_EMPTY", "an argument graph requires at least one argument")

        id_groups = (
            ("argument", [item.argument_id for item in self.arguments]),
            ("attack", [item.attack_id for item in self.attacks]),
            ("priority", [item.edge_id for item in self.priority_edges]),
            ("permission", [item.permission_id for item in self.permission_relations]),
        )
        for name, identities in id_groups:
            if any(type(item) is not str or not item for item in identities):
                _v4_fail("ARGUMENT_GRAPH_FIELD", f"{name} identities must be non-empty")
            if len(identities) != len(set(identities)):
                _v4_fail("ARGUMENT_GRAPH_DUPLICATE", f"duplicate {name} identity")

        ordered_arguments = tuple(sorted(self.arguments, key=lambda item: item.argument_id))
        ordered_attacks = tuple(sorted(self.attacks, key=lambda item: item.attack_id))
        ordered_priorities = tuple(sorted(self.priority_edges, key=lambda item: item.edge_id))
        ordered_permissions = tuple(
            sorted(self.permission_relations, key=lambda item: item.permission_id)
        )
        object.__setattr__(self, "arguments", ordered_arguments)
        object.__setattr__(self, "attacks", ordered_attacks)
        object.__setattr__(self, "priority_edges", ordered_priorities)
        object.__setattr__(self, "permission_relations", ordered_permissions)

        known = {argument_ref_v4(item) for item in ordered_arguments}
        known_claims = {item.claim_ref for item in ordered_arguments}
        if len(known) != len(ordered_arguments):
            _v4_fail("ARGUMENT_GRAPH_DUPLICATE", "duplicate canonical argument identity")
        for attack in ordered_attacks:
            if attack.attacker_ref not in known or attack.target_ref not in known:
                _v4_fail("ARGUMENT_GRAPH_ENDPOINT", f"unknown endpoint in {attack.attack_id}")
        for edge in ordered_priorities:
            if edge.preferred_ref not in known or edge.defeated_ref not in known:
                _v4_fail("ARGUMENT_GRAPH_ENDPOINT", f"unknown endpoint in {edge.edge_id}")
        for relation in ordered_permissions:
            if relation.permission_claim_ref not in known_claims or (
                relation.prohibition_claim_ref is not None
                and relation.prohibition_claim_ref not in known_claims
            ):
                _v4_fail(
                    "ARGUMENT_GRAPH_ENDPOINT",
                    f"unknown endpoint in {relation.permission_id}",
                )

    def canonical_payload(self) -> dict[str, object]:
        return {
            "schema_version": "jc/argument-graph-v4/1.0",
            "arguments": [item.to_dict() for item in self.arguments],
            "attacks": [item.to_dict() for item in self.attacks],
            "priority_edges": [item.to_dict() for item in self.priority_edges],
            "permission_relations": [item.to_dict() for item in self.permission_relations],
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.canonical_payload())

    def canonical_digest(self) -> DigestV4:
        return DigestV4.from_bytes(self.canonical_bytes())

    def content_ref(self) -> ContentRefV4:
        return ContentRefV4(ARGUMENT_GRAPH_KIND_V4, self.canonical_digest())


@dataclass(frozen=True, slots=True)
class ArgumentationEvaluationV4:
    graph_ref: ContentRefV4
    labels: tuple[ArgumentLabelV4, ...]
    effective_attacks: tuple[AttackV4, ...]
    permission_resolutions: tuple[PermissionResolutionV4, ...]
    exception_resolutions: tuple[ExceptionResolutionV4, ...]
    claim_projection: tuple[ClaimProjectionV4, ...]
    priority_cycles: tuple[tuple[ContentRefV4, ...], ...]
    state: str

    def __post_init__(self) -> None:
        if type(self.graph_ref) is not ContentRefV4:
            _v4_fail("ARGUMENT_GRAPH_TYPE", "evaluation graph ref must be ContentRefV4")
        typed_groups = (
            (self.labels, ArgumentLabelV4),
            (self.effective_attacks, AttackV4),
            (self.permission_resolutions, PermissionResolutionV4),
            (self.exception_resolutions, ExceptionResolutionV4),
            (self.claim_projection, ClaimProjectionV4),
        )
        for values, expected_type in typed_groups:
            if type(values) is not tuple or any(type(item) is not expected_type for item in values):
                _v4_fail("ARGUMENT_GRAPH_TYPE", f"evaluation requires {expected_type.__name__}")
        if self.state not in _GRAPH_STATES_V4:
            _v4_fail("ARGUMENT_GRAPH_STATE", f"unsupported graph state {self.state!r}")
        if type(self.priority_cycles) is not tuple or any(
            type(cycle) is not tuple
            or not cycle
            or any(type(item) is not ContentRefV4 for item in cycle)
            for cycle in self.priority_cycles
        ):
            _v4_fail("ARGUMENT_PRIORITY_CYCLE", "priority cycles must contain argument refs")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "jc/argumentation-evaluation-v4/1.0",
            "graph_ref": self.graph_ref.to_dict(),
            "labels": [item.to_dict() for item in self.labels],
            "effective_attacks": [item.to_dict() for item in self.effective_attacks],
            "permission_resolutions": [item.to_dict() for item in self.permission_resolutions],
            "exception_resolutions": [item.to_dict() for item in self.exception_resolutions],
            "claim_projection": [item.to_dict() for item in self.claim_projection],
            "priority_cycles": [
                [reference.to_dict() for reference in cycle]
                for cycle in self.priority_cycles
            ],
            "state": self.state,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

    def canonical_digest(self) -> DigestV4:
        return DigestV4.from_bytes(self.canonical_bytes())


def _effective_attacks_v4(graph: ArgumentGraphV4) -> tuple[AttackV4, ...]:
    attacks = list(graph.attacks)
    attacks.extend(
        AttackV4(
            attack_id=f"priority::{edge.edge_id}",
            attacker_ref=edge.preferred_ref,
            target_ref=edge.defeated_ref,
            attack_type="priority_defeat",
            target_aspect="claim",
        )
        for edge in graph.priority_edges
    )
    identities = [item.attack_id for item in attacks]
    if len(identities) != len(set(identities)):
        _v4_fail("ARGUMENT_GRAPH_DUPLICATE", "explicit and derived attack identities collide")
    return tuple(sorted(attacks, key=lambda item: item.attack_id))


def _priority_cycles_v4(
    graph: ArgumentGraphV4,
    argument_by_ref: dict[ContentRefV4, ArgumentV4],
) -> tuple[tuple[ContentRefV4, ...], ...]:
    claims = [{"id": item.argument_id} for item in graph.arguments]
    id_by_ref = {reference: argument.argument_id for reference, argument in argument_by_ref.items()}
    ref_by_id = {value: key for key, value in id_by_ref.items()}
    edges = [
        (id_by_ref[item.preferred_ref], id_by_ref[item.defeated_ref])
        for item in graph.priority_edges
    ]
    cycles = find_cycles(claims, edges)
    return tuple(
        sorted(
            (tuple(sorted((ref_by_id[item] for item in cycle), key=_ref_key)) for cycle in cycles),
            key=lambda cycle: tuple(_ref_key(item) for item in cycle),
        )
    )


def evaluate_argument_graph(graph: ArgumentGraphV4) -> ArgumentationEvaluationV4:
    """Evaluate one canonical V4 graph with the repository's sole grounded oracle."""

    if type(graph) is not ArgumentGraphV4:
        _v4_fail("ARGUMENT_GRAPH_TYPE", "evaluate_argument_graph requires ArgumentGraphV4")
    argument_by_ref = {argument_ref_v4(item): item for item in graph.arguments}
    ref_by_id = {item.argument_id: reference for reference, item in argument_by_ref.items()}
    id_by_ref = {reference: item.argument_id for reference, item in argument_by_ref.items()}
    effective_attacks = _effective_attacks_v4(graph)
    attack_pairs = [
        (id_by_ref[item.attacker_ref], id_by_ref[item.target_ref])
        for item in effective_attacks
    ]
    result = grounded_extension(
        [{"id": item.argument_id} for item in graph.arguments],
        attack_pairs,
    )
    if not result["convergent"] or result["truncated"]:
        _v4_fail("ARGUMENT_GROUNDED_TRUNCATED", "grounded evaluation did not converge")

    accepted = set(result["accepted"])
    rejected = set(result["rejected"])
    undecided = set(result["undecided"])
    label_by_id = {
        **{item: "IN" for item in accepted},
        **{item: "OUT" for item in rejected},
        **{item: "UNDEC" for item in undecided},
    }
    reasons = label_reasons(
        [{"id": item.argument_id} for item in graph.arguments],
        attack_pairs,
        result,
    )

    labels: list[ArgumentLabelV4] = []
    for argument in graph.arguments:
        label = label_by_id[argument.argument_id]
        witnesses = reasons[argument.argument_id]["witnesses"]
        labels.append(
            ArgumentLabelV4(
                argument_ref=ref_by_id[argument.argument_id],
                label=label,
                witness_refs=tuple(ref_by_id[item] for item in witnesses),
            )
        )
    label_by_ref = {item.argument_ref: item.label for item in labels}
    arguments_by_claim: dict[ContentRefV4, list[tuple[ContentRefV4, ArgumentV4]]] = {}
    for reference, argument in argument_by_ref.items():
        arguments_by_claim.setdefault(argument.claim_ref, []).append((reference, argument))

    permission_resolutions: list[PermissionResolutionV4] = []
    for relation in graph.permission_relations:
        permission_arguments = arguments_by_claim[relation.permission_claim_ref]
        prohibition_arguments = (
            arguments_by_claim[relation.prohibition_claim_ref]
            if relation.prohibition_claim_ref is not None
            else []
        )
        permission_labels = {label_by_ref[reference] for reference, _ in permission_arguments}
        prohibition_labels = {label_by_ref[reference] for reference, _ in prohibition_arguments}
        if "UNDEC" in permission_labels | prohibition_labels:
            status = "disputed"
        elif "IN" in permission_labels and "IN" not in prohibition_labels:
            status = "holds"
        elif "IN" not in permission_labels and "IN" in prohibition_labels:
            status = "does_not_hold"
        else:
            status = "disputed"
        witnesses = [
            relation.source_ref,
            *(reference for reference, _ in permission_arguments),
            *(reference for reference, _ in prohibition_arguments),
        ]
        permission_resolutions.append(
            PermissionResolutionV4(
                permission_id=relation.permission_id,
                claim_ref=relation.permission_claim_ref,
                prohibition_ref=relation.prohibition_claim_ref,
                status=status,
                witness_refs=_sorted_refs(tuple(witnesses)),
            )
        )

    exception_resolutions: list[ExceptionResolutionV4] = []
    for attack in effective_attacks:
        if attack.attack_type != "exception":
            continue
        attacker_label = label_by_ref[attack.attacker_ref]
        target_label = label_by_ref[attack.target_ref]
        if attacker_label == "IN" and target_label == "OUT":
            status = "applied"
        elif attacker_label == "OUT" and target_label == "IN":
            status = "defeated"
        else:
            status = "disputed"
        exception_resolutions.append(
            ExceptionResolutionV4(
                exception_id=attack.attack_id,
                claim_ref=argument_by_ref[attack.target_ref].claim_ref,
                target_ref=attack.target_ref,
                target_aspect=attack.target_aspect,
                status=status,
                witness_refs=_sorted_refs((attack.attacker_ref, attack.target_ref)),
            )
        )

    projection: dict[ContentRefV4, list[ContentRefV4]] = {}
    for argument in graph.arguments:
        reference = ref_by_id[argument.argument_id]
        projection.setdefault(argument.claim_ref, []).append(reference)
    claim_projection = tuple(
        ClaimProjectionV4(claim_ref, tuple(argument_refs))
        for claim_ref, argument_refs in sorted(projection.items(), key=lambda item: _ref_key(item[0]))
    )

    priority_cycles = _priority_cycles_v4(graph, argument_by_ref)
    if priority_cycles:
        state = "cycle_blocked"
    elif any(item.status == "disputed" for item in permission_resolutions):
        state = "disputed"
    elif undecided:
        state = "disputed"
    else:
        state = "accepted"
    return ArgumentationEvaluationV4(
        graph_ref=graph.content_ref(),
        labels=tuple(labels),
        effective_attacks=effective_attacks,
        permission_resolutions=tuple(permission_resolutions),
        exception_resolutions=tuple(exception_resolutions),
        claim_projection=claim_projection,
        priority_cycles=priority_cycles,
        state=state,
    )


def grounded_extension(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    max_iter: Optional[int] = None,
) -> dict[str, Any]:
    """Compute the grounded extension of a Dung abstract argumentation framework.

    Args:
        claims: List of dicts with at least 'id' key per argument.
        attacks: List of (source_id, target_id) pairs.
        max_iter: Optional explicit bound. If None, derived from |claims|.
                  If provided and insufficient, returns TRUNCATED.

    Returns:
        dict with:
          accepted: list of IN arguments (grounded extension members)
          rejected: list of OUT arguments (attacked by accepted)
          undecided: list of UNDEC arguments (cycles and their consequences)
          iterations: number of characteristic function evaluations
          derived_bound: upper bound derived from argument count
          convergent: True if least fixed point reached within bound
          truncated: True if max_iter was insufficient to reach fixed point
    """
    cids: Set[str] = {c["id"] for c in claims}
    n = len(cids)
    derived_bound = n + 1  # at most |AR| steps to reach fixed point, +1 for convergence check  # at least 1 iteration for empty check

    if max_iter is None:
        max_iter = derived_bound
    elif max_iter < 1:
        max_iter = 1

    # Build attack relation: attackers_of[tgt] = {src | src attacks tgt}
    attackers_of: Dict[str, Set[str]] = {}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)

    # Fixed-point iteration: F(S) = {a | all attackers of a are attacked by S}
    # Start from bottom (empty set), iterate F until stable or max_iter exhausted
    accepted: Set[str] = set()
    convergent = False
    iteration = 0

    while iteration < max_iter:
        iteration += 1
        defended = set()
        for cid in cids:
            atts = attackers_of.get(cid, set())
            if not atts:
                defended.add(cid)
            else:
                all_defeated = True
                for a in atts:
                    a_atts = attackers_of.get(a, set())
                    if not (a_atts & accepted):
                        all_defeated = False
                        break
                if all_defeated:
                    defended.add(cid)

        if defended == accepted:
            convergent = True
            break

        accepted = defended

    # Grounded labelling
    # IN  = accepted (grounded extension members)
    # OUT = attacked by IN (and not IN)
    # UNDECIDED = everything else (cycles where grounded semantics gives empty)
    rejected = set()
    for cid in cids:
        if cid in accepted:
            continue
        atts = attackers_of.get(cid, set())
        if atts & accepted:
            rejected.add(cid)

    undecided = cids - accepted - rejected

    return {
        "accepted": sorted(accepted),
        "rejected": sorted(rejected),
        "undecided": sorted(undecided),
        "iterations": iteration,
        "derived_bound": derived_bound,
        "convergent": convergent,
        "truncated": not convergent and iteration >= max_iter,
    }


# ---------------------------------------------------------------------------
# B6 Engineering capabilities: cycle/SCC witness, label reasons, proof trace
# ---------------------------------------------------------------------------

def scc_decomposition(
    claims: list[dict[str, Any]], attacks: list[tuple[str, str]]
) -> list[list[str]]:
    """Decompose attack graph into strongly connected components (Kosaraju).

    Returns list of SCCs, each a list of argument IDs. Topological order
    (source SCCs first, sink SCCs last).
    """
    cids = {c["id"] for c in claims}
    adj: dict[str, list[str]] = {cid: [] for cid in cids}
    radj: dict[str, list[str]] = {cid: [] for cid in cids}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            adj[src].append(tgt)
            radj[tgt].append(src)

    visited: set[str] = set()
    order: list[str] = []

    # Iterative DFS (first pass) — avoids recursion limit for large graphs
    def dfs1(start: str) -> None:
        stack: list[tuple[str, int]] = [(start, 0)]
        visited.add(start)
        while stack:
            v, idx = stack[-1]
            neighbors = adj.get(v, [])
            if idx < len(neighbors):
                w = neighbors[idx]
                stack[-1] = (v, idx + 1)
                if w not in visited:
                    visited.add(w)
                    stack.append((w, 0))
            else:
                stack.pop()
                order.append(v)

    for v in sorted(cids):
        if v not in visited:
            dfs1(v)

    visited.clear()
    sccs: list[list[str]] = []

    # Iterative DFS (second pass) — avoids recursion limit for large graphs
    def dfs2(start: str, comp: list[str]) -> None:
        stack: list[tuple[str, int]] = [(start, 0)]
        visited.add(start)
        comp.append(start)
        while stack:
            v, idx = stack[-1]
            neighbors = radj.get(v, [])
            if idx < len(neighbors):
                w = neighbors[idx]
                stack[-1] = (v, idx + 1)
                if w not in visited:
                    visited.add(w)
                    comp.append(w)
                    stack.append((w, 0))
            else:
                stack.pop()

    for v in reversed(order):
        if v not in visited:
            comp: list[str] = []
            dfs2(v, comp)
            sccs.append(sorted(comp))

    return sccs


def find_cycles(
    claims: list[dict[str, Any]], attacks: list[tuple[str, str]]
) -> list[list[str]]:
    """Find all SCCs that contain cycles (size > 1 or self-attack).
    Returns list of cycle witness SCCs.
    """
    sccs = scc_decomposition(claims, attacks)
    attack_set = {(s, t) for s, t in attacks}

    cycles = []
    for scc in sccs:
        if len(scc) > 1:
            cycles.append(scc)
        elif len(scc) == 1:
            # Check self-attack
            v = scc[0]
            if (v, v) in attack_set:
                cycles.append(scc)
    return cycles


def label_reasons(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    result: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Generate human-readable reasons for each argument's label.

    Returns dict mapping argument ID to:
      - label: "IN" | "OUT" | "UNDEC"
      - reason: short explanation
      - witnesses: list of relevant argument IDs
      - cycle_scc: SCC ID if undecided due to cycle
    """
    accepted = set(result["accepted"])
    rejected = set(result["rejected"])
    undecided = set(result["undecided"])
    cids = {c["id"] for c in claims}

    attackers_of: dict[str, set[str]] = {}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)

    sccs = scc_decomposition(claims, attacks)
    scc_map: dict[str, int] = {}
    for i, scc in enumerate(sccs):
        for v in scc:
            scc_map[v] = i

    reasons: dict[str, dict[str, Any]] = {}

    for cid in sorted(cids):
        if cid in accepted:
            atts = attackers_of.get(cid, set())
            if not atts:
                reasons[cid] = {"label": "IN", "reason": "no attackers", "witnesses": []}
            else:
                defenders = set()
                for a in atts:
                    a_atts = attackers_of.get(a, set())
                    defenders.update(a_atts & accepted)
                reasons[cid] = {
                    "label": "IN",
                    "reason": f"all attackers defeated by accepted arguments",
                    "witnesses": sorted(defenders),
                }
        elif cid in rejected:
            atts = attackers_of.get(cid, set())
            in_attackers = atts & accepted
            reasons[cid] = {
                "label": "OUT",
                "reason": f"attacked by IN argument(s)",
                "witnesses": sorted(in_attackers),
            }
        else:  # undecided
            scc_id = scc_map.get(cid)
            scc_nodes = sccs[scc_id] if scc_id is not None else [cid]
            if len(scc_nodes) > 1 or (
                len(scc_nodes) == 1 and (scc_nodes[0], scc_nodes[0]) in {(s, t) for s, t in attacks}
            ):
                reasons[cid] = {
                    "label": "UNDEC",
                    "reason": f"part of cycle/SCC that prevents grounded resolution",
                    "witnesses": scc_nodes,
                    "cycle_scc": scc_id,
                }
            else:
                # Depends on another undecided argument
                undecided_attackers = sorted(attackers_of.get(cid, set()) & undecided)
                reasons[cid] = {
                    "label": "UNDEC",
                    "reason": "depends on undecided argument(s)",
                    "witnesses": undecided_attackers,
                }

    return reasons


def proof_trace(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a complete proof trace for the grounded extension computation.

    Returns:
      - sccs: SCC decomposition
      - cycles: cycle witnesses
      - iteration_history: per-iteration accepted/defended sets
      - labels: per-argument label with reasons
      - convergent: whether convergence was achieved
    """
    if result is None:
        result = grounded_extension(claims, attacks)

    # Replay iterations to capture history
    cids = {c["id"] for c in claims}
    attackers_of: dict[str, set[str]] = {}
    for src, tgt in attacks:
        if src in cids and tgt in cids:
            attackers_of.setdefault(tgt, set()).add(src)

    iteration_history: list[dict[str, Any]] = []
    accepted: set[str] = set()
    iteration = 0
    max_iter = result["derived_bound"]

    while iteration < max_iter:
        iteration += 1
        defended = set()
        for cid in cids:
            atts = attackers_of.get(cid, set())
            if not atts:
                defended.add(cid)
            else:
                all_defeated = True
                for a in atts:
                    a_atts = attackers_of.get(a, set())
                    if not (a_atts & accepted):
                        all_defeated = False
                        break
                if all_defeated:
                    defended.add(cid)

        iteration_history.append({
            "iteration": iteration,
            "accepted": sorted(accepted),
            "defended": sorted(defended),
        })

        if defended == accepted:
            break
        accepted = defended

    sccs = scc_decomposition(claims, attacks)
    cycles = find_cycles(claims, attacks)

    return {
        "sccs": sccs,
        "cycles": cycles,
        "iteration_history": iteration_history,
        "labels": label_reasons(claims, attacks, result),
        "convergent": result["convergent"],
        "accepted": result["accepted"],
        "rejected": result["rejected"],
        "undecided": result["undecided"],
    }


def build_attack_graph_from_evaluator(
    rules: list[dict[str, Any]],
    evaluator_result: dict[str, Any],
) -> list[tuple[str, str]]:
    """Build attack graph edges from Horn rules and evaluator output.

    For each rule with an explicit priority_over or exception relationship,
    generate an attack edge from the overriding rule's head to the
    overridden rule's head.

    This serves as the Stage 2 AAF bridge in the stratified evaluator.
    """
    labels: dict[str, str] = evaluator_result.get("labels", {})
    attacks: list[tuple[str, str]] = []
    by_id: dict[str, dict[str, Any]] = {}
    by_head_lists: dict[str, list[str]] = {}

    def value(rule_obj: Any, name: str, default: Any) -> Any:
        return rule_obj.get(name, default) if isinstance(rule_obj, dict) else getattr(rule_obj, name, default)

    def iter_refs(raw_refs: Any) -> list[Any]:
        if raw_refs is None:
            return []
        if isinstance(raw_refs, (list, tuple, set)):
            return list(raw_refs)
        return [raw_refs]

    def resolve_target(target: Any) -> str:
        key = "" if target is None else str(target)
        if not key:
            return ""
        if key in by_id:
            return str(value(by_id[key], "head_claim", value(by_id[key], "head", "")) or key)
        if key in by_head_lists and by_head_lists[key]:
            return key
        for rule in rules:
            if str(value(rule, "id", "")) == key or str(value(rule, "head", "")) == key or str(value(rule, "head_claim", "")) == key:
                return str(value(rule, "head_claim", value(rule, "head", "")))
        return key

    for rule in rules:
        rid = str(value(rule, "id", ""))
        if rid:
            by_id[rid] = rule
        rhead = str(value(rule, "head", value(rule, "head_claim", "")))
        if rhead:
            by_head_lists[rhead] = by_head_lists.get(rhead, []) + [rid or rhead]

    for rule in rules:
        source_head = str(value(rule, "head", value(rule, "head_claim", "")))
        if not source_head:
            continue

        # Priority-based and explicit attacks: source_head defeats target
        for field_name in ("attacks", "priority_over", "exception_to"):
            for raw_target in iter_refs(value(rule, field_name, ())):
                target_head = resolve_target(raw_target)
                if target_head and (target_head in labels or source_head in labels):
                    attacks.append((source_head, target_head))

        # Exception-chain attacks are represented as exception -> target
        for raw_exception in iter_refs(value(rule, "exception_chain", ())):
            exception_head = resolve_target(raw_exception)
            if exception_head and source_head:
                attacks.append((exception_head, source_head))

    # Deduplicate deterministic ordering.
    return sorted(set(attacks))


def build_attack_edges_from_rules(
    rules: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """Build attack edges from Horn rules alone (no evaluator context).

    Extracts priority and exception relationships from rules and
    returns them as attack pairs.
    """
    def value(rule: Any, name: str, default: Any) -> Any:
        """统一读取dict或LegalRule字段。"""

        return rule.get(name, default) if isinstance(rule, dict) else getattr(rule, name, default)

    def iter_refs(raw_refs: Any) -> list[Any]:
        if raw_refs is None:
            return []
        if isinstance(raw_refs, (list, tuple, set)):
            return list(raw_refs)
        return [raw_refs]

    by_id = {str(value(rule, "id", "")): rule for rule in rules if str(value(rule, "id", ""))}
    by_head = {str(value(rule, "head", value(rule, "head_claim", ""))): rule for rule in rules if str(value(rule, "head", value(rule, "head_claim", "")))}
    attacks: set[tuple[str, str]] = set()

    def resolve_target(raw_target: Any) -> str:
        target_key = str(raw_target)
        target_rule = by_id.get(target_key)
        if target_rule is not None:
            target_head = str(value(target_rule, "head_claim", value(target_rule, "head", "")))
            return target_head
        if target_key in by_head:
            return target_key
        return target_key

    for rule in rules:
        source = str(value(rule, "head", value(rule, "head_claim", "")))
        if not source:
            continue

        for field_name in ("attacks", "priority_over", "exception_to"):
            for raw_target in iter_refs(value(rule, field_name, ())):
                target_head = resolve_target(raw_target)
                if target_head:
                    attacks.add((source, target_head))

        # exception_chain denotes target exception rule defeating the current rule.
        for raw_exception in iter_refs(value(rule, "exception_chain", ())):
            exception_head = resolve_target(raw_exception)
            if exception_head:
                attacks.add((exception_head, source))

    return sorted((src, tgt) for src, tgt in attacks if src and tgt)


# ---------------------------------------------------------------------------
# V5 bounded profile semantics (ULM09/ULM10; JC-UPGRADE-20260906-01 U05).
#
# Grounded keeps the proved least-fixed-point oracle above. preferred, stable
# and complete use a bounded finite reference enumeration over the same
# resolved defeat graph. Enumeration budgets are engineering start values
# awaiting U11 benchmarks, not performance facts; exhausting a budget yields
# a sound partial result, never a claimed-complete family.
# ---------------------------------------------------------------------------

DEFAULT_ENUMERATION_ARGUMENT_LIMIT_V5 = 16
HARD_ENUMERATION_ARGUMENT_LIMIT_V5 = 20
DEFAULT_ENUMERATION_SUBSET_LIMIT_V5 = 65_536
HARD_ENUMERATION_SUBSET_LIMIT_V5 = 1_048_576


@dataclass(frozen=True, slots=True)
class AttackRecordV5:
    """One validated typed attack entering defeat resolution."""

    attack_id: str
    attacker: str
    target: str
    kind: str
    witness: str

    def __post_init__(self) -> None:
        for field_name in ("attack_id", "attacker", "target", "kind", "witness"):
            value = getattr(self, field_name)
            if type(value) is not str or not value:
                _v4_fail("DEFEAT_INPUT_FIELD", f"{field_name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class ProfileEvaluationV5:
    """Internal bounded solver result; wire form is contracts.EvalOutcomeV5."""

    profile: str
    kind: str
    extensions: tuple[frozenset[str], ...]
    open_obligations: tuple[tuple[str, str], ...]

    @property
    def claims_complete_family(self) -> bool:
        return self.kind in ("no_extension", "extensions")


def resolve_defeats_v5(
    arguments: tuple[str, ...],
    attacks: tuple[AttackRecordV5, ...],
    *,
    policy_id: str,
    policy_version: str,
    allowed_kinds: tuple[str, ...],
    request_ref: str,
    priority_edges: tuple[tuple[str, str], ...] = (),
    priority_policy_id: str | None = None,
) -> tuple[tuple[str, str], ...]:
    """Resolve typed attacks into defeat pairs under one frozen policy.

    An attack becomes a defeat only when its kind is allowed by the admitted
    policy and both endpoints are known arguments of the same request. The
    policy decision is explicit and auditable; priority or authority alone
    manufactures no defeat edge.

    Admitted priority relations participate exactly through a registered
    priority policy: under ``target-preferred-rebut/1`` an admitted rebut does
    NOT become a defeat when its target is strictly preferred over its
    attacker, while every other admitted attack still does. Priority input
    without a registered policy, or a policy that cannot explain its input
    (non-strict cycles), fails closed instead of being silently dropped.
    """

    if not allowed_kinds:
        _v4_fail("DEFEAT_POLICY_EMPTY", "allowed_kinds must not be empty")
    known = set(arguments)
    blocked: frozenset[tuple[str, str]] = frozenset()
    if priority_edges:
        blocked = _priority_blocked_pairs_v5(
            attacks, priority_edges, priority_policy_id
        )
    resolved: list[tuple[str, str]] = []
    for attack in attacks:
        if attack.kind not in allowed_kinds:
            continue
        if attack.attacker not in known or attack.target not in known:
            _v4_fail(
                "DEFEAT_ENDPOINT_UNKNOWN",
                f"attack {attack.attack_id!r} references an unknown argument",
            )
        pair = (attack.attacker, attack.target)
        if pair in blocked:
            continue
        resolved.append(pair)
    return tuple(sorted(set(resolved)))


PRIORITY_POLICIES_V5 = MappingProxyType({
    # Registered engineering test strategy for wiring verification only: it is
    # not a claim about any jurisdiction's conflict-of-norms rules.
    "target-preferred-rebut/1": (
        "For an admitted rebut, the attack does not become a defeat when its "
        "target is strictly preferred over its attacker under the transitive "
        "closure of the admitted priority relations; every other admitted "
        "attack still becomes a defeat. The strategy never manufactures an "
        "attack or defeat edge."
    ),
})


def _strict_preference_closure_v5(
    priority_edges: tuple[tuple[str, str], ...],
) -> frozenset[tuple[str, str]]:
    """Transitive closure of the strict preference relation.

    Preference must stay a strict partial order: any non-strict cycle makes
    "strictly preferred" undecidable for every node on it, so the closure
    fails closed instead of guessing an orientation.
    """

    nodes = sorted({endpoint for pair in priority_edges for endpoint in pair})
    reach = set(priority_edges)
    for middle in nodes:
        reach |= {
            (start, end)
            for start in nodes if (start, middle) in reach
            for end in nodes if (middle, end) in reach
        }
    for node in nodes:
        if (node, node) in reach:
            _v4_fail(
                "PRIORITY_CYCLE_UNRESOLVED",
                f"priority relations form a non-strict cycle through {node!r}",
            )
    return frozenset(reach)


def _priority_blocked_pairs_v5(
    attacks: tuple[AttackRecordV5, ...],
    priority_edges: tuple[tuple[str, str], ...],
    priority_policy_id: str | None,
) -> frozenset[tuple[str, str]]:
    if priority_policy_id is None:
        _v4_fail(
            "PRIORITY_POLICY_REQUIRED",
            "admitted priority relations require a registered priority policy",
        )
    if priority_policy_id not in PRIORITY_POLICIES_V5:
        _v4_fail(
            "PRIORITY_POLICY_UNKNOWN",
            f"priority policy {priority_policy_id!r} is not registered",
        )
    closure = _strict_preference_closure_v5(priority_edges)
    return frozenset(
        (attack.attacker, attack.target)
        for attack in attacks
        if attack.kind == "rebut" and (attack.target, attack.attacker) in closure
    )


def priority_edge_decisions_v5(
    arguments: tuple[str, ...],
    attacks: tuple[AttackRecordV5, ...],
    priority_edges: tuple[tuple[str, str], ...],
    priority_policy_id: str | None,
) -> tuple[dict[str, object], ...]:
    """Per-edge audit record for how each admitted priority relation was handled.

    Every admitted edge is accounted for exactly once: which attacks it (or a
    closure it participates in) blocked, or an explicit statement that no
    admitted conflict exists for it to decide.
    """

    if not priority_edges:
        return ()
    known = set(arguments)
    closure = _strict_preference_closure_v5(priority_edges)
    decisions: list[dict[str, object]] = []
    for preferred, defeated in sorted(priority_edges):
        if preferred not in known or defeated not in known:
            _v4_fail(
                "DEFEAT_ENDPOINT_UNKNOWN",
                "priority relation references an unknown argument",
            )
        direct_blocks = sorted(
            attack.attack_id for attack in attacks
            if attack.kind == "rebut"
            and attack.target == preferred
            and attack.attacker == defeated
        )
        closure_blocks = sorted(
            attack.attack_id for attack in attacks
            if attack.kind == "rebut"
            and (attack.target, attack.attacker) in closure
            and {attack.attacker, attack.target} & {preferred, defeated}
        )
        if direct_blocks:
            disposition = "blocked_attack"
        elif closure_blocks:
            disposition = "participates_in_closure_block"
        else:
            disposition = "no_applicable_conflict"
        decisions.append({
            "preferred": preferred,
            "defeated": defeated,
            "policy": priority_policy_id,
            "disposition": disposition,
            "directly_blocked_attacks": direct_blocks,
            "closure_blocked_attacks": closure_blocks,
        })
    return tuple(decisions)


def _is_admissible(subset: frozenset[str], defeats: set[tuple[str, str]]) -> bool:
    for source, target in defeats:
        if source in subset and target in subset:
            return False
    for member in subset:
        if (member, member) in defeats:
            return False
        for attacker, target in defeats:
            if target == member and attacker not in subset:
                if not any(
                    defender in subset and defender_target == attacker
                    for defender, defender_target in defeats
                ):
                    return False
    return True


def _characteristic(
    arguments: frozenset[str], defeats: set[tuple[str, str]], subset: frozenset[str]
) -> frozenset[str]:
    """Dung's characteristic function: every attacker of the argument is attacked by S."""

    return frozenset(
        argument
        for argument in arguments
        if all(
            any((member, attacker) in defeats for member in subset)
            for attacker, target in defeats
            if target == argument
        )
    )


def _subsets(arguments: tuple[str, ...], total: int):
    for mask in range(total):
        yield frozenset(
            argument for index, argument in enumerate(arguments) if mask >> index & 1
        )


def evaluate_profile_v5(
    profile: str,
    arguments: tuple[str, ...],
    defeats: tuple[tuple[str, str], ...],
    *,
    argument_limit: int = DEFAULT_ENUMERATION_ARGUMENT_LIMIT_V5,
    subset_limit: int = DEFAULT_ENUMERATION_SUBSET_LIMIT_V5,
) -> ProfileEvaluationV5:
    """Bounded finite reference evaluation of one Dung profile.

    grounded delegates to the proved least-fixed-point oracle. preferred,
    stable and complete enumerate the bounded powerset and verify maximality
    or fixed-point membership directly. Exceeding a budget returns
    kind="incomplete" with open obligations instead of a claimed family.
    """

    if profile not in ("grounded", "preferred", "stable", "complete"):
        _v4_fail("PROFILE_UNKNOWN", f"unsupported profile {profile!r}")
    if len(arguments) > HARD_ENUMERATION_ARGUMENT_LIMIT_V5:
        return ProfileEvaluationV5(
            profile, "incomplete", (),
            (("argument_limit", "argument count exceeds the hard bound"),),
        )
    if len(arguments) > argument_limit:
        return ProfileEvaluationV5(
            profile, "incomplete", (),
            (("argument_limit", "argument count exceeds the configured bound"),),
        )
    argument_set = frozenset(arguments)
    defeat_set = set(defeats)

    if profile == "grounded":
        claims = [{"id": argument} for argument in arguments]
        labels = grounded_extension(claims, sorted(defeat_set))
        if not labels["convergent"]:
            return ProfileEvaluationV5(
                profile, "incomplete", (),
                (("grounded_truncated", "grounded iteration exceeded its bound"),),
            )
        accepted = frozenset(labels["accepted"])
        return ProfileEvaluationV5(profile, "extensions", (accepted,), ())

    total = 1 << len(arguments)
    subset_budget = min(subset_limit, HARD_ENUMERATION_SUBSET_LIMIT_V5)
    if total > subset_budget:
        return ProfileEvaluationV5(
            profile, "incomplete", (),
            (("enumeration_budget", "powerset exceeds the configured subset budget"),),
        )

    if profile == "stable":
        stable: list[frozenset[str]] = []
        for subset in _subsets(arguments, total):
            outside = argument_set - subset
            if any((source, target) in defeat_set for source in subset for target in subset):
                continue
            # ULM10DungProfiles.lean Stable: every argument OUTSIDE the set is
            # attacked BY some member INSIDE the set ((b, a) in defeats with
            # b in the subset, a outside it) — never the reverse direction.
            if all(
                any((source, member) in defeat_set for source in subset)
                for member in outside
            ):
                stable.append(subset)
        if not stable:
            return ProfileEvaluationV5(profile, "no_extension", (), ())
        return ProfileEvaluationV5(profile, "extensions", tuple(sorted(stable)), ())

    admissible_sets: list[frozenset[str]] = [
        subset for subset in _subsets(arguments, total)
        if _is_admissible(subset, defeat_set)
    ]
    if not admissible_sets:
        return ProfileEvaluationV5(profile, "no_extension", (), ())
    if profile == "complete":
        complete = tuple(sorted(
            subset for subset in admissible_sets
            if _characteristic(argument_set, defeat_set, subset) == subset
        ))
        return ProfileEvaluationV5(profile, "extensions", complete, ())
    # preferred: inclusion-maximal admissible sets, maximality actually verified
    maximal = tuple(sorted(
        candidate for candidate in admissible_sets
        if not any(candidate < other for other in admissible_sets)
    ))
    return ProfileEvaluationV5(profile, "extensions", maximal, ())


def _v5_attackers_of(
    argument_set: frozenset[str], defeat_set: frozenset[tuple[str, str]]
) -> dict[str, frozenset[str]]:
    attackers: dict[str, set[str]] = {argument: set() for argument in argument_set}
    for source, target in defeat_set:
        if source in attackers and target in attackers:
            attackers[target].add(source)
    return {argument: frozenset(values) for argument, values in attackers.items()}


def _v5_conflict_free(
    subset: frozenset[str], defeat_set: frozenset[tuple[str, str]]
) -> bool:
    return not any(source in subset and target in subset for source, target in defeat_set)


def _v5_defends(
    subset: frozenset[str],
    argument: str,
    attackers_of: dict[str, frozenset[str]],
) -> bool:
    return all(
        any(defender in subset for defender in attackers_of[attacker])
        for attacker in attackers_of[argument]
    )


def _v5_admissible(
    subset: frozenset[str],
    argument_set: frozenset[str],
    defeat_set: frozenset[tuple[str, str]],
    attackers_of: dict[str, frozenset[str]],
) -> bool:
    if not subset <= argument_set or not _v5_conflict_free(subset, defeat_set):
        return False
    return all(_v5_defends(subset, member, attackers_of) for member in subset)


def _v5_characteristic(
    subset: frozenset[str],
    argument_set: frozenset[str],
    attackers_of: dict[str, frozenset[str]],
) -> frozenset[str]:
    return frozenset(
        argument
        for argument in argument_set
        if all(
            any(defender in subset for defender in attackers_of[attacker])
            for attacker in attackers_of[argument]
        )
    )


def _v5_independent_grounded(
    argument_set: frozenset[str], attackers_of: dict[str, frozenset[str]]
) -> frozenset[str] | None:
    current = frozenset()
    for _ in range(len(argument_set) + 1):
        nxt = _v5_characteristic(current, argument_set, attackers_of)
        if nxt == current:
            return current
        current = nxt
    return None


def _v5_independent_extension(
    profile: str,
    subset: frozenset[str],
    argument_set: frozenset[str],
    defeat_set: frozenset[tuple[str, str]],
    attackers_of: dict[str, frozenset[str]],
) -> bool:
    """Definition-driven membership test for one claimed extension.

    Computed from the Dung definitions through the attacker adjacency alone;
    this path shares no code with ``evaluate_profile_v5`` so a solver error
    cannot certify itself.
    """

    if not subset <= argument_set:
        return False
    if profile == "grounded":
        grounded = _v5_independent_grounded(argument_set, attackers_of)
        return grounded is not None and subset == grounded
    if not _v5_conflict_free(subset, defeat_set):
        return False
    if profile == "stable":
        outside = argument_set - subset
        return all(
            any((source, member) in defeat_set for source in subset)
            for member in outside
        )
    if not _v5_admissible(subset, argument_set, defeat_set, attackers_of):
        return False
    if profile == "complete":
        return _v5_characteristic(subset, argument_set, attackers_of) == subset
    # preferred: admissible and no admissible strict superset exists
    outside = sorted(argument_set - subset)
    for mask in range(1 << len(outside)):
        superset = frozenset(subset | {
            argument for index, argument in enumerate(outside) if mask >> index & 1
        })
        if superset != subset and _v5_admissible(
            superset, argument_set, defeat_set, attackers_of
        ):
            return False
    return True


def _v5_independent_family(
    profile: str,
    argument_set: frozenset[str],
    defeat_set: frozenset[tuple[str, str]],
    attackers_of: dict[str, frozenset[str]],
) -> frozenset[frozenset[str]]:
    if profile == "grounded":
        grounded = _v5_independent_grounded(argument_set, attackers_of)
        return frozenset({grounded}) if grounded is not None else frozenset()
    return frozenset(
        subset
        for mask in range(1 << len(argument_set))
        for subset in (
            frozenset(
                argument
                for index, argument in enumerate(sorted(argument_set))
                if mask >> index & 1
            ),
        )
        if _v5_independent_extension(
            profile,
            subset,
            argument_set,
            defeat_set,
            attackers_of,
        )
    )


def verify_profile_family_v5(
    profile: str,
    arguments: tuple[str, ...],
    defeats: tuple[tuple[str, str], ...],
    claimed_extensions: tuple[frozenset[str], ...],
    *,
    coverage: str,
) -> tuple[bool, str]:
    """Verify a claimed profile family against the definitions, not the solver.

    The reference here is a definition-driven recomputation through the
    attacker adjacency (conflict-freedom, defense, the characteristic function
    and the stable all-outside-attack condition) that never calls
    ``evaluate_profile_v5``. A wrong solver result therefore cannot pass: every
    claimed extension must be a genuine extension of the semantics, and an
    ``exact`` claim must additionally equal the independently recomputed full
    family — omissions, non-maximal preferred sets and over-budget
    fake-completeness claims are all rejected. Budget exhaustion fails closed.
    """

    if coverage not in ("exact", "discovered_only"):
        return False, "coverage_unknown"
    if profile not in ("grounded", "preferred", "stable", "complete"):
        return False, "profile_unknown"
    if len(claimed_extensions) != len(set(claimed_extensions)):
        return False, "family_mismatch"
    if any(type(subset) is not frozenset for subset in claimed_extensions):
        return False, "family_mismatch"
    if len(arguments) > HARD_ENUMERATION_ARGUMENT_LIMIT_V5:
        return False, "reference_incomplete"

    argument_set = frozenset(arguments)
    defeat_set = frozenset(defeats)
    attackers_of = _v5_attackers_of(argument_set, defeat_set)
    total = 1 << len(argument_set)
    subset_budget = min(DEFAULT_ENUMERATION_SUBSET_LIMIT_V5, HARD_ENUMERATION_SUBSET_LIMIT_V5)
    if total > subset_budget:
        # Neither membership-maximality nor family completeness is verifiable
        # within the budget; no claim about this framework is accepted.
        return False, "reference_incomplete"

    for claimed in claimed_extensions:
        if not _v5_independent_extension(
            profile, claimed, argument_set, defeat_set, attackers_of
        ):
            return False, "discovered_unsound"
    if coverage == "discovered_only":
        return True, ""

    expected = _v5_independent_family(profile, argument_set, defeat_set, attackers_of)
    if profile == "grounded" and expected == frozenset():
        return False, "reference_incomplete"
    if set(claimed_extensions) == expected:
        return True, ""
    return False, "family_mismatch"


