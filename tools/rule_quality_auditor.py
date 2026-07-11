#!/usr/bin/env python3
"""兼容CLI wrapper；规则审计唯一实现位于compiler_core.rule_governance。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from compiler_core.rule_governance import audit_rule_file


def audit_rules(path: str | Path, strict_source_anchor: bool = False, tests_root: str | Path | None = None):
    """保留旧测试函数名；缺来源始终保留candidate，不因flag自动晋升。"""

    test_ids = None
    if tests_root is not None:
        from compiler_core.rule_governance import _test_rule_ids

        test_ids = _test_rule_ids(Path(tests_root))
    report = audit_rule_file(path, test_rule_ids=test_ids)
    if strict_source_anchor:
        for item in report["findings"]:
            if item["code"] in {"SOURCE_ANCHOR_MISSING", "SOURCE_ANCHOR_EMPTY"}:
                item["blocking"] = True
        report["blocking_count"] = sum(1 for item in report["findings"] if item["blocking"])
        report["status"] = "PASS" if report["blocking_count"] == 0 else "FAIL"
    inventory = report["inventory"]
    return {
        "path": str(Path(path)),
        "rule_count": inventory["corpus_total"],
        **inventory,
        "finding_count": report["finding_count"],
        "blocking_count": report["blocking_count"],
        "status": report["status"],
        "findings": [
            {
                "index": -1,
                "rule_id": item["rule_id"],
                "issue": item["code"],
                "score": 0.0 if item["blocking"] else 0.5,
                "evidence": [],
                "blocking_issue": item["blocking"],
                "repair_instruction": "Repair metadata and rerun governance; promotion remains manual.",
            }
            for item in report["findings"]
        ],
    }


def main() -> int:
    """运行单文件兼容审计。"""

    parser = argparse.ArgumentParser(description="Audit legal rule YAML quality.")
    parser.add_argument("path")
    parser.add_argument("--strict-source-anchor", action="store_true")
    parser.add_argument("--tests-root")
    args = parser.parse_args()
    report = audit_rules(args.path, args.strict_source_anchor, args.tests_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
