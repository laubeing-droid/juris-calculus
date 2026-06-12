#!/usr/bin/env python3
import sys, yaml
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
REQUIRED = ["contract_id","layer","purpose","inputs","outputs","must_hold","failure_modes","ref_docs","ref_code","ref_tests","dynamic_parameters","pseudocode"]
def measure_completeness(path="configs/juris_contracts.yaml"):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    contracts = data.get("contracts",[])
    if not contracts: return {"status":"FAIL","completeness_pct":0,"issues":["no contracts"]}
    scores = []
    for c in contracts:
        s=0; missing=[]
        for f in REQUIRED:
            v=c.get(f)
            if v and v!=[] and v!="": s+=1
            else: missing.append(f)
        pct=round(s/len(REQUIRED)*100,1)
        scores.append({"contract_id":c.get("contract_id","?"),"score_pct":pct,"missing_fields":missing})
    avg=round(sum(x["score_pct"] for x in scores)/len(scores),1)
    return {"status":"PASS" if avg>=80 else ("WARN" if avg>=60 else "FAIL"),"completeness_pct":avg,"contract_count":len(scores),"details":scores}
def main(argv=None):
    r=measure_completeness()
    print(f"completeness={r['completeness_pct']}% status={r['status']}")
    return 0 if r["status"]!="FAIL" else 1
if __name__=="__main__": sys.exit(main())
