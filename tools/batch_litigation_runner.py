#!/usr/bin/env python3
"""Batch litigation runner: process multiple cases through the reasoning chain."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.litigation_renderer import LitigationChainRenderer, LitigationReport
from compiler_core.evidence_checklist import build_enhanced_checklist
from compiler_core.types import LegalRule


def make_contract_rules() -> list[LegalRule]:
    return [
        LegalRule(id="rule::delivery_obligation", premise_atoms=["contract_exists", "delivery_due"], head_claim="norm::delivery::active", norm_modality="OBLIGATION"),
        LegalRule(id="rule::failed_delivery", premise_atoms=["norm::delivery::active", "goods_not_delivered"], head_claim="delivery_breach", norm_modality="OBLIGATION"),
    ]


def make_license_rules() -> list[LegalRule]:
    return [
        LegalRule(id="rule::license_status", premise_atoms=["license_signed", "rights_holder_authorized"], head_claim="license_status_active", norm_modality="CONSTITUTIVE"),
        LegalRule(id="rule::licensed_use_permission", premise_atoms=["license_status_active", "use_within_scope"], head_claim="use_permitted", norm_modality="PERMISSION", priority_over=["rule::used_work"]),
        LegalRule(id="rule::used_work", premise_atoms=["used_work"], head_claim="unauthorized_use", norm_modality="PROHIBITION"),
    ]


def make_tort_rules() -> list[LegalRule]:
    return [
        LegalRule(id="rule::tort_breach", premise_atoms=["duty_of_care", "breach_of_duty", "causation", "damage"], head_claim="tort_liability", norm_modality="OBLIGATION"),
    ]


def make_criminal_rules() -> list[LegalRule]:
    return [
        LegalRule(id="rule::theft_act", premise_atoms=["taking_property", "without_consent", "intent_to_deprive"], head_claim="actus_reus::theft", norm_modality="CONSTITUTIVE"),
        LegalRule(id="rule::theft_mens_rea", premise_atoms=["actus_reus::theft", "knowingly"], head_claim="crime::theft", norm_modality="CONSTITUTIVE"),
        LegalRule(id="rule::self_defense", premise_atoms=["imminent_threat", "proportional_force"], head_claim="defense::self_defense", norm_modality="PERMISSION", priority_over=["crime::assault"]),
        LegalRule(id="rule::assault_basic", premise_atoms=["physical_contact", "without_consent", "harm_caused"], head_claim="crime::assault", norm_modality="CONSTITUTIVE"),
    ]


def make_admin_rules() -> list[LegalRule]:
    return [
        LegalRule(id="rule::license_required", premise_atoms=["regulated_activity", "no_license_held"], head_claim="admin_violation::unlicensed", norm_modality="PROHIBITION"),
        LegalRule(id="rule::license_granted", premise_atoms=["application_approved", "fees_paid", "conditions_met"], head_claim="license::active", norm_modality="CONSTITUTIVE"),
        LegalRule(id="rule::license_defense", premise_atoms=["admin_violation::unlicensed", "license::active"], head_claim="license::active", norm_modality="PERMISSION", priority_over=["admin_violation::unlicensed"]),
        LegalRule(id="rule::environmental_harm", premise_atoms=["discharge_above_limit", "protected_area"], head_claim="admin_violation::environmental", norm_modality="PROHIBITION"),
    ]


BATCH_CASES: list[dict[str, Any]] = [
    {
        "case_id": "batch::contract_plain",
        "domain": "contract",
        "facts": ["contract_exists", "delivery_due", "goods_not_delivered"],
        "rules_fn": "make_contract_rules",
    },
    {
        "case_id": "batch::contract_force_majeure",
        "domain": "contract",
        "facts": ["contract_exists", "delivery_due", "goods_not_delivered", "force_majeure"],
        "rules_fn": "make_contract_rules",
    },
    {
        "case_id": "batch::license_priority_on",
        "domain": "license",
        "facts": ["license_signed", "rights_holder_authorized", "used_work", "use_within_scope"],
        "rules_fn": "make_license_rules",
    },
    {
        "case_id": "batch::license_priority_off",
        "domain": "license",
        "facts": ["used_work"],
        "rules_fn": "make_license_rules",
    },
    {
        "case_id": "batch::tort_plain",
        "domain": "tort",
        "facts": ["duty_of_care", "breach_of_duty", "causation", "damage"],
        "rules_fn": "make_tort_rules",
    },
    {
        "case_id": "batch::criminal_theft",
        "domain": "criminal",
        "facts": ["taking_property", "without_consent", "intent_to_deprive", "knowingly"],
        "rules_fn": "make_criminal_rules",
    },
    {
        "case_id": "batch::criminal_self_defense",
        "domain": "criminal",
        "facts": ["physical_contact", "without_consent", "harm_caused", "imminent_threat", "proportional_force"],
        "rules_fn": "make_criminal_rules",
    },
    {
        "case_id": "batch::admin_unlicensed",
        "domain": "administrative",
        "facts": ["regulated_activity", "no_license_held"],
        "rules_fn": "make_admin_rules",
    },
    {
        "case_id": "batch::admin_licensed",
        "domain": "administrative",
        "facts": ["regulated_activity", "application_approved", "fees_paid", "conditions_met"],
        "rules_fn": "make_admin_rules",
    },
]


def run_batch(output_dir: str | None = None) -> Dict[str, Any]:
    """Run all batch cases and return aggregate results."""
    fn_map = {
        "make_contract_rules": make_contract_rules,
        "make_license_rules": make_license_rules,
        "make_tort_rules": make_tort_rules,
        "make_criminal_rules": make_criminal_rules,
        "make_admin_rules": make_admin_rules,
    }

    results: list[Dict[str, Any]] = []
    for case in BATCH_CASES:
        rules_fn = fn_map[case["rules_fn"]]
        rules = rules_fn()
        renderer = LitigationChainRenderer(rules=rules, facts=case["facts"])
        report = renderer.evaluate()

        checklist = build_enhanced_checklist(
            report.claim_analyses,
            report.facts,
            report.rules_applied,
        )

        case_result = {
            "case_id": case["case_id"],
            "domain": case["domain"],
            "claims_count": len(report.claim_analyses),
            "proved": sum(1 for a in report.claim_analyses if a.status == "PROVED"),
            "refuted": sum(1 for a in report.claim_analyses if a.status == "REFUTED"),
            "undecided": sum(1 for a in report.claim_analyses if a.status == "UNDECIDED"),
            "critical_gaps": checklist.total_critical,
            "high_gaps": checklist.total_high,
            "fail_closed_ok": report.fail_closed_boundary.get("no_uncertainty_upgrade", False),
        }
        results.append(case_result)

        if output_dir:
            out = Path(output_dir) / f"{case['case_id']}.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(renderer.render_markdown(report), encoding="utf-8")

    return {
        "total_cases": len(results),
        "total_claims": sum(r["claims_count"] for r in results),
        "total_proved": sum(r["proved"] for r in results),
        "total_refuted": sum(r["refuted"] for r in results),
        "total_undecided": sum(r["undecided"] for r in results),
        "total_critical_gaps": sum(r["critical_gaps"] for r in results),
        "all_fail_closed": all(r["fail_closed_ok"] for r in results),
        "cases": results,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run batch litigation cases.")
    parser.add_argument("--output-dir", default=str(ROOT / "过程文件" / "batch_litigation"), help="Output directory for Markdown reports.")
    parser.add_argument("--json", action="store_true", help="Output JSON summary only.")
    args = parser.parse_args()

    summary = run_batch(args.output_dir if not args.json else None)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
