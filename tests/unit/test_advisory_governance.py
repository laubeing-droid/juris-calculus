"""Offline governance, training, and verified-bundle advisory source tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler_core.analysis import (
    AnalysisError,
    analyze_similar_cases,
    analyze_strategy,
    load_case_index,
)
from compiler_core.canonical_serialization import semantic_digest
from compiler_core.rule_governance import audit_pack
from compiler_core.rule_packs import RulePackRegistry
from compiler_core.training import export_corpus_pack
from tests.contract.test_audit_bundle import _fixture as _audit_fixture
from tests.unit.test_rule_pack_manifest import _write_pack


ROOT = Path(__file__).resolve().parents[2]
CASE_INDEX = ROOT / "tests/fixtures/synthetic_case_index.json"


def _verified_bundle(tmp_path: Path):
    _, _, bundles, capability, materials, _ = _audit_fixture(tmp_path)
    verified = bundles.write_run(
        capability,
        materials,
        now=materials.request.decision_time,
    )
    return verified


def test_rule_governance_remains_offline_and_never_promotes(tmp_path) -> None:
    _write_pack(tmp_path / "configs")
    report = audit_pack(RulePackRegistry(tmp_path / "configs"), "fixture-official")

    assert report["inventory"] == {
        "corpus_total": 2,
        "reasoning_eligible_total": 1,
        "candidate_only_total": 1,
    }
    assert report["candidate_rule_ids"] == ["R-CANDIDATE"]
    assert report["promotion"]["automatic"] is False
    assert report["test_coverage"]["status"] == "BLOCKED"


def test_training_export_keeps_candidates_outside_repository(tmp_path) -> None:
    config_root = tmp_path / "configs"
    _write_pack(config_root)
    registry = RulePackRegistry(config_root)
    output = tmp_path / "training"
    report = export_corpus_pack(registry, "fixture-official", output, seed=17)
    records = [
        json.loads(line)
        for name in ("rules_train.jsonl", "rules_dev.jsonl", "rules_test.jsonl")
        for line in (output / name).read_text(encoding="utf-8").splitlines()
    ]

    candidate = next(item for item in records if item["id"] == "R-CANDIDATE")
    assert candidate["admission_status"] == "CANDIDATE_ONLY"
    assert report["private_case_facts_included"] is False
    assert report["promotion"]["automatic"] is False
    with pytest.raises(ValueError, match="cannot be written"):
        export_corpus_pack(registry, "fixture-official", config_root / "generated")
    with pytest.raises(ValueError, match="Git worktree"):
        export_corpus_pack(registry, "fixture-official", ROOT / ".forbidden-training-output")


def test_strategy_requires_verified_v4_bundle_and_preserves_result(tmp_path) -> None:
    verified = _verified_bundle(tmp_path)
    before = verified.result.to_dict()

    report = analyze_strategy(verified, output_root=tmp_path / "source-tool-output")

    assert report["analysis_status"] == "ADVISORY"
    assert report["review_required"] is True
    assert report["formal_certificate_generated"] is False
    assert report["run_id"] == verified.run_identity.run_digest.hex
    assert report["result_digest"] == verified.result.result_digest.hex
    assert verified.result.to_dict() == before
    assert report["artifact_ref"].startswith("analysis/")
    with pytest.raises(AnalysisError) as caught:
        analyze_strategy(object(), output_root=tmp_path / "rejected")
    assert caught.value.code == "VERIFIED_BUNDLE_REQUIRED"


def test_similar_cases_are_deterministic_bounded_and_non_predictive(tmp_path) -> None:
    verified = _verified_bundle(tmp_path)
    output = tmp_path / "source-tool-output"

    first = analyze_similar_cases(verified, CASE_INDEX, output_root=output, limit=1)
    second = analyze_similar_cases(verified, CASE_INDEX, output_root=output, limit=1)

    assert first["quality_status"] == "FIXTURE_ONLY"
    assert len(first["matches"]) == 1
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert any("does not predict" in item for item in first["limitations"])
    assert first["formal_certificate_generated"] is False


def test_case_index_tamper_and_invalid_source_hash_fail_closed(tmp_path) -> None:
    payload = json.loads(CASE_INDEX.read_text(encoding="utf-8"))
    tampered = tmp_path / "tampered.json"
    payload["cases"][0]["case_id"] = "forged"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AnalysisError) as digest_error:
        load_case_index(tampered)
    assert digest_error.value.code == "CASE_INDEX_DIGEST_MISMATCH"

    payload = json.loads(CASE_INDEX.read_text(encoding="utf-8"))
    payload["cases"][0]["source_hash"] = "bad"
    payload["index_digest"] = semantic_digest({
        key: value for key, value in payload.items() if key != "index_digest"
    }).removeprefix("sha256:")
    invalid_source = tmp_path / "invalid-source.json"
    invalid_source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AnalysisError) as source_error:
        load_case_index(invalid_source)
    assert source_error.value.code == "INVALID_CASE_INDEX"
