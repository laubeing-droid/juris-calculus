from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from tools.generate_runtime_refinement_receipts import (
    build_receipt,
    canonical_digest,
    fixture_bindings,
    load_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "runtime_refinement"
LMM_COMMIT = "1" * 40
RUNTIME_COMMIT = "2" * 40
EXPECTED_STATUSES = {
    "contract_breach": ("PROVED", "REFUTED", "TAINTED"),
    "fact_admission": ("PROVED", "UNDECIDED", "UNDECIDED"),
    "unknown_timeout": ("UNDECIDED", "UNDECIDED"),
}


def _expected(group: str, statuses: tuple[str, ...] | None = None) -> dict:
    fixture = load_fixture(FIXTURES / f"{group}.fixture.json")
    cases = fixture["source_snapshot"]["cases"]
    source_digests, rule_pack_digest = fixture_bindings(fixture)
    body = {
        "lmm_commit": LMM_COMMIT,
        "cases": [
            {"case_id": case["case_id"], "expected_status": status}
            for case, status in zip(
                cases,
                statuses or EXPECTED_STATUSES[group],
                strict=True,
            )
        ],
        "source_snapshot_digests": source_digests,
        "rule_pack_digest": rule_pack_digest,
        "semantics": {"id": "grounded", "version": "1"},
    }
    return {
        "schema_version": "spec-runtime-refinement-v2",
        "role": "expected",
        "fixture_digest": canonical_digest(body),
        **body,
    }


@pytest.mark.parametrize("group", tuple(EXPECTED_STATUSES))
def test_executable_fixture_emits_runtime_observed_statuses(group: str) -> None:
    fixture = load_fixture(FIXTURES / f"{group}.fixture.json")
    receipt = build_receipt(
        _expected(group),
        fixture,
        runtime_commit=RUNTIME_COMMIT,
        runtime_build_id="test-build",
    )

    assert tuple(row["actual_status"] for row in receipt["cases"]) == EXPECTED_STATUSES[group]
    assert receipt["producer"] == "juris-calculus"
    assert receipt["runtime_commit"] == RUNTIME_COMMIT
    assert receipt["receipt_digest"] == canonical_digest(
        {key: value for key, value in receipt.items() if key != "receipt_digest"}
    )
    assert all(len(row["runtime_evidence_digest"]) == 64 for row in receipt["cases"])


def test_expected_status_is_not_used_to_generate_actual_status() -> None:
    fixture = load_fixture(FIXTURES / "contract_breach.fixture.json")
    receipt = build_receipt(
        _expected("contract_breach", ("UNDECIDED",) * 3),
        fixture,
        runtime_commit=RUNTIME_COMMIT,
        runtime_build_id="test-build",
    )

    assert tuple(row["actual_status"] for row in receipt["cases"]) == (
        "PROVED",
        "REFUTED",
        "TAINTED",
    )


def test_expected_fixture_must_bind_executable_fixture_content() -> None:
    fixture = load_fixture(FIXTURES / "fact_admission.fixture.json")
    expected = deepcopy(_expected("fact_admission"))
    expected["source_snapshot_digests"] = ["0" * 64]
    body = {
        name: expected[name]
        for name in (
            "lmm_commit",
            "cases",
            "source_snapshot_digests",
            "rule_pack_digest",
            "semantics",
        )
    }
    expected["fixture_digest"] = canonical_digest(body)

    with pytest.raises(ValueError, match="does not bind the JC source fixture"):
        build_receipt(
            expected,
            fixture,
            runtime_commit=RUNTIME_COMMIT,
            runtime_build_id="test-build",
        )
