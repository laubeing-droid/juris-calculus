"""规则来源准入、共享 inventory 与候选训练导出的回归测试。"""
from __future__ import annotations

import json

import yaml

from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.types import IRState, LegalDomain, LegalFact
from tools.export_training_corpus import export_rules_as_jsonl
from tools.rule_quality_auditor import audit_rules


def _write_admission_fixture(tmp_path):
    """写入一条可准入和一条仅候选规则，覆盖旧来源字段原样迁移边界。"""
    path = tmp_path / "rule_admission.yaml"
    path.write_text(yaml.safe_dump({
        "rules": [
            {
                "id": "R_ANCHORED",
                "premise_atoms": ["anchored_fact"],
                "head_claim": "anchored_claim",
                "head_type": "HORN",
                "legal_basis": "statute:1",
            },
            {
                "id": "R_CANDIDATE",
                "premise_atoms": ["candidate_fact"],
                "head_claim": "candidate_claim",
                "head_type": "HORN",
                "description": "描述不能被猜作来源锚",
                "trust_label": "ENGINEERING_BASELINE",
                "data_quality": "CLEAN",
            },
        ]
    }, allow_unicode=True), encoding="utf-8")
    return path


def test_yaml_admission_inventory_and_reasoning_gate(tmp_path):
    """无锚 YAML 规则必须留在 corpus，但不得进入正式索引或生成 claim。"""
    fixture = _write_admission_fixture(tmp_path)
    rules = load_rules_from_yaml(str(fixture))

    assert rules[0].source_anchor == "statute:1"
    assert rules[1].source_anchor == ""
    assert rules[1].trust_label == "UNVERIFIED"
    assert rules[1].data_quality == "CANDIDATE_ONLY"

    evaluator = FixpointEvaluator(rules, DomainConfig(domain=LegalDomain.CIVIL))
    assert evaluator.inventory == {
        "corpus_total": 2,
        "reasoning_eligible_total": 1,
        "candidate_only_total": 1,
    }
    assert len(evaluator.corpus_rules) == 2
    assert set(evaluator.rules) == {"R_ANCHORED"}

    state = IRState(world_id="rule-admission")
    state.facts["anchored_fact"] = LegalFact("anchored_fact")
    state.facts["candidate_fact"] = LegalFact("candidate_fact")
    result = evaluator.evaluate(state)
    assert "anchored_claim" in result.claims
    assert "candidate_claim" not in result.claims


def test_audit_and_training_export_share_candidate_inventory(tmp_path):
    """审计和训练导出必须共享同一计数，并在 JSONL 中保留候选状态。"""
    fixture = _write_admission_fixture(tmp_path)

    audit = audit_rules(fixture)
    expected_inventory = {
        "corpus_total": 2,
        "reasoning_eligible_total": 1,
        "candidate_only_total": 1,
    }
    assert {key: audit[key] for key in expected_inventory} == expected_inventory

    output = tmp_path / "corpus.jsonl"
    exported = export_rules_as_jsonl([fixture], output, seed=42)
    assert {key: exported[key] for key in expected_inventory} == expected_inventory

    items = []
    for split in ("train", "dev", "test"):
        split_path = tmp_path / f"corpus_{split}.jsonl"
        items.extend(json.loads(line) for line in split_path.read_text(encoding="utf-8").splitlines())
    candidate = next(item for item in items if item["id"] == "R_CANDIDATE")
    assert candidate["trust_label"] == "UNVERIFIED"
    assert candidate["data_quality"] == "CANDIDATE_ONLY"
