#!/usr/bin/env python3
from __future__ import annotations

from compiler_core.ddl_preclassifier import preclassify_batch, preclassify_rule
from compiler_core.types import NormModality
from tools.ddl_remedy_pool_filler import fill_remedy_pools


def test_preclassify_constitutive_signal():
    rule = {"id": "R1", "head_claim": "未经登记，不得对抗善意第三人", "premise_atoms": [], "concepts": [], "namespace": "contract"}
    r = preclassify_rule(rule)
    assert r.modality == NormModality.CONSTITUTIVE
    assert r.confidence >= 0.9


def test_preclassify_obligation_keyword():
    rule = {"id": "R2", "head_claim": "应当赔偿损失", "premise_atoms": ["damages_suffered"], "concepts": [], "namespace": "tort"}
    r = preclassify_rule(rule)
    assert r.modality == NormModality.OBLIGATION
    assert r.confidence >= 0.8


def test_preclassify_prohibition():
    rule = {"id": "R3", "head_claim": "不得泄露个人信息", "premise_atoms": [], "concepts": [], "namespace": "privacy"}
    r = preclassify_rule(rule)
    assert r.modality == NormModality.PROHIBITION
    assert r.confidence >= 0.8


def test_preclassify_concept_fallback():
    rule = {"id": "PC-001", "head_claim": "国家赔偿的责任主体是国家", "premise_atoms": [], "concepts": ["国家赔偿"], "namespace": "admin"}
    r = preclassify_rule(rule)
    assert r.modality == NormModality.CONSTITUTIVE
    assert r.confidence >= 0.5


def test_preclassify_batch_counts():
    rules = [{"id": "R1", "head_claim": "应当履行", "premise_atoms": [], "concepts": [], "namespace": ""},
             {"id": "R2", "head_claim": "定义条款", "premise_atoms": [], "concepts": [], "namespace": ""}]
    report = preclassify_batch(rules)
    assert report["rule_count"] == 2
    assert report["by_modality"]["OBLIGATION"] == 1
    assert report["by_modality"]["UNKNOWN"] == 1


def test_remedy_pool_fills_contract():
    rules = [{"id": "R1", "head_claim": "应当承担违约责任", "premise_atoms": [], "concepts": ["违约责任"], "namespace": "contract"}]
    report = fill_remedy_pools(rules)
    assert report["filled_count"] == 1
    assert report["filled"][0]["reparation_chain_pool"][0]["trigger"] == "breach_of_contract"


def test_remedy_pool_no_match():
    rules = [{"id": "R1", "head_claim": "nothing", "premise_atoms": [], "concepts": ["unknown"], "namespace": ""}]
    report = fill_remedy_pools(rules)
    assert report["filled_count"] == 0
