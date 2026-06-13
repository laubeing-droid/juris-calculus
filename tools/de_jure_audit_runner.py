#!/usr/bin/env python3
"""De Jure 19-dimension deterministic rule quality auditor."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.de_jure_auditor import audit_rules_de_jure, score_rule_de_jure
from compiler_core.types import LegalRule


def main() -> int:
    parser = argparse.ArgumentParser(description="De Jure 19-dimension rule quality audit.")
    parser.add_argument("source", help="Path to rule YAML file")
    args = parser.parse_args()
    p = Path(args.source)
    with open(p, "r", encoding="utf-8") as f:
        rules = yaml.safe_load(f).get("rules", [])
    report = audit_rules_de_jure(rules)
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))
    return 0  # De Jure audit reports status, not blocks phase


if __name__ == "__main__":
    raise SystemExit(main())
