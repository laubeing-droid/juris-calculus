"""Independent finite mutations for W3-02 protected graph semantics."""

from __future__ import annotations

from compiler_core.argumentation import (
    ArgumentGraphV4,
    PermissionRelationV4,
    argument_ref_v4,
    evaluate_argument_graph,
)
from compiler_core.canonical_serialization import DigestV4
from compiler_core.contracts import ArgumentV4, AttackV4, ContentRefV4, PriorityEdgeV4


def _ref(kind: str, value: str) -> ContentRefV4:
    return ContentRefV4(kind, DigestV4.from_bytes(value.encode()))


def _argument(name: str, claim: str | None = None) -> ArgumentV4:
    return ArgumentV4(
        name,
        (_ref("fact", name),),
        _ref("rule", name),
        _ref("claim", claim or name),
        (_ref("derivation", name),),
    )


def _attack(name: str, source: ArgumentV4, target: ArgumentV4, kind: str = "rebut") -> AttackV4:
    return AttackV4(
        name,
        argument_ref_v4(source),
        argument_ref_v4(target),
        kind,
        "rule_applicability" if kind in {"exception", "undercut"} else "claim",
    )


def _priority(name: str, winner: ArgumentV4, loser: ArgumentV4) -> PriorityEdgeV4:
    return PriorityEdgeV4(
        name,
        argument_ref_v4(winner),
        argument_ref_v4(loser),
        _ref("verified-fact", name),
        _ref("priority-source", name),
    )


def _labels(result) -> dict[ContentRefV4, str]:
    return {item.argument_ref: item.label for item in result.labels}


def _independent_grounded(
    arguments: tuple[ArgumentV4, ...], attacks: tuple[tuple[ContentRefV4, ContentRefV4], ...]
) -> dict[ContentRefV4, str]:
    """Tiny specification-side oracle; never calls production graph evaluation."""

    refs = {argument_ref_v4(item) for item in arguments}
    attackers = {item: set() for item in refs}
    for source, target in attacks:
        attackers[target].add(source)
    accepted: set[ContentRefV4] = set()
    while True:
        defended = {
            item
            for item in refs
            if all(any((defender, attacker) in attacks for defender in accepted) for attacker in attackers[item])
        }
        if defended == accepted:
            break
        accepted = defended
    rejected = {
        target for source, target in attacks if source in accepted and target not in accepted
    }
    return {
        item: "IN" if item in accepted else "OUT" if item in rejected else "UNDEC"
        for item in refs
    }


def test_pinned_b02_winner_to_loser_priority_direction_matches_independent_oracle() -> None:
    winner, loser = _argument("winner"), _argument("loser")
    graph = ArgumentGraphV4(
        (winner, loser), priority_edges=(_priority("winner-over-loser", winner, loser),)
    )
    result = evaluate_argument_graph(graph)
    expected = _independent_grounded(
        (winner, loser), ((argument_ref_v4(winner), argument_ref_v4(loser)),)
    )

    assert _labels(result) == expected
    assert [item.attack_type for item in result.effective_attacks] == ["priority_defeat"]


def test_priority_ignored_and_reversed_mutants_are_killed() -> None:
    winner, loser = _argument("winner"), _argument("loser")
    correct = evaluate_argument_graph(
        ArgumentGraphV4(
            (winner, loser), priority_edges=(_priority("correct", winner, loser),)
        )
    )
    ignored = evaluate_argument_graph(ArgumentGraphV4((winner, loser)))
    reversed_result = evaluate_argument_graph(
        ArgumentGraphV4(
            (winner, loser), priority_edges=(_priority("reversed", loser, winner),)
        )
    )
    expected = _independent_grounded(
        (winner, loser), ((argument_ref_v4(winner), argument_ref_v4(loser)),)
    )

    assert _labels(correct) == expected
    assert len({_labels(correct)[argument_ref_v4(winner)], _labels(reversed_result)[argument_ref_v4(winner)]}) == 2
    assert correct.canonical_digest() not in {
        ignored.canonical_digest(),
        reversed_result.canonical_digest(),
    }


def test_undecided_accepted_mutant_is_killed() -> None:
    a, b = _argument("a"), _argument("b")
    result = evaluate_argument_graph(
        ArgumentGraphV4(
            (a, b), attacks=(_attack("a-b", a, b), _attack("b-a", b, a))
        )
    )
    expected = _independent_grounded(
        (a, b),
        (
            (argument_ref_v4(a), argument_ref_v4(b)),
            (argument_ref_v4(b), argument_ref_v4(a)),
        ),
    )

    assert _labels(result) == expected
    assert set(expected.values()) == {"UNDEC"}
    assert result.state == "disputed"


def test_permission_dispute_collapse_mutant_is_killed() -> None:
    permission, prohibition = _argument("permission"), _argument("prohibition")
    relation = PermissionRelationV4(
        "permission",
        permission.claim_ref,
        prohibition.claim_ref,
        _ref("permission-source", "permission"),
    )
    disputed = evaluate_argument_graph(
        ArgumentGraphV4((permission, prohibition), permission_relations=(relation,))
    )
    holds = evaluate_argument_graph(
        ArgumentGraphV4(
            (permission, prohibition),
            priority_edges=(_priority("permission-wins", permission, prohibition),),
            permission_relations=(relation,),
        )
    )

    assert disputed.permission_resolutions[0].status == "disputed"
    assert holds.permission_resolutions[0].status == "holds"
    assert disputed.state != holds.state


def test_attack_type_erasure_mutant_changes_semantic_bytes() -> None:
    source, target = _argument("source"), _argument("target")
    rebut = evaluate_argument_graph(
        ArgumentGraphV4((source, target), attacks=(_attack("typed", source, target),))
    )
    exception = evaluate_argument_graph(
        ArgumentGraphV4(
            (source, target),
            attacks=(_attack("typed", source, target, "exception"),),
        )
    )

    assert _labels(rebut) == _labels(exception)
    assert rebut.canonical_digest() != exception.canonical_digest()
    assert not rebut.exception_resolutions and exception.exception_resolutions


def test_duplicate_claim_dictionary_overwrite_mutant_is_killed() -> None:
    first, second = _argument("first", "shared"), _argument("second", "shared")
    result = evaluate_argument_graph(ArgumentGraphV4((first, second)))

    assert len(result.claim_projection) == 1
    assert len(result.claim_projection[0].argument_refs) == 2


def test_edge_order_sensitive_mutant_is_killed() -> None:
    a, b, c = _argument("a"), _argument("b"), _argument("c")
    attacks = (_attack("a-b", a, b), _attack("c-b", c, b))
    forward = evaluate_argument_graph(ArgumentGraphV4((a, b, c), attacks=attacks))
    reverse = evaluate_argument_graph(
        ArgumentGraphV4((c, b, a), attacks=tuple(reversed(attacks)))
    )

    assert forward.canonical_bytes() == reverse.canonical_bytes()


def test_priority_must_not_suppress_an_independent_reverse_attack() -> None:
    winner, loser = _argument("winner"), _argument("loser")
    result = evaluate_argument_graph(
        ArgumentGraphV4(
            (winner, loser),
            attacks=(_attack("loser-rebuts", loser, winner),),
            priority_edges=(_priority("winner-over-loser", winner, loser),),
        )
    )

    assert set(_labels(result).values()) == {"UNDEC"}
