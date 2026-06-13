#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from compiler_core.semantic_compiler_contract import (
    CandidateFact, CandidateRule, CandidateStatus,
    CompilerContract, CompilerRequest, CompilerResponse, CompilerTask, validate_response,
)
from tools.semantic_compile_batch import compile_batch


def test_validate_response_passes_when_complete():
    response = CompilerResponse(
        request_id="REQ-1",
        status=CandidateStatus.CANDIDATE,
        facts=[CandidateFact(fact_id="F1", description="fact desc", source_span="span", confidence=0.5)],
        rules=[CandidateRule(rule_id_suggestion="R1", conclusion="claim", premises=["p1"], source_span="span", confidence=0.5)],
    )
    report = validate_response(response)
    assert report["contract_status"] == "PASS"


def test_validate_response_flags_missing_ids():
    response = CompilerResponse(request_id="REQ-1", status=CandidateStatus.CANDIDATE, rules=[CandidateRule(rule_id_suggestion="", conclusion="")])
    report = validate_response(response)
    assert report["contract_status"] == "FAIL"


def test_compile_batch_with_mock_provider(tmp_path):
    requests_path = tmp_path / "requests.jsonl"
    requests_path.write_text(
        json.dumps({"request_id": "REQ-1", "task": "rule_extraction", "text": "Section 1: a contract shall be valid if...", "jurisdiction": "test", "input_hash": "hash1"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "out.jsonl"
    contract = CompilerContract(provider="mock", model_id="mock/v0")
    report = compile_batch(requests_path, contract, out=out_path)
    assert report["status"] == "PASS"
    assert report["passed_count"] == 1
    out_data = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert out_data[0]["model"]["provider"] == "mock"


def test_compile_batch_dry_run_sets_needs_context(tmp_path):
    requests_path = tmp_path / "requests.jsonl"
    requests_path.write_text(
        json.dumps({"request_id": "REQ-1", "task": "rule_extraction", "text": "text", "jurisdiction": "test", "input_hash": "h"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    contract = CompilerContract(provider="mock", model_id="mock/v0")
    report = compile_batch(requests_path, contract, dry_run=True)
    assert report["status"] == "PASS"


def test_compile_batch_with_empty_request(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n", encoding="utf-8")
    contract = CompilerContract(provider="mock", model_id="mock/v0")
    report = compile_batch(path, contract)
    assert report["request_count"] == 0
    assert report["status"] == "PASS"

