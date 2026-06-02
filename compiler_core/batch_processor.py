#!/usr/bin/env python3
"""juris-calculus 批量处理器 + JSON审计输出"""
import sys,os,json
from typing import List,Dict
from dataclasses import dataclass,asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from compiler_core.types import LegalRule,LegalFact,IRState
from compiler_core.evaluator import FixpointEvaluator,CriticalClarityFailure

@dataclass
class ContractReviewResult:
    contract_id:str; claims_found:int=0; deterministic:int=0; tainted:int=0; critical:int=0
    coverage:float=0.0; halted:bool=False; trace_id:str=""; claims_detail:List[Dict]=None
    def __post_init__(self):
        if self.claims_detail is None: self.claims_detail=[]

class BatchProcessor:
    def __init__(self,ev:FixpointEvaluator): self.ev=ev; self.results:List[ContractReviewResult]=[]
    def process(self,contracts:Dict[str,Dict[str,str]], label:str="")->List[ContractReviewResult]:
        if not contracts:
            return []
        for cid,fd in contracts.items():
            s=IRState(world_id=cid)
            for fid,desc in fd.items():
                if fid.startswith("_"): continue
                if fid == "_domain" or fid == "_verdict": continue
                s.facts[fid]=LegalFact(fid,str(desc))
            halted=False
            try: r=self.ev.evaluate(s)
            except CriticalClarityFailure: halted=True; r=s
            cl=list(r.claims.values()) if r.claims else []
            det=sum(1 for c in cl if not c.requires_human_review)
            tnt=sum(1 for c in cl if c.requires_human_review and c.confidence>=0.2)
            cri=sum(1 for c in cl if c.confidence<0.2)
            total=len(cl); cov=round(det/max(1,total),2)
            rr=ContractReviewResult(contract_id=cid,claims_found=total,deterministic=det,tainted=tnt,critical=cri,coverage=cov,halted=halted,trace_id=f"TRACE-{hash(cid)&0xFFFFFFFF:08X}",claims_detail=[{"id":c.id,"confidence":c.confidence,"taint":c.taint_summary(),"human":c.requires_human_review} for c in cl])
            self.results.append(rr)
    def process_parallel(self, contracts: Dict[str, Dict[str, str]], max_workers: int = 8) -> List['ContractReviewResult']:
        """Process contracts in parallel using ThreadPoolExecutor."""
        if not contracts:
            return []
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._process_one, cid, fd): cid 
                       for cid, fd in contracts.items()}
            for future in as_completed(futures):
                results.append(future.result())
        self.results = results
        return results

    def _process_one(self, cid: str, fd: Dict[str, str]) -> ContractReviewResult:
        """Process a single contract (used by process_parallel)."""
        s = IRState(world_id=cid)
        for fid, desc in fd.items():
            if fid.startswith("_"): continue
            if fid == "_domain" or fid == "_verdict": continue
            s.facts[fid] = LegalFact(fid, str(desc))
        halted = False
        try:
            r = self.ev.evaluate(s)
        except CriticalClarityFailure:
            halted = True
            r = s
        cl = list(r.claims.values()) if r.claims else []
        det = sum(1 for c in cl if not c.requires_human_review)
        tnt = sum(1 for c in cl if c.requires_human_review and c.confidence >= 0.2)
        cri = sum(1 for c in cl if c.confidence < 0.2)
        total = len(cl)
        cov = round(det / max(1, total), 2)
        return ContractReviewResult(
            contract_id=cid, claims_found=total,
            deterministic=det, tainted=tnt, critical=cri,
            coverage=cov, halted=halted,
            trace_id=f"TRACE-{hash(cid) & 0xFFFFFFFF:08X}",
            claims_detail=[{"id": c.id, "confidence": c.confidence,
                           "taint": c.taint_summary(), "human": c.requires_human_review}
                          for c in cl]
        )
    def summary(self)->Dict:
        if not self.results: return {}
        n=len(self.results); ac=sum(r.coverage for r in self.results)/n; hn=sum(1 for r in self.results if r.halted)
        return {"total_contracts":n,"avg_coverage":round(ac,2),"halted_count":hn,"details":[asdict(r) for r in self.results]}
    def export_json(self,path:str):
        with open(path,'w',encoding='utf-8') as f: json.dump(self.summary(),f,indent=2,ensure_ascii=False)
