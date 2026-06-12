#!/usr/bin/env python3
"""Completeness audit: verify that contracts say enough to reconstruct behavior."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kg_audit_common import finding, load_yaml, make_report, write_json


REQUIRED_FIELDS = [
    "contract_id",
    "layer",
    "purpose",
    "inputs",
    "outputs",
    "must_hold",
    "failure_modes",
    "ref_docs",
    "ref_code",
    "ref_tests",
    "dynamic_parameters",
    "pseudocode",
]


def audit_completeness(contracts_path: str = "configs/juris_contracts.yaml") -> Dict[str, Any]:
    data = load_yaml(contracts_path)
    findings: List[Dict[str, Any]] = []
    for index, contract in enumerate(data.get("contracts", []) or []):
        contract_id = str(contract.get("contract_id", f"contract[{index}]"))
        for field in REQUIRED_FIELDS:
            value = contract.get(field)
            if value is None or value == "" or value == []:
                findings.append(finding(
                    contract_id,
                    field,
                    f"required field is empty: {field}",
                    f"{contract_id}.{field}",
                    f"Fill {field} so the contract is reconstructable.",
                ))
        pseudocode = str(contract.get("pseudocode", ""))
        lines = [line for line in pseudocode.splitlines() if line.strip()]
        if len(lines) < 4:
            findings.append(finding(
                contract_id,
                "pseudocode",
                "pseudocode is too short to be self-contained",
                f"{contract_id}.pseudocode",
                "Expand pseudocode to include inputs, core decision steps, and outputs.",
            ))
        if len(contract.get("dynamic_parameters", []) or []) == 0:
            findings.append(finding(
                contract_id,
                "dynamic_parameters",
                "contract has no physical config parameter sources",
                f"{contract_id}.dynamic_parameters",
                "Add dynamic parameter sources instead of relying on hardcoded implementation constants.",
            ))
    return make_report("kg_completeness_auditor", findings, {"contracts_path": contracts_path})


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run knowledge graph completeness audit.")
    parser.add_argument("--contracts", default="configs/juris_contracts.yaml")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    report = audit_completeness(args.contracts)
    if args.out:
        write_json(args.out, report)
    print(f"status={report['status']} findings={len(report['findings'])}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
