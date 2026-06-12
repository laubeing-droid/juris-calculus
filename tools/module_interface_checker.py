#!/usr/bin/env python3
"""Harness Module Interface Checker: verify key classes expose standard methods."""
import argparse, sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

REQUIRED = {
    ("compiler_core.evaluator", "FixpointEvaluator"): ["evaluate"],
    ("compiler_core.rule_router", "RuleRouter"): ["route"],
    ("compiler_core.step_verifier", "StepVerifier"): ["verify"],
    ("compiler_core.trust_labels", "EpistemicStatus"): ["to_dict"],
    ("pipeline.adversarial_pipeline", "AdversarialPipeline"): ["run_reasoner", "run_auditor", "run_verifier"],
}

def check_interfaces():
    findings = []; results = {}
    for (mod_name, cls_name), methods in REQUIRED.items():
        try:
            mod = __import__(mod_name, fromlist=[cls_name])
            cls = getattr(mod, cls_name, None)
            if cls is None: findings.append({"class":f"{mod_name}.{cls_name}","issue":"not found","severity":"ERROR"}); continue
            for m in methods:
                key = f"{cls_name}.{m}"
                results[key] = "PASS" if hasattr(cls, m) else "FAIL"
                if not hasattr(cls, m): findings.append({"class":cls_name,"method":m,"issue":"missing","severity":"ERROR"})
        except ImportError as e: findings.append({"module":mod_name,"issue":str(e),"severity":"ERROR"})
    return {"status":"PASS" if not any(f["severity"]=="ERROR" for f in findings) else "FAIL","results":results,"findings":findings}

def main(argv=None):
    r = check_interfaces()
    print(f"status={r['status']} checked={len(r['results'])}")
    for f in r["findings"]: print(f"  ISSUE: {f}")
    return 0 if r["status"]=="PASS" else 1
if __name__=="__main__": sys.exit(main())
