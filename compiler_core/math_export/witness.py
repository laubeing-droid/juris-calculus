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

Schema ``jc/lmm-c06-witness/1.1`` tightens two v1.0 behaviors (JC-01):

- a whole-run failure (``engine_error`` / ``blocked``) or an intake
  rejection is never upgraded by a locally accepted focus issue; the
  witness keeps the global unusable state while the per-issue rows stay
  visible with their own scope;
- a run-level ``conflict_certificate`` does not name a defeated claim,
  so it reads UNDECIDED at run level; REFUTED is granted only by an
  issue-level ``refuted`` row (the focus issue binding).

Validation (JC-02) requires the complete typed structure, cross-field
coherence and — when the caller provides them — the expected case,
subject and input/result/audit bindings. A recomputed self-digest alone
is never sufficient. Historical ``jc/lmm-c06-witness/1.0`` witnesses
remain readable through the legacy structural rules and are explicitly
marked as needing review; their bytes are never rewritten.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from compiler_core.canonical_serialization import DigestV4, digest_value
from compiler_core.math_export.fingerprint import subject_fingerprint

WITNESS_SCHEMA = "jc/lmm-c06-witness/1.1"
LEGACY_WITNESS_SCHEMA = "jc/lmm-c06-witness/1.0"

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

# The historical v1.0 run-level table. Its ``conflict_certificate`` row
# read REFUTED at run level, which named a defeated claim the envelope
# never identified; 1.1 consumption uses DECISION_STATUS_MAPPING below.
# The table stays here read-only as the interpretation of record for
# historical 1.0 witnesses and is never used to build new witnesses.
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

# v1.1 run-level consumption. A verified conflict at envelope level
# (``conflict_certificate``) proves the argumentation of the bundle is
# in conflict; it does not say which claim was defeated, so the
# run-level reading is UNDECIDED. REFUTED requires an issue-level
# ``refuted`` row bound through the focus issue.
DECISION_STATUS_MAPPING = {
    **DECISION_STATUS_MAPPING_V1,
    "conflict_certificate": "UNDECIDED",
}

# Decision statuses issued from the whole-run failure path
# (application ``_Failure``): the envelope answer is unavailable, so no
# per-issue result may upgrade the run into a decisive success.
RUN_GLOBAL_FAILURE_DECISIONS = frozenset({"blocked", "engine_error"})

# A public entry that refuses malformed input at intake never yields a
# decisive answer; the rejection is recorded as the witness outcome.
REJECTED_INPUT_STATUS = "TAINTED"

WITNESS_STATUSES = ("PROVED", "REFUTED", "UNDECIDED", "TAINTED")
DECISIVE_FOCUS_STATUSES = frozenset({"PROVED", "REFUTED", "TAINTED"})

STATUS_SCOPES = (
    "intake_rejected",
    "run_global_failure",
    "focus_issue",
    "run",
)

# A complete 1.1 witness is exactly these fields, nothing more.
FULL_WITNESS_FIELDS = frozenset({
    "schema_version",
    "producer",
    "entry",
    "case_id",
    "probe_semantics",
    "lmm_subject_fingerprint",
    "lmm_commit",
    "juris_calculus",
    "run_identity_digest",
    "input_digest",
    "result_digest",
    "audit_manifest_digest",
    "decision_status",
    "intake_error_code",
    "focus_issue",
    "status",
    "status_scope",
    "issues",
    "witness_digest",
})
LEGACY_WITNESS_FIELDS = FULL_WITNESS_FIELDS - {"status_scope"}

_DIGEST_FIELD_NAMES = (
    "run_identity_digest",
    "input_digest",
    "result_digest",
    "audit_manifest_digest",
)
_PREFIXED_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_BARE_DIGEST = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")


def map_issue_status(issue_status: str) -> str:
    try:
        return ISSUE_STATUS_MAPPING_V1[issue_status]
    except KeyError as exc:
        raise ValueError(f"unknown issue conclusion status: {issue_status!r}") from exc


def map_decision_status(decision_status: str) -> str:
    """Map one envelope decision status with the 1.1 consumption table."""

    try:
        return DECISION_STATUS_MAPPING[decision_status]
    except KeyError as exc:
        raise ValueError(
            f"unknown envelope decision status: {decision_status!r}"
        ) from exc


def digest_text(value: object, field: str) -> str:
    """Canonicalize one binding digest to ``sha256:<64 hex>``.

    Both the ``sha256:``-prefixed DigestV4 rendering and the bare
    64-hex form are accepted on input so historical producers stay
    loadable; the sealed witness body always carries the canonical
    prefixed form.
    """

    if type(value) is not str:
        raise ValueError(f"{field} must be a digest string, got {type(value)!r}")
    if _PREFIXED_DIGEST.fullmatch(value):
        return value
    if _BARE_DIGEST.fullmatch(value):
        return f"sha256:{value}"
    raise ValueError(f"{field} is not a sha256 digest: {value!r}")


def _resolve_status(
    decision_status: str,
    issue_rows: Mapping[str, str],
    focus_issue: str | None,
) -> tuple[str, str]:
    """Derive ``(status, status_scope)``; the single coherence authority.

    Used by both the builder and the validator, so a sealed witness can
    never disagree with the recorded raw state.
    """

    if decision_status in RUN_GLOBAL_FAILURE_DECISIONS:
        # The whole run failed: per-issue rows (when present) stay
        # recorded with their own scope but never decide the run.
        return "TAINTED", "run_global_failure"
    if focus_issue is not None and focus_issue not in issue_rows:
        raise ValueError(f"focus issue {focus_issue!r} has no witness row")
    if focus_issue is not None and issue_rows[focus_issue] in DECISIVE_FOCUS_STATUSES:
        return issue_rows[focus_issue], "focus_issue"
    return DECISION_STATUS_MAPPING[decision_status], "run"


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
    status — unless the whole run failed globally or the input was
    rejected at intake, in which case the global unusable state stands
    and the per-issue rows only annotate what had been computed.
    """

    if entry not in ENTRIES:
        raise ValueError(f"unknown public entry: {entry!r}")
    if intake_error_code is not None:
        status = REJECTED_INPUT_STATUS
        scope = "intake_rejected"
        issue_rows: dict[str, str] = {}
        recorded_decision = "intake_rejected"
        focus_issue = None
    else:
        recorded_decision = decision_status
        if decision_status is None:
            raise ValueError(
                "decision_status is required when the input was not "
                "rejected at intake",
            )
        issue_rows = {
            issue_id: map_issue_status(value)
            for issue_id, value in issue_statuses.items()
        }
        status, scope = _resolve_status(decision_status, issue_rows, focus_issue)
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
        "run_identity_digest": digest_text(run_identity_digest, "run_identity_digest"),
        "input_digest": digest_text(input_digest, "input_digest"),
        "result_digest": digest_text(result_digest, "result_digest"),
        "audit_manifest_digest": digest_text(
            audit_manifest_digest, "audit_manifest_digest",
        ),
        "decision_status": recorded_decision,
        "intake_error_code": intake_error_code,
        "focus_issue": focus_issue,
        "status": status,
        "status_scope": scope,
        "issues": issue_rows,
    }
    return {**body, "witness_digest": str(digest_value(body))}


def witness_body(witness: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in witness.items() if key != "witness_digest"
    }


def witness_digest(witness: Mapping[str, Any]) -> DigestV4:
    return digest_value(witness_body(witness))


def _require_text(
    witness: Mapping[str, Any], field: str, *, nonempty: bool = False,
) -> str:
    value = witness.get(field)
    if type(value) is not str or (nonempty and not value):
        raise ValueError(f"witness {field} must be a{' non-empty' if nonempty else ''} string")
    return value


def _validate_current(witness: Mapping[str, Any]) -> None:
    """Full typed structure and coherence checks for schema 1.1."""

    keys = set(witness)
    missing = sorted(FULL_WITNESS_FIELDS - keys)
    extra = sorted(keys - FULL_WITNESS_FIELDS)
    if missing or extra:
        raise ValueError(
            f"witness fields drifted: missing={missing}; extra={extra}",
        )
    _require_text(witness, "case_id", nonempty=True)
    _require_text(witness, "probe_semantics", nonempty=True)
    commit = _require_text(witness, "lmm_commit")
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("witness lmm_commit must be a 40-character Git SHA")
    fingerprint = _require_text(witness, "lmm_subject_fingerprint")
    if _PREFIXED_DIGEST.fullmatch(fingerprint) is None:
        raise ValueError("witness lmm_subject_fingerprint must be a sha256 digest")
    engine = witness.get("juris_calculus")
    if (
        type(engine) is not dict
        or set(engine) != {"engine_version", "engine_build_digest"}
        or type(engine.get("engine_version")) is not str
        or not engine["engine_version"]
        or type(engine.get("engine_build_digest")) is not str
        or not engine["engine_build_digest"]
    ):
        raise ValueError("witness juris_calculus engine identity is malformed")
    for field in _DIGEST_FIELD_NAMES:
        digest_text(witness.get(field), field)
    intake_error_code = witness.get("intake_error_code")
    if intake_error_code is not None and (
        type(intake_error_code) is not str or not intake_error_code
    ):
        raise ValueError("witness intake_error_code must be None or a non-empty string")
    focus_issue = witness.get("focus_issue")
    if focus_issue is not None and (type(focus_issue) is not str or not focus_issue):
        raise ValueError("witness focus_issue must be None or a non-empty string")
    decision_status = witness.get("decision_status")
    if type(decision_status) is not str or not decision_status:
        raise ValueError("witness decision_status must be a non-empty string")
    issues = witness.get("issues")
    if type(issues) is not dict:
        raise ValueError("witness issues must be an object")
    for issue_id, value in issues.items():
        if type(issue_id) is not str or not issue_id:
            raise ValueError("witness issue ids must be non-empty strings")
        if type(value) is not str or value not in WITNESS_STATUSES:
            raise ValueError(
                f"witness issue {issue_id!r} status is outside the LMM vocabulary",
            )
    scope = witness.get("status_scope")
    if scope not in STATUS_SCOPES:
        raise ValueError(f"witness status_scope is unknown: {scope!r}")
    if intake_error_code is not None:
        if (
            decision_status != "intake_rejected"
            or witness.get("status") != REJECTED_INPUT_STATUS
            or scope != "intake_rejected"
            or issues != {}
            or focus_issue is not None
        ):
            raise ValueError(
                "intake-rejected witness must stay TAINTED with no issue "
                "rows and no focus binding",
            )
    else:
        if decision_status not in DECISION_STATUS_MAPPING:
            raise ValueError(
                f"unknown envelope decision status: {decision_status!r}",
            )
        expected_status, expected_scope = _resolve_status(
            decision_status, issues, focus_issue,
        )
        if witness.get("status") != expected_status or scope != expected_scope:
            raise ValueError(
                "witness status disagrees with its recorded decision, "
                "issues and focus binding",
            )
    expected = str(digest_value(witness_body(witness)))
    if witness.get("witness_digest") != expected:
        raise ValueError("witness digest mismatch")


def _validate_legacy(witness: Mapping[str, Any]) -> None:
    """The v1.0 structural rules, kept read-only for historical records.

    No 1.1 coherence rule is applied: v1.0 witnesses were legal under
    the v1.0 rules and their bytes are never rewritten. Callers learn
    through the returned scope that these witnesses need review before
    any new consumption.
    """

    if witness.get("producer") != "juris-calculus":
        raise ValueError("witness producer must be juris-calculus")
    if witness.get("entry") not in ENTRIES:
        raise ValueError("witness entry must be a JC public entry")
    if witness.get("status") not in WITNESS_STATUSES:
        raise ValueError("witness status is outside the LMM vocabulary")
    expected = str(digest_value(witness_body(witness)))
    if witness.get("witness_digest") != expected:
        raise ValueError("witness digest mismatch")


def validate_witness(
    witness: Mapping[str, Any],
    *,
    expected_case_id: str | None = None,
    expected_subject: Mapping[str, Any] | None = None,
    expected_subject_fingerprint: str | None = None,
    expected_lmm_commit: str | None = None,
    expected_run_identity_digest: str | None = None,
    expected_input_digest: str | None = None,
    expected_result_digest: str | None = None,
    expected_audit_manifest_digest: str | None = None,
) -> dict[str, str]:
    """Fail-closed structural, coherence and binding validation.

    Structural validation and checker acceptance are separate concerns:
    passing this function never claims the independent checker accepted
    anything. The ``expected_*`` bindings are supplied by the real
    caller (the entry driver or the cross-repo verifier) and compared
    against the payload — a witness may never vouch for its own case,
    subject or digests. A recomputed self-digest alone is not a
    validation.

    Returns the validation scope: ``full`` for the current schema,
    ``legacy_structural_needs_review`` for historical 1.0 witnesses
    (old structural rules only; not rewritten, flagged for review).
    """

    if not isinstance(witness, Mapping):
        raise ValueError("witness must be a mapping")
    schema_version = witness.get("schema_version")
    if schema_version == WITNESS_SCHEMA:
        scope = "full"
        _validate_current(witness)
    elif schema_version == LEGACY_WITNESS_SCHEMA:
        scope = "legacy_structural_needs_review"
        _validate_legacy(witness)
    else:
        raise ValueError("witness schema drifted")

    if expected_case_id is not None:
        if witness.get("case_id") != expected_case_id:
            raise ValueError(
                f"witness case binding mismatch: {witness.get('case_id')!r} "
                f"!= {expected_case_id!r}",
            )
    if expected_subject is not None:
        if not isinstance(expected_subject, Mapping):
            raise ValueError("expected_subject must be a subject mapping")
        try:
            pinned_fingerprint = str(subject_fingerprint(expected_subject))
            pinned_commit = str(expected_subject["commit"])
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"expected_subject is not a complete subject: {exc}",
            ) from exc
        if witness.get("lmm_subject_fingerprint") != pinned_fingerprint:
            raise ValueError("witness subject binding mismatch")
        if witness.get("lmm_commit") != pinned_commit:
            raise ValueError("witness subject commit binding mismatch")
    if expected_subject_fingerprint is not None:
        if witness.get("lmm_subject_fingerprint") != expected_subject_fingerprint:
            raise ValueError("witness subject fingerprint binding mismatch")
    if expected_lmm_commit is not None:
        if witness.get("lmm_commit") != expected_lmm_commit:
            raise ValueError("witness subject commit binding mismatch")
    for name, expected_digest in (
        ("run_identity_digest", expected_run_identity_digest),
        ("input_digest", expected_input_digest),
        ("result_digest", expected_result_digest),
        ("audit_manifest_digest", expected_audit_manifest_digest),
    ):
        if expected_digest is None:
            continue
        recorded = witness.get(name)
        if recorded is None:
            raise ValueError(f"witness lacks the {name} needed for binding comparison")
        if digest_text(recorded, name) != digest_text(expected_digest, name):
            raise ValueError(f"witness {name} binding mismatch")
    return {"schema_version": str(schema_version), "validation_scope": scope}


def issue_statuses_of(witness: Mapping[str, Any]) -> dict[str, str]:
    issues = witness.get("issues")
    if not isinstance(issues, dict):
        raise ValueError("witness issues must be an object")
    return dict(issues)
