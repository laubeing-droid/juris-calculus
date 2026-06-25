"""Tests for horn_completeness.py D7 capabilities."""

from compiler_core.horn_completeness import (
    compute_minimal_support,
    compute_minimal_rebuttal,
    compute_missing_evidence,
    analyze_rule_impact,
    horn_fixpoint_with_completeness,
    HornCompletenessResult,
    ConclusionProvenance,
)


def _initial(**facts):
    return {k: True for k in facts}


def _rule(head, body=None, rid=None):
    r = {"head": head, "body": body or []}
    if rid:
        r["id"] = rid
    return r


def test_minimal_support_simple_chain():
    initial = _initial(fact_a=True, fact_b=True)
    rules = [_rule("C", ["fact_a", "fact_b"]), _rule("D", ["C"])]
    facts, comp = horn_fixpoint_with_completeness(initial, rules)
    assert compute_minimal_support("C", set(initial), rules, comp) == {"fact_a", "fact_b"}
    assert compute_minimal_support("D", set(initial), rules, comp) == {"fact_a", "fact_b"}


def test_minimal_support_not_derivable():
    initial = _initial(fact_a=True)
    rules = [_rule("C", ["fact_a", "fact_b"])]
    facts, comp = horn_fixpoint_with_completeness(initial, rules)
    assert compute_minimal_support("C", set(initial), rules, comp) == set()


def test_minimal_support_backward_chain():
    initial = _initial(a=True, b=True, c=True)
    rules = [
        _rule("D", ["a", "b"]),
        _rule("E", ["b", "c"]),
        _rule("F", ["D", "E"]),
    ]
    facts, comp = horn_fixpoint_with_completeness(initial, rules)
    result = compute_minimal_support("F", set(initial), rules, comp)
    assert result == {"a", "b", "c"}


def test_rebuttal_chain():
    initial = _initial(fact_a=True, fact_b=True)
    rules = [_rule("C", ["fact_a", "fact_b"])]
    facts, comp = horn_fixpoint_with_completeness(initial, rules)
    rebuttal = compute_minimal_rebuttal("C", set(initial), rules, comp)
    assert len(rebuttal) >= 1


def test_rebuttal_not_derivable():
    initial = _initial(fact_a=True)
    rules = [_rule("C", ["fact_a", "fact_b"])]
    facts, comp = horn_fixpoint_with_completeness(initial, rules)
    assert compute_minimal_rebuttal("C", set(initial), rules, comp) == []


def test_missing_evidence_sufficient():
    initial = _initial(a=True, b=True)
    rules = [_rule("C", ["a", "b"])]
    report = compute_missing_evidence("C", set(initial), rules)
    assert "sufficient" in report["checklist"].lower()
    assert report["missing_facts"] == []


def test_missing_evidence_insufficient():
    initial = _initial(a=True)
    rules = [_rule("C", ["a", "b"])]
    report = compute_missing_evidence("C", set(initial), rules)
    assert report["missing_facts"] == ["b"]


def test_missing_evidence_no_rules():
    initial = _initial(a=True)
    rules = []
    report = compute_missing_evidence("C", set(initial), rules)
    assert report["derivable"] is False
    assert report["missing_facts"] == []


def test_rule_impact_downstream_closure():
    initial = _initial(a=True, b=True)
    rules = [
        _rule("C", ["a", "b"], rid="r_c"),
        _rule("D", ["C"], rid="r_d"),
        _rule("E", ["D"], rid="r_e"),
    ]
    facts, comp = horn_fixpoint_with_completeness(initial, rules)
    impact = analyze_rule_impact("r_c", rules, set(initial), comp)
    assert impact["total_affected"] == 3
    assert impact["severity"] == "minor"


def test_rule_impact_leaf_rule():
    initial = _initial(a=True, b=True)
    rules = [
        _rule("C", ["a", "b"], rid="r_c"),
        _rule("D", ["C"], rid="r_d"),
    ]
    facts, comp = horn_fixpoint_with_completeness(initial, rules)
    impact = analyze_rule_impact("r_d", rules, set(initial), comp)
    assert impact["total_affected"] == 1
    assert impact["severity"] == "minor"


def test_rule_impact_unknown_rule():
    initial = _initial(a=True)
    rules = [_rule("C", ["a"], rid="r_c")]
    facts, comp = horn_fixpoint_with_completeness(initial, rules)
    impact = analyze_rule_impact("nonexistent", rules, set(initial), comp)
    assert impact["total_affected"] == 0
    assert impact["severity"] == "trivial"


def test_conclusion_provenance_builds_from_horn():
    initial = _initial(a=True, b=True)
    rules = [_rule("C", ["a", "b"])]
    facts, comp = horn_fixpoint_with_completeness(initial, rules)
    prov = ConclusionProvenance.from_horn_result("C", facts, comp, rules)
    assert prov.conclusion == "C"
    assert prov.complete is True
    assert prov.canonical_witness is not None
    assert len(prov.minimal_support_set) >= 1
