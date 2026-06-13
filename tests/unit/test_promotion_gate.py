#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from tools.promotion_gate import evaluate_batch, evaluate_candidate


def test_evaluate_candidate_passes_with_all_gates():
    candidate = {"candidate_id": "C1", "source_spans": ["statute:1"], "confidence": 0.8, "rollback_trigger": "benchmark_regression"}
    gates = {g: "PASS" for g in ["source_anchor", "type_check", "relevance_benchmark", "smt_sidecar", "shadow_divergence", "neural_contract_auditor", "promotion_policy"]}
    report = evaluate_candidate(candidate, gates)
    assert report["state"] == "FINAL_AUTOMATED"
    assert report["status"] == "PASS"


def test_evaluate_candidate_promotable_without_rollback():
    candidate = {"candidate_id": "C1", "source_spans": ["statute:1"], "confidence": 0.8}
    gates = {g: "PASS" for g in ["source_anchor", "type_check", "relevance_benchmark", "smt_sidecar", "shadow_divergence", "neural_contract_auditor", "promotion_policy"]}
    report = evaluate_candidate(candidate, gates)
    assert report["state"] == "PROMOTABLE"


def test_evaluate_candidate_blocks_without_source_spans():
    candidate = {"candidate_id": "C1", "source_spans": [], "confidence": 0.8}
    gates = {"source_anchor": "PASS"}
    report = evaluate_candidate(candidate, gates)
    assert report["state"] == "BLOCKED"


def test_evaluate_candidate_blocks_missing_gate():
    candidate = {"candidate_id": "C1", "source_spans": ["statute:1"], "confidence": 0.8}
    gates = {"source_anchor": "PASS"}
    report = evaluate_candidate(candidate, gates)
    assert any("GATE_MISSING" in i["issue"] for i in report["issues"])


def test_evaluate_batch_handles_multiple(tmp_path):
    path = tmp_path / "candidates.jsonl"
    path.write_text(
        json.dumps({"candidate_id": "C1", "source_spans": ["s1"], "confidence": 0.9, "rollback_trigger": "r1"}, ensure_ascii=False) + "\n" +
        json.dumps({"candidate_id": "C2", "source_spans": [], "confidence": 0.9}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    gates = {g: "PASS" for g in ["source_anchor", "type_check", "relevance_benchmark", "smt_sidecar", "shadow_divergence", "neural_contract_auditor", "promotion_policy"]}
    report = evaluate_batch(path, gates)
    assert report["candidate_count"] == 2
    assert report["passed_count"] == 1
