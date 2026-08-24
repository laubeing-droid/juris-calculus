"""First-method source intake stays fictional, content-bound, and test-only."""

from __future__ import annotations

import copy

import pytest

from compiler_core.canonical_serialization import parse_json_document
from compiler_core.contracts import ContentRefV4, SourceSnapshotV4
from tools import build_cn_official_pack as builder


def _source() -> dict:
    value = parse_json_document(builder.SOURCE_PATH.read_bytes())
    assert isinstance(value, dict)
    return value


def test_first_method_source_builds_content_bound_snapshot() -> None:
    document = builder.build_document(_source())
    source = document["source"]
    snapshot = SourceSnapshotV4.from_dict(source["snapshot"])
    raw_ref = ContentRefV4.from_dict(source["raw_ref"])
    normalized_ref = ContentRefV4.from_dict(source["normalized_ref"])

    assert snapshot.raw_digest == raw_ref.digest
    assert snapshot.normalized_digest == normalized_ref.digest
    assert snapshot.authority_tier == "synthetic_test_only"
    assert snapshot.license_status == "test-fixture"
    assert snapshot.distribution_status == "test-only"

    candidate_source = _source()
    candidate_source.update({
        "schema_version": "jc/cn-official-source-candidate/1.0",
        "scope": "candidate",
        "jurisdiction": "CN",
        "authority_tier": "law",
        "issuer": "candidate-source-custodian",
        "title": "candidate first-party source",
        "license_status": "official-publication",
        "distribution_status": "redistributable",
    })
    candidate = builder.build_document(candidate_source)
    assert candidate["schema_version"] == "jc/cn-official-candidate-bundle/1.0"
    assert candidate["candidate_pack"]["pack_id"] == "cn-official-candidate"
    assert candidate["candidate_pack"]["state"] == "CANDIDATE"
    assert candidate["candidate_pack"]["signature_ref"] is None
    assert candidate["production_allowed"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("scope", "production"),
        ("formal_source_claimed", True),
        ("license_status", "official"),
    ),
)
def test_source_identity_mutations_fail_closed(field: str, value: object) -> None:
    source = _source()
    source[field] = value

    with pytest.raises(builder.CandidatePackError):
        builder.build_document(source)


def test_legacy_identity_and_duplicate_units_are_rejected() -> None:
    legacy = _source()
    legacy["raw_text"] += builder._BANNED[1].decode("ascii")
    with pytest.raises(builder.CandidatePackError, match="retired corpus"):
        builder.build_document(legacy)

    duplicated = _source()
    duplicated["normative_units"].append(
        copy.deepcopy(duplicated["normative_units"][0])
    )
    with pytest.raises(builder.CandidatePackError, match="duplicated"):
        builder.build_document(duplicated)


def test_normative_unit_text_must_be_anchored_in_raw_source() -> None:
    source = _source()
    source["normative_units"][0]["text"] = "未见于原文的转述"

    with pytest.raises(builder.CandidatePackError, match="not anchored in source"):
        builder.build_document(source)


def test_review_markdown_binds_exact_source_and_subject_without_approval() -> None:
    source = _source()
    document = builder.build_document(source)

    review = builder.render_review_markdown(source, document).decode("utf-8")

    first_unit = source["normative_units"][0]
    assert first_unit["unit_id"] in review
    assert first_unit["text"] in review
    assert document["review_subject"]["subject_digest"] in review
    assert document["review_subject"]["rule_subject_digests"][0] in review
    assert "production_allowed=false" in review
    assert "本文不记录批准" in review
