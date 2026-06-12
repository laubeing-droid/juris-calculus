#!/usr/bin/env python3
"""Self-healing closed loop: detect regression, auto-diagnose, suggest fixes."""
import argparse, json, sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

def run_healing_loop(baseline_path=None, out_dir="reports/healing"):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    from tools.perf_baseline import collect_baseline
    current = collect_baseline("reports/perf")
    cm = current["trace"].get("metrics",{}) or current.get("metrics",{})
    findings = []
    if baseline_path and Path(baseline_path).exists():
        bl = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
        bm = bl.get("trace",{}).get("metrics",{}) or bl.get("metrics",{})
        for k, cv in cm.items():
            rv = bm.get(k)
            if rv and rv > 0 and cv/rv >= 1.5:
                findings.append({"op":k,"current":cv,"baseline":rv,"ratio":round(cv/rv,2)})
    # run harness checks if degraded
    hi = []
    if findings:
        from tools.shape_checker import check_shapes
        from tools.module_interface_checker import check_interfaces
        sr = check_shapes(); ir = check_interfaces()
        if sr["status"]!="PASS": hi.extend(sr["findings"])
        if ir["status"]!="PASS": hi.extend(ir["findings"])
    diag = {"rules_load_sec":"cached rule index","blueprint_load_sec":"lazy load","evaluator_fixpoint_sec":"early-exit threshold","router_scan_sec":"hash index","cross_jurisdiction_sec":"blocking dict cache"}
    suggestions = [f"[{f['op']}] {diag.get(f['op'],'unknown')} slowdown {round((f['ratio']-1)*100)}%" for f in findings]
    suggestions.extend([f"[HARNESS] {i.get('class','?')}: {i.get('issue','?')}" for i in hi])
    if not suggestions: suggestions.append("System healthy; no degradation detected.")
    report = {"status":"DEGRADED" if findings else "PASS","regressions":findings,"harness_issues":hi,"suggestions":suggestions}
    rp = out / f"healing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status":report["status"],"report_path":str(rp),"report":report}

def main(argv=None):
    p = argparse.ArgumentParser(); p.add_argument("--baseline"); p.add_argument("--out-dir",default="reports/healing")
    args = p.parse_args(argv)
    r = run_healing_loop(args.baseline, args.out_dir)
    print(f"status={r['report']['status']} report={r['report_path']}")
    for s in r["report"]["suggestions"]: print(f"  {s}")
    return 0 if r["report"]["status"]=="PASS" else 1
if __name__=="__main__": sys.exit(main())
