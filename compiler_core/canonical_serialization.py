#!/usr/bin/env python3
"""Sole V4 canonical JSON, DigestV4, AAF, and Horn serialization authority.

Formal JSON uses RFC 8785 string escaping, UTF-16 property ordering,
no-whitespace UTF-8 output, and a stricter I-JSON admission profile: every
float token and every integer outside the ECMAScript safe range is rejected.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
import json
import math
import re
from typing import Any


DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
SAFE_INTEGER_MIN = -(2**53) + 1
SAFE_INTEGER_MAX = (2**53) - 1


class CanonicalizationError(ValueError):
    """Stable fail-closed error for canonical JSON and digest admission."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class DigestV4(str):
    """Validated ``sha256:<64 lowercase hex>`` value object."""

    def __new__(cls, value: str) -> "DigestV4":
        if not isinstance(value, str) or DIGEST_PATTERN.fullmatch(value) is None:
            raise CanonicalizationError(
                "DIGEST_GRAMMAR",
                "digest must match sha256:<64 lowercase hex>",
            )
        return str.__new__(cls, value)

    @classmethod
    def parse(cls, value: object) -> "DigestV4":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise CanonicalizationError("DIGEST_GRAMMAR", "digest must be a string")
        return cls(value)

    @classmethod
    def from_bytes(cls, payload: bytes | bytearray | memoryview) -> "DigestV4":
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError("payload must be bytes-like")
        return cls("sha256:" + sha256(bytes(payload)).hexdigest())

    @classmethod
    def from_value(cls, value: object) -> "DigestV4":
        return cls.from_bytes(canonical_bytes(value))

    @property
    def hex(self) -> str:
        return self.removeprefix("sha256:")


def _well_formed_string(value: str) -> str:
    """Reject lone surrogates and combine valid UTF-16 surrogate pairs."""

    output: list[str] = []
    index = 0
    while index < len(value):
        code = ord(value[index])
        if 0xD800 <= code <= 0xDBFF:
            if index + 1 >= len(value):
                raise CanonicalizationError("LONE_SURROGATE", "unpaired high surrogate")
            low = ord(value[index + 1])
            if not 0xDC00 <= low <= 0xDFFF:
                raise CanonicalizationError("LONE_SURROGATE", "unpaired high surrogate")
            output.append(chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)))
            index += 2
            continue
        if 0xDC00 <= code <= 0xDFFF:
            raise CanonicalizationError("LONE_SURROGATE", "unpaired low surrogate")
        output.append(value[index])
        index += 1
    return "".join(output)


def _utf16_sort_key(value: str) -> bytes:
    return _well_formed_string(value).encode("utf-16-be")


def _escape_string(value: str) -> str:
    normalized = _well_formed_string(value)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def _canonical_text(value: object, seen: set[int]) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _escape_string(value)
    if isinstance(value, int):
        if not SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX:
            raise CanonicalizationError(
                "UNSAFE_INTEGER",
                "integer is outside the ECMAScript safe-integer range",
            )
        return str(value)
    if isinstance(value, float):
        code = "NON_JSON_NUMBER" if not math.isfinite(value) else "FLOAT_FORBIDDEN"
        raise CanonicalizationError(code, "formal V4 JSON forbids floating-point values")
    if isinstance(value, list):
        identity = id(value)
        if identity in seen:
            raise CanonicalizationError("CYCLIC_VALUE", "canonical JSON cannot contain cycles")
        seen.add(identity)
        try:
            return "[" + ",".join(_canonical_text(item, seen) for item in value) + "]"
        finally:
            seen.remove(identity)
    if isinstance(value, dict):
        identity = id(value)
        if identity in seen:
            raise CanonicalizationError("CYCLIC_VALUE", "canonical JSON cannot contain cycles")
        normalized: dict[str, object] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError("OBJECT_KEY_TYPE", "JSON object keys must be strings")
            normalized_key = _well_formed_string(key)
            if normalized_key in normalized:
                raise CanonicalizationError(
                    "DUPLICATE_KEY",
                    "object keys collide after Unicode scalar decoding",
                )
            normalized[normalized_key] = nested
        seen.add(identity)
        try:
            fields = (
                _escape_string(key) + ":" + _canonical_text(normalized[key], seen)
                for key in sorted(normalized, key=_utf16_sort_key)
            )
            return "{" + ",".join(fields) + "}"
        finally:
            seen.remove(identity)
    raise CanonicalizationError(
        "NON_JSON_VALUE",
        f"unsupported canonical JSON value type: {type(value).__name__}",
    )


def canonical_text(value: object) -> str:
    """Return canonical JSON text for a top-level object or array."""

    if not isinstance(value, (dict, list)):
        raise CanonicalizationError(
            "TOP_LEVEL_SCALAR",
            "canonical documents must be an object or array",
        )
    try:
        return _canonical_text(value, set())
    except RecursionError as exc:
        raise CanonicalizationError("DEPTH_LIMIT", "document nesting exceeds runtime limit") from exc


def canonical_bytes(value: object) -> bytes:
    """Return canonical UTF-8 bytes without Unicode normalization."""

    return canonical_text(value).encode("utf-8")


def _parse_integer(token: str) -> int:
    value = int(token)
    if not SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX:
        raise CanonicalizationError(
            "UNSAFE_INTEGER",
            "integer is outside the ECMAScript safe-integer range",
        )
    return value


def _reject_float(_token: str) -> object:
    raise CanonicalizationError("FLOAT_FORBIDDEN", "formal V4 JSON forbids float tokens")


def _reject_constant(_token: str) -> object:
    raise CanonicalizationError("NON_JSON_NUMBER", "NaN and Infinity are not JSON numbers")


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, nested in pairs:
        normalized_key = _well_formed_string(key)
        if normalized_key in value:
            raise CanonicalizationError("DUPLICATE_KEY", f"duplicate JSON member {normalized_key!r}")
        value[normalized_key] = nested
    return value


def parse_json_document(raw_json: str | bytes | bytearray) -> dict[str, object] | list[object]:
    """Parse strict JSON while preserving duplicate-key and number-token evidence."""

    if isinstance(raw_json, (bytes, bytearray)):
        try:
            text = bytes(raw_json).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CanonicalizationError("INVALID_UTF8", "JSON input is not valid UTF-8") from exc
    elif isinstance(raw_json, str):
        text = raw_json
    else:
        raise TypeError("raw_json must be str or bytes")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_closed_object,
            parse_int=_parse_integer,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except CanonicalizationError:
        raise
    except json.JSONDecodeError as exc:
        raise CanonicalizationError("INVALID_JSON", exc.msg) from exc
    if not isinstance(value, (dict, list)):
        raise CanonicalizationError(
            "TOP_LEVEL_SCALAR",
            "canonical documents must be an object or array",
        )
    return value


def canonicalize_json(raw_json: str | bytes | bytearray) -> bytes:
    """Strictly parse raw JSON and return canonical UTF-8 bytes."""

    return canonical_bytes(parse_json_document(raw_json))


def digest_value(value: object) -> DigestV4:
    """Return the sole canonical digest for a formal JSON value."""

    return DigestV4.from_value(value)


def semantic_projection(value: Any) -> Any:
    """Convert legacy containers to JSON values without dropping identity fields."""

    if isinstance(value, Mapping):
        projected: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError("OBJECT_KEY_TYPE", "JSON object keys must be strings")
            projected[key] = semantic_projection(nested)
        return projected
    if isinstance(value, (set, frozenset)):
        items = [semantic_projection(item) for item in value]
        return sorted(items, key=_canonical_sort_key)
    if isinstance(value, (list, tuple)):
        return [semantic_projection(item) for item in value]
    return deepcopy(value)


def semantic_digest(value: Any) -> DigestV4:
    """Hash an explicitly constructed semantic projection with DigestV4."""

    return digest_value(semantic_projection(value))


def content_id(prefix: str, value: Any, *, length: int = 16) -> str:
    """Build a stable public identifier from canonical semantic bytes."""

    if not prefix or length < 8 or length > 64:
        raise ValueError("prefix is required and length must be between 8 and 64")
    return f"{prefix}::{semantic_digest(value).hex[:length]}"


def _canonical_sort_key(value: Any) -> bytes:
    return _canonical_text(value, set()).encode("utf-8")


def _make_aaf_canonical(
    claims: list[dict[str, Any]], attacks: list[tuple[str, str]]
) -> dict[str, Any]:
    sorted_claims = sorted((deepcopy(claim) for claim in claims), key=lambda claim: claim.get("id", ""))
    sorted_attacks = sorted(attacks, key=lambda attack: (attack[0], attack[1]))
    return {"claims": sorted_claims, "attacks": [list(attack) for attack in sorted_attacks]}


def serialize_aaf(claims: list[dict[str, Any]], attacks: list[tuple[str, str]]) -> str:
    return canonical_text(_make_aaf_canonical(claims, attacks))


def deserialize_aaf(json_str: str) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    data = parse_json_document(json_str)
    if not isinstance(data, dict):
        raise CanonicalizationError("AAF_SCHEMA", "AAF document must be an object")
    claims = data.get("claims", [])
    attacks = data.get("attacks", [])
    if not isinstance(claims, list) or not isinstance(attacks, list):
        raise CanonicalizationError("AAF_SCHEMA", "claims and attacks must be arrays")
    return claims, [tuple(attack) for attack in attacks]


def _make_horn_canonical(rules: list[dict[str, Any]], facts: set[str]) -> dict[str, Any]:
    copied_rules = [deepcopy(rule) for rule in rules]
    sorted_rules = sorted(
        copied_rules,
        key=lambda rule: (rule.get("head", ""), tuple(sorted(rule.get("body", [])))),
    )
    for rule in sorted_rules:
        if "body" in rule:
            rule["body"] = sorted(rule["body"])
    return {"rules": sorted_rules, "facts": sorted(facts)}


def serialize_horn(rules: list[dict[str, Any]], facts: set[str]) -> str:
    return canonical_text(_make_horn_canonical(rules, facts))


def deserialize_horn(json_str: str) -> tuple[list[dict[str, Any]], set[str]]:
    data = parse_json_document(json_str)
    if not isinstance(data, dict):
        raise CanonicalizationError("HORN_SCHEMA", "Horn document must be an object")
    rules = data.get("rules", [])
    facts = data.get("facts", [])
    if not isinstance(rules, list) or not isinstance(facts, list):
        raise CanonicalizationError("HORN_SCHEMA", "rules and facts must be arrays")
    return rules, set(facts)


__all__ = [
    "CanonicalizationError",
    "DigestV4",
    "SAFE_INTEGER_MIN",
    "SAFE_INTEGER_MAX",
    "canonical_bytes",
    "canonical_text",
    "canonicalize_json",
    "content_id",
    "deserialize_aaf",
    "deserialize_horn",
    "digest_value",
    "parse_json_document",
    "semantic_digest",
    "semantic_projection",
    "serialize_aaf",
    "serialize_horn",
]
