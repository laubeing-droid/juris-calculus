"""Contract tests for the sole V4 canonical JSON and DigestV4 authority."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from compiler_core.canonical_serialization import (
    CanonicalizationError,
    DigestV4,
    canonical_bytes,
    canonicalize_json,
    digest_value,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "golden" / "jcs-v4-vectors.json"


def _vectors() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_frozen_positive_vectors_match_exact_bytes_and_digest() -> None:
    for vector in _vectors()["positive"]:
        encoded = canonical_bytes(vector["input"])
        assert encoded.hex() == vector["canonical_utf8_hex"], vector["id"]
        assert str(DigestV4.from_bytes(encoded)) == vector["sha256"], vector["id"]
        assert digest_value(vector["input"]) == DigestV4.parse(vector["sha256"])


def test_frozen_negative_vectors_fail_with_stable_codes() -> None:
    for vector in _vectors()["negative"]:
        if vector["kind"] == "digest_grammar":
            with pytest.raises(CanonicalizationError) as caught:
                DigestV4.parse(vector["value"])
        else:
            with pytest.raises(CanonicalizationError) as caught:
                canonicalize_json(vector["input_json"])
        assert caught.value.code == vector["expected_error"], vector["id"]


def test_digest_grammar_composes_across_request_receipt_bundle() -> None:
    request_digest = digest_value({"request": {"facts": ["F-1"]}})
    receipt_digest = digest_value({"request_digest": str(request_digest), "status": "verified"})
    bundle_digest = digest_value({"receipt_digest": str(receipt_digest), "files": []})

    assert DigestV4.parse(request_digest) is request_digest
    assert DigestV4.parse(str(receipt_digest)) == receipt_digest
    assert isinstance(DigestV4.parse(str(bundle_digest)), DigestV4)
    for legacy in (
        str(request_digest).replace("sha256:", "sha256-", 1),
        str(receipt_digest).removeprefix("sha256:"),
        str(bundle_digest).upper(),
    ):
        with pytest.raises(CanonicalizationError, match="DIGEST_GRAMMAR"):
            DigestV4.parse(legacy)


def test_raw_json_duplicate_keys_are_rejected_after_escape_decoding() -> None:
    for raw in ('{"a":1,"a":2}', '{"a":1,"\\u0061":2}'):
        with pytest.raises(CanonicalizationError, match="DUPLICATE_KEY"):
            canonicalize_json(raw)


def test_canonicalization_preserves_unicode_without_normalization() -> None:
    nfc = {"text": "é"}
    nfd = {"text": "e\u0301"}

    assert canonical_bytes(nfc) == b'{"text":"\xc3\xa9"}'
    assert canonical_bytes(nfd) == b'{"text":"e\xcc\x81"}'
    assert digest_value(nfc) != digest_value(nfd)


def test_raw_source_digest_preserves_exact_bytes() -> None:
    nfc = "é".encode("utf-8")
    nfd = "e\u0301".encode("utf-8")

    assert DigestV4.from_bytes(nfc) != DigestV4.from_bytes(nfd)


def test_valid_escaped_surrogate_pair_is_combined_without_normalization() -> None:
    assert canonicalize_json('{"text":"\\ud83d\\ude00"}') == (
        '{"text":"😀"}'.encode("utf-8")
    )


@pytest.mark.parametrize(
    ("value", "error_code"),
    [
        ({"n": 1.5}, "FLOAT_FORBIDDEN"),
        ({"n": math.nan}, "NON_JSON_NUMBER"),
        ({"n": math.inf}, "NON_JSON_NUMBER"),
        ({"n": 2**53}, "UNSAFE_INTEGER"),
        ({"n": -(2**53)}, "UNSAFE_INTEGER"),
        ({"text": "\ud800"}, "LONE_SURROGATE"),
        ({"text": "\udc00"}, "LONE_SURROGATE"),
        ({1: "non-string key"}, "OBJECT_KEY_TYPE"),
        (1, "TOP_LEVEL_SCALAR"),
    ],
)
def test_direct_python_values_fail_closed(value: object, error_code: str) -> None:
    with pytest.raises(CanonicalizationError) as caught:
        canonical_bytes(value)

    assert caught.value.code == error_code


def test_direct_python_cycles_are_rejected() -> None:
    cyclic: list[object] = []
    cyclic.append(cyclic)

    with pytest.raises(CanonicalizationError, match="CYCLIC_VALUE"):
        canonical_bytes(cyclic)
