"""JC-01/JC-02 witness guard regressions (math-downstream cases).

JC-01: a whole-run failure (``engine_error``, ``blocked``) or an intake
rejection must never be upgraded into a successful run witness by a
locally accepted focus issue; a legally incomplete but usable run keeps
its verified per-issue results. A run-level ``conflict_certificate``
does not name a defeated claim, so without an issue-level refuted row
it may not read REFUTED.

JC-02: five self-consistent fields plus a recomputed digest are not a
validated witness. Full typed structure, cross-field coherence and the
expected bindings (case, subject, input/result/audit digests) supplied
by the real caller must all hold; a recomputed self-digest alone proves
nothing about the content.
"""
from __future__ import annotations

import pytest

from compiler_core.canonical_serialization import digest_value
from compiler_core.math_export import (
    SUBJECT_COMMIT,
    WITNESS_SCHEMA,
    build_run_witness,
    validate_math_completion,
    validate_witness,
)
from compiler_core.math_export.witness import witness_body

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PINS = REPO / "proofs" / "lmm-fullmath"


def _subject() -> dict:
    return validate_math_completion(
        json.loads((PINS / "MATH_COMPLETION.json").read_bytes()),
    )


def _witness(**overrides: object) -> dict:
    values: dict = {
        "entry": "jc_client",
        "case_id": "guard::plain",
        "probe_semantics": "jc-01/jc-02 witness guard probe",
        "lmm_subject": _subject(),
        "engine_version": "5.0.1",
        "engine_build_digest": "sha256:" + "a" * 64,
        "run_identity_digest": "sha256:" + "b" * 64,
        "input_digest": "sha256:" + "c" * 64,
        "result_digest": "sha256:" + "d" * 64,
        "audit_manifest_digest": "sha256:" + "e" * 64,
        "decision_status": "accepted_formal_result",
        "issue_statuses": {},
    }
    values.update(overrides)
    return build_run_witness(**values)


# ---------------------------------------------------------------------------
# JC-01: whole-run failure cannot be upgraded by a focus issue
# ---------------------------------------------------------------------------


def test_jc01_engine_error_with_accepted_focus_is_not_proved() -> None:
    """engine_error + accepted focus issue must stay a failed run."""

    witness = _witness(
        case_id="guard::engine-error-focus",
        decision_status="engine_error",
        issue_statuses={"issue": "accepted"},
        focus_issue="issue",
    )
    assert witness["status"] == "TAINTED"
    assert witness["decision_status"] == "engine_error"
    validate_witness(witness)


def test_jc01_blocked_run_with_accepted_focus_is_not_proved() -> None:
    """blocked is a whole-run unavailability, not a per-issue verdict."""

    witness = _witness(
        case_id="guard::blocked-focus",
        decision_status="blocked",
        issue_statuses={"issue": "accepted"},
        focus_issue="issue",
    )
    assert witness["status"] == "TAINTED"
    validate_witness(witness)


def test_jc01_engine_error_with_refuted_focus_is_not_refuted() -> None:
    """No decisive reading at all may be granted from a failed run."""

    witness = _witness(
        case_id="guard::engine-error-refuted-focus",
        decision_status="engine_error",
        issue_statuses={"issue": "refuted"},
        focus_issue="issue",
    )
    assert witness["status"] == "TAINTED"
    validate_witness(witness)


def test_jc01_legal_partial_focus_result_is_kept() -> None:
    """One focus issue accepted while another is undecided stays PROVED."""

    witness = _witness(
        case_id="guard::partial-focus",
        decision_status="hypothetical_result",
        issue_statuses={"focus": "accepted", "other": "undecided"},
        focus_issue="focus",
    )
    assert witness["status"] == "PROVED"
    assert witness["issues"] == {"focus": "PROVED", "other": "UNDECIDED"}
    validate_witness(witness)


def test_jc01_intake_rejection_never_has_a_focus_upgraded_status() -> None:
    witness = _witness(
        case_id="guard::intake-rejected",
        decision_status=None,
        intake_error_code="FACT_DIGEST_MISMATCH",
        issue_statuses={"issue": "accepted"},
        focus_issue="issue",
    )
    assert witness["status"] == "TAINTED"
    assert witness["issues"] == {}
    assert witness["focus_issue"] is None
    validate_witness(witness)


def test_jc01_conflict_certificate_alone_is_not_a_refutation() -> None:
    """A run-level conflict certificate does not name the defeated claim."""

    witness = _witness(
        case_id="guard::conflict-no-focus",
        decision_status="conflict_certificate",
        issue_statuses={},
        focus_issue=None,
    )
    assert witness["status"] == "UNDECIDED"
    assert witness["decision_status"] == "conflict_certificate"
    validate_witness(witness)


def test_jc01_refuted_focus_issue_decides_the_conflict_run() -> None:
    """The legal refuted path: an issue-level refuted row reads REFUTED."""

    witness = _witness(
        case_id="guard::conflict-refuted-focus",
        decision_status="conflict_certificate",
        issue_statuses={"base": "refuted", "exception": "accepted"},
        focus_issue="base",
    )
    assert witness["status"] == "REFUTED"
    validate_witness(witness)


# ---------------------------------------------------------------------------
# JC-02: validation is full structure + real bindings, not a self-digest
# ---------------------------------------------------------------------------


def _forged(fields: dict) -> dict:
    body = {
        "schema_version": WITNESS_SCHEMA,
        "producer": "juris-calculus",
        "entry": "cli",
        "status": "PROVED",
    }
    body.update(fields)
    body["witness_digest"] = str(digest_value(body))
    return body


def test_jc02_five_field_witness_with_recomputed_digest_is_rejected() -> None:
    """The observed counterexample: schema/producer/entry/status + digest."""

    with pytest.raises(ValueError):
        validate_witness(_forged({}))


def test_jc02_witness_missing_each_required_field_is_rejected() -> None:
    baseline = _witness()
    for field in (
        "case_id", "probe_semantics", "lmm_subject_fingerprint", "lmm_commit",
        "juris_calculus", "run_identity_digest", "input_digest",
        "result_digest", "audit_manifest_digest", "decision_status",
        "intake_error_code", "focus_issue", "issues", "status",
    ):
        stripped = {
            key: value for key, value in baseline.items() if key != field
        }
        stripped["witness_digest"] = str(digest_value(witness_body(stripped)))
        with pytest.raises(ValueError):
            validate_witness(stripped)


def test_jc02_wrong_typed_fields_are_rejected() -> None:
    baseline = _witness()

    def _retyped(field: str, value: object) -> dict:
        forged = dict(baseline)
        forged[field] = value
        forged["witness_digest"] = str(digest_value(witness_body(forged)))
        return forged

    for field, value in (
        ("case_id", 15), ("probe_semantics", None), ("lmm_commit", "zz"),
        ("lmm_subject_fingerprint", "sha256:short"),
        ("input_digest", "sha256:" + "c" * 63),
        ("result_digest", "not-a-digest"), ("issues", ["PROVED"]),
        ("issues", {"i": "MAYBE"}), ("status", "MAYBE"),
        ("juris_calculus", {"engine_version": 5}),
    ):
        with pytest.raises(ValueError):
            validate_witness(_retyped(field, value))


def test_jc02_incoherent_intake_shape_is_rejected() -> None:
    baseline = _witness(decision_status=None, intake_error_code="FACT_DIGEST_MISMATCH")
    assert baseline["status"] == "TAINTED"

    def _reforged(**changes: object) -> dict:
        forged = dict(baseline)
        forged.update(changes)
        forged["witness_digest"] = str(digest_value(witness_body(forged)))
        return forged

    with pytest.raises(ValueError):
        # intake rejection with a decisive status claimed
        validate_witness(_reforged(status="PROVED"))
    with pytest.raises(ValueError):
        # intake rejection that still carries issue rows
        validate_witness(_reforged(issues={"i": "PROVED"}))
    with pytest.raises(ValueError):
        # intake rejection recorded under a real decision status
        validate_witness(_reforged(decision_status="accepted_formal_result"))


def test_jc02_focus_issue_without_matching_row_is_rejected() -> None:
    baseline = _witness(issue_statuses={"base": "accepted"}, focus_issue="base")
    forged = dict(baseline)
    forged["focus_issue"] = "missing-issue"
    forged["witness_digest"] = str(digest_value(witness_body(forged)))
    with pytest.raises(ValueError):
        validate_witness(forged)


def test_jc02_engine_error_body_claiming_proved_is_rejected() -> None:
    """Recomputed digest does not legitimize contradictory content."""

    baseline = _witness(
        decision_status="engine_error",
        issue_statuses={"issue": "accepted"},
        focus_issue="issue",
    )
    forged = dict(baseline)
    forged["status"] = "PROVED"
    forged["witness_digest"] = str(digest_value(witness_body(forged)))
    with pytest.raises(ValueError):
        validate_witness(forged)


def test_jc02_expected_bindings_are_actually_compared() -> None:
    witness = _witness(case_id="guard::bindings")
    validate_witness(witness, expected_case_id="guard::bindings")

    def _reject(**kwargs: object) -> None:
        with pytest.raises(ValueError):
            validate_witness(witness, **kwargs)

    _reject(expected_case_id="guard::other-case")
    _reject(expected_subject={"commit": "b" * 40})
    _reject(expected_subject_fingerprint="sha256:" + "0" * 64)
    _reject(expected_lmm_commit="a" * 40)
    _reject(expected_input_digest="sha256:" + "0" * 64)
    _reject(expected_result_digest="sha256:" + "0" * 64)
    _reject(expected_audit_manifest_digest="sha256:" + "0" * 64)
    _reject(expected_run_identity_digest="sha256:" + "0" * 64)

    drifted = dict(_subject())
    drifted["commit"] = "b" * 40
    _reject(expected_subject=drifted)

    validate_witness(
        witness,
        expected_case_id="guard::bindings",
        expected_subject=_subject(),
        expected_lmm_commit=SUBJECT_COMMIT,
        expected_input_digest=witness["input_digest"],
        expected_result_digest=witness["result_digest"],
        expected_audit_manifest_digest=witness["audit_manifest_digest"],
        expected_run_identity_digest=witness["run_identity_digest"],
    )


def test_jc02_legacy_witness_validates_with_limited_scope() -> None:
    """Historical 1.0 witnesses stay readable but are marked for review."""

    legacy = _witness()
    legacy["schema_version"] = "jc/lmm-c06-witness/1.0"
    legacy.pop("status_scope", None)
    legacy["witness_digest"] = str(digest_value(witness_body(legacy)))
    result = validate_witness(legacy)
    assert result["schema_version"] == "jc/lmm-c06-witness/1.0"
    assert result["validation_scope"] == "legacy_structural_needs_review"

    current = validate_witness(_witness())
    assert current["validation_scope"] == "full"
    assert current["schema_version"] == WITNESS_SCHEMA
