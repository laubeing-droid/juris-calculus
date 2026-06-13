#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.llm_batch_contract import create_batch, validate_candidates
from tools.llm_batch_acceptor import accept_ir_migration_repair_batch
from tools.llm_batch_orchestrator import gate_and_prepare_next
from tools.rule_to_ir_migrator import discover_rule_sources, migrate_rule_file


def test_rule_to_ir_migrator_writes_sidecar_without_touching_source(tmp_path):
    source = Path("tests/fixtures/rule_migration_sample.yaml")
    before = source.read_text(encoding="utf-8")
    out = tmp_path / "sample.ir.yaml"

    report = migrate_rule_file(source, out=out, jurisdiction="test")

    assert report["status"] == "PASS"
    assert report["migrated_count"] == 2
    assert report["blocking_count"] == 0
    assert source.read_text(encoding="utf-8") == before
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["schema"] == "legal_ir_v3"
    assert data["rules"][0]["rule_id"] == "R-SAMPLE-1"
    assert data["rules"][0]["exceptions"] == ["R-SAMPLE-2"]


def test_rule_source_discovery_includes_addon_paths():
    sources = discover_rule_sources()
    paths = {item["path"] for item in sources}

    assert "configs/zh_CN/rules.yaml" in paths
    assert "configs/hk/rules.yaml" in paths
    assert "configs/en_US/US_Adapter.yaml" in paths
    assert any(item["source"] == "addon" and item["jurisdiction"] == "us" for item in sources)


def test_rule_to_ir_migrator_writes_repair_requests_for_textual_exceptions(tmp_path):
    source = Path("tests/fixtures/rule_migration_sample.yaml")
    repair_out = tmp_path / "repair_requests.jsonl"

    report = migrate_rule_file(source, jurisdiction="test", repair_requests_out=repair_out)

    assert report["status"] == "PASS"
    assert report["repair_request_count"] == 0

    legacy = tmp_path / "legacy_textual_exception.yaml"
    legacy.write_text(
        yaml.safe_dump(
            {
                "rules": [
                    {
                        "id": "R-TEXT",
                        "premise_atoms": ["contract_exists"],
                        "head_claim": "Claim_Available",
                        "exception_chain": ["除非已经超过诉讼时效", "除非存在法定免责事由"],
                        "head_type": "HORN",
                        "source_anchor": "sample-authority:3",
                        "jurisdiction": "test",
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    report = migrate_rule_file(legacy, jurisdiction="test", repair_requests_out=repair_out)

    assert report["status"] == "PASS"
    assert report["repair_request_count"] == 2
    requests = [json.loads(line) for line in repair_out.read_text(encoding="utf-8").splitlines()]
    assert len({request["request_id"] for request in requests}) == 2
    assert all(request["task"] == "ir_migration_repair" for request in requests)
    assert all(request["constraints"]["repo_write_allowed"] is False for request in requests)
    assert {request["input"]["textual_exception"] for request in requests} == {
        "除非已经超过诉讼时效",
        "除非存在法定免责事由",
    }


def test_llm_batch_contract_creates_isolated_requests(tmp_path):
    manifest = create_batch(
        "BATCH_TEST",
        ["rule_extraction", "source_span_alignment"],
        out_root=tmp_path,
    )

    root = Path(manifest["batch_root"])
    requests = (root / "input" / "requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert manifest["repo_write_allowed"] is False
    assert len(requests) == 2
    first = json.loads(requests[0])
    assert first["constraints"]["repo_write_allowed"] is False
    assert first["constraints"]["must_return_jsonl"] is True


def test_llm_batch_contract_validates_candidate_schema(tmp_path):
    path = tmp_path / "candidates.jsonl"
    candidate = {
        "candidate_id": "C1",
        "batch_id": "BATCH_TEST",
        "request_id": "BATCH_TEST-REQ-0001",
        "task": "rule_extraction",
        "status": "candidate",
        "jurisdiction": "test",
        "domain": "contract",
        "source_ref": "sample",
        "source_span": "sample-authority text",
        "source_span_start": 0,
        "source_span_end": 21,
        "input_hash": "abc",
        "output": {"rule_id_suggestion": "R1"},
        "confidence": 0.7,
        "known_limitations": [],
        "model": {"provider": "cheap-api", "model_id": "bulk", "version": "1"},
    }
    path.write_text(json.dumps(candidate, ensure_ascii=False) + "\n", encoding="utf-8")

    report = validate_candidates(path, batch_id="BATCH_TEST")

    assert report["status"] == "PASS"
    assert report["candidate_count"] == 1


def test_llm_batch_contract_blocks_governance_claims(tmp_path):
    path = tmp_path / "bad.jsonl"
    candidate = {
        "candidate_id": "C1",
        "batch_id": "BATCH_TEST",
        "request_id": "BATCH_TEST-REQ-0001",
        "task": "rule_extraction",
        "status": "FINAL_AUTOMATED",
        "jurisdiction": "test",
        "domain": "contract",
        "source_ref": "sample",
        "source_span": None,
        "source_span_start": None,
        "source_span_end": None,
        "input_hash": "abc",
        "output": {"claim": "final legal truth"},
        "confidence": 1.2,
        "known_limitations": "none",
        "model": {},
    }
    path.write_text(json.dumps(candidate, ensure_ascii=False) + "\n", encoding="utf-8")

    report = validate_candidates(path, batch_id="BATCH_TEST")

    assert report["status"] == "FAIL"
    issues = {finding["issue"] for finding in report["findings"]}
    assert "INVALID_STATUS:FINAL_AUTOMATED" in issues
    assert "INVALID_CONFIDENCE" in issues
    assert "KNOWN_LIMITATIONS_NOT_LIST" in issues
    assert "FORBIDDEN_CLAIM:final" in issues


def test_llm_batch_acceptor_accepts_matching_ir_repair_candidate(tmp_path):
    root = tmp_path / "BATCH_ACCEPT"
    (root / "input").mkdir(parents=True)
    (root / "output").mkdir()
    request = {
        "request_id": "REQ-1",
        "batch_id": "BATCH_ACCEPT",
        "task": "ir_migration_repair",
        "input": {
            "rule_id": "R1",
            "textual_exception": "除非已经超过诉讼时效",
            "jurisdiction": "test",
        },
        "constraints": {"repo_write_allowed": False},
        "input_hash": "hash",
    }
    candidate = {
        "candidate_id": "C1",
        "batch_id": "BATCH_ACCEPT",
        "request_id": "REQ-1",
        "task": "ir_migration_repair",
        "status": "candidate",
        "jurisdiction": "test",
        "domain": "contract",
        "source_ref": "R1",
        "source_span": "除非已经超过诉讼时效",
        "source_span_start": None,
        "source_span_end": None,
        "input_hash": "hash",
        "output": {
            "original_candidate_id": "R1",
            "repair_type": "missing_anchor",
            "proposed_patch": {
                "exception_rule_id_suggestion": "R1-EX-01",
                "parent_rule_id": "R1",
                "trigger": "除非已经超过诉讼时效",
                "effect": "parent_rule_not_triggered",
                "suggested_rule_type": "exception",
            },
        },
        "confidence": 0.7,
        "known_limitations": ["source anchor missing"],
        "model": {"provider": "cheap-api", "model_id": "bulk", "version": None},
    }
    (root / "input" / "requests.jsonl").write_text(json.dumps(request, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "output" / "candidates.jsonl").write_text(json.dumps(candidate, ensure_ascii=False) + "\n", encoding="utf-8")

    report = accept_ir_migration_repair_batch(root)

    assert report["status"] == "ACCEPTED"
    assert report["accepted_count"] == 1
    assert (root / "notes" / "codex_acceptance_report.json").exists()


def test_llm_batch_acceptor_writes_repair_requests_for_mismatch(tmp_path):
    root = tmp_path / "BATCH_REPAIR"
    (root / "input").mkdir(parents=True)
    (root / "output").mkdir()
    request = {
        "request_id": "REQ-1",
        "batch_id": "BATCH_REPAIR",
        "task": "ir_migration_repair",
        "input": {
            "rule_id": "R1",
            "textual_exception": "除非已经超过诉讼时效",
            "jurisdiction": "test",
        },
        "constraints": {"repo_write_allowed": False},
        "input_hash": "hash",
    }
    candidate = {
        "candidate_id": "C1",
        "batch_id": "BATCH_REPAIR",
        "request_id": "REQ-1",
        "task": "ir_migration_repair",
        "status": "candidate",
        "jurisdiction": "test",
        "domain": "contract",
        "source_ref": "R1",
        "source_span": "错误文本",
        "source_span_start": None,
        "source_span_end": None,
        "input_hash": "hash",
        "output": {
            "original_candidate_id": "R1",
            "repair_type": "missing_anchor",
            "proposed_patch": {
                "exception_rule_id_suggestion": "R1-EX-01",
                "parent_rule_id": "R1",
                "trigger": "错误文本",
                "effect": "parent_rule_not_triggered",
                "suggested_rule_type": "exception",
            },
        },
        "confidence": 0.7,
        "known_limitations": ["source anchor missing"],
        "model": {"provider": "cheap-api", "model_id": "bulk", "version": None},
    }
    (root / "input" / "requests.jsonl").write_text(json.dumps(request, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "output" / "candidates.jsonl").write_text(json.dumps(candidate, ensure_ascii=False) + "\n", encoding="utf-8")

    report = accept_ir_migration_repair_batch(root)

    assert report["status"] == "REPAIRABLE"
    assert report["repairable_count"] == 1
    repair_path = root / "repair" / "validator_repair_requests.jsonl"
    assert repair_path.exists()
    repair = json.loads(repair_path.read_text(encoding="utf-8").strip())
    assert "SOURCE_SPAN_MUST_EQUAL_TEXTUAL_EXCEPTION" in repair["input"]["validator_issues"]


def test_llm_batch_orchestrator_prepares_next_repair_batch(tmp_path):
    root = tmp_path / "BATCH_REPAIR"
    (root / "input").mkdir(parents=True)
    (root / "output").mkdir()
    (root / "input" / "third_party_llm_work_order.md").write_text("work order", encoding="utf-8")
    request = {
        "request_id": "REQ-1",
        "batch_id": "BATCH_REPAIR",
        "task": "ir_migration_repair",
        "input": {
            "rule_id": "R1",
            "textual_exception": "除非已经超过诉讼时效",
            "jurisdiction": "test",
        },
        "constraints": {"repo_write_allowed": False},
        "input_hash": "hash",
    }
    candidate = {
        "candidate_id": "C1",
        "batch_id": "BATCH_REPAIR",
        "request_id": "REQ-1",
        "task": "ir_migration_repair",
        "status": "candidate",
        "jurisdiction": "test",
        "domain": "contract",
        "source_ref": "R1",
        "source_span": "错误文本",
        "source_span_start": None,
        "source_span_end": None,
        "input_hash": "hash",
        "output": {
            "original_candidate_id": "R1",
            "repair_type": "missing_anchor",
            "proposed_patch": {
                "exception_rule_id_suggestion": "R1-EX-01",
                "parent_rule_id": "R1",
                "trigger": "错误文本",
                "effect": "parent_rule_not_triggered",
                "suggested_rule_type": "exception",
            },
        },
        "confidence": 0.7,
        "known_limitations": ["source anchor missing"],
        "model": {"provider": "cheap-api", "model_id": "bulk", "version": None},
    }
    (root / "input" / "requests.jsonl").write_text(json.dumps(request, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "output" / "candidates.jsonl").write_text(json.dumps(candidate, ensure_ascii=False) + "\n", encoding="utf-8")

    result = gate_and_prepare_next(root)

    assert result["status"] == "NEXT_BATCH_READY"
    next_root = Path(result["next_batch_root"])
    assert next_root.name == "BATCH_REPAIR_R1"
    assert (next_root / "input" / "requests.jsonl").exists()
    assert (next_root / "input" / "START_HERE.md").exists()
    next_request = json.loads((next_root / "input" / "requests.jsonl").read_text(encoding="utf-8").strip())
    assert next_request["batch_id"] == "BATCH_REPAIR_R1"
    assert "validator_issues" in next_request["input"]
