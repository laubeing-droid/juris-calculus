"""Candidate generation covers typed semantics without promotion authority."""

from __future__ import annotations

from compiler_core.canonical_serialization import parse_json_document
from compiler_core.contracts import RuleV4
from tools import build_cn_official_pack as builder


def _document() -> dict:
    source = parse_json_document(builder.SOURCE_PATH.read_bytes())
    assert isinstance(source, dict)
    return builder.build_document(source)


def test_candidate_rules_are_real_rule_v4_objects_without_promotion() -> None:
    rules = [RuleV4.from_dict(item) for item in _document()["candidate_rules"]]

    assert len(rules) == 5
    assert {rule.modality for rule in rules} == {
        "OBLIGATION", "PROHIBITION", "PERMISSION", "CONSTITUTIVE",
    }
    assert all(rule.promotion_receipt_refs == () for rule in rules)
    assert all(rule.jurisdiction == "TEST-CN" for rule in rules)


def test_candidate_semantic_feature_matrix_is_not_flattened() -> None:
    rules = [RuleV4.from_dict(item) for item in _document()["candidate_rules"]]

    assert sum(bool(rule.exception_refs) for rule in rules) == 1
    assert sum(bool(rule.priority_refs) for rule in rules) == 1
    assert sum(rule.permission_ref is not None for rule in rules) == 1
    assert sum(bool(rule.temporal_constraint_refs) for rule in rules) == 1
    assert sum(bool(rule.numeric_constraint_refs) for rule in rules) == 1


def test_coverage_denominator_has_candidate_or_reasoned_omission() -> None:
    coverage = _document()["coverage"]

    assert len(coverage["denominator_unit_ids"]) == 6
    assert len(coverage["candidate_unit_ids"]) == 5
    assert coverage["omissions"] == [{
        "unit_id": "TEST-CN-X1",
        "reason": "non-normative-test-note",
    }]
    assert set(coverage["denominator_unit_ids"]) == (
        set(coverage["candidate_unit_ids"]) | {"TEST-CN-X1"}
    )


def test_review_subject_requires_distinct_roles_but_claims_no_review() -> None:
    review = _document()["review_subject"]

    assert review["status"] == "AWAITING_EXTERNAL_REVIEW"
    assert review["formal_source_claimed"] is False
    assert review["required_roles"] == [
        "legal_reviewer_1", "legal_reviewer_2", "engineering_reviewer",
    ]
    assert len(review["rule_subject_digests"]) == 5
