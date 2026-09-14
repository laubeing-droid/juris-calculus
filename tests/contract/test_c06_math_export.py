"""Contract tests for the C06 math-export integration.

These tests guard the pinned legal-math-modeling full-release subject, the
eleven required export interfaces, the B07-shaped cache invalidation, the
witness status mapping and the cross-entry consistency rule. They are pure
JC-side checks: the independent checker itself runs only in the cross-repo
verification lane.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler_core.canonical_serialization import DigestV4, digest_value
from compiler_core.math_export import (
    ATTEMPT,
    LAKE_MANIFEST_SHA256,
    LEAN_TOOLCHAIN_SHA256,
    REPOSITORY,
    REQUIRED_INTERFACES,
    RUNTIME_REF_COMMIT,
    RUN_ID,
    SUBJECT_COMMIT,
    SUBJECT_TREE,
    SubjectCacheKeyV1,
    WITNESS_SCHEMA,
    assert_cross_entry_consistency,
    build_run_witness,
    cache_entry,
    cache_entry_valid,
    contract_fingerprint,
    math_completion_fingerprint,
    subject_fingerprint,
    validate_export_contract,
    validate_math_completion,
    validate_witness,
    version_change_invalidates,
)
from compiler_core.math_export.consistency import CrossEntryInconsistency
from compiler_core.math_export.pins import (
    DO_NOT_RUN_NOW,
    EXTERNAL_ITEM_IDS,
    NOT_ESTABLISHED,
)
from compiler_core.math_export.subject import (
    MathExportContractError,
)
from compiler_core.math_export.witness import (
    DECISION_STATUS_MAPPING_V1,
    ISSUE_STATUS_MAPPING_V1,
)

REPO = Path(__file__).resolve().parents[2]
PINS = REPO / "proofs" / "lmm-fullmath"


def _load(relative: str) -> dict:
    return json.loads((PINS / relative).read_bytes())


def _subject() -> dict:
    return validate_math_completion(_load("MATH_COMPLETION.json"))


def _witness(**overrides: object) -> dict:
    values: dict = {
        "entry": "jc_client",
        "case_id": "contract::plain",
        "probe_semantics": "engineering probe",
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


def test_pins_match_the_pinned_subject_documents() -> None:
    completion = _load("MATH_COMPLETION.json")
    assert completion["status"] == "MATH_BUILD_COMPLETE"
    assert completion["mandatory_registrations"] == 217
    assert completion["not_established"] == list(NOT_ESTABLISHED)
    assert SUBJECT_COMMIT == completion["subject"]["commit"]
    assert SUBJECT_TREE == completion["subject"]["tree"]
    assert REPOSITORY == completion["subject"]["repository"]
    assert RUN_ID == completion["subject"]["run_id"]
    assert ATTEMPT == completion["subject"]["attempt"]
    assert LEAN_TOOLCHAIN_SHA256 == completion["subject"]["lean_toolchain_sha256"]
    assert LAKE_MANIFEST_SHA256 == completion["subject"]["lake_manifest_sha256"]


def test_export_contract_carries_the_eleven_interfaces_and_guards() -> None:
    contract = _load("EXPORT_CONTRACT.json")
    completion = _load("MATH_COMPLETION.json")
    validate_export_contract(contract)
    assert contract["contract"]["required"] == list(REQUIRED_INTERFACES)
    assert contract["contract"]["do_not_run_now"] == list(DO_NOT_RUN_NOW)
    assert [item["id"] for item in contract["external"]["items"]] == list(
        EXTERNAL_ITEM_IDS,
    )
    assert str(contract_fingerprint(contract)).startswith("sha256:")
    assert str(math_completion_fingerprint(completion)).startswith("sha256:")


def test_bindings_extract_binds_the_c06_registrations() -> None:
    extract = _load("BINDINGS_EXTRACT.json")
    assert extract["subject"]["commit"] == SUBJECT_COMMIT
    assert extract["subject"]["runtime_ref_commit"] == RUNTIME_REF_COMMIT
    assert extract["source"]["binding_count"] == 217
    bound = extract["bound_registrations"]
    assert "TARGET:C06" in bound
    assert bound["TARGET:C06"]["theorem"] == (
        "JurisLean.FullMath.Acceptance.target_C06"
    )
    assert bound["TARGET:C06"]["semantic_links"] == [
        "JurisLean.FullMath.Composition.checker_correspondence",
    ]
    assert "TARGET:B07" in bound
    assert bound["TARGET:B07"]["semantic_links"] == [
        "JurisLean.FullMath.Burden.version_change_invalidates",
    ]
    roots = [name for name in bound if name.startswith("ROOT:")]
    assert len(roots) == 7
    assert extract["honest_boundaries"]["not_established"] == list(NOT_ESTABLISHED)


def test_status_mapping_is_total_and_conservative() -> None:
    assert len(set(ISSUE_STATUS_MAPPING_V1.values())) == 4
    assert ISSUE_STATUS_MAPPING_V1["accepted"] == "PROVED"
    assert ISSUE_STATUS_MAPPING_V1["refuted"] == "REFUTED"
    for raw in ("possible", "undecided", "incomplete", "excluded"):
        assert ISSUE_STATUS_MAPPING_V1[raw] == "UNDECIDED"
    assert ISSUE_STATUS_MAPPING_V1["inconsistent"] == "TAINTED"
    assert DECISION_STATUS_MAPPING_V1["accepted_formal_result"] == "PROVED"
    assert DECISION_STATUS_MAPPING_V1["conflict_certificate"] == "REFUTED"
    for raw in (
        "hypothetical_result", "review_only_result", "missing_required_fact",
        "unknown",
    ):
        assert DECISION_STATUS_MAPPING_V1[raw] == "UNDECIDED"
    for raw in ("blocked", "engine_error"):
        assert DECISION_STATUS_MAPPING_V1[raw] == "TAINTED"


def test_witness_rejected_input_maps_to_tainted() -> None:
    witness = _witness(
        case_id="contract::malformed-certificate",
        decision_status=None,
        intake_error_code="FACT_DIGEST_MISMATCH",
    )
    assert witness["status"] == "TAINTED"
    assert witness["decision_status"] == "intake_rejected"
    validate_witness(witness)


def test_witness_focus_issue_decides_and_digest_seals() -> None:
    witness = _witness(
        case_id="contract::force-majeure",
        decision_status="accepted_formal_result",
        issue_statuses={"base": "refuted", "exception": "accepted"},
        focus_issue="base",
    )
    assert witness["status"] == "REFUTED"
    assert witness["issues"] == {"base": "REFUTED", "exception": "PROVED"}
    validate_witness(witness)
    forged = dict(witness)
    forged["status"] = "PROVED"
    with pytest.raises(ValueError):
        validate_witness(forged)


def test_witness_fingerprint_binds_the_mathematics_subject() -> None:
    witness = _witness()
    subject = dict(_subject())
    witness2 = _witness(lmm_subject=subject)
    assert (
        witness["lmm_subject_fingerprint"]
        == witness2["lmm_subject_fingerprint"]
    )
    drifted = dict(_subject())
    drifted["commit"] = "b" * 40
    witness3 = _witness(lmm_subject=drifted)
    assert witness3["lmm_subject_fingerprint"] != witness["lmm_subject_fingerprint"]


def test_cross_entry_consistency_passes_and_fails_closed() -> None:
    witnesses = [
        _witness(entry=entry) for entry in ("jc_client", "cli", "mcp")
    ]
    summary = assert_cross_entry_consistency(witnesses)
    assert summary["contract::plain"]["agreement"] is True
    assert summary["contract::plain"]["entries"] == ["cli", "jc_client", "mcp"]
    with pytest.raises(CrossEntryInconsistency):
        assert_cross_entry_consistency([
            _witness(entry="jc_client"),
            _witness(entry="cli", decision_status="unknown"),
        ])
    with pytest.raises(CrossEntryInconsistency):
        assert_cross_entry_consistency([_witness(entry="jc_client")])


def test_cache_key_invalidation_mirrors_b07() -> None:
    import dataclasses

    pinned = SubjectCacheKeyV1.pinned()
    same = SubjectCacheKeyV1(
        commit=SUBJECT_COMMIT,
        tree=SUBJECT_TREE,
        lean_toolchain_sha256=LEAN_TOOLCHAIN_SHA256,
        lake_manifest_sha256=LAKE_MANIFEST_SHA256,
    )
    assert pinned == same
    assert not version_change_invalidates(pinned, same)
    for field in ("commit", "tree", "lean_toolchain_sha256", "lake_manifest_sha256"):
        drifted = dataclasses.replace(
            pinned,
            **{field: "f" * 64 if field != "commit" else "f" * 40},
        )
        assert version_change_invalidates(pinned, drifted) is True
        assert drifted.fingerprint() != pinned.fingerprint()


def test_cache_entry_sealed_by_subject_fingerprint() -> None:
    key = SubjectCacheKeyV1.pinned()
    entry = cache_entry(key, DigestV4("sha256:" + "1" * 64))
    assert cache_entry_valid(entry, key)
    assert cache_entry_valid(entry, SubjectCacheKeyV1.pinned())
    drifted = dict(entry)
    drifted["cache_key"] = {**entry["cache_key"], "commit": "e" * 40}
    assert not cache_entry_valid(drifted, key)
    refingerprinted = dict(entry)
    refingerprinted["subject_fingerprint"] = str(
        SubjectCacheKeyV1(
            commit="e" * 40,
            tree=SUBJECT_TREE,
            lean_toolchain_sha256=LEAN_TOOLCHAIN_SHA256,
            lake_manifest_sha256=LAKE_MANIFEST_SHA256,
        ).fingerprint(),
    )
    assert not cache_entry_valid(refingerprinted, key)
    truncated = dict(entry)
    truncated["payload_digest"] = "sha256:short"
    assert not cache_entry_valid(truncated, key)


def test_document_drift_fails_closed() -> None:
    completion = _load("MATH_COMPLETION.json")
    drifted = json.loads(json.dumps(completion))
    drifted["status"] = "MATH_BUILD_COMPLETE_BUT_MORE"
    with pytest.raises(MathExportContractError):
        validate_math_completion(drifted)
    drained = json.loads(json.dumps(completion))
    drained["not_established"] = []
    with pytest.raises(MathExportContractError):
        validate_math_completion(drained)
    contract = _load("EXPORT_CONTRACT.json")
    trimmed = json.loads(json.dumps(contract))
    trimmed["contract"]["required"] = list(REQUIRED_INTERFACES)[:-1]
    with pytest.raises(MathExportContractError):
        validate_export_contract(trimmed)


def test_subject_fingerprint_is_canonical_and_stable() -> None:
    subject = _subject()
    first = subject_fingerprint(subject)
    reordered = {key: subject[key] for key in reversed(list(subject))}
    assert first == subject_fingerprint(reordered)
    assert first == digest_value(subject)
    assert str(first).startswith("sha256:")
