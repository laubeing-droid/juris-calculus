"""Validation and canonical fingerprints of the pinned completion documents."""
from __future__ import annotations

import re
from typing import Any, Mapping

from compiler_core.canonical_serialization import (
    DigestV4,
    digest_value,
)
from compiler_core.math_export.pins import (
    ATTEMPT,
    DO_NOT_RUN_NOW,
    LAKE_MANIFEST_SHA256,
    LEAN_TOOLCHAIN_SHA256,
    NOT_ESTABLISHED,
    REPOSITORY,
    REQUIRED_INTERFACES,
    RUN_ID,
    SUBJECT_COMMIT,
    SUBJECT_TREE,
)

_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")

MATH_COMPLETION_STATUS = "MATH_BUILD_COMPLETE"
EXPORT_CONTRACT_STATUS = "READY_FOR_LATER_INTEGRATION_DESIGN"
MANDATORY_REGISTRATIONS = 217


class MathExportContractError(RuntimeError):
    """Raised when a completion document drifts from the pinned subject."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise MathExportContractError(code, detail)


def _string(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    _require(isinstance(value, str), "CONTRACT_FIELD_TYPE", field)
    return str(value)


def validate_math_completion(document: Mapping[str, Any]) -> dict[str, str]:
    """Validate MATH_COMPLETION.json against the pinned subject; return it."""

    _require(
        _string(document, "status") == MATH_COMPLETION_STATUS,
        "COMPLETION_STATUS_DRIFT",
        "status must stay MATH_BUILD_COMPLETE",
    )
    subject = document.get("subject")
    _require(isinstance(subject, dict), "COMPLETION_SUBJECT_TYPE", "subject")
    expected = {
        "commit": SUBJECT_COMMIT,
        "tree": SUBJECT_TREE,
        "repository": REPOSITORY,
        "run_id": RUN_ID,
        "attempt": ATTEMPT,
        "lean_toolchain_sha256": LEAN_TOOLCHAIN_SHA256,
        "lake_manifest_sha256": LAKE_MANIFEST_SHA256,
    }
    _require(
        set(subject) == set(expected),
        "COMPLETION_SUBJECT_FIELDS",
        f"subject fields must be exactly {sorted(expected)}",
    )
    for field, value in expected.items():
        actual = subject[field]
        _require(
            isinstance(actual, str) and actual == value,
            "COMPLETION_SUBJECT_DRIFT",
            f"subject.{field} drifted from the pinned full-release subject",
        )
    _require(
        _HEX40.fullmatch(SUBJECT_COMMIT) is not None
        and _HEX40.fullmatch(SUBJECT_TREE) is not None,
        "COMPLETION_SUBJECT_SHAPE",
        "commit and tree must be 40-character hex subjects",
    )
    _require(
        _HEX64.fullmatch(LEAN_TOOLCHAIN_SHA256) is not None
        and _HEX64.fullmatch(LAKE_MANIFEST_SHA256) is not None,
        "COMPLETION_SUBJECT_SHAPE",
        "toolchain and manifest digests must be 64-character hex",
    )
    not_established = document.get("not_established")
    _require(
        isinstance(not_established, list)
        and tuple(not_established) == NOT_ESTABLISHED,
        "NOT_ESTABLISHED_DRIFT",
        "not_established must be carried verbatim and never closed",
    )
    _require(
        document.get("mandatory_registrations") == MANDATORY_REGISTRATIONS,
        "REGISTRATION_COUNT_DRIFT",
        "the pinned subject carries 217 mandatory registrations",
    )
    _require(
        isinstance(document.get("evidence_type"), str),
        "COMPLETION_FIELD_TYPE",
        "evidence_type",
    )
    return dict(subject)


def validate_export_contract(document: Mapping[str, Any]) -> None:
    """Validate EXPORT_CONTRACT.json against the pinned handover shape."""

    _require(
        _string(document, "status") == EXPORT_CONTRACT_STATUS,
        "CONTRACT_STATUS_DRIFT",
        "status must stay READY_FOR_LATER_INTEGRATION_DESIGN",
    )
    contract = document.get("contract")
    _require(isinstance(contract, dict), "CONTRACT_SECTION_TYPE", "contract")
    required = contract.get("required")
    _require(
        isinstance(required, list) and tuple(required) == REQUIRED_INTERFACES,
        "CONTRACT_REQUIRED_DRIFT",
        "the eleven required export interfaces must be preserved",
    )
    do_not_run = contract.get("do_not_run_now")
    _require(
        isinstance(do_not_run, list) and tuple(do_not_run) == DO_NOT_RUN_NOW,
        "CONTRACT_GUARDS_DRIFT",
        "do_not_run_now guards must be preserved verbatim",
    )
    external = document.get("external")
    _require(isinstance(external, dict), "CONTRACT_SECTION_TYPE", "external")
    items = external.get("items")
    _require(isinstance(items, list), "CONTRACT_SECTION_TYPE", "external.items")
    identifiers = tuple(
        item.get("id") for item in items if isinstance(item, dict)
    )
    _require(
        len(identifiers) == 5,
        "CONTRACT_EXTERNAL_DRIFT",
        "five deferred external obligations must be preserved",
    )
    mathematics = document.get("mathematics")
    _require(
        isinstance(mathematics, dict),
        "CONTRACT_SECTION_TYPE",
        "mathematics",
    )
    validate_math_completion(mathematics)


def math_completion_fingerprint(document: Mapping[str, Any]) -> DigestV4:
    """Canonical digest of the validated completion document."""

    validate_math_completion(document)
    return digest_value(document)


def contract_fingerprint(document: Mapping[str, Any]) -> DigestV4:
    """Canonical digest of the validated export contract document."""

    validate_export_contract(document)
    return digest_value(document)
