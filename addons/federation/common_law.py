#!/usr/bin/env python3
"""Common Law Federation — dynamic N-way comparison between common-law jurisdictions.

Discovers all registered common-law addons from plugin_registry.
Adding UK auto-includes it in all pair-wise comparisons.
"""
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from compiler_core.plugin_registry import registry
from compiler_core.types import LegalFact, IRState, LegalDomain
from compiler_core.domain_config import DomainConfig


class FederatedReasoner:
    """Dynamic common-law federation: auto-discovers common-law adapters."""

    def __init__(self):
        self.adapters = registry.get_by_family("common_law")

    @property
    def jurisdictions(self) -> List[str]:
        return sorted(self.adapters.keys())

    @property
    def pair_count(self) -> int:
        n = len(self.jurisdictions)
        return n * (n - 1) // 2

    def run(self, facts: Dict[str, float], jurisdictions: List[str] = None) -> Dict:
        if jurisdictions is None:
            jurisdictions = self.jurisdictions
        results = {}
        for jdx in jurisdictions:
            adapter = self.adapters.get(jdx)
            if adapter is None:
                results[jdx] = {"error": f"Adapter {jdx} not installed"}
                continue
            s = IRState(domain=LegalDomain.CIVIL, jurisdiction=jdx)
            for fid, conf in facts.items():
                s.facts[fid] = LegalFact(fid, extraction_confidence=conf)
            try:
                ev = adapter.load_evaluator()
                res = ev.evaluate(s)
                results[jdx] = {
                    "claims": {c.id: c.confidence for c in res.claims.values() if c.confidence > 0},
                    "state": s.state_tracker.get("Contract_Validity", "?"),
                    "rebuttals": len(s.rebuttal_log),
                    "L0_map": {fid: adapter.map_to_L0(fid) for fid in facts},
                    "guardrail": adapter.validate_against_guardrails(s),
                }
            except Exception as e:
                results[jdx] = {"error": str(e)}
        diff = self._compute_diffs(results, jurisdictions)
        return {"results": results, "diff": diff, "jurisdictions": jurisdictions}

    def _compute_diffs(self, results: Dict, jdxs: List[str]) -> List[Dict]:
        diffs = []
        for i, j1 in enumerate(jdxs):
            for j2 in jdxs[i + 1:]:
                r1, r2 = results.get(j1, {}), results.get(j2, {})
                c1, c2 = set(r1.get("claims", {}).keys()), set(r2.get("claims", {}).keys())
                diffs.append({
                    "pair": f"{j1} vs {j2}",
                    "shared_claims": sorted(c1 & c2),
                    f"{j1}_only": sorted(c1 - c2),
                    f"{j2}_only": sorted(c2 - c1),
                    "state_divergence": (
                        f"{r1.get('state','?')} vs {r2.get('state','?')}"
                        if r1.get("state") != r2.get("state") else ""
                    ),
                })
        return diffs
