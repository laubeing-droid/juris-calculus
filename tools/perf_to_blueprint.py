#!/usr/bin/env python3
"""Feed perf_baseline results back into the knowledge graph (MetaInfer Section 7.1).

For JC, "performance knowledge graph enhancement" means:
  - Extract performance patterns from baseline traces
  - Create structured performance rules in the blueprint
  - Enable throughput comparison between current and baseline
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PATTERNS_PATH = "configs/perf_patterns.yaml"


def extract_patterns(baseline_path: str) -> Dict[str, Any]:
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    trace = baseline.get("trace", baseline)
    metrics = trace.get("metrics", {}) or baseline.get("metrics", {})
    details = trace.get("details", {}) or baseline.get("details", {})

    patterns: List[Dict[str, Any]] = []

    # Pattern 1: rules_load
    if "rules_load_sec" in metrics:
        patterns.append({
            "id": "PERF_RULES_LOAD",
            "layer": "P2",
            "metric": "rules_load_sec",
            "value": metrics["rules_load_sec"],
            "threshold_warn": metrics["rules_load_sec"] * 1.5,
            "threshold_error": metrics["rules_load_sec"] * 3.0,
            "note": "rules.yaml load time; use cached index for hot paths",
            "ref_code": "compiler_core/config_paths.py",
        })

    # Pattern 2: evaluator
    if "evaluator_fixpoint_sec" in metrics:
        patterns.append({
            "id": "PERF_EVALUATOR_FIXPOINT",
            "layer": "P3",
            "metric": "evaluator_fixpoint_sec",
            "value": metrics["evaluator_fixpoint_sec"],
            "threshold_warn": metrics["evaluator_fixpoint_sec"] * 1.5,
            "threshold_error": metrics["evaluator_fixpoint_sec"] * 3.0,
            "claims": details.get("eval_claims", 0),
            "trust_label": details.get("eval_trust_label", "N/A"),
            "note": "FixpointEvaluator convergence; early-exit threshold can reduce iterations",
            "ref_code": "compiler_core/evaluator.py",
        })

    # Pattern 3: router
    if "router_scan_sec" in metrics:
        patterns.append({
            "id": "PERF_ROUTER_SCAN",
            "layer": "P4",
            "metric": "router_scan_sec",
            "value": metrics["router_scan_sec"],
            "threshold_warn": max(metrics["router_scan_sec"] * 2.0, 0.01),
            "threshold_error": max(metrics["router_scan_sec"] * 5.0, 0.05),
            "experts": details.get("router_experts", []),
            "note": "MoE keyword scan; pre-building domain-to-keyword hash index eliminates O(n*m) scan",
            "ref_code": "compiler_core/rule_router.py",
        })

    # Pattern 4: blueprint load
    if "blueprint_load_sec" in metrics:
        patterns.append({
            "id": "PERF_BLUEPRINT_LOAD",
            "layer": "P2",
            "metric": "blueprint_load_sec",
            "value": metrics["blueprint_load_sec"],
            "threshold_warn": metrics["blueprint_load_sec"] * 1.5,
            "threshold_error": metrics["blueprint_load_sec"] * 3.0,
            "domain_count": details.get("blueprint_domains", 0),
            "note": "Blueprint JSON load; lazy loading or mmap reduces startup cost",
            "ref_code": "compiler_core/juris_blueprint.py",
        })

    # Pattern 5: cross-jurisdiction (JC's "communication efficiency")
    if "cross_jurisdiction_sec" in metrics:
        patterns.append({
            "id": "PERF_CROSS_JURISDICTION",
            "layer": "P9",
            "metric": "cross_jurisdiction_sec",
            "value": metrics["cross_jurisdiction_sec"],
            "threshold_warn": metrics["cross_jurisdiction_sec"] * 1.3,
            "threshold_error": metrics["cross_jurisdiction_sec"] * 2.0,
            "note": "Cross-jurisdiction collision; pre-built blocking dictionary replaces O(n^2) pair check (equivalent to CustomAR vs NCCL watershed)",
            "ref_code": "compiler_core/legal_compiler.py",
        })

    patterns_doc = {
        "version": "2.0.0",
        "name": "JC performance knowledge graph patterns (Section 7.1 inspired)",
        "source": baseline_path,
        "updated": datetime.now(timezone.utc).isoformat(),
        "patterns": patterns,
    }

    out_path = ROOT / PATTERNS_PATH
    out_path.write_text(yaml.dump(patterns_doc, allow_unicode=True), encoding="utf-8")

    return {"status": "PASS", "patterns_path": str(out_path), "pattern_count": len(patterns)}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract performance patterns from baseline and feed back into knowledge graph.")
    parser.add_argument("--baseline", required=True, help="Path to a perf_baseline JSON report")
    args = parser.parse_args(argv)
    report = extract_patterns(args.baseline)
    print(f"status={report['status']} patterns={report['pattern_count']} path={report['patterns_path']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
