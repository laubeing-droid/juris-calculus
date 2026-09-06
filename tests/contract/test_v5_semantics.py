"""U05 acceptance samples JT16-JT27: defeat resolution, four bounded profiles,
branch isolation and query semantics.

JT16-JT19 are abstract Dung graphs over argument ids; they are mathematics
samples, not case-level win/loss labels.
"""
from __future__ import annotations

import pytest

from compiler_core.argumentation import (
    AttackRecordV5,
    evaluate_profile_v5,
    resolve_defeats_v5,
    verify_profile_family_v5,
)
from compiler_core.query_semantics import (
    GateStateV5,
    ProfileEvaluationV5,
    QueryInputV5,
    QueryRefutationV5,
    evaluate_query_v5,
)


def _families(result):
    return tuple(sorted(tuple(sorted(extension)) for extension in result.extensions))


# ---------------------------------------------------------------------------
# JT16-JT19: the four abstract graph samples
# ---------------------------------------------------------------------------


def test_jt16_no_attacks_yields_singleton_family_everywhere() -> None:
    for profile in ("grounded", "preferred", "stable", "complete"):
        result = evaluate_profile_v5(profile, ("a",), ())
        assert result.kind == "extensions"
        assert _families(result) == (("a",),)


def test_jt17_self_attack_grounded_empty_and_stable_absent() -> None:
    defeats = (("a", "a"),)
    assert _families(evaluate_profile_v5("grounded", ("a",), defeats)) == ((),)
    assert _families(evaluate_profile_v5("preferred", ("a",), defeats)) == ((),)
    assert evaluate_profile_v5("stable", ("a",), defeats).kind == "no_extension"
    assert _families(evaluate_profile_v5("complete", ("a",), defeats)) == ((),)


def test_jt18_symmetric_pair_separates_all_four_profiles() -> None:
    defeats = (("a", "b"), ("b", "a"))
    assert _families(evaluate_profile_v5("grounded", ("a", "b"), defeats)) == ((),)
    assert _families(evaluate_profile_v5("preferred", ("a", "b"), defeats)) == (("a",), ("b",))
    assert _families(evaluate_profile_v5("stable", ("a", "b"), defeats)) == (("a",), ("b",))
    assert _families(evaluate_profile_v5("complete", ("a", "b"), defeats)) == (
        (), ("a",), ("b",),
    )


def test_jt19_three_cycle_stable_absent_and_empty_extension_elsewhere() -> None:
    defeats = (("a", "b"), ("b", "c"), ("c", "a"))
    assert evaluate_profile_v5("stable", ("a", "b", "c"), defeats).kind == "no_extension"
    for profile in ("grounded", "preferred", "complete"):
        result = evaluate_profile_v5(profile, ("a", "b", "c"), defeats)
        assert _families(result) == ((),)


# ---------------------------------------------------------------------------
# JT20 / JT21: budget exhaustion and independent family verification
# ---------------------------------------------------------------------------


def test_jt20_budget_exhaustion_returns_incomplete_not_empty() -> None:
    arguments = tuple(f"a{index}" for index in range(17))
    result = evaluate_profile_v5("preferred", arguments, ())
    assert result.kind == "incomplete"
    assert result.open_obligations
    result = evaluate_profile_v5("stable", ("a", "b"), (), subset_limit=2)
    assert result.kind == "incomplete"
    assert any(code == "enumeration_budget" for code, _ in result.open_obligations)


def test_jt21_non_maximal_preferred_claim_is_rejected_by_reference() -> None:
    # preferred family for a<->b is {{a},{b}}; claiming only {a} as exact is a
    # maximality failure even though {a} is genuinely admissible.
    defeats = (("a", "b"), ("b", "a"))
    ok, reason = verify_profile_family_v5(
        "preferred", ("a", "b"), defeats, (frozenset({"a"}),),
        coverage="discovered_only",
    )
    assert ok and not reason
    ok, reason = verify_profile_family_v5(
        "preferred", ("a", "b"), defeats, (frozenset({"a"}),), coverage="exact",
    )
    assert not ok and reason == "family_mismatch"
    # {a,b} is not even conflict-free, so a discovered claim containing it is unsound
    ok, reason = verify_profile_family_v5(
        "preferred", ("a", "b"), defeats, (frozenset({"a", "b"}),),
        coverage="discovered_only",
    )
    assert not ok and reason == "discovered_unsound"


# ---------------------------------------------------------------------------
# JT22: no defeat without policy-admissible evidence
# ---------------------------------------------------------------------------


def test_jt22_policy_gate_blocks_unwitnessed_and_out_of_policy_attacks() -> None:
    attacks = (
        AttackRecordV5("atk-1", "a", "b", "rebut", "admitted contrary authority"),
        AttackRecordV5("atk-2", "b", "a", "authority_attack", "senior rule evidence"),
    )
    defeats = resolve_defeats_v5(
        ("a", "b"), attacks,
        policy_id="policy-x", policy_version="1",
        allowed_kinds=("rebut",), request_ref="r",
    )
    assert defeats == (("a", "b"),)
    with pytest.raises(Exception) as caught:
        resolve_defeats_v5(
            ("a",), (AttackRecordV5("atk-3", "a", "ghost", "rebut", "w"),),
            policy_id="p", policy_version="1", allowed_kinds=("rebut",),
            request_ref="r",
        )
    assert "DEFEAT_ENDPOINT_UNKNOWN" in str(caught.value)


def test_jt22_attack_record_requires_witness() -> None:
    with pytest.raises(Exception) as caught:
        AttackRecordV5("atk-4", "a", "b", "rebut", "")
    assert "DEFEAT_INPUT_FIELD" in str(caught.value)


# ---------------------------------------------------------------------------
# JT23-JT27: query semantics
# ---------------------------------------------------------------------------


def _evaluation(profile, kind, extensions):
    return ProfileEvaluationV5(profile, kind, tuple(frozenset(e) for e in extensions), ())


def test_jt23_one_in_one_out_supporter_does_not_refute() -> None:
    # a (supporting q) is OUT; b (supporting q) is IN within the same branch.
    status = evaluate_query_v5(QueryInputV5(
        query_id="q1", claim="q", profile="grounded",
        evaluation=_evaluation("grounded", "extensions", [{"b"}]),
        argument_claims={"a": "q", "b": "q"},
    ))
    assert status.common is True
    assert status.possibly_refuted is False
    assert status.common_refuted is False
    assert status.acceptance_witnesses == ("b",)


def test_jt24_refutation_direction_is_not_symmetric() -> None:
    refutations = (QueryRefutationV5(refuter="q", target="r"),)
    status = evaluate_query_v5(QueryInputV5(
        query_id="q2", claim="q", profile="grounded",
        evaluation=_evaluation("grounded", "extensions", [{"a"}]),
        argument_claims={"a": "q"}, refutations=refutations,
    ))
    assert status.possibly_refuted is False
    assert status.common_refuted is False
    with pytest.raises(Exception) as caught:
        QueryRefutationV5(refuter="same", target="same")
    assert "IRREFLEXIVE" in str(caught.value)


def test_jt25_excluded_and_incomplete_gates_report_no_status() -> None:
    evaluation = _evaluation("preferred", "extensions", [{"a"}, {"b"}])
    status = evaluate_query_v5(QueryInputV5(
        query_id="q3", claim="q", profile="preferred",
        evaluation=evaluation, argument_claims={"a": "q", "b": "q"},
        gates=(
            GateStateV5(0, "excluded", "claim outside this branch's problem scope"),
            GateStateV5(1, "excluded", "gate evidence incomplete for this branch"),
        ),
    ))
    assert status.excluded is True
    assert status.common is False and status.undecided_some is False
    status = evaluate_query_v5(QueryInputV5(
        query_id="q4", claim="q", profile="preferred",
        evaluation=evaluation, argument_claims={"a": "q", "b": "q"},
        gates=(GateStateV5(0, "enterable"), GateStateV5(1, "incomplete")),
    ))
    assert status.gate == "enterable"
    assert status.common is False
    assert status.possible is True


def test_jt26_empty_family_and_incomplete_search_never_vacuous_common() -> None:
    status = evaluate_query_v5(QueryInputV5(
        query_id="q5", claim="q", profile="grounded",
        evaluation=_evaluation("grounded", "no_extension", []),
        argument_claims={"a": "q"},
    ))
    assert status.common is False and status.possible is False
    assert status.common_refuted is False
    status = evaluate_query_v5(QueryInputV5(
        query_id="q6", claim="q", profile="stable",
        evaluation=_evaluation("stable", "incomplete", [{"a"}]),
        argument_claims={"a": "q"},
    ))
    assert status.common is False
    assert status.possible is True
    assert status.gate == "incomplete"


def test_jt27_branch_keys_isolate_scenarios_profiles_and_extensions() -> None:
    from compiler_core.query_semantics import compose_branch_key_v5

    base = compose_branch_key_v5("s1", ("x",), "grounded", frozenset({"a"}))
    other_scenario = compose_branch_key_v5("s2", ("x",), "grounded", frozenset({"a"}))
    other_assumptions = compose_branch_key_v5("s1", ("y",), "grounded", frozenset({"a"}))
    other_profile = compose_branch_key_v5("s1", ("x",), "preferred", frozenset({"a"}))
    other_extension = compose_branch_key_v5("s1", ("x",), "grounded", frozenset({"b"}))
    assert len({base, other_scenario, other_assumptions, other_profile, other_extension}) == 5
