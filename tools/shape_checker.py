#!/usr/bin/env python3
"""Harness Shape Checker: verify JC core data class interfaces."""
import argparse, sys, inspect
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SPEC = {
    "LegalFact": {"fields": ["id", "description", "source", "formalizable", "taint_status"]},
    "LegalClaim": {"fields": ["id", "description", "confidence", "epistemic_status"], "methods": ["get_trust_label"]},
    "IRState": {"fields": ["facts", "claims", "rules_applied", "domain"]},
    "LegalRule": {"fields": ["id", "premise_atoms", "head_claim"]},
    "FixpointEvaluator": {"methods": ["evaluate"]},
    "RuleRouter": {"methods": ["route"]},
    "AdversarialPipeline": {"methods": ["run_reasoner", "run_auditor", "run_verifier"]},
    "StepVerifier": {"methods": ["verify"]},
}

def check_shapes():
    findings = []; results = {}
    for name, spec in SPEC.items():
        try:
            mod_map = {
                "LegalFact": "compiler_core.types", "LegalClaim": "compiler_core.types",
                "IRState": "compiler_core.types", "LegalRule": "compiler_core.types",
                "FixpointEvaluator": "compiler_core.evaluator",
                "RuleRouter": "compiler_core.rule_router",
                "AdversarialPipeline": "pipeline.adversarial_pipeline",
                "StepVerifier": "compiler_core.step_verifier",
            }
            mod = __import__(mod_map[name], fromlist=[name])
            cls = getattr(mod, name, None)
            if cls is None: findings.append({"class":name,"issue":"not found","severity":"ERROR"}); results[name]="FAIL"; continue
            dc_fields = set(getattr(cls, "__dataclass_fields__", {}))
            issues = []
            for f in spec.get("fields", []):
                if not hasattr(cls, f) and f not in dc_fields: issues.append(f"missing field: {f}")
            for m in spec.get("methods", []):
                if not hasattr(cls, m): issues.append(f"missing method: {m}")
            if issues: findings.append({"class":name,"issue":"; ".join(issues),"severity":"ERROR"}); results[name]="FAIL"
            else: results[name] = "PASS"
        except Exception as e: findings.append({"class":name,"issue":str(e),"severity":"ERROR"}); results[name]="FAIL"
    return {"status":"PASS" if not any(f["severity"]=="ERROR" for f in findings) else "FAIL","results":results,"findings":findings}

def main(argv=None):
    r = check_shapes()
    print(f"status={r['status']}")
    for f in r["findings"]: print(f"  ISSUE: {f}")
    return 0 if r["status"]=="PASS" else 1
if __name__=="__main__": sys.exit(main())
