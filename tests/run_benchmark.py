"""
juris-calculus US Common Law Benchmark Runner

Objective:
  Feed 10 real US Complaint facts into FixpointEvaluator.
  Record: convergence, missing concepts, predicted hours, alpha fit.
  Zero code changes to compiler_core/ or legalos_services/.

Author: Laupinco — Hokkien Computational Jurisprudence Enthusiast
"""

import sys, os, json, glob, time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from compiler_core.types import LegalRule, LegalFact, IRState, LegalDomain
from compiler_core.evaluator import FixpointEvaluator, CriticalClarityFailure, load_rules_from_yaml
from compiler_core.domain_config import DomainConfig, get_domain_config

# Load US contract rules from YAML (configurable, not hardcoded)
US_CONTRACT_RULES = load_rules_from_yaml(
    os.path.join(os.path.dirname(__file__), '..', 'configs', 'en_US', 'rules.yaml')
)

US_CONFIG = DomainConfig(
    domain=LegalDomain.CIVIL,
    weights=(0.2, 0.2, 0.4, 0.2),
    taint_threshold=0.5,
    hard_audit_threshold=0.2,
    k_max=3,
    critical_score_threshold=0.3,
    critical_streak_max=3,
    concept_registry={
        "Contract", "Offer", "Acceptance", "Consideration", "Delivery",
        "Payment", "Breach", "ForceMajeure", "Impossibility", "Damages", "Remedies"
    },
    valid_transitions={
        "Pre-trial": ["Discovery"],
        "Discovery": ["Summary_Judgment", "Trial"],
        "Trial": ["Appeal"]
    }
)


@dataclass
class BenchmarkResult:
    case_id: str
    cause_of_action: str
    complexity: str = "?"
    expected: str = "—"
    notes: str = ""
    pre_missing: List[str] = field(default_factory=list)
    convergence: bool = False
    claims_found: int = 0
    deterministic: int = 0
    tainted: int = 0
    critical: int = 0
    actual_missing: List[str] = field(default_factory=list)
    pred_hours: float = 0.0
    alpha_fit: float = 0.0
    elapsed_ms: float = 0.0
    trace: str = ""


def load_complaint(filepath: str) -> Dict[str, Any]:
    """Load JSON complaint. Strips // and # comments."""
    import re
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    # Remove // comments and # comments
    text = re.sub(r'//.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'#.*$', '', text, flags=re.MULTILINE)
    return json.loads(text)


def run_benchmark(complaints_dir: str) -> List[BenchmarkResult]:
    ev = FixpointEvaluator(US_CONTRACT_RULES, US_CONFIG)
    results = []

    for fp in sorted(glob.glob(os.path.join(complaints_dir, 'US-*.json'))):
        case = load_complaint(fp)
        case_id = case.get('case_id', os.path.basename(fp))
        cause = case.get('cause_of_action', 'Unknown')
        facts_raw = case.get('facts', {})
        expected = case.get('expected', '—')
        complexity = case.get('complexity', '?')
        pre_missing = case.get('missing_concepts', [])

        # Build IRState
        state = IRState(world_id=case_id)
        missing = []
        for fid, desc in facts_raw.items():
            if desc and desc != 'TODO':
                state.facts[fid] = LegalFact(fid, str(desc))
            else:
                missing.append(fid)

        # Run evaluator
        t0 = time.time()
        halted = False
        try:
            state = ev.evaluate(state)
        except CriticalClarityFailure as e:
            halted = True
            state.trace = str(e)
        elapsed = round((time.time() - t0) * 1000, 1)

        # Analyze claims
        claims = list(state.claims.values()) if state.claims else []
        det = sum(1 for c in claims if not c.requires_human_review)
        tnt = sum(1 for c in claims if c.requires_human_review and c.confidence >= 0.2)
        cri = sum(1 for c in claims if c.confidence < 0.2)

        # Estimate hours (α=1.0 demo)
        from legalos_services.legalos_pricing import LegalOSPricingEngine, PricingCase
        engine = LegalOSPricingEngine()
        engine.ALPHA = 1.0
        ne = len(state.facts) + len(claims)
        case_p = PricingCase(effective_nodes=ne, location="CROSS_PROVINCE", stage="FIRST_INSTANCE")
        pricing = engine.predict_hours(case_p)

        result = BenchmarkResult(
            case_id=case_id, cause_of_action=cause,
            complexity=complexity, expected=expected,
            notes=case.get('notes', ''),
            pre_missing=pre_missing,
            convergence=not halted,
            claims_found=len(claims),
            deterministic=det, tainted=tnt, critical=cri,
            actual_missing=missing,
            pred_hours=pricing['total_hours'],
            alpha_fit=round(pricing['total_hours'] / max(1, ne), 2),
            elapsed_ms=elapsed,
            trace=f"HALTED: {state.trace}" if halted else f"CONVERGED: {len(claims)} claims"
        )
        results.append(result)

    return results


def export_markdown(results: List[BenchmarkResult], outpath: str):
    lines = [
        "# juris-calculus US Common Law Benchmark — 10 Complaint Cases",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M')}",
        f"Rules: US_CONTRACT_RULES ({len(US_CONTRACT_RULES)} rules)",
        f"Evaluator: FixpointEvaluator (juris-calculus v1.0.0)",
        "",
        "| Case | Cause of Action | Complx | Expected | Conv | Claims | Missing (Pre) | Missing (Actual) | Pred h | α Fit |",
        "|------|----------------|--------|----------|------|--------|---------------|------------------|--------|-------|",
    ]

    for r in results:
        conv = "✅" if r.convergence else "❌"
        pre_m = ", ".join(r.pre_missing[:3]) if r.pre_missing else "—"
        act_m = ", ".join(r.actual_missing[:3]) if r.actual_missing else "—"
        exp = r.expected[:30] if r.expected else "—"
        lines.append(
            f"| {r.case_id} | {r.cause_of_action[:30]} | {r.complexity} | {exp} | {conv} | "
            f"{r.claims_found} | {pre_m[:30]} | {act_m[:30]} | {r.pred_hours:.1f}h | {r.alpha_fit:.1f} |"
        )

    with open(outpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    with open(outpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"\n✅ Benchmark exported: {outpath}")
    print(f"   {len(results)} cases processed")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    complaints_dirs = [
        os.path.join(base_dir, "us_complaints", "core"),
        os.path.join(base_dir, "us_complaints", "roadmap"),
    ]
    results_dir = os.path.join(base_dir, "results")
    os.makedirs(results_dir, exist_ok=True)

    print("=" * 60)
    print("juris-calculus US Common Law Benchmark")
    print(f"Rules: {len(US_CONTRACT_RULES)} US contract rules")
    print("=" * 60)

    results = run_benchmark(complaints_dirs[0])
    for d in complaints_dirs[1:]:
        if os.path.isdir(d):
            results += run_benchmark(d)

    for r in results:
        conv = "✅" if r.convergence else "❌"
        match = "✓" if r.expected in str(r.trace) or (r.expected == 'HONEST_REFUSAL' and not r.convergence) else "?"
        print(f"\n{r.case_id} [{r.complexity:7s}] {conv} {r.claims_found} claims")
        print(f"  Expected: {r.expected}")
        print(f"  Pre-missing: {r.pre_missing}")
        print(f"  Actual-missing: {r.actual_missing}")
        print(f"  Pred: {r.pred_hours:.1f}h | α={r.alpha_fit:.1f} | {r.trace}")

    outpath = os.path.join(results_dir, "Benchmark_10Cases_US.md")
    export_markdown(results, outpath)
