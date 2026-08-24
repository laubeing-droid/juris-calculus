"""Deterministic candidate-pack bytes are closed and unpromotable."""

from __future__ import annotations

import copy

import pytest

from compiler_core.canonical_serialization import parse_json_document
from tools import build_cn_official_pack as builder


def _document() -> dict:
    value = parse_json_document(builder.OUTPUT_PATH.read_bytes())
    assert isinstance(value, dict)
    return value


def test_committed_candidate_pack_is_reproducible_byte_for_byte() -> None:
    first = builder.build_fixture_bytes()
    second = builder.build_fixture_bytes()

    assert first == second == builder.OUTPUT_PATH.read_bytes()


def test_committed_candidate_pack_has_closed_artifact_graph() -> None:
    document = _document()

    assert builder.validate_document(document) == []
    assert document["scope"] == "test-only"
    assert document["production_allowed"] is False
    assert document["formal_source_claimed"] is False
    assert document["candidate_pack"]["pack_id"] == builder.PACK_ID
    assert document["candidate_pack"]["signature_ref"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("state", "ACTIVE"),
        ("production_allowed", True),
        ("formal_source_claimed", True),
    ),
)
def test_candidate_pack_cannot_self_promote(field: str, value: object) -> None:
    document = copy.deepcopy(_document())
    document["candidate_pack"][field] = value

    assert builder.validate_document(document)
