#!/usr/bin/env python3
"""Check Typed Legal IR v3 YAML files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.legal_ir_v3 import legal_ir_rule_from_dict
from compiler_core.type_checker import check_legal_ir_rule


def check_ir_file(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    raw_rules = data.get("rules", [])
    rule_ids = [rule.get("rule_id", "") for rule in raw_rules]
    findings: List[Dict[str, Any]] = []
    for raw in raw_rules:
        try:
            rule = legal_ir_rule_from_dict(raw)
            report = check_legal_ir_rule(rule, known_rule_ids=rule_ids)
            for issue in report.issues:
                findings.append({"rule_id": rule.rule_id, "issue": issue})
        except Exception as exc:
            findings.append({"rule_id": raw.get("rule_id", "<unknown>"), "issue": f"PARSE_ERROR:{exc}"})
    return {
        "path": str(p),
        "rule_count": len(raw_rules),
        "finding_count": len(findings),
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Typed Legal IR v3 YAML.")
    parser.add_argument("path")
    args = parser.parse_args()
    report = check_ir_file(args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
