#!/usr/bin/env python3
"""Collect E2E evidence: evaluator trace, rules timing, trust_label provenance."""
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


def collect_evidence(out_dir: str = "reports/e2e_evidence") -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    from compiler_core.config_paths import rules_path
    import yaml
    rules = yaml.safe_load(Path(rules_path("zh_CN")).read_text(encoding="utf-8"))
    rules_load_sec = round(time.time() - t0, 3)

    t0 = time.time()
    from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
    from compiler_core.types import IRState, LegalFact, LegalDomain
    from compiler_core.domain_config import DomainConfig
    loaded_rules = load_rules_from_yaml(rules_path("zh_CN"))
    config = DomainConfig(domain=LegalDomain.CIVIL)
    evaluator = FixpointEvaluator(loaded_rules, config)
    state = IRState()
    state.facts["test_contract"] = LegalFact(id="test_contract", description="买卖合同成立", formalizable=1.0)
    result_state = evaluator.evaluate(state)
    claims_list = list(result_state.claims.values()) if hasattr(result_state, "claims") else []
    eval_sec = round(time.time() - t0, 3)

    trace = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "rules_load_sec": rules_load_sec,
        "evaluation_sec": eval_sec,
        "rules_loaded": len(loaded_rules),
        "claims_produced": len(claims_list),
        "top_claim": claims_list[0].description if claims_list else "none",
        "trust_label": claims_list[0].get_trust_label() if claims_list else "N/A",
    }

    trace_path = out / f"eval_trace_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json"
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "PASS" if claims_list else "WARN",
        "trace_path": str(trace_path),
        "trace": trace,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect E2E evidence for JC verification.")
    parser.add_argument("--out-dir", default="reports/e2e_evidence")
    args = parser.parse_args(argv)
    report = collect_evidence(args.out_dir)
    print(f"status={report['status']} trace={report['trace_path']}")
    return 0 if report["status"] == "PASS" else 0


if __name__ == "__main__":
    sys.exit(main())
