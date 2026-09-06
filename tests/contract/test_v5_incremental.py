"""U09 acceptance samples JT40-JT43: add-only Horn increment safety and the
read-only empirical channel."""
from __future__ import annotations

import pytest

from compiler_core.canonical_serialization import digest_value
from compiler_core.contracts import DigestV4, EmpiricalResultV5, HornDeltaV5
from compiler_core.incremental import (
    HornSubjectV5,
    IncrementalV5Error,
    add_only_child,
    attach_empirical_v5,
    horn_closure,
    incremental_matches_full_recompute,
    requires_full_recompute,
)


def _digest(value) -> DigestV4:
    document = value if isinstance(value, (dict, list)) else {"value": value}
    return DigestV4(digest_value(document))


def _empirical(**overrides) -> dict:
    payload = {
        "observation_target": "outcome_frequency",
        "model_ref": str(_digest("model-v1")),
        "dataset_ref": str(_digest("dataset-1")),
        "evaluation_ref": None,
        "target_definition": "outcome frequency in comparable judgments",
        "population": "first-instance contract disputes",
        "time_range": "2020-01-01/2025-12-31",
        "missing_items": [],
        "calibration_status": "uncalibrated",
    }
    payload.update(overrides)
    payload["empirical_digest"] = str(
        digest_value({k: v for k, v in payload.items() if k != "empirical_digest"})
    )
    return payload


def _delta(parent: HornSubjectV5, facts, rules, child: HornSubjectV5) -> HornDeltaV5:
    return HornDeltaV5.from_dict({
        "parent_subject_digest": str(parent.subject_digest),
        "child_subject_digest": str(child.subject_digest),
        "universe_digest": str(_digest({"universe": sorted(parent.universe)})),
        "added_facts": list(facts),
        "added_rules": [str(_digest([head, sorted(body)])) for head, body in rules],
    })


UNIVERSE = frozenset({"fact-a", "fact-b", "atom-x", "atom-y"})


def _parent() -> HornSubjectV5:
    return HornSubjectV5.build(
        universe=UNIVERSE,
        facts=frozenset({"fact-a"}),
        rules=(("atom-x", ("fact-a",)),),
    )


def test_jt40_add_only_increment_equals_full_recompute() -> None:
    parent = _parent()
    added_rules: tuple[tuple[str, tuple[str, ...]], ...] = (("atom-y", ("atom-x",)),)
    child = HornSubjectV5.build(
        universe=parent.universe,
        facts=parent.facts | {"fact-b"},
        rules=(*parent.rules, *added_rules),
    )
    delta = _delta(parent, ("fact-b",), added_rules, child)
    assert incremental_matches_full_recompute(parent, delta, added_rules)
    closure = horn_closure(add_only_child(parent, delta, added_rules))
    assert closure == frozenset({"fact-a", "fact-b", "atom-x", "atom-y"})


def test_jt41_non_monotonic_changes_never_take_the_fast_path() -> None:
    parent = _parent()
    # universe growth
    grown = HornSubjectV5.build(
        universe=parent.universe | {"atom-z"},
        facts=parent.facts,
        rules=parent.rules,
    )
    delta = HornDeltaV5.from_dict({
        "parent_subject_digest": str(parent.subject_digest),
        "child_subject_digest": str(grown.subject_digest),
        "universe_digest": str(_digest({"universe": sorted(grown.universe)})),
        "added_facts": ["atom-z"],
        "added_rules": [],
    })
    with pytest.raises(IncrementalV5Error) as caught:
        add_only_child(parent, delta, ())
    assert caught.value.code == "HORN_UNIVERSE_GROWTH"
    # delta binding another parent is refused
    with pytest.raises(IncrementalV5Error) as caught:
        add_only_child(grown, delta, ())
    assert caught.value.code == "HORN_PARENT_MISMATCH"
    # the named invalidation list covers every non-monotonic change class
    reasons = requires_full_recompute(
        deleted_facts=("fact-a",), revoked_attestations=("att-1",),
        rule_rewrites=("rule-1",), profile_changed=True, mapping_changed=True,
        assumptions_changed=True, universe_growth=("atom-z",),
    )
    assert reasons == (
        "fact_deletion", "attestation_revocation", "rule_rewrite", "profile_change",
        "mapping_change", "assumption_set_change", "universe_growth",
    )


def test_jt42_empirical_perturbation_leaves_normative_digest_unchanged() -> None:
    normative = _digest({"result": "accepted", "claims": ["claim-1"]})
    result = EmpiricalResultV5.from_dict(_empirical())
    attached = attach_empirical_v5(normative, result=result)
    assert attached.normative_subject_digest == normative
    # replacing or reordering the empirical artifact cannot move the subject
    other = EmpiricalResultV5.from_dict(_empirical(
        observation_target="risk_ranking",
        model_ref=str(_digest("model-v2")),
        dataset_ref=str(_digest("dataset-2")),
        target_definition="risk ordering only",
        missing_items=["calibration"],
    ))
    replaced = attach_empirical_v5(normative, result=other)
    assert replaced.normative_subject_digest == attached.normative_subject_digest


def test_jt43_without_model_or_data_no_estimate_is_returned() -> None:
    estimate = attach_empirical_v5(_digest({"result": "unknown"}))
    assert estimate.result is None
    assert estimate.absent_reason == "no-verified-empirical-model"
    # constructing an empirical result with neither model nor evaluation ref is refused
    with pytest.raises(Exception) as caught:
        EmpiricalResultV5.from_dict(_empirical(
            observation_target="predicted_probability",
            model_ref=None,
            dataset_ref=None,
            evaluation_ref=None,
            target_definition="win probability",
            population="all disputes",
            time_range="unknown",
            missing_items=["model", "dataset", "calibration"],
            calibration_status="not_calibrated",
        ))
    assert "requires a model or evaluation reference" in str(caught.value)
