#!/usr/bin/env python3
"""Correctness audit: verify that graph claims point to real artifacts."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kg_audit_common import finding, load_yaml, make_report, resolve_ref, write_json


def audit_correctness(contracts_path: str = "configs/juris_contracts.yaml") -> Dict[str, Any]:
    data = load_yaml(contracts_path)
    findings: List[Dict[str, Any]] = []
    for contract in data.get("contracts", []):
        contract_id = str(contract.get("contract_id", "<missing>"))
        for field in ("ref_docs", "ref_code", "ref_tests"):
            for ref in contract.get(field, []) or []:
                if not resolve_ref(str(ref)).exists():
                    findings.append(finding(
                        contract_id,
                        field,
                        f"reference does not exist: {ref}",
                        f"{contract_id}.{field}",
                        f"Remove stale reference or add the referenced artifact: {ref}",
                    ))
        for index, param in enumerate(contract.get("dynamic_parameters", []) or []):
            source = str(param.get("source", ""))
            if not source or not resolve_ref(source).exists():
                findings.append(finding(
                    contract_id,
                    f"dynamic_parameters[{index}].source",
                    f"dynamic parameter source missing: {source}",
                    f"{contract_id}.dynamic_parameters[{index}]",
                    "Point the parameter to an existing physical config path.",
                ))
    return make_report("kg_correctness_auditor", findings, {"contracts_path": contracts_path})


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run knowledge graph correctness audit.")
    parser.add_argument("--contracts", default="configs/juris_contracts.yaml")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    report = audit_correctness(args.contracts)
    if args.out:
        write_json(args.out, report)
    print(f"status={report['status']} findings={len(report['findings'])}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
