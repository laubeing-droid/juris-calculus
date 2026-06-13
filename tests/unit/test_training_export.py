#!/usr/bin/env python3
from __future__ import annotations

from tools.export_training_corpus import export_rules_as_jsonl, generate_model_card


def test_export_rules_as_jsonl_writes_splits(tmp_path):
    from pathlib import Path
    import yaml
    fixture = tmp_path / "rules.yaml"
    fixture.write_text(yaml.safe_dump({
        "rules": [
            {"id": "R1", "premise_atoms": ["p1"], "head_claim": "claim1", "exception_chain": [], "attacks": [], "priority_over": [], "source_anchor": "anchor:1", "jurisdiction": "test"},
            {"id": "R2", "premise_atoms": ["p2"], "head_claim": "claim2", "exception_chain": [], "attacks": [], "priority_over": [], "source_anchor": "anchor:2", "jurisdiction": "test"},
            {"id": "R3", "premise_atoms": ["p3"], "head_claim": "claim3", "exception_chain": [], "attacks": [], "priority_over": [], "source_anchor": "anchor:3", "jurisdiction": "test"},
        ]
    }, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "corpus.jsonl"
    report = export_rules_as_jsonl([str(fixture)], out=str(out))
    assert report["status"] == "PASS"
    assert report["total_items"] == 3
    assert (tmp_path / "corpus_train.jsonl").exists()
    assert (tmp_path / "corpus_dev.jsonl").exists()
    assert (tmp_path / "corpus_test.jsonl").exists()


def test_export_rules_as_jsonl_reproducible_hash(tmp_path):
    from pathlib import Path
    import yaml
    fixture = tmp_path / "rules.yaml"
    fixture.write_text(yaml.safe_dump({
        "rules": [{"id": "R1", "premise_atoms": ["p1"], "head_claim": "claim1"}]
    }, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "corpus.jsonl"
    r1 = export_rules_as_jsonl([str(fixture)], out=str(out), seed=42)
    r2 = export_rules_as_jsonl([str(fixture)], out=str(out), seed=42)
    assert r1["dataset_hash"] == r2["dataset_hash"]


def test_export_rules_as_jsonl_empty_rules(tmp_path):
    from pathlib import Path
    import yaml
    fixture = tmp_path / "empty.yaml"
    fixture.write_text(yaml.safe_dump({"rules": []}, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "corpus.jsonl"
    report = export_rules_as_jsonl([str(fixture)], out=str(out))
    assert report["total_items"] == 0


def test_generate_model_card_shadow_only():
    card = generate_model_card("m1", "0.1", "domain_routing", "hash-abc", {"f1": 0.85})
    assert card["promotion_status_suggestion"] == "SHADOW_ONLY"
    assert "source anchor validation" in card["limitations"][1]


def test_generate_model_card_no_metrics():
    card = generate_model_card("m1", "0.1", "domain_routing", "hash-abc")
    assert card["evaluation_metrics"] == {}


def test_export_rules_as_jsonl_handles_missing_rules_key(tmp_path):
    fixture = tmp_path / "norules.yaml"
    fixture.write_text("key: value\n", encoding="utf-8")
    out = tmp_path / "corpus.jsonl"
    report = export_rules_as_jsonl([str(fixture)], out=str(out))
    assert report["total_items"] == 0
