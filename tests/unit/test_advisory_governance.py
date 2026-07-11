"""规则治理、训练导出、缺失事实、策略与类案ADVISORY门禁。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler_core.analysis import AnalysisError, analyze_similar_cases, analyze_strategy, load_case_index
from compiler_core.audit_bundle import evaluate_to_audit_bundle
from compiler_core.canonical_serialization import semantic_digest
from compiler_core.contracts import CaseRequest
from compiler_core.rule_governance import audit_pack
from compiler_core.rule_packs import RulePackRegistry
from compiler_core.training import export_corpus_pack
from tests.unit.test_audit_bundle import _fixture
from tests.unit.test_rule_pack_manifest import _write_pack


ROOT = Path(__file__).resolve().parents[2]
CASE_INDEX = ROOT / "tests" / "fixtures" / "synthetic_case_index.json"


def _run(tmp_path: Path, *, unknown: bool = False):
    """创建正式或UNKNOWN审计run。"""

    loaded, request = _fixture(tmp_path / "configs")
    if unknown:
        payload = request.to_dict()
        payload["facts"][0]["status"] = "unknown"
        payload["facts"][0]["human_reviewed"] = False
        request = CaseRequest.from_dict(payload)
    state_root = tmp_path / "state"
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=state_root)
    return state_root, bundle


def test_rule_governance_reuses_pack_inventory_and_never_promotes(tmp_path) -> None:
    """治理报告保留candidate ID、source hash和人工promotion边界。"""

    _write_pack(tmp_path / "configs")
    report = audit_pack(RulePackRegistry(tmp_path / "configs"), "fixture-official")

    assert report["status"] == "PASS"
    assert report["inventory"] == {
        "corpus_total": 2,
        "reasoning_eligible_total": 1,
        "candidate_only_total": 1,
    }
    assert report["candidate_rule_ids"] == ["R-CANDIDATE"]
    assert report["source_snapshots"][0]["content_hash"] == "a" * 64
    assert report["promotion"] == {
        "automatic": False,
        "suggestion_only": True,
        "required_action": "run promotion gate and obtain human approval before changing pack status",
    }
    assert report["test_coverage"]["status"] == "BLOCKED"
    assert report["blocking_count"] == 0


def test_training_export_keeps_candidates_and_cannot_write_back_to_pack(tmp_path) -> None:
    """训练导出包含candidate与pack/seed元数据，且不读取案件事实。"""

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
    assert candidate["pack_id"] == "fixture-official"
    assert candidate["split_seed"] == 17
    assert report["private_case_facts_included"] is False
    assert report["promotion"]["automatic"] is False
    assert set(report["artifact_files"]) == {
        "rules_train.jsonl", "rules_dev.jsonl", "rules_test.jsonl", "training_manifest.json",
    }
    with pytest.raises(ValueError, match="cannot be written"):
        export_corpus_pack(registry, "fixture-official", config_root / "generated")
    with pytest.raises(ValueError, match="Git worktree"):
        export_corpus_pack(registry, "fixture-official", ROOT / ".forbidden-training-output")


def test_strategy_is_advisory_and_does_not_modify_canonical_result(tmp_path, monkeypatch) -> None:
    """策略只读审计run，并且不生成certificate或到达evaluator。"""

    state_root, bundle = _run(tmp_path)
    result_path = bundle.run_directory / "result.json"
    before = result_path.read_bytes()

    def explode(*_args, **_kwargs):
        raise AssertionError("analysis reached evaluator")

    monkeypatch.setattr("compiler_core.evaluator.FixpointEvaluator", explode)
    report = analyze_strategy(bundle.result.semantic.run_id, state_root=state_root)

    assert report["analysis_status"] == "ADVISORY"
    assert report["review_required"] is True
    assert report["formal_certificate_generated"] is False
    assert report["paths"][0]["path_type"] == "PRESERVE_FORMAL_BASIS"
    assert report["artifact_ref"].startswith("analysis/")
    assert result_path.read_bytes() == before


def test_unknown_run_exposes_machine_review_data_and_strategy_gap(tmp_path) -> None:
    """UNKNOWN结果带影响规则/结论/回答类型，策略不得补造案情。"""

    state_root, bundle = _run(tmp_path, unknown=True)
    semantic = bundle.result.semantic
    review = semantic.missing_fact_review[0]
    report = analyze_strategy(semantic.run_id, state_root=state_root)

    assert review.fact_id == "fact::a"
    assert review.impacted_rule_ids == ("R-ANCHORED",)
    assert review.impacted_claim_ids == ("claim::a",)
    assert report["paths"][0]["path_type"] == "EVIDENCE_COMPLETION"
    assert report["basis"]["claim_ids"] == []


def test_similar_cases_are_deterministic_fixture_only_and_non_predictive(tmp_path) -> None:
    """合成index只验机制，结构相似不得包装为法院结果预测。"""

    state_root, bundle = _run(tmp_path)
    first = analyze_similar_cases(bundle.result.semantic.run_id, CASE_INDEX, state_root=state_root)
    second = analyze_similar_cases(bundle.result.semantic.run_id, CASE_INDEX, state_root=state_root)

    assert first["quality_status"] == "FIXTURE_ONLY"
    assert [item["case_id"] for item in first["matches"]] == ["fixture::close", "fixture::distant"]
    assert first["matches"][0]["score"] > first["matches"][1]["score"]
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert any("does not predict" in item for item in first["limitations"])
    assert first["formal_certificate_generated"] is False


def test_case_index_tamper_and_invalid_source_hash_fail_closed(tmp_path) -> None:
    """index或逐案来源hash异常不能进入类案排序。"""

    payload = json.loads(CASE_INDEX.read_text(encoding="utf-8"))
    tampered = tmp_path / "tampered.json"
    payload["cases"][0]["case_id"] = "forged"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AnalysisError) as digest_error:
        load_case_index(tampered)
    assert digest_error.value.code == "CASE_INDEX_DIGEST_MISMATCH"

    payload = json.loads(CASE_INDEX.read_text(encoding="utf-8"))
    payload["cases"][0]["source_hash"] = "bad"
    payload["index_digest"] = semantic_digest({key: value for key, value in payload.items() if key != "index_digest"})
    invalid_source = tmp_path / "invalid-source.json"
    invalid_source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AnalysisError) as source_error:
        load_case_index(invalid_source)
    assert source_error.value.code == "INVALID_CASE_INDEX"
