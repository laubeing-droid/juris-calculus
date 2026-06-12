#!/usr/bin/env python3
"""Compare two JC baseline traces to detect performance regression (MetaInfer anti-regression gate)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


REGRESSION_THRESHOLD = 1.2


def compare_baselines(before_path: str, after_path: str, threshold: float = REGRESSION_THRESHOLD) -> Dict[str, Any]:
    before = json.loads(Path(before_path).read_text(encoding="utf-8"))
    after = json.loads(Path(after_path).read_text(encoding="utf-8"))
    before_m = before.get("trace", {}).get("metrics", {})
    after_m = after.get("trace", {}).get("metrics", {})

    findings: List[Dict[str, Any]] = []
    for key in sorted(set(list(before_m) + list(after_m))):
        bv = before_m.get(key)
        av = after_m.get(key)
        if bv is None:
            findings.append({"op": key, "issue": "missing in baseline", "severity": "WARN"})
            continue
        if av is None:
            findings.append({"op": key, "issue": "missing in new run", "severity": "ERROR"})
            continue
        ratio = av / bv if bv > 0 else float("inf")
        if ratio >= threshold:
            findings.append({
                "op": key,
                "before_sec": bv,
                "after_sec": av,
                "ratio": round(ratio, 2),
                "severity": "ERROR" if ratio >= 2.0 else "WARN",
                "issue": f"slowed {round((ratio-1)*100)}% (threshold: {round((threshold-1)*100)}%)",
            })

    passed = not any(f["severity"] == "ERROR" for f in findings)
    return {
        "status": "PASS" if passed else "FAIL",
        "threshold": threshold,
        "before": str(before_path),
        "after": str(after_path),
        "findings": findings,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare two JC baseline traces. Exits 1 if any op regressed beyond threshold.")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--threshold", type=float, default=REGRESSION_THRESHOLD)
    args = parser.parse_args(argv)
    report = compare_baselines(args.before, args.after, args.threshold)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
