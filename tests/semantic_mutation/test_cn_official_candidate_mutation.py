"""Semantic mutations of the first-method candidate closure must be detected."""

from __future__ import annotations

import copy

import pytest

from compiler_core.canonical_serialization import parse_json_document
from tools import build_cn_official_pack as builder


def _document() -> dict:
    value = parse_json_document(builder.OUTPUT_PATH.read_bytes())
    assert isinstance(value, dict)
    return value


@pytest.mark.parametrize(
    "mutation",
    (
        "rule-modality",
        "promotion-receipt",
        "coverage-denominator",
        "omission-reason",
        "review-approved",
        "artifact-content",
    ),
)
def test_candidate_semantic_mutations_fail_closed(mutation: str) -> None:
    document = copy.deepcopy(_document())
    if mutation == "rule-modality":
        document["candidate_rules"][0]["modality"] = "PROHIBITION"
    elif mutation == "promotion-receipt":
        document["candidate_rules"][0]["promotion_receipt_refs"] = [
            document["candidate_pack"]["coverage_ref"]
        ]
    elif mutation == "coverage-denominator":
        document["coverage"]["denominator_unit_ids"].pop()
    elif mutation == "omission-reason":
        document["coverage"]["omissions"][0]["reason"] = ""
    elif mutation == "review-approved":
        document["review_subject"]["status"] = "APPROVED"
    else:
        document["artifacts"][0]["content"] = {"tampered": True}

    assert builder.validate_document(document)
