#!/usr/bin/env python3
"""Build, validate, and sample relevance benchmark datasets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "benchmarks" / "relevance" / "manifest.yaml"
ALLOWED_KINDS = {
    "SHOULD_NOT_CHANGE", "SHOULD_CHANGE", "STATUTE_CONFUSION",
    "TEMPORAL_SPLIT", "EXCEPTION_SENSITIVITY", "PARAPHRASE_INVARIANCE",
}


def load_manifest() -> Dict[str, Any]:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}


def validate_dataset(directory: str | Path) -> Dict[str, Any]:
    root = Path(directory)
    manifest = load_manifest()
    allowed_domains = set(manifest.get("domains", []))
    allowed_kinds = ALLOWED_KINDS
    fixture_files = sorted(root.glob("*.yaml"))
    findings: List[Dict[str, Any]] = []
    total_cases = 0
    by_kind: Dict[str, int] = {}

    if not fixture_files:
        findings.append({"file": str(root), "issue": "NO_FIXTURES_FOUND"})

    for fixture_path in fixture_files:
        data = yaml.safe_load(fixture_path.read_text(encoding="utf-8")) or {}
        cases = data.get("cases", []) if isinstance(data, dict) else []
        for idx, case in enumerate(cases):
            if not isinstance(case, dict):
                findings.append({"file": str(fixture_path), "index": idx, "issue": "CASE_NOT_MAPPING"})
                continue
            total_cases += 1
            kind = case.get("kind", "")
            if kind not in allowed_kinds:
                findings.append({"file": str(fixture_path), "index": idx, "case_id": case.get("id", ""), "issue": f"UNKNOWN_KIND:{kind}"})
            domain = case.get("domain", "")
            if domain and domain not in allowed_domains:
                findings.append({"file": str(fixture_path), "index": idx, "case_id": case.get("id", ""), "issue": f"UNKNOWN_DOMAIN:{domain}"})
            split = case.get("split", "gold")
            if split not in {"gold", "silver"}:
                findings.append({"file": str(fixture_path), "index": idx, "case_id": case.get("id", ""), "issue": f"INVALID_SPLIT:{split}"})
            by_kind[kind] = by_kind.get(kind, 0) + 1

    blocking = [f for f in findings if f.get("issue", "").startswith("UNKNOWN_") or f.get("issue") == "NO_FIXTURES_FOUND"]
    return {
        "directory": str(root),
        "fixture_count": len(fixture_files),
        "case_count": total_cases,
        "by_kind": by_kind,
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "status": "PASS" if not blocking else "FAIL",
        "findings": findings,
    }


def sample_dataset(directory: str | Path, size: int = 30, seed: int = 42) -> Dict[str, Any]:
    import random
    root = Path(directory)
    fixture_files = sorted(root.glob("*.yaml"))
    gold_cases: List[Dict[str, Any]] = []

    for fixture_path in fixture_files:
        data = yaml.safe_load(fixture_path.read_text(encoding="utf-8")) or {}
        cases = data.get("cases", []) if isinstance(data, dict) else []
        for case in cases:
            if isinstance(case, dict) and case.get("split", "gold") == "gold":
                gold_cases.append(dict(case, fixture=str(fixture_path)))

    rng = random.Random(seed)
    sample = rng.sample(gold_cases, min(size, len(gold_cases)))
    return {
        "sample_size": len(sample),
        "gold_available": len(gold_cases),
        "kinds_in_sample": sorted({c.get("kind", "") for c in sample}),
        "cases": sample,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build, validate, and sample relevance benchmark datasets.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("directory")
    sample = sub.add_parser("sample")
    sample.add_argument("directory")
    sample.add_argument("--size", type=int, default=30)
    sample.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.cmd == "validate":
        report = validate_dataset(args.directory)
    else:
        report = sample_dataset(args.directory, size=args.size, seed=args.seed)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status", "UNKNOWN") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
