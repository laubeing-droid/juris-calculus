"""Tests for litigation_renderer.py -- end-to-end reasoning chain."""

import json
from pathlib import Path

import pytest

from compiler_core.litigation_renderer import (
    LitigationChainRenderer,
    LitigationReport,
    ClaimAnalysis,
)
from compiler_core.types import LegalRule


def _contract_rules() -> list[LegalRule]:
    return [
        LegalRule(
            id="rule::delivery_obligation",
            premise_atoms=["contract_exists", "delivery_due"],
            head_claim="norm::delivery::active",
            norm_modality="OBLIGATION",
        ),
        LegalRule(
            id="rule::failed_delivery",
            premise_atoms=["norm::delivery::active", "goods_not_delivered"],
            head_claim="delivery_breach",
            norm_modality="OBLIGATION",
        ),
    ]


def test_renderer_evaluates_simple_contract_breach():
    renderer = LitigationChainRenderer(
        rules=_contract_rules(),
        facts=["contract_exists", "delivery_due", "goods_not_delivered"],
    )
    report = renderer.evaluate()

    assert isinstance(report, LitigationReport)
    assert report.facts == ["contract_exists", "delivery_due", "goods_not_delivered"]
    assert "rule::delivery_obligation" in report.rules_applied
    assert "rule::failed_delivery" in report.rules_applied

    # delivery_breach should be IN
    breach_analysis = next(a for a in report.claim_analyses if a.claim_id == "delivery_breach")
    assert breach_analysis.status == "PROVED"
    assert breach_analysis.label == "IN"

    # norm::delivery::active should also be IN
    norm_analysis = next(a for a in report.claim_analyses if a.claim_id == "norm::delivery::active")
    assert norm_analysis.status == "PROVED"


def test_renderer_handles_missing_facts():
    renderer = LitigationChainRenderer(
        rules=_contract_rules(),
        facts=["contract_exists"],  # missing delivery_due and goods_not_delivered
    )
    report = renderer.evaluate()

    assert report.truncation_warning is None  # No actual truncation, just fewer claims
    assert len(report.claim_analyses) == 0  # No rules fired


def test_renderer_produces_valid_json():
    renderer = LitigationChainRenderer(
        rules=_contract_rules(),
        facts=["contract_exists", "delivery_due", "goods_not_delivered"],
    )
    report = renderer.evaluate()
    from dataclasses import asdict

    d = asdict(report)
    assert json.dumps(d, default=str)  # Must not raise


def test_renderer_produces_markdown():
    renderer = LitigationChainRenderer(
        rules=_contract_rules(),
        facts=["contract_exists", "delivery_due", "goods_not_delivered"],
    )
    report = renderer.evaluate()
    md = renderer.render_markdown(report)

    assert "# Litigation Reasoning Report" in md
    assert "delivery_breach" in md
    assert "PROVED" in md


def test_renderer_with_impact_analysis():
    renderer_old = LitigationChainRenderer(
        rules=_contract_rules(),
        facts=["contract_exists", "delivery_due", "goods_not_delivered"],
    )
    baseline = renderer_old.evaluate()

    new_rules = _contract_rules() + [
        LegalRule(
            id="rule::extra_delivery",
            premise_atoms=["contract_exists", "contract_exists"],
            head_claim="extra_delivery_due",
            norm_modality="OBLIGATION",
        ),
    ]
    renderer_new = LitigationChainRenderer(
        rules=new_rules,
        facts=["contract_exists", "delivery_due", "goods_not_delivered"],
    )
    report = renderer_new.evaluate_with_impact(baseline)

    assert report.impact_analysis is not None
    assert "rule::extra_delivery" in report.impact_analysis["rules_added"]


def test_fail_closed_boundary():
    renderer = LitigationChainRenderer(
        rules=_contract_rules(),
        facts=["contract_exists", "delivery_due", "goods_not_delivered"],
    )
    report = renderer.evaluate()

    assert not report.fail_closed_boundary["horn_truncated"]
    assert not report.fail_closed_boundary["grounded_truncated"]
    assert report.fail_closed_boundary["no_uncertainty_upgrade"]
