#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
def verify_recovery_safeguards():
    findings = []; results = {}
    from compiler_core.types import IRState
    s = IRState(); results["max_iterations"] = s.max_iterations
    if s.max_iterations <= 0 or s.max_iterations > 10000:
        findings.append({"guard":"max_iterations","issue":f"out of range: {s.max_iterations}","severity":"ERROR"})
    from compiler_core.domain_config import DomainConfig
    c = DomainConfig(); results["hard_audit_threshold"] = c.hard_audit_threshold
    if c.hard_audit_threshold <= 0 or c.hard_audit_threshold >= 1:
        findings.append({"guard":"hard_audit_threshold","issue":str(c.hard_audit_threshold),"severity":"ERROR"})
    from compiler_core.rule_router import FALLBACK_ROUTER_CONFIG
    results["fallback_config"] = bool(FALLBACK_ROUTER_CONFIG and FALLBACK_ROUTER_CONFIG.get("expert_shards"))
    return {"status":"PASS" if not any(f["severity"]=="ERROR" for f in findings) else "FAIL","results":results,"findings":findings}
def main(argv=None):
    r=verify_recovery_safeguards()
    print(f"status={r['status']}")
    return 0 if r["status"]=="PASS" else 1
if __name__=="__main__": sys.exit(main())
