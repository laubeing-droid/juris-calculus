#!/usr/bin/env python3
"""Generate shadow-vs-official divergence reports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.shadow_state import compare_shadow_to_official


def build_report(official_claims: List[str], shadow_claims: List[str], world_id: str = "") -> Dict[str, Any]:
    comparison = compare_shadow_to_official(official_claims, shadow_claims)
    return {
        "world_id": world_id,
        "status": "DIVERGED" if comparison["divergence"] else "ALIGNED",
        **comparison,
    }


def build_report_from_json(path: str | Path) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return build_report(
        official_claims=list(data.get("official_claims", [])),
        shadow_claims=list(data.get("shadow_claims", [])),
        world_id=str(data.get("world_id", "")),
    )


def write_jsonl_example(report: Dict[str, Any], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "world_id": report.get("world_id", ""),
        "label": report.get("status", ""),
        "official_only": report.get("official_only", []),
        "shadow_only": report.get("shadow_only", []),
        "overlap": report.get("overlap", []),
    }
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare official and shadow claim ids.")
    parser.add_argument("--official", nargs="*", default=[])
    parser.add_argument("--shadow", nargs="*", default=[])
    parser.add_argument("--world-id", default="")
    parser.add_argument("--input-json")
    parser.add_argument("--output-json")
    parser.add_argument("--output-jsonl")
    args = parser.parse_args()
    report = build_report_from_json(args.input_json) if args.input_json else build_report(args.official, args.shadow, args.world_id)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(text, encoding="utf-8")
    if args.output_jsonl:
        write_jsonl_example(report, args.output_jsonl)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
