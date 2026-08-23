"""Executable W3-02 contract for canonical V4 argumentation."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler_core.argumentation import (
    ArgumentGraphV4,
    ArgumentationV4Error,
    PermissionRelationV4,
    argument_ref_v4,
    evaluate_argument_graph,
)
from compiler_core.canonical_serialization import DigestV4
from compiler_core.contracts import ArgumentV4, AttackV4, ContentRefV4, PriorityEdgeV4


ROOT = Path(__file__).resolve().parents[2]


def _ref(kind: str, value: str) -> ContentRefV4:
    return ContentRefV4(kind, DigestV4.from_bytes(value.encode("utf-8")))


def _argument(argument_id: str, claim: str | None = None) -> ArgumentV4:
    claim_id = claim or argument_id
    return ArgumentV4(
        argument_id=argument_id,
        premise_refs=(_ref("fact", f"fact::{argument_id}"),),
        rule_ref=_ref("rule-v4", f"rule::{argument_id}"),
        claim_ref=_ref("claim-v4", claim_id),
        derivation_refs=(_ref("derivation", f"derivation::{argument_id}"),),
    )


def _attack(
    attack_id: str,
    attacker: ArgumentV4,
    target: ArgumentV4,
    *,
    attack_type: str = "rebut",
    target_aspect: str = "claim",
) -> AttackV4:
    return AttackV4(
        attack_id=attack_id,
        attacker_ref=argument_ref_v4(attacker),
        target_ref=argument_ref_v4(target),
        attack_type=attack_type,
        target_aspect=target_aspect,
    )


def _priority(edge_id: str, preferred: ArgumentV4, defeated: ArgumentV4) -> PriorityEdgeV4:
    return PriorityEdgeV4(
        edge_id=edge_id,
        preferred_ref=argument_ref_v4(preferred),
        defeated_ref=argument_ref_v4(defeated),
        condition_ref=_ref("verified-fact", f"condition::{edge_id}"),
        source_ref=_ref("priority-source", f"source::{edge_id}"),
    )


def _permission(permission: ArgumentV4, prohibition: ArgumentV4) -> PermissionRelationV4:
    return PermissionRelationV4(
        permission_id="permission::use",
        permission_claim_ref=permission.claim_ref,
        prohibition_claim_ref=prohibition.claim_ref,
        source_ref=_ref("permission-source", "permission::use"),
    )


def _labels(result) -> dict[str, str]:
    return {item.argument_ref.digest: item.label for item in result.labels}


def _label(result, argument: ArgumentV4) -> str:
    return _labels(result)[argument_ref_v4(argument).digest]


def test_priority_permission_attack_mutations_change_result() -> None:
    """Required P1-06 selector: every protected relation is executable."""

    permission = _argument("permission")
    prohibition = _argument("prohibition")
    relation = _permission(permission, prohibition)

    unresolved = evaluate_argument_graph(
        ArgumentGraphV4((permission, prohibition), permission_relations=(relation,))
    )
    preferred = evaluate_argument_graph(
        ArgumentGraphV4(
            (permission, prohibition),
            priority_edges=(_priority("permission-wins", permission, prohibition),),
            permission_relations=(relation,),
        )
    )
    reversed_priority = evaluate_argument_graph(
        ArgumentGraphV4(
            (permission, prohibition),
            priority_edges=(_priority("prohibition-wins", prohibition, permission),),
            permission_relations=(relation,),
        )
    )
    attacked = evaluate_argument_graph(
        ArgumentGraphV4(
            (permission, prohibition),
            attacks=(_attack("prohibition-rebut", prohibition, permission),),
            permission_relations=(relation,),
        )
    )
    relation_removed = evaluate_argument_graph(ArgumentGraphV4((permission, prohibition)))

    assert unresolved.permission_resolutions[0].status == "disputed"
    assert preferred.permission_resolutions[0].status == "holds"
    assert reversed_priority.permission_resolutions[0].status == "does_not_hold"
    assert attacked.permission_resolutions[0].status == "does_not_hold"
    assert relation_removed.permission_resolutions == ()
    assert len({
        unresolved.canonical_digest(),
        preferred.canonical_digest(),
        reversed_priority.canonical_digest(),
        attacked.canonical_digest(),
        relation_removed.canonical_digest(),
    }) == 5


@pytest.mark.parametrize(
    ("edges", "expected"),
    [
        ((), ("IN", "IN", "disputed")),
        (("permission", "prohibition"), ("IN", "OUT", "holds")),
        (("prohibition", "permission"), ("OUT", "IN", "does_not_hold")),
    ],
)
def test_permission_three_state_is_a_graph_label_observation(edges, expected) -> None:
    permission = _argument("permission")
    prohibition = _argument("prohibition")
    by_name = {"permission": permission, "prohibition": prohibition}
    priorities = (
        (_priority("priority", by_name[edges[0]], by_name[edges[1]]),)
        if edges
        else ()
    )
    result = evaluate_argument_graph(
        ArgumentGraphV4(
            (permission, prohibition),
            priority_edges=priorities,
            permission_relations=(_permission(permission, prohibition),),
        )
    )

    assert (_label(result, permission), _label(result, prohibition)) == expected[:2]
    assert result.permission_resolutions[0].status == expected[2]
    assert "decision_status" not in result.to_dict()


@pytest.mark.parametrize(
    "attacks",
    [
        (("a", "a"),),
        (("a", "b"), ("b", "a")),
        (("a", "b"), ("b", "c"), ("c", "a")),
    ],
)
def test_self_mutual_and_cycle_are_undecided_and_never_accepted(attacks) -> None:
    arguments = {name: _argument(name) for name in ("a", "b", "c")}
    used = sorted({item for edge in attacks for item in edge})
    graph = ArgumentGraphV4(
        tuple(arguments[item] for item in used),
        attacks=tuple(
            _attack(f"attack::{source}->{target}", arguments[source], arguments[target])
            for source, target in attacks
        ),
    )
    result = evaluate_argument_graph(graph)

    assert {item.label for item in result.labels} == {"UNDEC"}
    assert result.state == "disputed"


def test_priority_cycle_is_fail_closed_without_invented_tie_break() -> None:
    a, b = _argument("a"), _argument("b")
    result = evaluate_argument_graph(
        ArgumentGraphV4(
            (a, b),
            priority_edges=(
                _priority("a-over-b", a, b),
                _priority("b-over-a", b, a),
            ),
        )
    )

    assert result.state == "cycle_blocked"
    assert len(result.priority_cycles) == 1
    assert {_label(result, a), _label(result, b)} == {"UNDEC"}


@pytest.mark.parametrize(
    ("attack_type", "target_aspect"),
    [
        ("rebut", "claim"),
        ("undercut", "rule_applicability"),
        ("exception", "rule_applicability"),
    ],
)
def test_typed_attacks_preserve_type_and_execute_as_directed_defeat(
    attack_type: str, target_aspect: str,
) -> None:
    attacker, target = _argument("attacker"), _argument("target")
    result = evaluate_argument_graph(
        ArgumentGraphV4(
            (attacker, target),
            attacks=(
                _attack(
                    "typed-attack",
                    attacker,
                    target,
                    attack_type=attack_type,
                    target_aspect=target_aspect,
                ),
            ),
        )
    )

    assert (_label(result, attacker), _label(result, target)) == ("IN", "OUT")
    assert result.effective_attacks[0].attack_type == attack_type
    assert len(result.exception_resolutions) == (attack_type == "exception")


def test_priority_adds_winner_to_loser_defeat_without_suppressing_other_attacks() -> None:
    preferred, defeated = _argument("preferred"), _argument("defeated")
    one_way = evaluate_argument_graph(
        ArgumentGraphV4(
            (preferred, defeated),
            priority_edges=(_priority("preferred-over-defeated", preferred, defeated),),
        )
    )
    explicit_reverse = evaluate_argument_graph(
        ArgumentGraphV4(
            (preferred, defeated),
            attacks=(_attack("reverse", defeated, preferred),),
            priority_edges=(_priority("preferred-over-defeated", preferred, defeated),),
        )
    )

    assert (_label(one_way, preferred), _label(one_way, defeated)) == ("IN", "OUT")
    assert {_label(explicit_reverse, preferred), _label(explicit_reverse, defeated)} == {
        "UNDEC"
    }


def test_duplicate_claim_projection_preserves_every_accepted_argument_witness() -> None:
    first = _argument("first", claim="shared")
    second = _argument("second", claim="shared")
    result = evaluate_argument_graph(ArgumentGraphV4((first, second)))

    assert len(result.claim_projection) == 1
    assert set(result.claim_projection[0].argument_refs) == {
        argument_ref_v4(first),
        argument_ref_v4(second),
    }


def test_claim_projection_retains_out_and_undecided_argument_witnesses() -> None:
    accepted = _argument("accepted", claim="shared")
    rejected = _argument("rejected", claim="shared")
    undecided = _argument("undecided", claim="shared")
    result = evaluate_argument_graph(
        ArgumentGraphV4(
            (accepted, rejected, undecided),
            attacks=(
                _attack("accepted-rejects", accepted, rejected),
                _attack("self-cycle", undecided, undecided),
            ),
        )
    )

    assert set(result.claim_projection[0].argument_refs) == {
        argument_ref_v4(accepted),
        argument_ref_v4(rejected),
        argument_ref_v4(undecided),
    }
    assert {_label(result, accepted), _label(result, rejected), _label(result, undecided)} == {
        "IN",
        "OUT",
        "UNDEC",
    }


def test_label_witnesses_use_defenders_attackers_and_complete_cycle_scc() -> None:
    defender, attacker, target = (
        _argument("defender"),
        _argument("attacker"),
        _argument("target"),
    )
    defended = evaluate_argument_graph(
        ArgumentGraphV4(
            (defender, attacker, target),
            attacks=(
                _attack("defender-attacks", defender, attacker),
                _attack("attacker-attacks", attacker, target),
            ),
        )
    )
    by_ref = {item.argument_ref: item for item in defended.labels}
    assert by_ref[argument_ref_v4(target)].witness_refs == (argument_ref_v4(defender),)
    assert by_ref[argument_ref_v4(attacker)].witness_refs == (argument_ref_v4(defender),)

    left, right = _argument("left"), _argument("right")
    cycle = evaluate_argument_graph(
        ArgumentGraphV4(
            (left, right),
            attacks=(
                _attack("left-right", left, right),
                _attack("right-left", right, left),
            ),
        )
    )
    expected_cycle = {argument_ref_v4(left), argument_ref_v4(right)}
    assert all(set(item.witness_refs) == expected_cycle for item in cycle.labels)


def test_collection_permutation_has_identical_graph_and_evaluation_bytes() -> None:
    a, b, c = _argument("a"), _argument("b"), _argument("c")
    attacks = (_attack("a-b", a, b), _attack("c-b", c, b))
    first = ArgumentGraphV4((a, b, c), attacks=attacks)
    second = ArgumentGraphV4((c, a, b), attacks=tuple(reversed(attacks)))

    assert first.canonical_bytes() == second.canonical_bytes()
    assert evaluate_argument_graph(first).canonical_bytes() == evaluate_argument_graph(
        second
    ).canonical_bytes()


def test_disconnected_argument_does_not_change_existing_component_labels() -> None:
    a, b, isolated = _argument("a"), _argument("b"), _argument("isolated")
    base = evaluate_argument_graph(
        ArgumentGraphV4((a, b), attacks=(_attack("a-b", a, b),))
    )
    extended = evaluate_argument_graph(
        ArgumentGraphV4((isolated, b, a), attacks=(_attack("a-b", a, b),))
    )

    assert (_label(base, a), _label(base, b)) == (
        _label(extended, a),
        _label(extended, b),
    )
    assert _label(extended, isolated) == "IN"


@pytest.mark.parametrize(
    "builder",
    [
        lambda a, b: ArgumentGraphV4((a, a)),
        lambda a, b: ArgumentGraphV4(
            (a,), attacks=(_attack("unknown", b, a),)
        ),
        lambda a, b: ArgumentGraphV4(
            (a,), priority_edges=(_priority("unknown-priority", a, b),)
        ),
        lambda a, b: ArgumentGraphV4(
            (a,), permission_relations=(_permission(a, b),)
        ),
    ],
)
def test_duplicate_or_unknown_graph_identity_fails_closed(builder) -> None:
    with pytest.raises(ArgumentationV4Error) as exc:
        builder(_argument("a"), _argument("b"))
    assert exc.value.code in {"ARGUMENT_GRAPH_DUPLICATE", "ARGUMENT_GRAPH_ENDPOINT"}


def test_production_argumentation_imports_no_v2_test_or_companion_oracle() -> None:
    source = (ROOT / "compiler_core/argumentation.py").read_text(encoding="utf-8")
    assert "argumentation_v2" not in source
    assert "legal-math-modeling" not in source
    assert "reference_semantics" not in source
    assert "tests." not in source
