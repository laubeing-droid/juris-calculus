#!/usr/bin/env python3
"""Collect JC performance baseline across 5 key operations (profiler)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OPS = [
    "rules_load",
    "blueprint_load",
    "evaluator_fixpoint",
    "router_domain_scan",
    "cross_jurisdiction_collide",
]


def collect_baseline(out_dir: str = "reports/perf") -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    metrics: Dict[str, float] = {}
    details: Dict[str, Any] = {}

    # 1. rules_load
    t0 = time.time()
    from compiler_core.config_paths import rules_path
    import yaml
    rules = yaml.safe_load(Path(rules_path("zh_CN")).read_text(encoding="utf-8"))
    metrics["rules_load_sec"] = round(time.time() - t0, 3)
    details["rules_count"] = len(rules) if isinstance(rules, list) else 0

    # 2. blueprint_load
    t0 = time.time()
    from compiler_core.config_paths import blueprint_path
    import json as _json
    bp = _json.loads(Path(blueprint_path()).read_text(encoding="utf-8"))
    metrics["blueprint_load_sec"] = round(time.time() - t0, 3)
    details["blueprint_domains"] = len(bp.get("domain_assets", []) or []) or len(bp.get("element_composition_contracts", []) or [])

    # 3. evaluator_fixpoint
    t0 = time.time()
    from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
    from compiler_core.types import IRState, LegalFact, LegalDomain
    from compiler_core.domain_config import DomainConfig
    loaded = load_rules_from_yaml(rules_path("zh_CN"))
    config = DomainConfig(domain=LegalDomain.CIVIL)
    ev = FixpointEvaluator(loaded, config)
    st = IRState()
    st.facts["f1"] = LegalFact(id="f1", description="合同已签订", formalizable=1.0)
    result = ev.evaluate(st)
    claims = list(result.claims.values()) if hasattr(result, "claims") else []
    metrics["evaluator_fixpoint_sec"] = round(time.time() - t0, 3)
    details["eval_claims"] = len(claims)
    details["eval_trust_label"] = claims[0].get_trust_label() if claims else "N/A"

    # 4. router_domain_scan
    t0 = time.time()
    from compiler_core.rule_router import RuleRouter
    rr = RuleRouter()
    routed = rr.route(["买卖合同纠纷", "被告逾期未交付"])
    metrics["router_scan_sec"] = round(time.time() - t0, 3)
    details["router_experts"] = routed.get("selected_experts", [])

    # 5. cross_jurisdiction_collide
    t0 = time.time()
    try:
        from compiler_core.legal_compiler import LegalCompiler
        lc = LegalCompiler()
        collision = lc.collide("CN", "US", ["contract", "breach"])
        metrics["cross_jurisdiction_sec"] = round(time.time() - t0, 3)
        details["collision_ok"] = bool(collision)
    except Exception:
        metrics["cross_jurisdiction_sec"] = round(time.time() - t0, 3)
        details["collision_ok"] = False

    trace = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "metrics": metrics,
        "details": details,
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_path = out / f"baseline_{stamp}.json"
    trace_path.write_text(_json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"status": "PASS", "trace_path": str(trace_path), "trace": trace}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect JC performance baseline.")
    parser.add_argument("--out-dir", default="reports/perf")
    args = parser.parse_args(argv)
    report = collect_baseline(args.out_dir)
    print(f"status={report['status']} trace={report['trace_path']}")
    for k, v in report["trace"]["metrics"].items():
        print(f"  {k}={v}s")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
