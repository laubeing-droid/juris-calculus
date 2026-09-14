"""Integration test: C06 receipts build and match the pinned expectations.

This exercises the whole receipt-production path — production material,
three public entries, witnesses, cross-entry consistency, and receipt
assembly — without needing the legal-math-modeling checkout. The
independent checker itself runs in the cross-repo verification workflow;
here the receipts are validated against the same pinned expected fixtures
with the verifier's own checks (fixture digest, identity binding, case
statuses, receipt digest).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PINS = ROOT / "proofs" / "lmm-fullmath"
SCHEMA = "spec-runtime-refinement-v2"
GROUPS = ("contract_breach", "fact_admission", "unknown_timeout")


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@pytest.fixture(scope="module")
def receipts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("c06-receipts")
    completed = subprocess.run(  # noqa: S603 - fixed argv
        [
            sys.executable, "-B",
            str(ROOT / "tools" / "generate_c06_entry_receipts.py"),
            "--output-dir", str(output),
        ],
        cwd=str(ROOT), capture_output=True, text=True, check=False, shell=False,
    )
    if completed.returncode != 0:
        pytest.fail("receipt producer failed:\n" + completed.stderr[-2000:])
    return output


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_receipts_match_the_pinned_expected_fixtures(receipts: Path) -> None:
    witnesses = _load(receipts / "witnesses.json")
    consistency = _load(receipts / "consistency.json")
    assert len(witnesses) == 8 * 3 - 2  # the keyless MCP surface is fail-closed
    assert len(consistency) == 8
    for group in GROUPS:
        expected = _load(PINS / "expected" / f"{group}.expected.json")
        receipt = _load(receipts / f"{group}.actual.json")
        assert receipt["schema_version"] == SCHEMA
        assert receipt["role"] == "actual"
        assert receipt["producer"] == "juris-calculus"
        assert receipt["fixture_digest"] == expected["fixture_digest"]
        assert (
            receipt["source_snapshot_digests"]
            == expected["source_snapshot_digests"]
        )
        assert receipt["rule_pack_digest"] == expected["rule_pack_digest"]
        assert receipt["execution_status"] == "SUCCESS"
        body = {key: value for key, value in receipt.items() if key != "receipt_digest"}
        assert _canonical_digest(body) == receipt["receipt_digest"]
        for row in expected["cases"]:
            actual = next(
                item for item in receipt["cases"] if item["case_id"] == row["case_id"]
            )
            assert actual["actual_status"] == row["expected_status"]
            witness = next(
                item for item in witnesses
                if item["case_id"] == row["case_id"]
                and item["witness_digest"] == actual["runtime_evidence_digest"]
            )
            validate = _load_witness_digest(witness)
            assert validate == witness["witness_digest"]


def _load_witness_digest(witness: dict) -> str:
    from compiler_core.canonical_serialization import digest_value

    body = {key: value for key, value in witness.items() if key != "witness_digest"}
    return str(digest_value(body))


def test_every_case_agrees_across_the_entries_it_exercised(receipts: Path) -> None:
    witnesses = _load(receipts / "witnesses.json")
    entries_by_case: dict[str, set[str]] = {}
    for witness in witnesses:
        entries_by_case.setdefault(witness["case_id"], set()).add(witness["entry"])
    assert set(entries_by_case) == {
        "contract::plain", "contract::force-majeure",
        "contract::malformed-certificate", "admission::three-gates-pass",
        "admission::disputed-fact", "admission::revoked-attestation",
        "backend::unknown-outcome", "backend::timeout-outcome",
    }
    for case_id, entries in entries_by_case.items():
        if case_id in {"contract::force-majeure", "backend::timeout-outcome"}:
            # the keyless local surface has no MCP evaluation (fail-closed)
            assert entries == {"jc_client", "cli"}
        else:
            assert entries == {"jc_client", "cli", "mcp"}


def test_receipts_bind_the_pinned_mathematics_subject(receipts: Path) -> None:
    subject = _load(PINS / "MATH_COMPLETION.json")["subject"]
    for group in GROUPS:
        receipt = _load(receipts / f"{group}.actual.json")
        assert receipt["lmm_commit"] == subject["commit"]
        assert len(receipt["runtime_commit"]) == 40
        assert receipt["runtime_build_id"]
