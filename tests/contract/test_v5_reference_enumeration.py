"""Independent finite-graph enumeration regression for the V5 profile solver.

Motivated by the 2026-09-07 independent audit: the production stable solver
had its attack direction inverted and the contract samples JT16-JT19 were too
weak to expose it. This file pins the solver against a definition-driven
reference enumerator over EVERY directed attack graph on 0-3 arguments
(including self-attacks) — 531 frameworks, four semantics each — plus the
audit's minimal counterexamples, an attack chain, and a fork.

The reference enumerator in this file is written directly from the Dung
definitions and shares no code with ``compiler_core.argumentation``.
"""
from __future__ import annotations

from itertools import product

from compiler_core.argumentation import evaluate_profile_v5

PROFILES = ("grounded", "preferred", "stable", "complete")


# ---------------------------------------------------------------------------
# Definition-driven reference implementation (independent of the solver)
# ---------------------------------------------------------------------------


def _extensions(profile: str, arguments: frozenset[str], defeats: frozenset) -> list[frozenset]:
    attackers_of = {
        argument: frozenset(
            source for source, target in defeats if target == argument
        )
        for argument in arguments
    }

    def conflict_free(subset: frozenset) -> bool:
        return not any(
            source in subset and target in subset for source, target in defeats
        )

    def defends(subset: frozenset, argument: str) -> bool:
        return all(
            any(defender in subset for defender in attackers_of[attacker])
            for attacker in attackers_of[argument]
        )

    def admissible(subset: frozenset) -> bool:
        return conflict_free(subset) and all(defends(subset, item) for item in subset)

    def characteristic(subset: frozenset) -> frozenset:
        return frozenset(
            argument
            for argument in arguments
            if defends(subset, argument)
        )

    def stable_member(subset: frozenset) -> bool:
        return conflict_free(subset) and all(
            any((source, member) in defeats for source in subset)
            for member in arguments - subset
        )

    def subsets():
        ordered = sorted(arguments)
        for mask in range(1 << len(ordered)):
            yield frozenset(
                argument for index, argument in enumerate(ordered) if mask >> index & 1
            )

    if profile == "grounded":
        current = frozenset()
        for _ in range(len(arguments) + 1):
            nxt = characteristic(current)
            if nxt == current:
                return [current]
            current = nxt
        raise AssertionError("characteristic function must converge on finite graphs")

    members = []
    for subset in subsets():
        if profile == "stable":
            if stable_member(subset):
                members.append(subset)
        elif profile == "complete":
            if admissible(subset) and characteristic(subset) == subset:
                members.append(subset)
        elif profile == "preferred":
            if admissible(subset) and not any(
                other > subset and admissible(other) for other in subsets()
            ):
                members.append(subset)
        else:
            raise AssertionError(profile)
    return members


def _all_frameworks(max_arguments: int = 3):
    """Every directed attack graph on 0..max_arguments nodes, self-loops included."""

    for size in range(0, max_arguments + 1):
        arguments = tuple(f"a{index}" for index in range(size))
        pairs = [(source, target) for source in arguments for target in arguments]
        for bits in product((False, True), repeat=len(pairs)):
            defeats = frozenset(
                pair for pair, present in zip(pairs, bits) if present
            )
            yield arguments, defeats


# ---------------------------------------------------------------------------
# The audit's named counterexamples
# ---------------------------------------------------------------------------


def _family(result):
    return tuple(sorted(tuple(sorted(extension)) for extension in result.extensions))


def test_audit_counterexample_single_attack_is_not_inverted() -> None:
    # a->b: {a} is conflict-free and attacks the only outside argument; {b}
    # attacks nothing outside itself and is therefore NOT stable.
    result = evaluate_profile_v5("stable", ("a", "b"), (("a", "b"),))
    assert result.kind == "extensions"
    assert _family(result) == (("a",),)

    result = evaluate_profile_v5("stable", ("a", "b"), (("b", "a"),))
    assert _family(result) == (("b",),)


def test_audit_attack_chain_and_fork() -> None:
    # chain a->b->c: c has no attacker, so every stable/complete extension must
    # contain c; {a, c} is conflict-free and attacks the only outsider (b).
    chain = (("a", "b"), ("b", "c"))
    assert _family(evaluate_profile_v5("stable", ("a", "b", "c"), chain)) == (("a", "c"),)
    assert _family(evaluate_profile_v5("grounded", ("a", "b", "c"), chain)) == (("a", "c"),)
    assert _family(evaluate_profile_v5("preferred", ("a", "b", "c"), chain)) == (("a", "c"),)
    assert _family(evaluate_profile_v5("complete", ("a", "b", "c"), chain)) == (("a", "c"),)

    # fork c attacks both a and b: {c} is the unique extension everywhere
    fork = (("c", "a"), ("c", "b"))
    assert _family(evaluate_profile_v5("stable", ("a", "b", "c"), fork)) == (("c",),)
    assert _family(evaluate_profile_v5("grounded", ("a", "b", "c"), fork)) == (("c",),)
    assert _family(evaluate_profile_v5("preferred", ("a", "b", "c"), fork)) == (("c",),)
    assert _family(evaluate_profile_v5("complete", ("a", "b", "c"), fork)) == (("c",),)


# ---------------------------------------------------------------------------
# Exhaustive finite comparison against the reference enumerator
# ---------------------------------------------------------------------------


def test_every_directed_graph_on_zero_to_three_arguments_matches_definitions() -> None:
    frameworks = list(_all_frameworks(3))
    # 1 + 2 + 16 + 512 = 531 directed graphs including self-attacks.
    assert len(frameworks) == 531

    mismatches: list[str] = []
    for arguments, defeats in frameworks:
        for profile in PROFILES:
            result = evaluate_profile_v5(profile, arguments, tuple(sorted(defeats)))
            if result.kind == "no_extension":
                observed: list[frozenset] = []
            elif result.kind == "extensions":
                observed = list(result.extensions)
            else:
                mismatches.append(
                    f"{profile}/{sorted(arguments)}/{sorted(defeats)}: incomplete"
                )
                continue
            expected = _extensions(profile, frozenset(arguments), defeats)
            if sorted(map(sorted, observed)) != sorted(map(sorted, expected)):
                mismatches.append(
                    f"{profile}/{sorted(arguments)}/{sorted(defeats)}: "
                    f"{sorted(map(sorted, observed))} != {sorted(map(sorted, expected))}"
                )
    assert mismatches == []
