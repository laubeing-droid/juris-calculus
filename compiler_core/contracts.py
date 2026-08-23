"""Sole Python authority for the frozen JC V4 public contracts.

W1-02 freezes the field names and field types in this module as the Python
contract authority. Every wire object is closed, immutable, canonicalizable,
and represented by an explicit ``frozen=True, slots=True`` dataclass. Wire
arrays are JSON lists and are copied to tuples at the admission boundary.
"""

from __future__ import annotations

import calendar
from dataclasses import MISSING, dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from functools import total_ordering
from math import gcd
import re
import time
from types import MappingProxyType
from typing import Union, get_args, get_origin, get_type_hints

from compiler_core.canonical_serialization import (
    SAFE_INTEGER_MAX,
    SAFE_INTEGER_MIN,
    CanonicalizationError,
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)


SCHEMA_VERSION_V4 = "jc/4.0"
_ENGINE_VERSION_RE = re.compile(
    r"4\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:(?:a|b|rc)(?:0|[1-9][0-9]*))?\Z"
)
_TIME_SYNTAX_RE = re.compile(
    r"(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
    r"T(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{1,9}))?Z\Z"
)
_CURRENCY_RE = re.compile(r"[A-Z]{3}\Z")
_ABSOLUTE_OR_DEVICE_PATH_RE = re.compile(r"(?:[A-Za-z]:|[\\/]{2}|[\\/])")
_UNION_TYPE = type(str | None)
_ATTACK_TYPES_V4 = frozenset({
    "rebut", "undercut", "exception", "premise_challenge", "priority_defeat",
})
_ATTACK_TARGET_ASPECTS_V4 = frozenset({"claim", "premise", "rule_applicability"})


class ContractV4Error(ValueError):
    """Stable fail-closed error raised by all V4 contract admission paths."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise ContractV4Error(code, detail)


def _nonempty(value: str, path: str) -> None:
    if not value:
        _fail("EMPTY_STRING", f"{path} must not be empty")


def _safe_integer(value: object, path: str) -> int:
    if isinstance(value, float):
        _fail("FLOAT_FORBIDDEN", f"{path} must be an integer")
    if type(value) is not int:
        _fail("TYPE_MISMATCH", f"{path} must be an integer")
    if not SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX:
        _fail("UNSAFE_INTEGER", f"{path} is outside the safe-integer range")
    return value


def validate_safe_integer_v4(value: object) -> int:
    """Return a strict ECMAScript-safe integer; reject booleans and every float."""

    return _safe_integer(value, "value")


def _closed_payload(payload: object, names: tuple[str, ...], scope: str) -> dict[str, object]:
    if type(payload) is not dict:
        _fail("TYPE_MISMATCH", f"{scope} must be an object")
    for key in payload:
        if type(key) is not str:
            _fail("OBJECT_KEY_TYPE", f"{scope} keys must be strings")
    unknown = set(payload) - set(names)
    if unknown:
        _fail("UNKNOWN_FIELD", f"{scope} has unknown field {sorted(unknown)[0]!r}")
    missing = set(names) - set(payload)
    if missing:
        _fail("MISSING_FIELD", f"{scope} is missing field {sorted(missing)[0]!r}")
    return payload


def validate_money_v4(payload: object) -> tuple[str, int]:
    """Validate the frozen ``{currency, minor_units}`` money representation."""

    value = _closed_payload(payload, ("currency", "minor_units"), "money")
    currency = value["currency"]
    if type(currency) is not str or _CURRENCY_RE.fullmatch(currency) is None:
        _fail("CURRENCY_CODE", "currency must match ^[A-Z]{3}$")
    return currency, _safe_integer(value["minor_units"], "money.minor_units")


def validate_rational_v4(payload: object) -> tuple[int, int]:
    """Validate a reduced rational with positive denominator and canonical zero."""

    value = _closed_payload(payload, ("numerator", "denominator"), "rational")
    numerator = _safe_integer(value["numerator"], "rational.numerator")
    denominator = _safe_integer(value["denominator"], "rational.denominator")
    if denominator <= 0:
        _fail("DENOMINATOR_NONPOSITIVE", "denominator must be positive")
    if (numerator == 0 and denominator != 1) or gcd(abs(numerator), denominator) != 1:
        _fail("NON_CANONICAL_RATIONAL", "rational must be reduced and zero must be 0/1")
    return numerator, denominator


_LIMIT_DEFAULTS = {
    "max_request_bytes": 262_144,
    "max_json_depth": 16,
    "max_json_nodes": 10_000,
    "max_object_members_per_object": 64,
    "max_total_object_members": 4_096,
    "max_array_items_per_array": 512,
    "max_total_array_items": 4_096,
    "max_string_utf8_bytes": 8_192,
    "max_total_string_utf8_bytes": 196_608,
    "max_total_reference_values": 1_536,
    "max_fact_attestation_refs": 512,
    "max_proposal_refs": 512,
    "admission_deadline_ms": 250,
    "artifact_page_bytes": 65_536,
    "solver_deadline_ms": 2_500,
    "worker_queue_items": None,
    "in_flight_runs": None,
    "state_quota_bytes": None,
    "retention_seconds": None,
}
_LIMIT_HARD_MAXIMA = {
    "max_request_bytes": 1_048_576,
    "max_json_depth": 32,
    "max_json_nodes": 50_000,
    "max_object_members_per_object": 128,
    "max_total_object_members": 20_000,
    "max_array_items_per_array": 1_024,
    "max_total_array_items": 20_000,
    "max_string_utf8_bytes": 65_536,
    "max_total_string_utf8_bytes": 786_432,
    "max_total_reference_values": 2_048,
    "max_fact_attestation_refs": 512,
    "max_proposal_refs": 512,
    "admission_deadline_ms": 1_000,
    "artifact_page_bytes": 262_144,
    "solver_deadline_ms": 10_000,
    "worker_queue_items": None,
    "in_flight_runs": None,
    "state_quota_bytes": None,
    "retention_seconds": None,
}
_LIMIT_ERROR_CODES = {
    "max_request_bytes": "REQUEST_TOO_LARGE",
    "max_json_depth": "JSON_DEPTH_LIMIT",
    "max_json_nodes": "JSON_NODE_LIMIT",
    "max_object_members_per_object": "OBJECT_MEMBER_LIMIT",
    "max_total_object_members": "TOTAL_OBJECT_MEMBER_LIMIT",
    "max_array_items_per_array": "ARRAY_ITEM_LIMIT",
    "max_total_array_items": "TOTAL_ARRAY_ITEM_LIMIT",
    "max_string_utf8_bytes": "STRING_BYTE_LIMIT",
    "max_total_string_utf8_bytes": "TOTAL_STRING_BYTE_LIMIT",
    "max_total_reference_values": "REFERENCE_LIMIT",
    "max_fact_attestation_refs": "FACT_REFERENCE_LIMIT",
    "max_proposal_refs": "PROPOSAL_REFERENCE_LIMIT",
    "admission_deadline_ms": "ADMISSION_DEADLINE",
    "artifact_page_bytes": "ARTIFACT_PAGE_LIMIT",
    "solver_deadline_ms": "SOLVER_DEADLINE",
}
DEFAULT_RESOURCE_LIMITS_V4 = MappingProxyType(
    {name: _LIMIT_DEFAULTS[name] for name in _LIMIT_ERROR_CODES}
)
HARD_MAX_RESOURCE_LIMITS_V4 = MappingProxyType(
    {name: _LIMIT_HARD_MAXIMA[name] for name in _LIMIT_ERROR_CODES}
)
RESOURCE_LIMIT_ERROR_CODES_V4 = MappingProxyType(_LIMIT_ERROR_CODES.copy())
ENGINE_LIMITS_V4 = MappingProxyType(
    {name: (_LIMIT_DEFAULTS[name], _LIMIT_HARD_MAXIMA[name]) for name in _LIMIT_DEFAULTS}
)


def _reference_count(key: str | None, value: object) -> int:
    if key is None or value is None:
        return 0
    if key.endswith("_refs") and type(value) is list:
        return len(value)
    if key.endswith("_ref"):
        return 1
    return 0


def _walk_wire(
    root: object,
    *,
    limits: ResourceLimitsV4 | None = None,
    deadline_ns: int | None = None,
) -> None:
    """Iteratively reject non-I-JSON values, cycles, and configured overages."""

    nodes = members = array_items = string_bytes = references = 0
    active: set[int] = set()
    stack: list[tuple[object, int, str | None, bool]] = [(root, 1, None, False)]
    while stack:
        value, depth, parent_key, leaving = stack.pop()
        if leaving:
            active.remove(id(value))
            continue
        if deadline_ns is not None and time.monotonic_ns() > deadline_ns:
            _fail("ADMISSION_DEADLINE", "request admission deadline exceeded")
        nodes += 1
        references += _reference_count(parent_key, value)
        if limits is not None:
            if depth > limits.max_json_depth:
                _fail("JSON_DEPTH_LIMIT", "JSON nesting exceeds max_json_depth")
            if nodes > limits.max_json_nodes:
                _fail("JSON_NODE_LIMIT", "JSON node count exceeds max_json_nodes")
            if references > limits.max_total_reference_values:
                _fail("REFERENCE_LIMIT", "reference count exceeds max_total_reference_values")
        if value is None or type(value) is bool:
            continue
        if type(value) is int:
            _safe_integer(value, parent_key or "value")
            continue
        if isinstance(value, float):
            _fail("FLOAT_FORBIDDEN", f"{parent_key or 'value'} must not be a float")
        if type(value) is str:
            try:
                size = len(value.encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise ContractV4Error("INVALID_STRING", "string contains an unpaired surrogate") from exc
            if any(ord(character) < 0x20 for character in value):
                _fail("CONTROL_CHARACTER", f"{parent_key or 'value'} contains a control character")
            string_bytes += size
            if limits is not None:
                if size > limits.max_string_utf8_bytes:
                    _fail("STRING_BYTE_LIMIT", "string exceeds max_string_utf8_bytes")
                if string_bytes > limits.max_total_string_utf8_bytes:
                    _fail("TOTAL_STRING_BYTE_LIMIT", "strings exceed max_total_string_utf8_bytes")
            continue
        if type(value) not in (dict, list):
            _fail("NON_JSON_VALUE", f"unsupported wire value type {type(value).__name__}")
        identity = id(value)
        if identity in active:
            _fail("CYCLIC_VALUE", "wire value contains a cycle")
        active.add(identity)
        stack.append((value, depth, parent_key, True))
        if type(value) is dict:
            length = len(value)
            members += length
            if limits is not None:
                if length > limits.max_object_members_per_object:
                    _fail("OBJECT_MEMBER_LIMIT", "object exceeds max_object_members_per_object")
                if members > limits.max_total_object_members:
                    _fail("TOTAL_OBJECT_MEMBER_LIMIT", "objects exceed max_total_object_members")
            for key, nested in reversed(tuple(value.items())):
                if type(key) is not str:
                    _fail("OBJECT_KEY_TYPE", "wire object keys must be strings")
                try:
                    key_size = len(key.encode("utf-8"))
                except UnicodeEncodeError as exc:
                    raise ContractV4Error("INVALID_STRING", "object key has an unpaired surrogate") from exc
                if any(ord(character) < 0x20 for character in key):
                    _fail("CONTROL_CHARACTER", "object key contains a control character")
                string_bytes += key_size
                if limits is not None:
                    if key_size > limits.max_string_utf8_bytes:
                        _fail("STRING_BYTE_LIMIT", "object key exceeds max_string_utf8_bytes")
                    if string_bytes > limits.max_total_string_utf8_bytes:
                        _fail("TOTAL_STRING_BYTE_LIMIT", "strings exceed max_total_string_utf8_bytes")
                stack.append((nested, depth + 1, key, False))
        else:
            length = len(value)
            array_items += length
            if limits is not None:
                if length > limits.max_array_items_per_array:
                    _fail("ARRAY_ITEM_LIMIT", "array exceeds max_array_items_per_array")
                if array_items > limits.max_total_array_items:
                    _fail("TOTAL_ARRAY_ITEM_LIMIT", "arrays exceed max_total_array_items")
            for nested in reversed(value):
                stack.append((nested, depth + 1, parent_key, False))


_TYPE_HINT_CACHE: dict[type[object], dict[str, object]] = {}


def _hints(contract_type: type[object]) -> dict[str, object]:
    hints = _TYPE_HINT_CACHE.get(contract_type)
    if hints is None:
        hints = get_type_hints(contract_type)
        _TYPE_HINT_CACHE[contract_type] = hints
    return hints


def _decode_wire(annotation: object, value: object, path: str) -> object:
    origin = get_origin(annotation)
    if origin in (Union, _UNION_TYPE):
        choices = get_args(annotation)
        if value is None and type(None) in choices:
            return None
        non_null = tuple(choice for choice in choices if choice is not type(None))
        if len(non_null) != 1:
            _fail("TYPE_AUTHORITY", f"{path} has an unsupported union")
        return _decode_wire(non_null[0], value, path)
    if origin is tuple:
        if type(value) is not list:
            _fail("ARRAY_REQUIRED", f"{path} must be a JSON array")
        args = get_args(annotation)
        if len(args) != 2 or args[1] is not Ellipsis:
            _fail("TYPE_AUTHORITY", f"{path} must use a variadic tuple annotation")
        return tuple(_decode_wire(args[0], item, f"{path}[{index}]") for index, item in enumerate(value))
    if annotation is DigestV4:
        try:
            return DigestV4.parse(value)
        except CanonicalizationError as exc:
            raise ContractV4Error(exc.code, f"{path}: {exc.detail}") from exc
    if isinstance(annotation, type) and issubclass(annotation, _V4StringEnum):
        return annotation.parse(value)
    if isinstance(annotation, type) and issubclass(annotation, V4Contract):
        if type(value) is not dict:
            _fail("TYPE_MISMATCH", f"{path} must be an object")
        return annotation.from_dict(value)
    if annotation is str:
        if type(value) is not str:
            _fail("TYPE_MISMATCH", f"{path} must be a string")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ContractV4Error("INVALID_STRING", f"{path} has an unpaired surrogate") from exc
        return value
    if annotation is bool:
        if type(value) is not bool:
            _fail("TYPE_MISMATCH", f"{path} must be a boolean")
        return value
    if annotation is int:
        return _safe_integer(value, path)
    _fail("TYPE_AUTHORITY", f"{path} uses unsupported annotation {annotation!r}")


def _freeze_internal(annotation: object, value: object, path: str) -> object:
    origin = get_origin(annotation)
    if origin in (Union, _UNION_TYPE):
        choices = get_args(annotation)
        if value is None and type(None) in choices:
            return None
        non_null = tuple(choice for choice in choices if choice is not type(None))
        if len(non_null) != 1:
            _fail("TYPE_AUTHORITY", f"{path} has an unsupported union")
        return _freeze_internal(non_null[0], value, path)
    if origin is tuple:
        if type(value) is not tuple:
            _fail("ARRAY_TYPE", f"{path} constructor value must be a tuple")
        args = get_args(annotation)
        if len(args) != 2 or args[1] is not Ellipsis:
            _fail("TYPE_AUTHORITY", f"{path} must use a variadic tuple annotation")
        return tuple(_freeze_internal(args[0], item, f"{path}[{index}]") for index, item in enumerate(value))
    if annotation is DigestV4:
        if type(value) is not DigestV4:
            _fail("TYPE_MISMATCH", f"{path} constructor value must be DigestV4")
        return value
    if isinstance(annotation, type) and issubclass(annotation, _V4StringEnum):
        if type(value) is not annotation:
            _fail("TYPE_MISMATCH", f"{path} constructor value must be {annotation.__name__}")
        return value
    if isinstance(annotation, type) and issubclass(annotation, V4Contract):
        if type(value) is not annotation:
            _fail("TYPE_MISMATCH", f"{path} constructor value must be {annotation.__name__}")
        return value
    if annotation is str:
        if type(value) is not str:
            _fail("TYPE_MISMATCH", f"{path} constructor value must be str")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ContractV4Error("INVALID_STRING", f"{path} has an unpaired surrogate") from exc
        return value
    if annotation is bool:
        if type(value) is not bool:
            _fail("TYPE_MISMATCH", f"{path} constructor value must be bool")
        return value
    if annotation is int:
        return _safe_integer(value, path)
    _fail("TYPE_AUTHORITY", f"{path} uses unsupported annotation {annotation!r}")


def _to_wire(value: object) -> object:
    if isinstance(value, V4Contract):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if type(value) is DigestV4:
        return str(value)
    if type(value) is tuple:
        return [_to_wire(item) for item in value]
    if value is None or type(value) in (str, bool, int):
        return value
    _fail("NON_JSON_VALUE", f"contract contains unsupported value {type(value).__name__}")


class _V4StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, value: object) -> _V4StringEnum:
        if type(value) is not str:
            _fail("TYPE_MISMATCH", f"{cls.__name__} must be a string")
        try:
            return cls(value)
        except ValueError as exc:
            raise ContractV4Error("ENUM_VALUE", f"invalid {cls.__name__} value {value!r}") from exc


_SELF_DIGEST_FIELDS_V4 = MappingProxyType({
    "TrustPolicyV4": "policy_digest",
    "StorageCapabilityV4": "capability_digest",
    "SourceBundleV4": "bundle_digest",
    "EvidenceManifestV4": "manifest_digest",
    "RuleV4": "rule_digest",
    "PackManifestV4": "manifest_digest",
    "LegalSpecV4": "spec_digest",
    "LegalIVLV4": "ivl_digest",
    "BranchResultV4": "branch_digest",
    "SemanticResultV4": "result_digest",
    "RunIdentityV4": "run_digest",
    "FormalCertificateV4": "certificate_digest",
    "ConflictCertificateV4": "certificate_digest",
    "AuditManifestV4": "manifest_digest",
    "AuditBundleIndexV4": "bundle_digest",
})
_SIGNED_BODY_FIELDS_V4 = MappingProxyType({
    "ArtifactHandleV4": "signature",
    "PackSignatureV4": "signature",
    "FactAttestationV4": "signature",
    "FactAdmissionReceiptV4": "signature",
    "RulePromotionReceiptV4": "signature",
    "TranslationReceiptV4": "signature",
    "SolverReceiptV4": "signature",
    "CheckerReceiptV4": "signature",
    "ProofReceiptV4": "signature",
})
_SIGNED_SUBJECT_FIELDS_V4 = MappingProxyType({
    "ArtifactHandleV4": "content_ref",
    "PackSignatureV4": "manifest_ref",
    "FactAttestationV4": "candidate_ref",
    "FactAdmissionReceiptV4": "subject_digest",
    "RulePromotionReceiptV4": "rule_subject_digest",
    "TranslationReceiptV4": "target_ref",
    "SolverReceiptV4": "backend_result_ref",
    "CheckerReceiptV4": "subject_ref",
    "ProofReceiptV4": "subject_ref",
})


class V4Contract:
    """Strict codec shared by all 68 closed V4 object contracts."""

    __slots__ = ()

    def __post_init__(self) -> None:
        hints = _hints(type(self))
        for item in fields(self):
            frozen = _freeze_internal(
                hints[item.name],
                getattr(self, item.name),
                f"{type(self).__name__}.{item.name}",
            )
            object.__setattr__(self, item.name, frozen)
        self._validate()
        self._validate_signature_binding()
        self._validate_self_digest()

    def _validate(self) -> None:
        return None

    def _self_digest_field(self) -> str | None:
        return _SELF_DIGEST_FIELDS_V4.get(type(self).__name__)

    def signature_body(self) -> dict[str, object]:
        """Return the immutable body authenticated by an attached signature."""

        value = self.to_dict()
        signature_field = _SIGNED_BODY_FIELDS_V4.get(type(self).__name__)
        if signature_field is None:
            _fail("UNSIGNED_CONTRACT", f"{type(self).__name__} has no attached signature")
        del value[signature_field]
        return value

    def _validate_signature_binding(self) -> None:
        signature_field = _SIGNED_BODY_FIELDS_V4.get(type(self).__name__)
        if signature_field is None:
            return
        signature = getattr(self, signature_field)
        expected_payload = digest_value(self.signature_body())
        subject = getattr(self, _SIGNED_SUBJECT_FIELDS_V4[type(self).__name__])
        expected_subject = subject.digest if type(subject) is ContentRefV4 else subject
        if signature.payload_digest != expected_payload or signature.subject_digest != expected_subject:
            _fail(
                "SIGNATURE_SUBJECT_MISMATCH",
                f"{type(self).__name__} signature does not bind its canonical body",
            )

    def digest_body(self) -> dict[str, object]:
        """Return the canonical identity projection without a recursive self digest."""

        value = self.to_dict()
        digest_field = self._self_digest_field()
        if digest_field is not None:
            del value[digest_field]
        return value

    def _validate_self_digest(self) -> None:
        digest_field = self._self_digest_field()
        if digest_field is None:
            return
        expected = digest_value(self.digest_body())
        if getattr(self, digest_field) != expected:
            _fail(
                "SELF_DIGEST_MISMATCH",
                f"{type(self).__name__}.{digest_field} does not match its canonical body",
            )

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> V4Contract:
        if type(payload) is not dict:
            _fail("TYPE_MISMATCH", f"{cls.__name__} must be an object")
        _walk_wire(payload)
        contract_fields = {item.name: item for item in fields(cls)}
        unknown = set(payload) - set(contract_fields)
        if unknown:
            _fail("UNKNOWN_FIELD", f"{cls.__name__} has unknown field {sorted(unknown)[0]!r}")
        missing = [
            name
            for name, item in contract_fields.items()
            if name not in payload and item.default is MISSING and item.default_factory is MISSING
        ]
        if missing:
            _fail("MISSING_FIELD", f"{cls.__name__} is missing field {missing[0]!r}")
        hints = _hints(cls)
        values = {
            name: _decode_wire(hints[name], payload[name], f"{cls.__name__}.{name}")
            for name in contract_fields
            if name in payload
        }
        return cls(**values)

    def to_dict(self) -> dict[str, object]:
        value = {item.name: _to_wire(getattr(self, item.name)) for item in fields(self)}
        _walk_wire(value)
        return value

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

    def canonical_digest(self) -> DigestV4:
        digest_field = self._self_digest_field()
        if digest_field is not None:
            return getattr(self, digest_field)
        return digest_value(self.to_dict())


@total_ordering
@dataclass(frozen=True, slots=True)
class CanonicalTimeV4(V4Contract):
    wire: str

    def _match(self) -> re.Match[str]:
        match = _TIME_SYNTAX_RE.fullmatch(self.wire)
        if match is None:
            _fail("INVALID_CANONICAL_TIME", "time must be RFC3339 UTC Z with 0-9 fractional digits")
        fraction = match["fraction"]
        if fraction is not None and fraction.endswith("0"):
            _fail("NON_CANONICAL_TIME", "fractional seconds must not have a trailing zero")
        try:
            datetime(
                int(match["year"]),
                int(match["month"]),
                int(match["day"]),
                int(match["hour"]),
                int(match["minute"]),
                int(match["second"]),
                tzinfo=timezone.utc,
            )
        except ValueError as exc:
            raise ContractV4Error("INVALID_CALENDAR_TIME", "time is not a real calendar instant") from exc
        return match

    def _validate(self) -> None:
        self._match()

    @classmethod
    def parse(cls, value: object) -> CanonicalTimeV4:
        if type(value) is not str:
            _fail("TYPE_MISMATCH", "CanonicalTimeV4 must be a string")
        return cls(value)

    @property
    def epoch_seconds(self) -> int:
        match = self._match()
        return calendar.timegm(
            (
                int(match["year"]), int(match["month"]), int(match["day"]),
                int(match["hour"]), int(match["minute"]), int(match["second"]),
            )
        )

    @property
    def nanosecond(self) -> int:
        fraction = self._match()["fraction"] or ""
        return int(fraction.ljust(9, "0")) if fraction else 0

    @property
    def instant(self) -> tuple[int, int]:
        return self.epoch_seconds, self.nanosecond

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, CanonicalTimeV4):
            return NotImplemented
        return self.instant < other.instant

    @staticmethod
    def contains_half_open(
        start: CanonicalTimeV4,
        end: CanonicalTimeV4,
        value: CanonicalTimeV4,
    ) -> bool:
        if not all(type(item) is CanonicalTimeV4 for item in (start, end, value)):
            _fail("TYPE_MISMATCH", "half-open interval requires CanonicalTimeV4 values")
        if not start < end:
            _fail("TIME_INTERVAL", "half-open interval start must precede end")
        return start <= value < end

    def in_half_open(self, start: CanonicalTimeV4, end: CanonicalTimeV4) -> bool:
        return self.contains_half_open(start, end, self)


@dataclass(frozen=True, slots=True)
class ContentRefV4(V4Contract):
    kind: str
    digest: DigestV4

    def _validate(self) -> None:
        _nonempty(self.kind, "ContentRefV4.kind")


@dataclass(frozen=True, slots=True)
class ArtifactHandleV4(V4Contract):
    artifact_id: str
    kind: str
    content_ref: ContentRefV4
    run_identity_ref: ContentRefV4
    scope: str
    media_type: str
    size_bytes: int
    expires_at: CanonicalTimeV4
    max_bytes: int
    signature: SignatureEnvelopeV4

    def _validate(self) -> None:
        for field_name in ("artifact_id", "kind", "scope", "media_type"):
            _nonempty(getattr(self, field_name), f"ArtifactHandleV4.{field_name}")
        if self.size_bytes < 0 or self.max_bytes < 0 or self.max_bytes > self.size_bytes:
            _fail("ARTIFACT_BOUNDS", "artifact size and capability byte bound are inconsistent")


@dataclass(frozen=True, slots=True)
class ErrorV4(V4Contract):
    code: str
    message: str
    stage: str
    retryable: bool
    correlation_id: str
    field_path: tuple[str, ...]

    def _validate(self) -> None:
        for field_name in ("code", "message", "stage", "correlation_id"):
            _nonempty(getattr(self, field_name), f"ErrorV4.{field_name}")
        if any(
            not segment
            or segment in {".", ".."}
            or any(marker in segment for marker in ("/", "\\", ":"))
            for segment in self.field_path
        ):
            _fail("ERROR_FIELD_PATH", "field_path must contain only relative field segments")


@dataclass(frozen=True, slots=True)
class SignatureEnvelopeV4(V4Contract):
    algorithm: str
    key_id: str
    issuer: str
    role: str
    scope: str
    kind: str
    schema_version: str
    subject_digest: DigestV4
    run_identity_ref: ContentRefV4 | None
    status: str
    issued_at: CanonicalTimeV4
    expires_at: CanonicalTimeV4 | None
    nonce: str
    evidence_refs: tuple[ContentRefV4, ...]
    payload_digest: DigestV4
    policy_digest: DigestV4
    revocation_ref: ContentRefV4 | None
    signature: str

    def _validate(self) -> None:
        for field_name in (
            "algorithm", "key_id", "issuer", "role", "scope", "kind", "status",
            "nonce", "signature",
        ):
            _nonempty(getattr(self, field_name), f"SignatureEnvelopeV4.{field_name}")
        if self.schema_version != SCHEMA_VERSION_V4:
            _fail("SCHEMA_VERSION", f"schema_version must be exactly {SCHEMA_VERSION_V4}")
        if self.expires_at is not None and not self.issued_at < self.expires_at:
            _fail("SIGNATURE_TIME_ORDER", "expires_at must follow issued_at")


@dataclass(frozen=True, slots=True)
class TrustPolicyV4(V4Contract):
    policy_id: str
    allowed_algorithms: tuple[str, ...]
    trusted_key_ids: tuple[str, ...]
    revoked_key_ids: tuple[str, ...]
    allowed_issuers: tuple[str, ...]
    allowed_roles: tuple[str, ...]
    allowed_scopes: tuple[str, ...]
    allowed_artifact_kinds: tuple[str, ...]
    valid_from: CanonicalTimeV4
    valid_to: CanonicalTimeV4 | None
    authorization_policy_ref: ContentRefV4
    revocation_policy_ref: ContentRefV4
    replay_policy_ref: ContentRefV4
    separation_of_duties_ref: ContentRefV4
    policy_digest: DigestV4

    def _validate(self) -> None:
        _nonempty(self.policy_id, "TrustPolicyV4.policy_id")
        for field_name in (
            "allowed_algorithms", "trusted_key_ids", "allowed_issuers", "allowed_roles",
            "allowed_scopes", "allowed_artifact_kinds",
        ):
            if not getattr(self, field_name):
                _fail("TRUST_POLICY_EMPTY", f"TrustPolicyV4.{field_name} must not be empty")
        if set(self.trusted_key_ids) & set(self.revoked_key_ids):
            _fail("TRUST_KEY_STATE", "a trusted key cannot also be revoked")
        if self.valid_to is not None and not self.valid_from < self.valid_to:
            _fail("TRUST_TIME_ORDER", "valid_to must follow valid_from")


@dataclass(frozen=True, slots=True)
class StorageCapabilityV4(V4Contract):
    provider_id: str
    namespace: str
    content_addressed: bool
    atomic_write: bool
    no_follow: bool
    max_artifact_bytes: int
    durability_ref: ContentRefV4
    access_policy_ref: ContentRefV4
    encryption_ref: ContentRefV4
    quota_policy_ref: ContentRefV4
    retention_policy_ref: ContentRefV4
    attestation_refs: tuple[ContentRefV4, ...]
    policy_digest: DigestV4
    capability_digest: DigestV4

    def _validate(self) -> None:
        _nonempty(self.provider_id, "StorageCapabilityV4.provider_id")
        _nonempty(self.namespace, "StorageCapabilityV4.namespace")
        if self.max_artifact_bytes <= 0:
            _fail("STORAGE_CAPABILITY", "max_artifact_bytes must be positive")
        if not self.attestation_refs:
            _fail("STORAGE_ATTESTATION_REQUIRED", "storage capability requires attestation refs")


@dataclass(frozen=True, slots=True)
class ObservabilityEnvelopeV4(V4Contract):
    run_identity_ref: ContentRefV4
    started_at: CanonicalTimeV4
    finished_at: CanonicalTimeV4 | None
    host_id: str
    process_id: int
    elapsed_ms: int
    event_refs: tuple[ContentRefV4, ...]

    def _validate(self) -> None:
        _nonempty(self.host_id, "ObservabilityEnvelopeV4.host_id")
        if self.process_id < 0 or self.elapsed_ms < 0:
            _fail("OBSERVABILITY_RANGE", "process_id and elapsed_ms must be non-negative")
        if self.finished_at is not None and self.finished_at < self.started_at:
            _fail("RUN_TIME_ORDER", "finished_at must not precede started_at")


@dataclass(frozen=True, slots=True)
class LegalContextV4(V4Contract):
    jurisdiction: str
    governing_law: str

    def _validate(self) -> None:
        _nonempty(self.jurisdiction, "LegalContextV4.jurisdiction")
        _nonempty(self.governing_law, "LegalContextV4.governing_law")


@dataclass(frozen=True, slots=True)
class RequestedOutputV4(V4Contract):
    kind: str
    format: str
    locale: str

    def _validate(self) -> None:
        _nonempty(self.kind, "RequestedOutputV4.kind")
        _nonempty(self.format, "RequestedOutputV4.format")
        _nonempty(self.locale, "RequestedOutputV4.locale")


@dataclass(frozen=True, slots=True)
class ResourceLimitsV4(V4Contract):
    max_request_bytes: int = 262_144
    max_json_depth: int = 16
    max_json_nodes: int = 10_000
    max_object_members_per_object: int = 64
    max_total_object_members: int = 4_096
    max_array_items_per_array: int = 512
    max_total_array_items: int = 4_096
    max_string_utf8_bytes: int = 8_192
    max_total_string_utf8_bytes: int = 196_608
    max_total_reference_values: int = 1_536
    max_fact_attestation_refs: int = 512
    max_proposal_refs: int = 512
    admission_deadline_ms: int = 250
    artifact_page_bytes: int = 65_536
    solver_deadline_ms: int = 2_500
    worker_queue_items: int | None = None
    in_flight_runs: int | None = None
    state_quota_bytes: int | None = None
    retention_seconds: int | None = None

    def _validate(self) -> None:
        validate_resource_limits_v4(self)


def validate_resource_limits_v4(limits: ResourceLimitsV4) -> None:
    if type(limits) is not ResourceLimitsV4:
        _fail("TYPE_MISMATCH", "limits must be ResourceLimitsV4")
    for name, hard_max in _LIMIT_HARD_MAXIMA.items():
        value = getattr(limits, name)
        if hard_max is None:
            if value is not None:
                _fail("DEFERRED_LIMIT", f"{name} must remain None until its closure task")
            continue
        if value <= 0:
            _fail("RESOURCE_LIMIT_VALUE", f"{name} must be positive")
        if value > hard_max:
            _fail(_LIMIT_ERROR_CODES[name], f"{name} exceeds its hard maximum {hard_max}")


def _check_deadline(deadline_ns: int) -> None:
    if time.monotonic_ns() > deadline_ns:
        _fail("ADMISSION_DEADLINE", "request admission deadline exceeded")


def _prescan_json_depth(text: str, max_depth: int, deadline_ns: int) -> None:
    depth = 0
    in_string = escaped = False
    for index, character in enumerate(text):
        if index & 1023 == 0:
            _check_deadline(deadline_ns)
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > max_depth:
                _fail("JSON_DEPTH_LIMIT", "JSON nesting exceeds max_json_depth")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                return


@dataclass(frozen=True, slots=True)
class CaseRequestV4(V4Contract):
    request_id: str
    schema_version: str
    legal_context: LegalContextV4
    decision_time: CanonicalTimeV4
    source_bundle_ref: ContentRefV4
    evidence_manifest_ref: ContentRefV4
    fact_attestation_refs: tuple[ContentRefV4, ...]
    rule_pack_ref: ContentRefV4
    requested_outputs: tuple[RequestedOutputV4, ...]
    proposal_refs: tuple[ContentRefV4, ...]

    def _validate(self) -> None:
        _nonempty(self.request_id, "CaseRequestV4.request_id")
        if self.schema_version != SCHEMA_VERSION_V4:
            _fail("SCHEMA_VERSION", f"schema_version must be exactly {SCHEMA_VERSION_V4}")
        if len(self.fact_attestation_refs) > 512:
            _fail("FACT_REFERENCE_LIMIT", "fact_attestation_refs exceeds 512")
        if len(self.proposal_refs) > 512:
            _fail("PROPOSAL_REFERENCE_LIMIT", "proposal_refs exceeds 512")
        for field_name, references in (
            ("fact_attestation_refs", self.fact_attestation_refs),
            ("proposal_refs", self.proposal_refs),
        ):
            identities = tuple((item.kind, item.digest) for item in references)
            if len(identities) != len(set(identities)):
                _fail("DUPLICATE_REFERENCE", f"{field_name} contains a duplicate")
        if not self.requested_outputs:
            _fail("MISSING_FIELD", "requested_outputs must not be empty")
        output_kinds = tuple(item.kind for item in self.requested_outputs)
        if len(output_kinds) != len(set(output_kinds)):
            _fail("DUPLICATE_REQUESTED_OUTPUT", "requested_outputs contains a duplicate kind")

    @classmethod
    def from_json_bytes(
        cls,
        raw: bytes,
        *,
        limits: ResourceLimitsV4 | None = None,
        deadline_ns: int | None = None,
    ) -> CaseRequestV4:
        if type(raw) is not bytes:
            _fail("INPUT_TYPE", "CaseRequestV4.from_json_bytes requires bytes")
        admitted_limits = ResourceLimitsV4() if limits is None else limits
        validate_resource_limits_v4(admitted_limits)
        absolute_deadline = (
            time.monotonic_ns() + admitted_limits.admission_deadline_ms * 1_000_000
            if deadline_ns is None
            else _safe_integer(deadline_ns, "deadline_ns")
        )
        if len(raw) > admitted_limits.max_request_bytes:
            _fail("REQUEST_TOO_LARGE", "request exceeds max_request_bytes")
        _check_deadline(absolute_deadline)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractV4Error("INVALID_UTF8", "request is not valid UTF-8") from exc
        _check_deadline(absolute_deadline)
        _prescan_json_depth(text, admitted_limits.max_json_depth, absolute_deadline)
        try:
            document = parse_json_document(text)
        except CanonicalizationError as exc:
            raise ContractV4Error(exc.code, exc.detail) from exc
        _check_deadline(absolute_deadline)
        if type(document) is not dict:
            _fail("TYPE_MISMATCH", "CaseRequestV4 document must be an object")
        _walk_wire(document, limits=admitted_limits, deadline_ns=absolute_deadline)
        _check_deadline(absolute_deadline)
        result = cls.from_dict(document)
        if len(result.fact_attestation_refs) > admitted_limits.max_fact_attestation_refs:
            _fail("FACT_REFERENCE_LIMIT", "fact_attestation_refs exceeds configured limit")
        if len(result.proposal_refs) > admitted_limits.max_proposal_refs:
            _fail("PROPOSAL_REFERENCE_LIMIT", "proposal_refs exceeds configured limit")
        _check_deadline(absolute_deadline)
        return result


def require_engine_match(
    engine_version: str,
    schema_version: str = SCHEMA_VERSION_V4,
) -> str:
    """Require the exact V4 schema and a well-formed engine version with major 4."""

    if type(schema_version) is not str or schema_version != SCHEMA_VERSION_V4:
        _fail("SCHEMA_VERSION", f"schema_version must be exactly {SCHEMA_VERSION_V4}")
    if type(engine_version) is not str or _ENGINE_VERSION_RE.fullmatch(engine_version) is None:
        _fail(
            "ENGINE_VERSION_MISMATCH",
            "engine_version must be 4.x.y with an optional a/b/rc suffix",
        )
    return engine_version


@dataclass(frozen=True, slots=True)
class CanonicalLocatorV4(V4Contract):
    kind: str
    value: str
    page: int | None
    span_start: int | None
    span_end: int | None

    def _validate(self) -> None:
        _nonempty(self.kind, "CanonicalLocatorV4.kind")
        _nonempty(self.value, "CanonicalLocatorV4.value")
        candidate = self.value.lstrip()
        normalized = candidate.replace("\\", "/")
        if (
            candidate.casefold().startswith("file:")
            or _ABSOLUTE_OR_DEVICE_PATH_RE.match(candidate)
            or ".." in normalized.split("/")
        ):
            _fail("UNSAFE_LOCATOR", "wire locators cannot contain machine paths or traversal")
        if self.page is not None and self.page < 1:
            _fail("LOCATOR_RANGE", "page must be positive")
        if (self.span_start is None) != (self.span_end is None):
            _fail("LOCATOR_RANGE", "span_start and span_end must be supplied together")
        if self.span_start is not None and not (0 <= self.span_start < self.span_end):
            _fail("LOCATOR_RANGE", "locator span must be non-negative and half-open")


@dataclass(frozen=True, slots=True)
class SourceSnapshotV4(V4Contract):
    source_id: str
    jurisdiction: str
    authority_tier: str
    issuer: str
    title: str
    publication_time: CanonicalTimeV4
    effective_from: CanonicalTimeV4
    effective_to: CanonicalTimeV4 | None
    retrieved_at: CanonicalTimeV4
    canonical_locator: CanonicalLocatorV4
    raw_digest: DigestV4
    normalization_profile: str
    normalized_digest: DigestV4
    structure_map_ref: ContentRefV4
    authenticity_receipt_ref: ContentRefV4
    provenance_refs: tuple[ContentRefV4, ...]
    acquisition_method: str
    license_status: str
    distribution_status: str

    def _validate(self) -> None:
        for field_name in (
            "source_id", "jurisdiction", "authority_tier", "issuer", "title",
            "normalization_profile", "acquisition_method", "license_status",
            "distribution_status",
        ):
            _nonempty(getattr(self, field_name), f"SourceSnapshotV4.{field_name}")
        if self.effective_to is not None and not self.effective_from < self.effective_to:
            _fail("SOURCE_TIME_ORDER", "effective_to must follow effective_from")
        if not self.provenance_refs:
            _fail("SOURCE_PROVENANCE_REQUIRED", "source snapshot requires provenance")


@dataclass(frozen=True, slots=True)
class SourceVersionEdgeV4(V4Contract):
    source_ref: ContentRefV4
    target_ref: ContentRefV4
    relation: str
    locator: CanonicalLocatorV4
    retrieval_receipt_ref: ContentRefV4


@dataclass(frozen=True, slots=True)
class SourceBundleV4(V4Contract):
    bundle_id: str
    root_source_ref: ContentRefV4
    terminal_source_ref: ContentRefV4
    snapshots: tuple[SourceSnapshotV4, ...]
    version_edges: tuple[SourceVersionEdgeV4, ...]
    bundle_digest: DigestV4


@dataclass(frozen=True, slots=True)
class EvidenceItemV4(V4Contract):
    evidence_id: str
    document_ref: ContentRefV4
    locators: tuple[CanonicalLocatorV4, ...]
    custody_provenance: tuple[ContentRefV4, ...]
    redaction_state: str
    review_state: str


@dataclass(frozen=True, slots=True)
class ContradictionRefV4(V4Contract):
    left_ref: ContentRefV4
    right_ref: ContentRefV4
    kind: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class EvidenceManifestV4(V4Contract):
    manifest_id: str
    request_ref: ContentRefV4
    case_scope: str
    items: tuple[EvidenceItemV4, ...]
    fact_candidate_refs: tuple[ContentRefV4, ...]
    contradictions: tuple[ContradictionRefV4, ...]
    manifest_digest: DigestV4

    def _validate(self) -> None:
        _nonempty(self.manifest_id, "EvidenceManifestV4.manifest_id")
        _nonempty(self.case_scope, "EvidenceManifestV4.case_scope")


@dataclass(frozen=True, slots=True)
class FactCandidateV4(V4Contract):
    candidate_id: str
    proposition_ref: ContentRefV4
    value_kind: str
    value_ref: ContentRefV4
    evidence_refs: tuple[ContentRefV4, ...]
    producer_kind: str
    proposal_ref: ContentRefV4 | None

    def _validate(self) -> None:
        for field_name in ("candidate_id", "value_kind", "producer_kind"):
            _nonempty(getattr(self, field_name), f"FactCandidateV4.{field_name}")


@dataclass(frozen=True, slots=True)
class FactAttestationV4(V4Contract):
    attestation_id: str
    candidate_ref: ContentRefV4
    request_ref: ContentRefV4
    case_scope: str
    proposition_digest: DigestV4
    value_digest: DigestV4
    source_refs: tuple[ContentRefV4, ...]
    evidence_refs: tuple[ContentRefV4, ...]
    interpretation_version: str
    admission_basis: str
    issuer_role: str
    issued_at: CanonicalTimeV4
    expires_at: CanonicalTimeV4 | None
    dispute_state: str
    assumption_state: str
    nonce: str
    replay_policy_ref: ContentRefV4
    revocation_ref: ContentRefV4 | None
    signature: SignatureEnvelopeV4

    def _validate(self) -> None:
        for field_name in (
            "attestation_id", "case_scope", "interpretation_version", "admission_basis",
            "issuer_role", "dispute_state", "assumption_state", "nonce",
        ):
            _nonempty(getattr(self, field_name), f"FactAttestationV4.{field_name}")
        if not self.source_refs or not self.evidence_refs:
            _fail("FACT_EVIDENCE_REQUIRED", "fact attestation requires source and evidence refs")
        if self.expires_at is not None and not self.issued_at < self.expires_at:
            _fail("ATTESTATION_TIME_ORDER", "expires_at must follow issued_at")


@dataclass(frozen=True, slots=True)
class RuleV4(V4Contract):
    rule_id: str
    rule_digest: DigestV4
    jurisdiction: str
    governing_law: str
    authority_ref: ContentRefV4
    variable_declaration_refs: tuple[ContentRefV4, ...]
    premise_refs: tuple[ContentRefV4, ...]
    conclusion_ref: ContentRefV4
    modality: str
    permission_ref: ContentRefV4 | None
    exception_refs: tuple[ContentRefV4, ...]
    priority_refs: tuple[ContentRefV4, ...]
    attack_refs: tuple[ContentRefV4, ...]
    temporal_constraint_refs: tuple[ContentRefV4, ...]
    numeric_constraint_refs: tuple[ContentRefV4, ...]
    source_snapshot_ref: ContentRefV4
    source_locator: CanonicalLocatorV4
    source_structure_ref: ContentRefV4
    interpretation_choice_refs: tuple[ContentRefV4, ...]
    defined_term_refs: tuple[ContentRefV4, ...]
    promotion_receipt_refs: tuple[ContentRefV4, ...]
    effective_from: CanonicalTimeV4
    effective_to: CanonicalTimeV4 | None

    def _validate(self) -> None:
        for field_name in ("rule_id", "jurisdiction", "governing_law", "modality"):
            _nonempty(getattr(self, field_name), f"RuleV4.{field_name}")
        if self.effective_to is not None and not self.effective_from < self.effective_to:
            _fail("RULE_TIME_ORDER", "effective_to must follow effective_from")

    def promotion_subject_digest(self) -> DigestV4:
        """Digest the pre-promotion rule body without creating a receipt cycle."""

        body = self.to_dict()
        del body["rule_digest"]
        del body["promotion_receipt_refs"]
        return digest_value(body)


@dataclass(frozen=True, slots=True)
class PackManifestV4(V4Contract):
    pack_id: str
    pack_version: str
    engine_api: str
    rule_refs: tuple[ContentRefV4, ...]
    source_refs: tuple[ContentRefV4, ...]
    config_refs: tuple[ContentRefV4, ...]
    receipt_refs: tuple[ContentRefV4, ...]
    compiler_build_digest: DigestV4
    source_tree_digest: DigestV4
    schema_digest: DigestV4
    trust_policy_ref: ContentRefV4
    coverage_receipt_refs: tuple[ContentRefV4, ...]
    verification_receipt_refs: tuple[ContentRefV4, ...]
    manifest_digest: DigestV4

    def _validate(self) -> None:
        _nonempty(self.pack_id, "PackManifestV4.pack_id")
        _nonempty(self.pack_version, "PackManifestV4.pack_version")
        require_engine_match(self.engine_api)


@dataclass(frozen=True, slots=True)
class PackSignatureV4(V4Contract):
    manifest_ref: ContentRefV4
    signature: SignatureEnvelopeV4


@dataclass(frozen=True, slots=True)
class LegalSpecV4(V4Contract):
    spec_id: str
    rule_ref: ContentRefV4
    jurisdiction: str
    governing_law: str
    authority_ref: ContentRefV4
    variable_declaration_refs: tuple[ContentRefV4, ...]
    premise_refs: tuple[ContentRefV4, ...]
    conclusion_ref: ContentRefV4
    modality: str
    permission_ref: ContentRefV4 | None
    exception_refs: tuple[ContentRefV4, ...]
    priority_refs: tuple[ContentRefV4, ...]
    attack_refs: tuple[ContentRefV4, ...]
    temporal_constraint_refs: tuple[ContentRefV4, ...]
    numeric_constraint_refs: tuple[ContentRefV4, ...]
    source_snapshot_ref: ContentRefV4
    source_locator: CanonicalLocatorV4
    source_structure_ref: ContentRefV4
    interpretation_choice_refs: tuple[ContentRefV4, ...]
    defined_term_refs: tuple[ContentRefV4, ...]
    promotion_receipt_refs: tuple[ContentRefV4, ...]
    effective_from: CanonicalTimeV4
    effective_to: CanonicalTimeV4 | None
    spec_digest: DigestV4

    def _validate(self) -> None:
        for field_name in ("spec_id", "jurisdiction", "governing_law", "modality"):
            _nonempty(getattr(self, field_name), f"LegalSpecV4.{field_name}")
        if self.effective_to is not None and not self.effective_from < self.effective_to:
            _fail("SPEC_TIME_ORDER", "effective_to must follow effective_from")


@dataclass(frozen=True, slots=True)
class LegalIVLV4(V4Contract):
    ivl_id: str
    spec_ref: ContentRefV4
    type_environment_ref: ContentRefV4
    authority_ref: ContentRefV4
    variable_declaration_refs: tuple[ContentRefV4, ...]
    premise_refs: tuple[ContentRefV4, ...]
    conclusion_ref: ContentRefV4
    modality_ref: ContentRefV4
    clause_refs: tuple[ContentRefV4, ...]
    exception_attack_refs: tuple[ContentRefV4, ...]
    permission_refs: tuple[ContentRefV4, ...]
    priority_refs: tuple[ContentRefV4, ...]
    temporal_constraint_refs: tuple[ContentRefV4, ...]
    numeric_constraint_refs: tuple[ContentRefV4, ...]
    source_map_ref: ContentRefV4
    interpretation_choice_refs: tuple[ContentRefV4, ...]
    interpretation_approval_refs: tuple[ContentRefV4, ...]
    defined_term_refs: tuple[ContentRefV4, ...]
    proof_obligation_refs: tuple[ContentRefV4, ...]
    ivl_digest: DigestV4

    def _validate(self) -> None:
        _nonempty(self.ivl_id, "LegalIVLV4.ivl_id")


@dataclass(frozen=True, slots=True)
class ArgumentV4(V4Contract):
    argument_id: str
    premise_refs: tuple[ContentRefV4, ...]
    rule_ref: ContentRefV4
    claim_ref: ContentRefV4
    derivation_refs: tuple[ContentRefV4, ...]


@dataclass(frozen=True, slots=True)
class AttackV4(V4Contract):
    attack_id: str
    attacker_ref: ContentRefV4
    target_ref: ContentRefV4
    attack_type: str
    target_aspect: str

    def _validate(self) -> None:
        _nonempty(self.attack_id, "AttackV4.attack_id")
        if self.attack_type not in _ATTACK_TYPES_V4:
            _fail("ATTACK_TYPE", f"unsupported attack type {self.attack_type!r}")
        if self.target_aspect not in _ATTACK_TARGET_ASPECTS_V4:
            _fail("ATTACK_TARGET_ASPECT", f"unsupported attack target {self.target_aspect!r}")


@dataclass(frozen=True, slots=True)
class PriorityEdgeV4(V4Contract):
    edge_id: str
    preferred_ref: ContentRefV4
    defeated_ref: ContentRefV4
    condition_ref: ContentRefV4 | None
    source_ref: ContentRefV4

    def _validate(self) -> None:
        _nonempty(self.edge_id, "PriorityEdgeV4.edge_id")


@dataclass(frozen=True, slots=True)
class PermissionResolutionV4(V4Contract):
    permission_id: str
    claim_ref: ContentRefV4
    prohibition_ref: ContentRefV4 | None
    status: str
    witness_refs: tuple[ContentRefV4, ...]

    def _validate(self) -> None:
        _nonempty(self.permission_id, "PermissionResolutionV4.permission_id")
        if self.status not in {"holds", "does_not_hold", "disputed"}:
            _fail("PERMISSION_STATUS", f"invalid permission status {self.status!r}")
        if not self.witness_refs:
            _fail("PERMISSION_WITNESS_REQUIRED", "permission resolution requires witnesses")


@dataclass(frozen=True, slots=True)
class ExceptionResolutionV4(V4Contract):
    exception_id: str
    claim_ref: ContentRefV4
    target_ref: ContentRefV4
    target_aspect: str
    status: str
    witness_refs: tuple[ContentRefV4, ...]

    def _validate(self) -> None:
        for field_name in ("exception_id", "target_aspect", "status"):
            _nonempty(getattr(self, field_name), f"ExceptionResolutionV4.{field_name}")
        if not self.witness_refs:
            _fail("EXCEPTION_WITNESS_REQUIRED", "exception resolution requires witnesses")


@dataclass(frozen=True, slots=True)
class BackendInvocationV4(V4Contract):
    invocation_id: str
    provider_id: str
    provider_version: str
    provider_package_digest: DigestV4
    provider_binary_digest: DigestV4
    provider_build_digest: DigestV4
    provider_capability_ref: ContentRefV4
    ir_ref: ContentRefV4
    algorithm_profile_digest: DigestV4
    limits_ref: ContentRefV4
    seed: int

    def _validate(self) -> None:
        for field_name in ("invocation_id", "provider_id", "provider_version"):
            _nonempty(getattr(self, field_name), f"BackendInvocationV4.{field_name}")


@dataclass(frozen=True, slots=True)
class FactAdmissionReceiptV4(V4Contract):
    receipt_id: str
    request_ref: ContentRefV4
    case_scope: str
    run_identity_ref: ContentRefV4
    subject_digest: DigestV4
    status: str
    source_gate_receipt_ref: ContentRefV4
    interpretation_gate_receipt_ref: ContentRefV4
    fact_gate_receipt_ref: ContentRefV4
    attestation_ref: ContentRefV4
    fact_ref: ContentRefV4
    issued_at: CanonicalTimeV4
    issuer: str
    signature: SignatureEnvelopeV4

    def _validate(self) -> None:
        for field_name in ("receipt_id", "case_scope", "status", "issuer"):
            _nonempty(getattr(self, field_name), f"FactAdmissionReceiptV4.{field_name}")


@dataclass(frozen=True, slots=True)
class RulePromotionReceiptV4(V4Contract):
    receipt_id: str
    rule_subject_digest: DigestV4
    legal_review_ref: ContentRefV4
    engineering_review_ref: ContentRefV4
    status: str
    issued_at: CanonicalTimeV4
    signature: SignatureEnvelopeV4


@dataclass(frozen=True, slots=True)
class TranslationReceiptV4(V4Contract):
    receipt_id: str
    run_identity_ref: ContentRefV4
    hop: str
    translator_ref: ContentRefV4
    source_ref: ContentRefV4
    target_ref: ContentRefV4
    field_mapping_ref: ContentRefV4
    field_coverage: tuple[str, ...]
    lost_fields: tuple[str, ...]
    defaulted_fields: tuple[str, ...]
    unsupported_fields: tuple[str, ...]
    counterexample_refs: tuple[ContentRefV4, ...]
    proof_obligation_refs: tuple[ContentRefV4, ...]
    status: str
    issued_at: CanonicalTimeV4
    signature: SignatureEnvelopeV4

    def _validate(self) -> None:
        for field_name in ("receipt_id", "hop", "status"):
            _nonempty(getattr(self, field_name), f"TranslationReceiptV4.{field_name}")


@dataclass(frozen=True, slots=True)
class SolverReceiptV4(V4Contract):
    receipt_id: str
    run_identity_ref: ContentRefV4
    invocation_ref: ContentRefV4
    status: str
    exit_status: int
    backend_result_ref: ContentRefV4
    model_or_core_ref: ContentRefV4 | None
    proof_ref: ContentRefV4 | None
    issued_at: CanonicalTimeV4
    signature: SignatureEnvelopeV4


@dataclass(frozen=True, slots=True)
class CheckerReceiptV4(V4Contract):
    receipt_id: str
    run_identity_ref: ContentRefV4
    subject_ref: ContentRefV4
    argument_graph_ref: ContentRefV4
    backend_result_ref: ContentRefV4
    checker_build_digest: DigestV4
    algorithm_profile_digest: DigestV4
    input_digest: DigestV4
    output_digest: DigestV4
    witness_refs: tuple[ContentRefV4, ...]
    status: str
    issued_at: CanonicalTimeV4
    signature: SignatureEnvelopeV4


@dataclass(frozen=True, slots=True)
class ProofReceiptV4(V4Contract):
    receipt_id: str
    run_identity_ref: ContentRefV4
    subject_ref: ContentRefV4
    proof_kind: str
    proof_ref: ContentRefV4
    checker_receipt_ref: ContentRefV4
    proof_build_digest: DigestV4
    trusted_computing_base_refs: tuple[ContentRefV4, ...]
    status: str
    issued_at: CanonicalTimeV4
    signature: SignatureEnvelopeV4


class ExecutionStatusV4(_V4StringEnum):
    COMPLETED = "completed"
    ADMISSION_BLOCKED = "admission_blocked"
    INTERRUPTED = "interrupted"
    UNSUPPORTED = "unsupported"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    CANCELLED = "cancelled"
    ENGINE_ERROR = "engine_error"


class DecisionStatusV4(_V4StringEnum):
    ACCEPTED_FORMAL_RESULT = "accepted_formal_result"
    HYPOTHETICAL_RESULT = "hypothetical_result"
    REVIEW_ONLY_RESULT = "review_only_result"
    MISSING_REQUIRED_FACT = "missing_required_fact"
    CONFLICT_CERTIFICATE = "conflict_certificate"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"
    ENGINE_ERROR = "engine_error"


class CompletenessStateV4(_V4StringEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    TRUNCATED = "truncated"
    INTERRUPTED = "interrupted"


class CertificateKindV4(_V4StringEnum):
    NONE = "none"
    FORMAL_VERIFIED = "formal_verified"
    CONFLICT_VERIFIED = "conflict_verified"


_REVIEW_STATES = frozenset(("not_required", "required", "pending", "approved", "rejected"))
_TRANSPORT_STATES = frozenset(("success", "error"))


@dataclass(frozen=True, slots=True)
class ReviewStateV4(V4Contract):
    status: str
    unresolved_item_refs: tuple[ContentRefV4, ...]
    responsible_role: str | None
    release_condition_refs: tuple[ContentRefV4, ...]
    review_receipt_ref: ContentRefV4 | None

    def _validate(self) -> None:
        if self.status not in _REVIEW_STATES:
            _fail("REVIEW_STATE", f"invalid review state {self.status!r}")
        if self.responsible_role is not None:
            _nonempty(self.responsible_role, "ReviewStateV4.responsible_role")
        if self.status == "not_required" and (
            self.unresolved_item_refs
            or self.responsible_role is not None
            or self.release_condition_refs
            or self.review_receipt_ref is not None
        ):
            _fail("REVIEW_STATE_DETAIL", "not_required review cannot carry review work")
        if self.status in {"required", "pending"} and (
            not self.unresolved_item_refs
            or self.responsible_role is None
            or not self.release_condition_refs
        ):
            _fail("REVIEW_STATE_DETAIL", "open review requires items, owner, and release conditions")
        if self.status in {"approved", "rejected"} and self.review_receipt_ref is None:
            _fail("REVIEW_RECEIPT_REQUIRED", "closed review requires a review receipt")


@dataclass(frozen=True, slots=True)
class InterruptionStateV4(V4Contract):
    reason_code: str
    at_stage: str

    def _validate(self) -> None:
        _nonempty(self.reason_code, "InterruptionStateV4.reason_code")
        _nonempty(self.at_stage, "InterruptionStateV4.at_stage")


@dataclass(frozen=True, slots=True)
class TransportOutcomeV4(V4Contract):
    status: str
    error: ErrorV4 | None = None

    def _validate(self) -> None:
        if self.status not in _TRANSPORT_STATES:
            _fail("TRANSPORT_STATE", f"invalid transport outcome {self.status!r}")
        if self.status == "success" and self.error is not None:
            _fail("TRANSPORT_OUTCOME", "success transport cannot carry an error")
        if self.status == "error" and self.error is None:
            _fail("TRANSPORT_OUTCOME", "error transport must carry ErrorV4")


@dataclass(frozen=True, slots=True)
class RuntimeProfileV4(V4Contract):
    engine_version: str
    engine_build_digest: DigestV4
    formal_kernel: bool
    backend_invocation_ref: ContentRefV4 | None
    backend_receipt_ref: ContentRefV4 | None
    trust_policy_ref: ContentRefV4
    storage_capability_ref: ContentRefV4

    def _validate(self) -> None:
        require_engine_match(self.engine_version)


@dataclass(frozen=True, slots=True)
class ClaimResultV4(V4Contract):
    claim_id: str
    claim_ref: ContentRefV4
    status: str
    label: str
    argument_refs: tuple[ContentRefV4, ...]
    fact_refs: tuple[ContentRefV4, ...]
    rule_refs: tuple[ContentRefV4, ...]
    source_refs: tuple[ContentRefV4, ...]
    proof_receipt_refs: tuple[ContentRefV4, ...]
    checker_receipt_refs: tuple[ContentRefV4, ...]

    def _validate(self) -> None:
        for field_name in ("claim_id", "status", "label"):
            _nonempty(getattr(self, field_name), f"ClaimResultV4.{field_name}")


@dataclass(frozen=True, slots=True)
class BranchResultV4(V4Contract):
    branch_id: str
    assumption_refs: tuple[ContentRefV4, ...]
    claim_refs: tuple[ContentRefV4, ...]
    decision_status: DecisionStatusV4
    branch_digest: DigestV4


@dataclass(frozen=True, slots=True)
class MissingFactRequirementV4(V4Contract):
    fact_id: str
    impacted_rule_refs: tuple[ContentRefV4, ...]
    impacted_claim_refs: tuple[ContentRefV4, ...]
    allowed_answer_types: tuple[str, ...]
    required_source_kinds: tuple[str, ...]
    priority: int

    def _validate(self) -> None:
        _nonempty(self.fact_id, "MissingFactRequirementV4.fact_id")
        if (
            not self.impacted_rule_refs
            or not self.impacted_claim_refs
            or not self.allowed_answer_types
            or not self.required_source_kinds
        ):
            _fail(
                "MISSING_FACT_BINDING_REQUIRED",
                "missing fact must bind impacted rules, claims, answer types, and sources",
            )


@dataclass(frozen=True, slots=True)
class RunIdentityV4(V4Contract):
    request_ref: ContentRefV4
    source_bundle_ref: ContentRefV4
    evidence_manifest_ref: ContentRefV4
    fact_attestation_refs: tuple[ContentRefV4, ...]
    rule_pack_ref: ContentRefV4
    engine_version: str
    engine_source_commit: str
    engine_source_tree: str
    engine_build_digest: DigestV4
    wheel_digest: DigestV4
    package_digest: DigestV4
    schema_digest: DigestV4
    tool_spec_digest: DigestV4
    lock_digest: DigestV4
    runtime_config_digest: DigestV4
    algorithm_profile_digest: DigestV4
    trust_policy_ref: ContentRefV4
    storage_capability_ref: ContentRefV4
    backend_invocation_ref: ContentRefV4 | None
    run_digest: DigestV4

    def _validate(self) -> None:
        require_engine_match(self.engine_version)
        for field_name in ("engine_source_commit", "engine_source_tree"):
            value = getattr(self, field_name)
            if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value) is None:
                _fail("SOURCE_IDENTITY", f"{field_name} must be a 40- or 64-hex Git identity")


@dataclass(frozen=True, slots=True)
class FormalCertificateV4(V4Contract):
    request_ref: ContentRefV4
    result_ref: ContentRefV4
    run_identity_ref: ContentRefV4
    bundle_core_digest: DigestV4
    claim_refs: tuple[ContentRefV4, ...]
    source_receipt_refs: tuple[ContentRefV4, ...]
    evidence_receipt_refs: tuple[ContentRefV4, ...]
    fact_admission_receipt_refs: tuple[ContentRefV4, ...]
    rule_promotion_receipt_refs: tuple[ContentRefV4, ...]
    translation_receipt_refs: tuple[ContentRefV4, ...]
    solver_receipt_refs: tuple[ContentRefV4, ...]
    proof_receipt_refs: tuple[ContentRefV4, ...]
    checker_receipt_refs: tuple[ContentRefV4, ...]
    certificate_digest: DigestV4

    def _validate(self) -> None:
        if not self.claim_refs:
            _fail("FORMAL_CLAIM_REQUIRED", "formal certificate requires claim refs")
        if not self.proof_receipt_refs:
            _fail("FORMAL_PROOF_REQUIRED", "formal certificate requires proof receipts")
        if not self.checker_receipt_refs:
            _fail("FORMAL_CHECKER_REQUIRED", "formal certificate requires checker receipts")
        required_receipt_groups = (
            self.source_receipt_refs,
            self.evidence_receipt_refs,
            self.fact_admission_receipt_refs,
            self.rule_promotion_receipt_refs,
            self.translation_receipt_refs,
            self.solver_receipt_refs,
        )
        if any(not group for group in required_receipt_groups):
            _fail("FORMAL_RECEIPT_CHAIN_REQUIRED", "formal certificate requires the full receipt chain")


@dataclass(frozen=True, slots=True)
class ConflictCertificateV4(V4Contract):
    request_ref: ContentRefV4
    result_ref: ContentRefV4
    run_identity_ref: ContentRefV4
    bundle_core_digest: DigestV4
    conflict_refs: tuple[ContentRefV4, ...]
    argument_refs: tuple[ContentRefV4, ...]
    attack_refs: tuple[ContentRefV4, ...]
    exception_resolution_refs: tuple[ContentRefV4, ...]
    priority_resolution_refs: tuple[ContentRefV4, ...]
    permission_resolution_refs: tuple[ContentRefV4, ...]
    source_receipt_refs: tuple[ContentRefV4, ...]
    evidence_receipt_refs: tuple[ContentRefV4, ...]
    fact_admission_receipt_refs: tuple[ContentRefV4, ...]
    rule_promotion_receipt_refs: tuple[ContentRefV4, ...]
    translation_receipt_refs: tuple[ContentRefV4, ...]
    solver_receipt_refs: tuple[ContentRefV4, ...]
    proof_receipt_refs: tuple[ContentRefV4, ...]
    checker_receipt_refs: tuple[ContentRefV4, ...]
    certificate_digest: DigestV4

    def _validate(self) -> None:
        if not self.conflict_refs or not self.argument_refs or not self.attack_refs:
            _fail("CONFLICT_WITNESS_REQUIRED", "conflict certificate requires witnesses and arguments")
        if not self.checker_receipt_refs:
            _fail("CONFLICT_CHECKER_REQUIRED", "conflict certificate requires checker receipts")


@dataclass(frozen=True, slots=True)
class CertificateEnvelopeV4(V4Contract):
    kind: CertificateKindV4
    formal: FormalCertificateV4 | None
    conflict: ConflictCertificateV4 | None
    service_signature: SignatureEnvelopeV4 | None

    def _validate(self) -> None:
        certificate: FormalCertificateV4 | ConflictCertificateV4 | None
        if self.kind is CertificateKindV4.NONE:
            if (
                self.formal is not None
                or self.conflict is not None
                or self.service_signature is not None
            ):
                _fail("CERTIFICATE_ENVELOPE", "none certificate kind cannot carry a certificate or signature")
            return
        if self.kind is CertificateKindV4.FORMAL_VERIFIED:
            if self.formal is None or self.conflict is not None:
                _fail("CERTIFICATE_ENVELOPE", "formal_verified must carry only a formal certificate")
            certificate = self.formal
        elif self.kind is CertificateKindV4.CONFLICT_VERIFIED:
            if self.conflict is None or self.formal is not None:
                _fail("CERTIFICATE_ENVELOPE", "conflict_verified must carry only a conflict certificate")
            certificate = self.conflict
        else:  # pragma: no cover - enum admission is closed before this point
            _fail("CERTIFICATE_ENVELOPE", "unsupported certificate kind")
        if self.service_signature is None:
            return
        unsigned_envelope = self.to_dict()
        del unsigned_envelope["service_signature"]
        if (
            self.service_signature.subject_digest != certificate.certificate_digest
            or self.service_signature.run_identity_ref != certificate.run_identity_ref
            or self.service_signature.payload_digest != digest_value(unsigned_envelope)
        ):
            _fail(
                "CERTIFICATE_SIGNATURE_MISMATCH",
                "service signature does not bind the certificate payload and run identity",
            )


_STATE_MATRIX = {
    "accepted_formal_result": (
        frozenset(("completed",)),
        frozenset(("not_required",)),
        frozenset(("complete",)),
        frozenset(("formal_verified",)),
        frozenset(("success",)),
    ),
    "hypothetical_result": (
        frozenset(("completed",)),
        frozenset(("required", "pending", "approved")),
        frozenset(("complete", "partial")),
        frozenset(("none",)),
        frozenset(("success",)),
    ),
    "review_only_result": (
        frozenset(("completed",)),
        frozenset(("required", "pending", "approved", "rejected")),
        frozenset(("complete", "partial")),
        frozenset(("none",)),
        frozenset(("success",)),
    ),
    "missing_required_fact": (
        frozenset(("completed",)),
        frozenset(("required", "pending")),
        frozenset(("partial",)),
        frozenset(("none",)),
        frozenset(("success",)),
    ),
    "conflict_certificate": (
        frozenset(("completed",)),
        frozenset(("required", "pending", "approved")),
        frozenset(("complete", "partial")),
        frozenset(("conflict_verified",)),
        frozenset(("success",)),
    ),
    "blocked": (
        frozenset(("admission_blocked", "interrupted", "unsupported", "resource_exhausted", "cancelled")),
        _REVIEW_STATES,
        frozenset(("partial", "truncated", "interrupted")),
        frozenset(("none",)),
        frozenset(("error",)),
    ),
    "unknown": (
        frozenset(("completed",)),
        frozenset(("not_required", "required", "pending", "approved")),
        frozenset(("complete", "partial")),
        frozenset(("none",)),
        frozenset(("success",)),
    ),
    "engine_error": (
        frozenset(("engine_error",)),
        frozenset(("not_required", "required", "pending")),
        frozenset(("partial", "truncated", "interrupted")),
        frozenset(("none",)),
        frozenset(("error",)),
    ),
}


def validate_state_matrix(
    execution: ExecutionStatusV4,
    decision: DecisionStatusV4,
    review: ReviewStateV4,
    completeness: CompletenessStateV4,
    certificate: CertificateKindV4,
    transport: TransportOutcomeV4,
) -> None:
    expected = (
        ExecutionStatusV4, DecisionStatusV4, ReviewStateV4,
        CompletenessStateV4, CertificateKindV4, TransportOutcomeV4,
    )
    actual = (execution, decision, review, completeness, certificate, transport)
    if any(type(value) is not kind for value, kind in zip(actual, expected, strict=True)):
        _fail("TYPE_MISMATCH", "state matrix values must use the six V4 state types")
    allowed = _STATE_MATRIX[decision.value]
    values = (execution.value, review.status, completeness.value, certificate.value, transport.status)
    if any(value not in choices for value, choices in zip(values, allowed, strict=True)):
        _fail("INVALID_STATE_COMBINATION", "state axes violate the decision constraint matrix")


@dataclass(frozen=True, slots=True)
class SemanticResultV4(V4Contract):
    request_ref: ContentRefV4
    execution_status: ExecutionStatusV4
    decision_status: DecisionStatusV4
    review_state: ReviewStateV4
    completeness_state: CompletenessStateV4
    interruption_state: InterruptionStateV4 | None
    certificate_kind: CertificateKindV4
    runtime_profile: RuntimeProfileV4
    claims: tuple[ClaimResultV4, ...]
    branches: tuple[BranchResultV4, ...]
    missing_facts: tuple[MissingFactRequirementV4, ...]
    admitted_fact_refs: tuple[ContentRefV4, ...]
    rejected_fact_refs: tuple[ContentRefV4, ...]
    applicable_rule_refs: tuple[ContentRefV4, ...]
    inapplicable_rule_refs: tuple[ContentRefV4, ...]
    argument_refs: tuple[ContentRefV4, ...]
    attack_refs: tuple[ContentRefV4, ...]
    exception_resolution_refs: tuple[ContentRefV4, ...]
    permission_resolution_refs: tuple[ContentRefV4, ...]
    priority_resolution_refs: tuple[ContentRefV4, ...]
    temporal_result_refs: tuple[ContentRefV4, ...]
    numeric_result_refs: tuple[ContentRefV4, ...]
    decision_reason_codes: tuple[str, ...]
    taint_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    receipt_refs: tuple[ContentRefV4, ...]
    run_identity_ref: ContentRefV4
    result_digest: DigestV4

    def digest_body(self) -> dict[str, object]:
        """Project semantic identity without receipt issuance or observability metadata."""

        body = self.to_dict()
        del body["result_digest"]
        runtime_profile = body["runtime_profile"]
        if not isinstance(runtime_profile, dict):  # defensive; to_dict() is closed
            _fail("TYPE_MISMATCH", "SemanticResultV4.runtime_profile is not an object")
        del runtime_profile["backend_receipt_ref"]
        claims = body["claims"]
        if not isinstance(claims, list):  # defensive; to_dict() is closed
            _fail("TYPE_MISMATCH", "SemanticResultV4.claims is not an array")
        for claim in claims:
            if not isinstance(claim, dict):
                _fail("TYPE_MISMATCH", "SemanticResultV4.claims contains a non-object")
            del claim["proof_receipt_refs"]
            del claim["checker_receipt_refs"]
        del body["receipt_refs"]
        return body

    def _validate(self) -> None:
        allowed = _STATE_MATRIX[self.decision_status.value]
        semantic_values = (
            self.execution_status.value,
            self.review_state.status,
            self.completeness_state.value,
            self.certificate_kind.value,
        )
        if any(
            value not in choices
            for value, choices in zip(semantic_values, allowed[:4], strict=True)
        ):
            _fail("INVALID_STATE_COMBINATION", "semantic state axes violate the decision matrix")
        interruption_required = self.execution_status in {
            ExecutionStatusV4.INTERRUPTED,
            ExecutionStatusV4.RESOURCE_EXHAUSTED,
            ExecutionStatusV4.CANCELLED,
            ExecutionStatusV4.ENGINE_ERROR,
        }
        if interruption_required != (self.interruption_state is not None):
            _fail(
                "INTERRUPTION_DETAIL",
                "interruption details must exist exactly for interrupted execution states",
            )
        if self.decision_status is DecisionStatusV4.ACCEPTED_FORMAL_RESULT:
            if not self.runtime_profile.formal_kernel:
                _fail("FORMAL_KERNEL_REQUIRED", "formal result requires a formal kernel runtime")
            if not self.claims:
                _fail("FORMAL_CLAIM_REQUIRED", "formal result requires at least one typed claim")
            if any(not claim.proof_receipt_refs for claim in self.claims):
                _fail("FORMAL_PROOF_REQUIRED", "every formal claim requires a proof receipt")
            if any(not claim.checker_receipt_refs for claim in self.claims):
                _fail("FORMAL_CHECKER_REQUIRED", "every formal claim requires a checker receipt")
            if any(
                not claim.argument_refs
                or not claim.fact_refs
                or not claim.rule_refs
                or not claim.source_refs
                for claim in self.claims
            ):
                _fail(
                    "FORMAL_CLAIM_BINDING_REQUIRED",
                    "every formal claim must bind arguments, facts, rules, and sources",
                )
            if self.runtime_profile.backend_invocation_ref is None:
                _fail(
                    "FORMAL_BACKEND_INVOCATION_REQUIRED",
                    "formal result requires a backend invocation",
                )
            if self.runtime_profile.backend_receipt_ref is None:
                _fail("FORMAL_BACKEND_RECEIPT_REQUIRED", "formal result requires a backend receipt")
            if self.taint_codes:
                _fail("FORMAL_TAINT", "formal result cannot carry taint codes")
        if self.decision_status is DecisionStatusV4.UNKNOWN and not self.decision_reason_codes:
            _fail("DECISION_REASON_REQUIRED", "unknown result requires a decision reason code")
        if self.decision_status is DecisionStatusV4.HYPOTHETICAL_RESULT:
            if not self.branches or any(not branch.assumption_refs for branch in self.branches):
                _fail(
                    "HYPOTHETICAL_ASSUMPTION_REQUIRED",
                    "hypothetical result requires explicit non-empty branch assumptions",
                )
            admitted = set(self.admitted_fact_refs)
            assumptions = {
                assumption
                for branch in self.branches
                for assumption in branch.assumption_refs
            }
            if admitted & assumptions:
                _fail(
                    "HYPOTHETICAL_FACT_MIX",
                    "hypothetical assumptions cannot be admitted as facts",
                )
        if self.decision_status is DecisionStatusV4.MISSING_REQUIRED_FACT and not self.missing_facts:
            _fail("MISSING_FACT_REQUIRED", "missing-fact result requires typed requirements")
        if self.decision_status is DecisionStatusV4.CONFLICT_CERTIFICATE and (
            not self.claims or not self.argument_refs or not self.attack_refs
        ):
            _fail(
                "CONFLICT_WITNESS_REQUIRED",
                "conflict result requires claims, arguments, and typed attacks",
            )
        if self.decision_status is DecisionStatusV4.REVIEW_ONLY_RESULT and not self.review_state.unresolved_item_refs:
            _fail("REVIEW_ITEM_REQUIRED", "review-only result requires unresolved items")


@dataclass(frozen=True, slots=True)
class AuditManifestV4(V4Contract):
    run_identity_ref: ContentRefV4
    request_ref: ContentRefV4
    input_ref: ContentRefV4
    source_index_ref: ContentRefV4
    fact_admission_ref: ContentRefV4
    rule_pack_ref: ContentRefV4
    translation_receipts_ref: ContentRefV4
    backend_receipts_ref: ContentRefV4
    checker_receipts_ref: ContentRefV4
    events_ref: ContentRefV4
    graph_ref: ContentRefV4
    result_ref: ContentRefV4
    certificate_ref: ContentRefV4
    bundle_core_digest: DigestV4
    manifest_digest: DigestV4


@dataclass(frozen=True, slots=True)
class AuditBundleIndexV4(V4Contract):
    manifest_ref: ContentRefV4
    checksums_ref: ContentRefV4
    complete_marker_ref: ContentRefV4
    entries: tuple[ContentRefV4, ...]
    bundle_digest: DigestV4


@dataclass(frozen=True, slots=True)
class EvaluationEnvelopeV4(V4Contract):
    request: CaseRequestV4
    result: SemanticResultV4
    run_identity: RunIdentityV4
    certificate: CertificateEnvelopeV4
    transport_outcome: TransportOutcomeV4
    audit_manifest_ref: ContentRefV4
    audit_bundle_index: AuditBundleIndexV4

    def _validate(self) -> None:
        validate_state_matrix(
            self.result.execution_status,
            self.result.decision_status,
            self.result.review_state,
            self.result.completeness_state,
            self.result.certificate_kind,
            self.transport_outcome,
        )
        if self.certificate.kind is not self.result.certificate_kind:
            _fail("CERTIFICATE_KIND", "certificate envelope kind does not match result state")
        if (
            self.run_identity.request_ref.digest != self.request.canonical_digest()
            or self.result.request_ref != self.run_identity.request_ref
        ):
            _fail("REQUEST_BINDING_MISMATCH", "request, result, and run identity are not bound")
        if self.result.run_identity_ref.digest != self.run_identity.canonical_digest():
            _fail("RUN_BINDING_MISMATCH", "result does not bind the enclosed run identity")
        profile = self.result.runtime_profile
        if (
            profile.engine_version != self.run_identity.engine_version
            or profile.engine_build_digest != self.run_identity.engine_build_digest
            or profile.trust_policy_ref != self.run_identity.trust_policy_ref
            or profile.storage_capability_ref != self.run_identity.storage_capability_ref
            or (
                profile.backend_invocation_ref is not None
                and profile.backend_invocation_ref != self.run_identity.backend_invocation_ref
            )
        ):
            _fail("RUNTIME_BINDING_MISMATCH", "runtime profile does not match the run identity")
        if self.audit_bundle_index.manifest_ref != self.audit_manifest_ref:
            _fail("AUDIT_BINDING_MISMATCH", "audit bundle index does not bind the manifest")
        certificate = self.certificate.formal or self.certificate.conflict
        if certificate is not None:
            if certificate.request_ref != self.result.request_ref:
                _fail("CERTIFICATE_REQUEST_MISMATCH", "certificate does not bind the request")
            if certificate.result_ref.digest != self.result.canonical_digest():
                _fail("CERTIFICATE_RESULT_MISMATCH", "certificate does not bind the result")
            if certificate.run_identity_ref != self.result.run_identity_ref:
                _fail("CERTIFICATE_RUN_MISMATCH", "certificate does not bind the result run")


@dataclass(frozen=True, slots=True)
class VerificationResultV4(V4Contract):
    run_identity_ref: ContentRefV4
    status: str
    certificate_ref: ContentRefV4
    audit_manifest_ref: ContentRefV4
    audit_bundle_ref: ContentRefV4
    verified_artifact_refs: tuple[ContentRefV4, ...]
    failed_artifact_refs: tuple[ContentRefV4, ...]
    checker_receipt_refs: tuple[ContentRefV4, ...]
    verification_receipt_refs: tuple[ContentRefV4, ...]
    error_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReplayResultV4(V4Contract):
    run_identity_ref: ContentRefV4
    replay_run_identity_ref: ContentRefV4
    status: str
    replay_policy_ref: ContentRefV4
    original_result_ref: ContentRefV4
    replay_result_ref: ContentRefV4
    original_bundle_ref: ContentRefV4
    replay_bundle_ref: ContentRefV4
    exact_equal: bool
    semantic_equal: bool
    differing_paths: tuple[str, ...]

    def _validate(self) -> None:
        _nonempty(self.status, "ReplayResultV4.status")


@dataclass(frozen=True, slots=True)
class MCPCapabilitiesInputV4(V4Contract):
    pass


@dataclass(frozen=True, slots=True)
class ToolSpecV4(V4Contract):
    name: str
    description: str
    input_type: str
    output_type: str
    error_type: str


@dataclass(frozen=True, slots=True)
class MCPCapabilitiesOutputV4(V4Contract):
    schema_version: str
    engine_version: str
    engine_source_tree: str
    engine_build_digest: DigestV4
    wheel_digest: DigestV4
    package_digest: DigestV4
    lock_digest: DigestV4
    schema_digest: DigestV4
    tool_spec_digest: DigestV4
    tool_specs: tuple[ToolSpecV4, ...]
    resource_limits: ResourceLimitsV4
    active_pack_ref: ContentRefV4 | None
    trust_policy_ref: ContentRefV4
    storage_capability_ref: ContentRefV4
    kernel_ready: bool
    legal_production_ready: bool

    def _validate(self) -> None:
        require_engine_match(self.engine_version, self.schema_version)
        if self.legal_production_ready and (
            not self.kernel_ready or self.active_pack_ref is None
        ):
            _fail(
                "CAPABILITY_READINESS",
                "legal production readiness requires a formal kernel and active pack",
            )


@dataclass(frozen=True, slots=True)
class MCPCapabilitiesErrorV4(V4Contract):
    error: ErrorV4


@dataclass(frozen=True, slots=True)
class MCPEvaluateInputV4(V4Contract):
    request: CaseRequestV4 | None
    request_handle: ArtifactHandleV4 | None

    def _validate(self) -> None:
        if (self.request is None) == (self.request_handle is None):
            _fail("MCP_REQUEST_SOURCE", "exactly one of request or request_handle is required")


@dataclass(frozen=True, slots=True)
class MCPEvaluateOutputV4(V4Contract):
    result: SemanticResultV4
    certificate_handle: ArtifactHandleV4
    run_handle: ArtifactHandleV4
    artifact_handles: tuple[ArtifactHandleV4, ...]


@dataclass(frozen=True, slots=True)
class MCPEvaluateErrorV4(V4Contract):
    error: ErrorV4
    result: SemanticResultV4 | None
    run_handle: ArtifactHandleV4 | None
    artifact_handles: tuple[ArtifactHandleV4, ...]


@dataclass(frozen=True, slots=True)
class MCPVerifyRunInputV4(V4Contract):
    run_handle: ArtifactHandleV4
    offline_replay: bool


@dataclass(frozen=True, slots=True)
class MCPVerifyRunOutputV4(V4Contract):
    verification: VerificationResultV4
    replay: ReplayResultV4 | None


@dataclass(frozen=True, slots=True)
class MCPVerifyRunErrorV4(V4Contract):
    error: ErrorV4
    run_handle: ArtifactHandleV4 | None
    verification: VerificationResultV4 | None
    replay: ReplayResultV4 | None


@dataclass(frozen=True, slots=True)
class MCPReadArtifactInputV4(V4Contract):
    artifact_handle: ArtifactHandleV4
    offset: int
    length: int

    def _validate(self) -> None:
        if self.offset < 0 or self.length <= 0:
            _fail("ARTIFACT_RANGE", "artifact offset must be non-negative and length positive")
        requested_end = self.offset + self.length
        if (
            requested_end > self.artifact_handle.max_bytes
            or requested_end > self.artifact_handle.size_bytes
        ):
            _fail("ARTIFACT_RANGE", "requested range exceeds the signed handle bound")


@dataclass(frozen=True, slots=True)
class MCPReadArtifactOutputV4(V4Contract):
    artifact_handle: ArtifactHandleV4
    offset: int
    length: int
    next_offset: int | None
    content_base64: str
    chunk_digest: DigestV4
    artifact_digest: DigestV4
    content_type: str
    eof: bool

    def _validate(self) -> None:
        if self.offset < 0 or self.length < 0:
            _fail("ARTIFACT_RANGE", "artifact output offset and length must be non-negative")
        returned_end = self.offset + self.length
        if (
            returned_end > self.artifact_handle.max_bytes
            or returned_end > self.artifact_handle.size_bytes
        ):
            _fail("ARTIFACT_RANGE", "returned range exceeds the signed handle bound")
        if self.next_offset is not None and self.next_offset != self.offset + self.length:
            _fail("ARTIFACT_RANGE", "next_offset must equal offset plus returned length")
        if self.eof and self.next_offset is not None:
            _fail("ARTIFACT_RANGE", "eof output cannot advertise a next offset")
        if self.artifact_digest != self.artifact_handle.content_ref.digest:
            _fail("ARTIFACT_DIGEST_MISMATCH", "artifact digest does not match the signed handle")
        _nonempty(self.content_type, "MCPReadArtifactOutputV4.content_type")


@dataclass(frozen=True, slots=True)
class MCPReadArtifactErrorV4(V4Contract):
    error: ErrorV4
    artifact_handle: ArtifactHandleV4 | None


_REGISTRY_TYPES = (
    DigestV4,
    CanonicalTimeV4,
    ContentRefV4,
    ArtifactHandleV4,
    ErrorV4,
    SignatureEnvelopeV4,
    TrustPolicyV4,
    StorageCapabilityV4,
    ObservabilityEnvelopeV4,
    CaseRequestV4,
    LegalContextV4,
    RequestedOutputV4,
    ResourceLimitsV4,
    SourceSnapshotV4,
    CanonicalLocatorV4,
    SourceVersionEdgeV4,
    SourceBundleV4,
    EvidenceManifestV4,
    EvidenceItemV4,
    ContradictionRefV4,
    FactCandidateV4,
    FactAttestationV4,
    RuleV4,
    PackManifestV4,
    PackSignatureV4,
    LegalSpecV4,
    LegalIVLV4,
    ArgumentV4,
    AttackV4,
    PriorityEdgeV4,
    PermissionResolutionV4,
    ExceptionResolutionV4,
    BackendInvocationV4,
    FactAdmissionReceiptV4,
    RulePromotionReceiptV4,
    TranslationReceiptV4,
    SolverReceiptV4,
    CheckerReceiptV4,
    ProofReceiptV4,
    ExecutionStatusV4,
    DecisionStatusV4,
    ReviewStateV4,
    CompletenessStateV4,
    InterruptionStateV4,
    CertificateKindV4,
    TransportOutcomeV4,
    RuntimeProfileV4,
    ClaimResultV4,
    BranchResultV4,
    MissingFactRequirementV4,
    SemanticResultV4,
    RunIdentityV4,
    FormalCertificateV4,
    ConflictCertificateV4,
    CertificateEnvelopeV4,
    AuditManifestV4,
    AuditBundleIndexV4,
    EvaluationEnvelopeV4,
    VerificationResultV4,
    ReplayResultV4,
    MCPCapabilitiesInputV4,
    MCPCapabilitiesOutputV4,
    MCPCapabilitiesErrorV4,
    MCPEvaluateInputV4,
    MCPEvaluateOutputV4,
    MCPEvaluateErrorV4,
    MCPVerifyRunInputV4,
    MCPVerifyRunOutputV4,
    MCPVerifyRunErrorV4,
    MCPReadArtifactInputV4,
    MCPReadArtifactOutputV4,
    MCPReadArtifactErrorV4,
    ToolSpecV4,
)
V4_TYPE_REGISTRY = MappingProxyType({item.__name__: item for item in _REGISTRY_TYPES})
V4_OBJECT_REGISTRY = MappingProxyType(
    {
        item.__name__: item
        for item in _REGISTRY_TYPES
        if isinstance(item, type) and issubclass(item, V4Contract)
    }
)
OBJECT_TYPE_REGISTRY_V4 = V4_OBJECT_REGISTRY


__all__ = [
    "SCHEMA_VERSION_V4",
    "ContractV4Error",
    "V4Contract",
    "V4_TYPE_REGISTRY",
    "V4_OBJECT_REGISTRY",
    "OBJECT_TYPE_REGISTRY_V4",
    "DEFAULT_RESOURCE_LIMITS_V4",
    "HARD_MAX_RESOURCE_LIMITS_V4",
    "RESOURCE_LIMIT_ERROR_CODES_V4",
    "ENGINE_LIMITS_V4",
    "validate_safe_integer_v4",
    "validate_money_v4",
    "validate_rational_v4",
    "validate_resource_limits_v4",
    "require_engine_match",
    "validate_state_matrix",
    *[item.__name__ for item in _REGISTRY_TYPES],
]
