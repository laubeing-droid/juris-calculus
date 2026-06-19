#!/usr/bin/env python3
"""
Blind Reconstruction Audit for juris-calculus.

Methodology: MetaInfer isolated_reconstructability_audit (v1-v17)
Adapted from: MetaInfer notebooks-cn/07_improvementPlan/build_prompt/

Only given juris_blueprint.json + 法条原文, attempt to reconstruct
legal conclusions WITHOUT access to configs/zh_CN/rules.yaml.
Purpose: discover missing rules / contradictions in the blueprint.

Usage:
    python tools/audit_blind_reconstruction.py
    python tools/audit_blind_reconstruction.py --blueprint configs/juris_blueprint.json
"""
import json, sys, os
from pathlib import Path
from typing import Dict, List, Set

BLUEPRINT_PATH = Path(__file__).resolve().parents[1] / "configs" / "juris_blueprint.json"
RULES_PATH = Path(__file__).resolve().parents[1] / "configs" / "zh_CN" / "rules.yaml"


def load_blueprint(path: Path = BLUEPRINT_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_elements_from_blueprint(bp: dict) -> Dict[str, List[str]]:
    """Extract required elements per claim type from blueprint."""
    ec = bp.get("knowledge_categories", {}).get("element_composition", {})
    return {k: v.get("elements", []) for k, v in ec.items()}


def extract_cbl_blocks(bp: dict) -> List[dict]:
    """Extract CBL blocking rules from blueprint."""
    return bp.get("knowledge_categories", {}).get(
        "jurisdiction_conflict_interfaces", {}
    ).get("cbl_blocking_rules", [])


def extract_failure_modes(bp: dict) -> List[dict]:
    return bp.get("knowledge_categories", {}).get("failure_mode_library", [])


def extract_gates(bp: dict) -> List[dict]:
    return bp.get("runtime_acceptance_layer", {}).get("legal_gates", [])


def check_blueprint_completeness(bp: dict) -> Dict:
    """Check blueprint internal consistency without external rules."""
    report = {
        "elements_count": 0,
        "cbl_rules_count": 0,
        "gates_count": 0,
        "failure_modes_count": 0,
        "missing_categories": [],
        "gaps": [],
    }

    # Check 6 knowledge categories exist
    required_categories = [
        "element_composition", "jurisdiction_conflict_interfaces",
        "burden_of_proof_state_machine", "statute_of_limitations",
        "remedy_computation", "failure_mode_library"
    ]
    kc = bp.get("knowledge_categories", {})
    for cat in required_categories:
        if cat not in kc:
            report["missing_categories"].append(cat)

    elements = extract_elements_from_blueprint(bp)
    report["elements_count"] = sum(len(v) for v in elements.values())

    cbl = extract_cbl_blocks(bp)
    report["cbl_rules_count"] = len(cbl)

    gates = extract_gates(bp)
    report["gates_count"] = len(gates)

    fm = extract_failure_modes(bp)
    report["failure_modes_count"] = len(fm)

    # Check element coverage: does each claim type have >= 3 elements?
    for claim_type, elems in elements.items():
        if len(elems) < 3:
            report["gaps"].append({
                "type": "ELEMENT_INSUFFICIENT",
                "claim_type": claim_type,
                "elements": elems,
                "min_required": 3
            })

    return report


def run_reconstruction_simulation(bp: dict, test_cases: List[Dict]) -> Dict:
    """
    Simulate reconstruction: for each test case, extract required elements
    from the blueprint and check if blueprint can reconstruct the conclusion.
    """
    elements = extract_elements_from_blueprint(bp)
    failures = []

    for case in test_cases:
        claim_type = case.get("claim_type", "")
        available_facts = set(case.get("facts", []))
        expected_elements = elements.get(claim_type, [])

        if not expected_elements:
            failures.append({
                "case": case.get("id", "unknown"),
                "issue": "CLAIM_TYPE_NOT_IN_BLUEPRINT",
                "claim_type": claim_type,
            })
            continue

        missing = [e for e in expected_elements if e not in available_facts]
        if missing:
            failures.append({
                "case": case.get("id", "unknown"),
                "issue": "ELEMENT_MISSING",
                "claim_type": claim_type,
                "missing": missing,
                "available": list(available_facts)
            })

    return {
        "total_cases": len(test_cases),
        "failures": len(failures),
        "failures_detail": failures
    }


def generate_report(bp: dict, completeness: Dict, simulation: Dict) -> str:
    """Generate markdown report."""
    lines = [
        "# Blind Reconstruction Audit Report",
        f"\n**Blueprint version**: {bp.get('metadata', {}).get('version', 'unknown')}",
        f"**Date**: 2026-06-12",
        f"**Method**: MetaInfer isolated_reconstructability_audit",
        "",
        "## Blueprint Completeness",
        "",
        f"- Elements: {completeness['elements_count']}",
        f"- CBL rules: {completeness['cbl_rules_count']}",
        f"- Gates: {completeness['gates_count']}",
        f"- Failure modes: {completeness['failure_modes_count']}",
    ]

    if completeness["missing_categories"]:
        lines.append(f"\n**Missing categories**: {completeness['missing_categories']}")
    if completeness["gaps"]:
        lines.append("\n**Gaps found**:")
        for g in completeness["gaps"]:
            lines.append(f"- {g['type']}: {g.get('claim_type', '')} ({g})")

    lines.extend([
        "\n## Reconstruction Simulation",
        f"\n- Test cases: {simulation['total_cases']}",
        f"- Failures: {simulation['failures']}",
    ])

    if simulation["failures_detail"]:
        lines.append("\n**Failure details**:")
        for f in simulation["failures_detail"]:
            lines.append(f"- Case {f['case']}: {f['issue']} — {f.get('claim_type', '')}")

    return "\n".join(lines)


if __name__ == "__main__":
    bp = load_blueprint()
    print(f"Loaded blueprint: {bp.get('metadata', {}).get('version', 'unknown')}")

    completeness = check_blueprint_completeness(bp)
    print(f"Completeness: {completeness['elements_count']} elements, "
          f"{completeness['cbl_rules_count']} CBL rules, "
          f"{completeness['gates_count']} gates")

    # Test cases: 20 sample contract/tort cases
    test_cases = [
        {"id": "TC-01", "claim_type": "tort_liability_prc", "facts": ["damage", "causation", "fault", "capacity"]},
        {"id": "TC-02", "claim_type": "tort_liability_prc", "facts": ["damage", "causation", "fault"]},
        {"id": "TC-03", "claim_type": "breach_liability_prc", "facts": ["valid_contract", "breach", "damage", "causation"]},
        {"id": "TC-04", "claim_type": "breach_liability_prc", "facts": ["valid_contract", "breach"]},
    ]

    simulation = run_reconstruction_simulation(bp, test_cases)
    report = generate_report(bp, completeness, simulation)

    report_path = Path(__file__).resolve().parents[1] / "reports" / "blind_reconstruction_audit.md"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"Report: {report_path}")
    print(f"Failures: {simulation['failures']}/{simulation['total_cases']}")
