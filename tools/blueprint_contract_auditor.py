#!/usr/bin/env python3
"""Audit the juris-calculus phase matrix before runtime verification."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml


ROOT = Path(__file__).resolve().parent.parent


def load_matrix(path: str | Path) -> Dict[str, Any]:
    matrix_path = _resolve(path)
    data = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("phase matrix must be a YAML mapping")
    return data


def audit_matrix(path: str | Path, contracts_path: str | Path | None = "configs/juris_contracts.yaml") -> Dict[str, Any]:
    matrix_path = _resolve(path)
    matrix = load_matrix(matrix_path)
    issues: List[str] = []

    phases = matrix.get("phases", [])
    if not isinstance(phases, list) or not phases:
        issues.append("phases must be a non-empty list")

    seen_ids = set()
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            issues.append(f"phase[{index}] must be a mapping")
            continue
        phase_id = str(phase.get("id", "")).strip()
        if not phase_id:
            issues.append(f"phase[{index}] missing id")
        if phase_id in seen_ids:
            issues.append(f"duplicate phase id: {phase_id}")
        seen_ids.add(phase_id)

        commands = phase.get("commands", [])
        if not isinstance(commands, list) or not commands:
            issues.append(f"{phase_id}: commands must be a non-empty list")
        elif not all(isinstance(cmd, str) and cmd.strip() for cmd in commands):
            issues.append(f"{phase_id}: every command must be a non-empty string")

        for contract in phase.get("blueprint_contracts", []):
            contract_path = _resolve(contract)
            if not contract_path.exists():
                issues.append(f"{phase_id}: missing blueprint contract {contract}")

    role_names = set((matrix.get("roles") or {}).keys())
    required_roles = {"implementer", "spec_reviewer", "verification"}
    missing_roles = required_roles - role_names
    if missing_roles:
        issues.append("missing roles: " + ", ".join(sorted(missing_roles)))

    replay_policy = matrix.get("replay_policy", {})
    if not isinstance(replay_policy, dict):
        issues.append("replay_policy must be a mapping")
    elif replay_policy.get("enabled", True) and int(replay_policy.get("sample_size", 0)) < 1:
        issues.append("replay_policy.sample_size must be >= 1 when enabled")

    closure_policy = matrix.get("closure_policy", {})
    required_closure_items = {
        "root_cause",
        "code_change",
        "test_or_phase_command",
        "blueprint_or_matrix_update_when_contract_changes",
    }
    actual_closure_items = set(closure_policy.get("bug_fix_requires", [])) if isinstance(closure_policy, dict) else set()
    missing_closure_items = required_closure_items - actual_closure_items
    if missing_closure_items:
        issues.append("closure_policy missing: " + ", ".join(sorted(missing_closure_items)))


    anti = matrix.get("anti_degradation", {})
    if not isinstance(anti, dict):
        issues.append("anti_degradation must be a mapping")
    else:
        for rule in [
            "scripts_immutable",
            "phase_gate_strict",
            "l0_import_source_guard",
            "step35_spot_check",
            "cross_phase_regression",
            "e2e_evidence_chain",
            "anti_hardcoded_reasoning",
        ]:
            rule_cfg = anti.get(rule, {})
            if not isinstance(rule_cfg, dict) or not rule_cfg.get("enforced"):
                issues.append(f"anti_degradation.{rule} must exist and be enforced")

    build_phases = matrix.get("build_phases", [])
    if not isinstance(build_phases, list):
        issues.append("build_phases must be a list")
    elif build_phases:
        seen_build_ids = set()
        for index, phase in enumerate(build_phases):
            if not isinstance(phase, dict):
                issues.append(f"build_phase[{index}] must be a mapping")
                continue
            bpid = str(phase.get("id", "")).strip()
            if not bpid:
                issues.append(f"build_phase[{index}] missing id")
            if bpid in seen_build_ids:
                issues.append(f"duplicate build_phase id: {bpid}")
            seen_build_ids.add(bpid)
            if not isinstance(phase.get("commands", []), list) or not phase.get("commands", []):
                issues.append(f"{bpid}: commands must be a non-empty list")
            dep = phase.get("physical_dependency")
            valid_ids = seen_build_ids.copy() - {bpid}
            if dep and dep != "none" and dep not in valid_ids:
                issues.append(f"{bpid}: physical_dependency '{dep}' must reference a prior build_phase id or 'none'")
            if dep is None:
                issues.append(f"{bpid}: physical_dependency field required")

    if contracts_path:
        contract_report = audit_experience_contracts(contracts_path)
        for issue in contract_report["issues"]:
            issues.append(f"experience_contracts: {issue}")

    return {
        "matrix": str(matrix_path),
        "phase_count": len(phases) if isinstance(phases, list) else 0,
        "build_phase_count": len(build_phases) if isinstance(build_phases, list) else 0,
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
    }


def audit_experience_contracts(path: str | Path) -> Dict[str, Any]:
    contract_path = _resolve(path)
    issues: List[str] = []
    if not contract_path.exists():
        return {"contracts": str(contract_path), "contract_count": 0, "status": "FAIL", "issues": ["missing contracts file"]}

    data = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
    contracts = data.get("contracts", [])
    if not isinstance(contracts, list) or not contracts:
        issues.append("contracts must be a non-empty list")
        contracts = []

    seen_ids = set()
    required = {"contract_id", "layer", "purpose", "ref_docs", "ref_code", "ref_tests", "dynamic_parameters", "pseudocode"}
    for index, contract in enumerate(contracts):
        if not isinstance(contract, dict):
            issues.append(f"contract[{index}] must be a mapping")
            continue
        contract_id = str(contract.get("contract_id", "")).strip()
        if not contract_id:
            issues.append(f"contract[{index}] missing contract_id")
        if contract_id in seen_ids:
            issues.append(f"duplicate contract_id: {contract_id}")
        seen_ids.add(contract_id)

        missing = required - set(contract.keys())
        if missing:
            issues.append(f"{contract_id}: missing keys {sorted(missing)}")
        pseudocode = str(contract.get("pseudocode", "")).strip()
        if len([line for line in pseudocode.splitlines() if line.strip()]) < 4:
            issues.append(f"{contract_id}: pseudocode must be self-contained with at least 4 non-empty lines")

        for key in ("ref_docs", "ref_code", "ref_tests"):
            refs = contract.get(key, [])
            if not isinstance(refs, list) or not refs:
                issues.append(f"{contract_id}: {key} must be a non-empty list")
                continue
            for ref in refs:
                if not _resolve_ref(str(ref)).exists():
                    issues.append(f"{contract_id}: missing {key} path {ref}")

        params = contract.get("dynamic_parameters", [])
        if not isinstance(params, list) or not params:
            issues.append(f"{contract_id}: dynamic_parameters must be non-empty")
        for param in params if isinstance(params, list) else []:
            if not isinstance(param, dict) or not param.get("name") or not param.get("source"):
                issues.append(f"{contract_id}: dynamic parameter requires name and source")
                continue
            source_path = str(param["source"]).split("#", 1)[0]
            if source_path and not _resolve_ref(source_path).exists():
                issues.append(f"{contract_id}: dynamic parameter source missing {param['source']}")

    return {
        "contracts": str(contract_path),
        "contract_count": len(contracts),
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
    }


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p


def _resolve_ref(path: str) -> Path:
    return _resolve(path.split("#", 1)[0])


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit juris-calculus phase matrix contracts.")
    parser.add_argument("--matrix", default="configs/juris_phase_matrix.yaml")
    parser.add_argument("--contracts", default="configs/juris_contracts.yaml")
    args = parser.parse_args(argv)
    report = audit_matrix(args.matrix, args.contracts)
    print(f"status={report['status']} phases={report['phase_count']}")
    for issue in report["issues"]:
        print(f"ISSUE: {issue}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
