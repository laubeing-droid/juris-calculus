"""Final-remediation regressions (JC-FINAL-FIX-20260908).

Every counterexample from the 2026-09-08 remediation package is pinned here
as a permanent red-to-green regression:

- B: branch identity delimiter collisions (FIX-01)
- C: query refutation semantics and result contracts (FIX-02)
- D: incomplete propagation as typed obligations (FIX-03)
- E: priority relations participate or block completeness (FIX-04)
- G: solver/priority gaps never surface as unreserved complete answers

Stage-level checks drive the pure layers directly; chain-level checks go
through the sole public ApplicationV4 spine with sealed audit bundles.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import compiler_core.application as application_module
from compiler_core.application import (
    ApplicationV4,
    PROFILE_STAGE_KIND_V5,
    _v5_branch_identity,
)
from compiler_core.argumentation import (
    AttackRecordV5,
    ArgumentationV4Error,
    evaluate_profile_v5,
    priority_edge_decisions_v5,
    resolve_defeats_v5,
)
from compiler_core.canonical_serialization import DigestV4, digest_value
from compiler_core.contracts import (
    ClaimRefutationV5,
    ContractV4Error,
    DefeatPolicyV5,
    OpenObligationEntryV5,
    ProcedureResultV5,
    QueryGateRequestV5,
    QueryResultV5,
)
from compiler_core.procedure import adjudicate_v5
from compiler_core.query_semantics import (
    GateStateV5,
    ProfileEvaluationV5,
    QueryInputV5,
    QueryRefutationV5,
    evaluate_query_v5,
)

from tests.contract.test_v5_profile_chain import (
    EXCEPTION_FACTS,
    _application,
    _seed_with_v5,
    _stage_document,
    _v5_inputs,
)
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness


# ---------------------------------------------------------------------------
# B: branch identity (FIX-01)
# ---------------------------------------------------------------------------


def test_branch_identity_delimiter_collision_is_impossible() -> None:
    """`{"a","b"}` and `{"a|b"}` are distinct real stable branches (B01)."""

    ext_pair = frozenset({"a", "b"})
    ext_joined = frozenset({"a|b"})
    id_pair, ref_pair = _v5_branch_identity("req-1", "stable", ext_pair)
    id_joined, ref_joined = _v5_branch_identity("req-1", "stable", ext_joined)
    assert id_pair != id_joined
    assert ref_pair != ref_joined

    evaluation = evaluate_profile_v5(
        "stable",
        ("a", "b", "a|b"),
        (
            ("a", "a|b"), ("b", "a|b"), ("a|b", "a"), ("a|b", "b"),
        ),
    )
    by_size = {
        len(extension): extension for extension in evaluation.extensions
    }
    assert {len(item) for item in evaluation.extensions} == {1, 2}
    branch_ids = {
        _v5_branch_identity("req-1", "stable", extension)
        for extension in evaluation.extensions
    }
    assert len(branch_ids) == 2


def test_assumption_set_identity_is_order_insensitive_and_collision_free() -> None:
    """Same assumption set in any order shares identity; different sets do not (B02)."""

    from compiler_core.contracts import ScenarioKeyV5

    def key(assumptions: tuple[str, ...]) -> DigestV4:
        return ScenarioKeyV5(
            request_ref=digest_value({"r": 1}),
            scenario_id="s1",
            assumptions=assumptions,
            assumptions_digest=digest_value({
                "assumptions": sorted(set(assumptions)),
            }),
        ).assumptions_digest

    assert key(("x", "y")) == key(("y", "x"))
    assert key(("x", "y")) != key(("x|y",))

    scenario_a, assumptions_a, profile_a, extension_a = (
        application_module.compose_branch_key_v5("s1", ("x|y",), "grounded", frozenset({"a"}))
    )
    scenario_b, assumptions_b, profile_b, extension_b = (
        application_module.compose_branch_key_v5("s1", ("x", "y"), "grounded", frozenset({"a"}))
    )
    assert assumptions_a != assumptions_b
    assert extension_a == extension_b


# ---------------------------------------------------------------------------
# C: query refutation semantics (FIX-02)
# ---------------------------------------------------------------------------


def _single_extension_query(
    extensions: tuple[frozenset[str], ...],
    claims: dict[str, str],
    refutations: tuple[QueryRefutationV5, ...],
    query_claim: str = "q",
):
    evaluation = ProfileEvaluationV5("stable", "extensions", extensions, ())
    return evaluate_query_v5(QueryInputV5(
        query_id="q1", claim=query_claim, profile="stable",
        evaluation=evaluation, argument_claims=claims,
        refutations=refutations,
    ))


def test_refutation_runs_through_conclusion_not_argument_id() -> None:
    """arg_r concludes r, r refutes q => q is refuted (C01)."""

    status = _single_extension_query(
        (frozenset({"arg_r"}),),
        {"arg_r": "r"},
        (QueryRefutationV5("r", "q"),),
    )
    assert status.common_refuted is True
    assert status.possibly_refuted is True
    assert status.undecided_some is False
    assert status.refutation_witnesses == ("arg_r",)


def test_renaming_the_argument_does_not_change_refutation_semantics() -> None:
    """Naming the argument exactly `r` must not flip any aggregate (C02)."""

    renamed = _single_extension_query(
        (frozenset({"r"}),),
        {"r": "r"},
        (QueryRefutationV5("r", "q"),),
    )
    assert renamed.common_refuted is True
    assert renamed.possibly_refuted is True

    reverse = _single_extension_query(
        (frozenset({"arg_r"}),),
        {"arg_r": "r"},
        (QueryRefutationV5("r", "q"),),
        query_claim="r",
    )
    assert reverse.common_refuted is False
    assert reverse.possibly_refuted is False


def test_inconsistent_some_is_existential_per_branch() -> None:
    """One branch both accepting and refuting is inconsistent; universality not required (C03)."""

    claims = {"arg_a": "q", "arg_r": "r"}
    refutations = (QueryRefutationV5("r", "q"),)
    mixed = evaluate_query_v5(QueryInputV5(
        query_id="q1", claim="q", profile="stable",
        evaluation=ProfileEvaluationV5(
            "stable", "extensions",
            (frozenset({"arg_a", "arg_r"}), frozenset({"arg_n"})),
            (),
        ),
        argument_claims={**claims, "arg_n": "other"},
        refutations=refutations,
    ))
    assert mixed.inconsistent_some is True
    assert mixed.common is False
    assert mixed.common_refuted is False
    assert mixed.possibly_refuted is True
    assert mixed.undecided_some is True

    separated = evaluate_query_v5(QueryInputV5(
        query_id="q1", claim="q", profile="stable",
        evaluation=ProfileEvaluationV5(
            "stable", "extensions",
            (frozenset({"arg_a"}), frozenset({"arg_r"})),
            (),
        ),
        argument_claims={**claims, "arg_r": "r"},
        refutations=refutations,
    ))
    assert separated.inconsistent_some is False
    assert separated.common is False
    assert separated.possible is True
    assert separated.possibly_refuted is True


def test_excluded_query_contract_is_constructible() -> None:
    """A legally excluded query is a valid, serializable answer (C04)."""

    result = QueryResultV5(
        query_id="q1", profile="stable",
        branch_ref=digest_value({"branch": 1}),
        gate="excluded",
        common=False, possible=False, common_refuted=False,
        possibly_refuted=False, undecided_some=False,
        inconsistent_some=False, excluded=True,
        witnesses=(),
    )
    assert result.to_dict()["excluded"] is True
    with pytest.raises(ContractV4Error) as caught:
        QueryResultV5(
            query_id="q1", profile="stable",
            branch_ref=digest_value({"branch": 1}),
            gate="excluded",
            common=False, possible=False, common_refuted=False,
            possibly_refuted=False, undecided_some=False,
            inconsistent_some=False, excluded=False,
            witnesses=(),
        )
    assert caught.value.code == "TYPE_AUTHORITY"


def test_incomplete_gate_never_witnesses_status() -> None:
    with pytest.raises(ContractV4Error) as caught:
        QueryResultV5(
            query_id="q1", profile="stable",
            branch_ref=digest_value({"branch": 1}),
            gate="incomplete",
            common=False, possible=True, common_refuted=False,
            possibly_refuted=False, undecided_some=False,
            inconsistent_some=False, excluded=False,
            witnesses=(),
        )
    assert caught.value.code == "TYPE_AUTHORITY"


def test_no_extension_versus_incomplete_families_stay_distinct() -> None:
    """Empty family, discovered-only family and completed family differ (C05)."""

    empty = evaluate_query_v5(QueryInputV5(
        query_id="q", claim="q", profile="stable",
        evaluation=ProfileEvaluationV5("stable", "no_extension", (), ()),
        argument_claims={"a": "q"},
    ))
    assert (empty.common, empty.possible, empty.gate) == (False, False, "enterable")

    partial = evaluate_query_v5(QueryInputV5(
        query_id="q", claim="q", profile="stable",
        evaluation=ProfileEvaluationV5(
            "stable", "incomplete", (frozenset({"a"}),),
            (("enumeration_budget", "powerset exceeds the budget"),),
        ),
        argument_claims={"a": "q"},
    ))
    assert partial.common is False
    assert partial.possible is True
    assert partial.gate == "incomplete"


# ---------------------------------------------------------------------------
# D: incomplete obligations are typed (FIX-03)
# ---------------------------------------------------------------------------


def test_solver_incomplete_reaches_every_contract_layer_typed() -> None:
    """17 arguments + preferred reports typed obligations, never tuples (D01)."""

    evaluation = evaluate_profile_v5(
        "preferred",
        tuple(f"arg-{index}" for index in range(17)),
        (("arg-0", "arg-1"),),
    )
    assert evaluation.kind == "incomplete"
    assert evaluation.open_obligations
    typed = application_module._v5_typed_obligations(evaluation.open_obligations)
    assert all(type(item) is OpenObligationEntryV5 for item in typed)
    procedure = adjudicate_v5(
        request_ref=digest_value({"r": 1}),
        evaluation_kind=evaluation.kind,
        evaluation_open_obligations=typed,
    )
    assert procedure.kind == "solver_incomplete"
    assert procedure.open_obligations == typed
    with pytest.raises(ContractV4Error) as caught:
        ProcedureResultV5(
            request_ref=digest_value({"r": 1}),
            kind="solver_incomplete",
            status=None,
            missing=(),
            open_obligations=evaluation.open_obligations,
            authority_ref=None,
        )
    assert caught.value.code == "TYPE_MISMATCH"


# ---------------------------------------------------------------------------
# E: priority relations (FIX-04)
# ---------------------------------------------------------------------------

PRIORITY_POLICY = "target-preferred-rebut/1"


def _rebut_pair() -> tuple[AttackRecordV5, ...]:
    return (
        AttackRecordV5("atk-ab", "a", "b", "rebut", "w1"),
        AttackRecordV5("atk-ba", "b", "a", "rebut", "w2"),
    )


def _resolve(priority_edges: tuple[tuple[str, str], ...]):
    return resolve_defeats_v5(
        ("a", "b"), _rebut_pair(),
        policy_id="p", policy_version="1", allowed_kinds=("rebut",),
        request_ref="req",
        priority_edges=priority_edges,
        priority_policy_id=PRIORITY_POLICY if priority_edges else None,
    )


def test_priority_policy_actually_changes_defeats_and_extensions() -> None:
    """b>a and a>b produce different defeat sets and stable extensions (E01)."""

    with_b_preferred = _resolve((("b", "a"),))
    with_a_preferred = _resolve((("a", "b"),))
    assert with_b_preferred == (("b", "a"),)
    assert with_a_preferred == (("a", "b"),)

    stable_b = evaluate_profile_v5("stable", ("a", "b"), with_b_preferred)
    stable_a = evaluate_profile_v5("stable", ("a", "b"), with_a_preferred)
    assert stable_b.extensions == (frozenset({"b"}),)
    assert stable_a.extensions == (frozenset({"a"}),)


def test_priority_never_manufactures_an_attack() -> None:
    """b>a alone neither attacks nor excludes anything (E02/E03)."""

    defeats = resolve_defeats_v5(
        ("a", "b"), (),
        policy_id="p", policy_version="1", allowed_kinds=("rebut",),
        request_ref="req", priority_edges=(("b", "a"),),
        priority_policy_id=PRIORITY_POLICY,
    )
    assert defeats == ()
    stable = evaluate_profile_v5("stable", ("a", "b"), defeats)
    assert stable.extensions == (frozenset({"a", "b"}),)
    decisions = priority_edge_decisions_v5(
        ("a", "b"), (), (("b", "a"),), PRIORITY_POLICY,
    )
    assert decisions[0]["disposition"] == "no_applicable_conflict"

    single_blocked = resolve_defeats_v5(
        ("a", "b"), (_rebut_pair()[0],),
        policy_id="p", policy_version="1", allowed_kinds=("rebut",),
        request_ref="req", priority_edges=(("b", "a"),),
        priority_policy_id=PRIORITY_POLICY,
    )
    assert single_blocked == ()
    stable_single = evaluate_profile_v5("stable", ("a", "b"), single_blocked)
    assert stable_single.extensions == (frozenset({"a", "b"}),)


@pytest.mark.parametrize("edges", [(("b", "a"), ("a", "b"))])
def test_priority_cycle_fails_closed(edges: tuple[tuple[str, str], ...]) -> None:
    with pytest.raises(ArgumentationV4Error) as caught:
        _resolve(edges)
    assert caught.value.code == "PRIORITY_CYCLE_UNRESOLVED"


def test_priority_without_registered_policy_fails_closed() -> None:
    with pytest.raises(ArgumentationV4Error) as caught:
        resolve_defeats_v5(
            ("a", "b"), _rebut_pair(),
            policy_id="p", policy_version="1", allowed_kinds=("rebut",),
            request_ref="req", priority_edges=(("b", "a"),),
        )
    assert caught.value.code == "PRIORITY_POLICY_REQUIRED"
    with pytest.raises(ArgumentationV4Error) as caught:
        resolve_defeats_v5(
            ("a", "b"), _rebut_pair(),
            policy_id="p", policy_version="1", allowed_kinds=("rebut",),
            request_ref="req", priority_edges=(("b", "a"),),
            priority_policy_id="lex-specialis/9",
        )
    assert caught.value.code == "PRIORITY_POLICY_UNKNOWN"


# ---------------------------------------------------------------------------
# Chain-level: unsupported priority blocks completeness, never passes silently
# ---------------------------------------------------------------------------


PRIORITY_CONDITION_FACT = "synthetic-exception-priority.priority-condition"


def _run_chain(
    tmp_path: Path,
    *,
    policy_extra: dict | None = None,
    policy: DefeatPolicyV5 | None = None,
    profiles: tuple[str, ...] = ("grounded",),
    extra_fact_keys: tuple[str, ...] = EXCEPTION_FACTS + (PRIORITY_CONDITION_FACT,),
):
    harness = _ChainHarness()
    if policy is None:
        base_policy, queries, claim = _v5_inputs(harness, profiles=profiles)
        if policy_extra:
            policy = replace(base_policy, **policy_extra)
        else:
            policy = base_policy
    else:
        _unused, queries, claim = _v5_inputs(harness, profiles=profiles)
    seed, request_ref, _, run_ref = _seed_with_v5(
        harness, policy=policy, queries=queries, extra_fact_keys=extra_fact_keys,
    )
    application, store = _application(tmp_path / f"case-{seed.request_id[-6:]}", harness)
    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)
    return envelope, store, harness, run_ref, seed


def test_chain_without_priority_policy_blocks_completeness(tmp_path: Path) -> None:
    """An admitted priority relation without a registered policy is a formal
    mapping gap: queries go incomplete, obligations flow, completeness drops
    (E04/E06), and the run still succeeds observably."""

    envelope, store, harness, run_ref, _ = _run_chain(tmp_path)
    assert envelope.transport_outcome.status == "success"
    document = _stage_document(store, envelope, harness, run_ref)

    if document["priority"]["edges"]:
        assert document["mapping_coverage"]["status"] == "incomplete"
        codes = [
            item["code"]
            for item in document["mapping_coverage"]["open_obligations"]
        ]
        assert codes == ["priority_policy_missing"]
        for row in document["queries"]:
            assert row["gate"] == "incomplete"
            assert row["common"] is False
            assert row["mapping_incomplete"] is True
        for row in document["procedures"]:
            if row["kind"] == "solver_incomplete":
                continue
            assert row["kind"] == "pending_legal_judgment"
            assert "v5-mapping-incomplete" in row["missing"]
        for profile in document["profiles"].values():
            assert profile["verification"]["mapping"] == "incomplete"
            obligation_codes = [
                item["code"] for item in profile["assurance"]["coverage_open_obligations"]
            ]
            assert "priority_policy_missing" in obligation_codes
            assert profile["assurance"]["spec"] == "openObligations"
        assert envelope.result.completeness_state.value == "partial"
        assert "v5_mapping_incomplete" in envelope.result.decision_reason_codes
    else:
        pytest.fail("chain fixture unexpectedly carries no priority edge")


def test_chain_with_registered_priority_policy_maps_complete(tmp_path: Path) -> None:
    """Declaring the registered strategy turns the priority input into a
    real mapping decision and restores complete answers (E01 at chain level)."""

    envelope, store, harness, run_ref, _ = _run_chain(
        tmp_path,
        policy_extra={
            "priority_policy_id": PRIORITY_POLICY,
            "priority_policy_version": "1",
        },
    )
    assert envelope.transport_outcome.status == "success"
    document = _stage_document(store, envelope, harness, run_ref)
    assert document["mapping_coverage"]["status"] == "complete"
    assert document["priority"]["policy"] == PRIORITY_POLICY
    if document["priority"]["edges"]:
        assert document["priority"]["decisions"]
    for row in document["queries"]:
        assert row["gate"] == "enterable"
        assert row["mapping_incomplete"] is False
    assert envelope.result.completeness_state.value == "complete"


def test_chain_injected_priority_mapping_error_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A production mapping that misapplies the priority strategy (here:
    inverting the strategy so it also blocks non-rebut attacks) cannot
    certify itself: the independent recheck rejects the defeat set (E05)."""

    production = application_module.resolve_defeats_v5

    def inverting_mapper(arguments, attacks, *, priority_edges=(), **kwargs):
        if not priority_edges:
            return production(arguments, attacks, priority_edges=(), **kwargs)
        preferred = {pair[0] for pair in priority_edges}
        resolved = [
            (attack.attacker, attack.target)
            for attack in attacks
            # inverted strategy: blocks every attack touching the preferred
            # node, including non-rebut kinds
            if attack.attacker not in preferred and attack.target not in preferred
        ]
        return tuple(sorted(set(resolved)))

    monkeypatch.setattr(application_module, "resolve_defeats_v5", inverting_mapper)
    envelope, _store, _harness, _run_ref, _ = _run_chain(
        tmp_path,
        policy_extra={
            "priority_policy_id": PRIORITY_POLICY,
            "priority_policy_version": "1",
        },
    )
    assert envelope.transport_outcome.status == "error"
    assert envelope.transport_outcome.error.code == "APPLICATION_V5_VERIFICATION"


def test_chain_17_arguments_preferred_stays_typed_incomplete(tmp_path: Path) -> None:
    """The 17-argument preferred budget case returns solver_incomplete with
    typed obligations through the public chain (D01/D02)."""

    budget_facts = tuple(
        f"synthetic-budget-{index}.required-fact" for index in range(15)
    )
    harness = _ChainHarness()
    policy, queries, _claim = _v5_inputs(harness, profiles=("preferred",))
    seed, request_ref, _, run_ref = _seed_with_v5(
        harness,
        policy=policy,
        queries=queries,
        extra_fact_keys=EXCEPTION_FACTS + budget_facts,
    )
    application, store = _application(tmp_path / f"budget-{seed.request_id[-6:]}", harness)
    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)

    assert envelope.transport_outcome.status == "success"
    document = _stage_document(store, envelope, harness, run_ref)
    profile_row = document["profiles"]["preferred"]
    assert profile_row["kind"] == "incomplete"
    assert profile_row["verification"]["coverage"] == "incomplete"
    assert profile_row["verification"]["verified"] is False
    assert profile_row["open_obligations"], "incomplete solve must disclose obligations"
    assert all(
        set(entry) == {"code", "detail"} for entry in profile_row["open_obligations"]
    )
    for row in document["queries"]:
        assert row["gate"] == "incomplete"
        assert row["common"] is False
    for row in document["procedures"]:
        assert row["kind"] == "solver_incomplete"
        assert row["open_obligations"]
    assurance = profile_row["assurance"]
    assert assurance["spec"] == "openObligations"
    assert assurance["coverage_open_obligations"]
    assert envelope.result.completeness_state.value == "partial"
    assert "v5_solver_incomplete" in envelope.result.decision_reason_codes
