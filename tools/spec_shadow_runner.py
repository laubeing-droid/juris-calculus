#!/usr/bin/env python3
"""Run the JC-vs-spec shadow harness and write the first differential report."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.spec_shadow_harness import SPEC_REPO_ROOT, build_cross_repo_differential_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the spec shadow differential harness.")
    parser.add_argument(
        "--spec-repo",
        default=str(SPEC_REPO_ROOT),
        help="Path to legal-math-modeling repository.",
    )
    parser.add_argument(
        "--output-json",
        default=str(ROOT / "reports" / "spec_shadow_differential_report.json"),
        help="Output path for the machine-readable differential report.",
    )
    parser.add_argument(
        "--output-md",
        default=str(ROOT / "过程文件" / f"{date.today().isoformat()}-spec-shadow-differential-report.md"),
        help="Output path for the human-readable summary report.",
    )
    args = parser.parse_args()

    report = build_cross_repo_differential_report(Path(args.spec_repo))

    json_path = Path(args.output_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = Path(args.output_md)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Spec Shadow Differential Report",
        "",
        f"- spec_repo_root: `{report['spec_repo_root']}`",
        f"- fixture_count: `{report['summary']['fixture_count']}`",
        f"- aligned_count: `{report['summary']['aligned_count']}`",
        f"- diverged_count: `{report['summary']['diverged_count']}`",
        "",
    ]
    for item in report["fixtures"]:
        result = item["report"]
        lines.extend(
            [
                f"## {result['fixture_id']} / {result['variant']}",
                "",
                f"- status: `{result['status']}`",
                f"- aligned_fields: `{', '.join(result['aligned_fields']) if result['aligned_fields'] else 'none'}`",
                f"- blockers: `{'; '.join(result['blockers']) if result['blockers'] else 'none'}`",
                "",
            ]
        )
        if result["diverged_fields"]:
            lines.append("### Diverged Fields")
            lines.append("")
            for field, payload in result["diverged_fields"].items():
                lines.append(f"- `{field}`")
                lines.append(f"  - spec: `{payload['spec']}`")
                lines.append(f"  - jc: `{payload['jc']}`")
            lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"output_json": str(json_path), "output_md": str(md_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
