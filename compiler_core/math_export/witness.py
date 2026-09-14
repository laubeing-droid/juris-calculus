"""Public-entry run witnesses for the C06 checker correspondence.

A witness is the JC-side record of one public-entry evaluation (CLI,
``JCClient`` or MCP). It binds the run to the pinned mathematics subject,
carries the raw JC semantic state plus the pinned mapping into the LMM
four-value status vocabulary, and is content-addressed so an independent
checker can accept or reject it without ever importing JC code.

The mapping is total and conservative: only unattacked accepted results
may read PROVED, only defeated claims may read REFUTED, every
non-decisive state reads UNDECIDED, and every fail-closed or tainted
state — including rejected input — reads TAINTED.
"""
from __future__ import annotations

from typing import Any, Mapping

from compiler_core.canonical_serialization import DigestV4, digest_value
from compiler_core.math_export.fingerprint import subject_fingerprint

WITNESS_SCHEMA = "jc/lmm-c06-witness/1.0"

ENTRIES = ("jc_client", "cli", "mcp")

# Issue-level conclusion_status values (harness_contract HarnessIssueResultV5)
# and the envelope-level DecisionStatusV4 values, mapped into the LMM
# refinement vocabulary {PROVED, REFUTED, UNDECIDED, TAINTED}.
ISSUE_STATUS_MAPPING_V1 = {
    "accepted": "PROVED",
    "refuted": "REFUTED",
    "possible": "UNDECIDED",
    "undecided": "UNDECIDED",
    "incomplete": "UNDECIDED",
    "excluded": "UNDECIDED",
    "inconsistent": "TAINTED",
}

DECISION_STATUS_MAPPING_V1 = {
    "accepted_formal_result": "PROVED",
    "conflict_certificate": "REFUTED",
    "hypothetical_result": "UNDECIDED",
    "review_only_result": "UNDECIDED",
    "missing_required_fact": "UNDECIDED",
    "unknown": "UNDECIDED",
    "blocked": "TAINTED",
    "engine_error": "TAINTED",
}

# A public entry that refuses malformed input at intake never yields a
# decisive answer; the rejection is recorded as the witness outcome.
REJECTED_INPUT_STATUS = "TAINTED"

WITNESS_STATUSES = ("PROVED", "REFUTED", "UNDECIDED", "TAINTED")


def map_issue_status(issue_status: str) -> str:
    try:
        return ISSUE_STATUS_MAPPING_V1[issue_status]
    except KeyError as exc:
        raise ValueError(f"unknown issue conclusion status: {issue_status!r}") from exc


def map_decision_status(decision_status: str) -> str:
    try:
        return DECISION_STATUS_MAPPING_V1[decision_status]
    except KeyError as exc:
        raise ValueError(
            f"unknown envelope decision status: {decision_status!r}"
        ) from exc


def build_run_witness(
    *,
    entry: str,
    case_id: str,
    probe_semantics: str,
    lmm_subject: Mapping[str, Any],
    engine_version: str,
    engine_build_digest: str,
    run_identity_digest: str,
    input_digest: str,
    result_digest: str,
    audit_manifest_digest: str,
    decision_status: str | None,
    issue_statuses: Mapping[str, str],
    intake_error_code: str | None = None,
    focus_issue: str | None = None,
) -> dict[str, Any]:
    """Build and seal one run witness; fails closed on unknown vocabulary.

    ``focus_issue`` names the one issue a probe case is about. A run-level
    decision aggregates every issue of the bundle, so a decisive focus
    issue (PROVED, REFUTED or TAINTED at issue level) decides the witness
    status; non-decisive focus states never override the run level.
    """

    if entry not in ENTRIES:
        raise ValueError(f"unknown public entry: {entry!r}")
    if intake_error_code is not None:
        status = REJECTED_INPUT_STATUS
        issue_rows: dict[str, str] = {}
        recorded_decision = "intake_rejected"
    else:
        recorded_decision = decision_status
        status = map_decision_status(decision_status)
        issue_rows = {
            issue_id: map_issue_status(value)
            for issue_id, value in issue_statuses.items()
        }
        for issue_id, value in issue_statuses.items():
            if value not in ISSUE_STATUS_MAPPING_V1:
                raise ValueError(f"unknown issue conclusion status: {value!r}")
    if focus_issue is not None and intake_error_code is None:
        if focus_issue not in issue_rows:
            raise ValueError(f"focus issue {focus_issue!r} has no witness row")
        decisive = issue_rows[focus_issue]
        if decisive in {"PROVED", "REFUTED", "TAINTED"}:
            status = decisive
    if status not in WITNESS_STATUSES:
        raise ValueError(f"unknown witness status: {status!r}")
    body = {
        "schema_version": WITNESS_SCHEMA,
        "producer": "juris-calculus",
        "entry": entry,
        "case_id": case_id,
        "probe_semantics": probe_semantics,
        "lmm_subject_fingerprint": str(subject_fingerprint(lmm_subject)),
        "lmm_commit": str(lmm_subject["commit"]),
        "juris_calculus": {
            "engine_version": engine_version,
            "engine_build_digest": engine_build_digest,
        },
        "run_identity_digest": run_identity_digest,
        "input_digest": input_digest,
        "result_digest": result_digest,
        "audit_manifest_digest": audit_manifest_digest,
        "decision_status": recorded_decision,
        "intake_error_code": intake_error_code,
        "focus_issue": focus_issue,
        "status": status,
        "issues": issue_rows,
    }
    return {**body, "witness_digest": str(digest_value(body))}


def witness_body(witness: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in witness.items() if key != "witness_digest"
    }


def witness_digest(witness: Mapping[str, Any]) -> DigestV4:
    return digest_value(witness_body(witness))


def validate_witness(witness: Mapping[str, Any]) -> None:
    """Fail-closed structural and digest validation of one witness."""

    if witness.get("schema_version") != WITNESS_SCHEMA:
        raise ValueError("witness schema drifted")
    if witness.get("producer") != "juris-calculus":
        raise ValueError("witness producer must be juris-calculus")
    if witness.get("entry") not in ENTRIES:
        raise ValueError("witness entry must be a JC public entry")
    if witness.get("status") not in WITNESS_STATUSES:
        raise ValueError("witness status is outside the LMM vocabulary")
    expected = str(digest_value(witness_body(witness)))
    if witness.get("witness_digest") != expected:
        raise ValueError("witness digest mismatch")


def issue_statuses_of(witness: Mapping[str, Any]) -> dict[str, str]:
    issues = witness.get("issues")
    if not isinstance(issues, dict):
        raise ValueError("witness issues must be an object")
    return dict(issues)
