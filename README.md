# juris-calculus

**Deterministic Symbolic Legal Reasoning Engine — Four-Stage Pipeline + Multi-Jurisdiction + Evidence-Calibrated Trust Labels**

A jurisdiction-agnostic Horn clause engine with Dung AAF grounded extension, Defeasible Deontic Logic (DDL) modal classification, cross-jurisdiction obstruction-first routing, and a 7-level trust label system backed by a formal specification boundary.

*Not a legal app. A legal reasoning kernel.*

---

## What It Does

juris-calculus compiles statutory law into executable Horn rules, then reasons over them through a **four-stage pipeline** with evidence-calibrated trust labels.

```
Stage 1: Monotone Horn Closure (Lean-spec-backed + runtime-tested)
    ↓
Stage 2: Dung AAF Attack Graph (Lean-spec-backed + runtime-tested)
    ↓
Stage 3: Grounded Extension (deterministic, finite convergence)
    ↓
Stage 4: Trust Label Projection + allowed/forbidden marking
```

**Three jurisdictions, one engine:**

| Jurisdiction | Rules | Source | Role |
|-------------|-------|--------|------|
| CN (China) | 21,144 | 20 books (8,712 pages, 727万字) | Primary jurisdiction |
| HK (Hong Kong) | 104 | HK legislation | US↔CN bridge layer |
| US (Federal) | 123 | US Code + UCC + Restatement | Cross-border disputes |

**Cross-border architecture (obstruction-first):**

```
US Terms ──→ L0 Primitives ←── HK Terms ──→ L0 Primitives ←── CN Terms
              (Status/Act/Defect/Power/Agent/Asset)

Obstruction Registry:
  MATCH       → allow mapping (preserve jurisdiction tag)
  COLLISION   → block automatic mapping
  ASYMMETRY   → block automatic mapping
  UNVERIFIED  → human review only
```

---

## Architecture

```
juris-calculus/
├── compiler_core/                    # Reasoning kernel (68 modules)
│   ├── evaluator.py                  #   FixpointEvaluator + evaluate_horn() + DDL modal gate
│   ├── stratified_evaluator.py       #   Four-stage pipeline (Horn → AAF → GE → Trust Labels)
│   ├── argumentation.py              #   Dung AAF grounded extension + attack graph builder
│   ├── types.py                      #   LegalRule / LegalClaim / IRState / DataQuality
│   ├── trust_labels.py               #   7-level TrustLabel + EpistemicStatus + RuleMaturity
│   ├── constraint_validator.py       #   Absolute/Conditional rebuttal + L0 constraints
│   ├── domain_config.py              #   Weight/threshold config per domain
│   ├── dp_policy_loader.py           #   Differential privacy policy (epsilon from config, not law)
│   ├── source_manifest.py            #   Source verification (20 books + statutes registered)
│   ├── evidence_evaluation.py        #   Evidence credibility: S(e) = reliability × independence × authenticity
│   ├── burden_of_proof.py            #   Burden allocation and completion tracking
│   ├── legal_reasoning.py            #   Analogical, precedent, interpretation, interest balancing
│   ├── cross_jurisdiction_router.py  #   Obstruction-first routing (no universal functor)
│   ├── proof_trace_renderer.py       #   Proof trace → Chinese natural language
│   ├── invariance_metrics.py         #   Inv(f)/Align(f) + ContextualOverlapScore (NOT a metric)
│   └── ... (15 more modules)
├── addons/
│   ├── cn/                           #   China addon
│   ├── hk/                           #   Hong Kong addon (bridge layer)
│   └── us/                           #   US Federal addon
├── configs/
│   ├── zh_CN/rules.yaml              #   21,144 CN rules (20 books auto-distilled)
│   ├── zh_CN/concept_registry.yaml   #   31,749 unique legal concepts
│   ├── zh_CN/dp_policy.yaml          #   DP privacy policies
│   ├── zh_CN/source_manifest.yaml    #   Registered sources (20 books + statutes)
│   ├── obstruction_registry.yaml     #   CN↔HK↔US concept mapping status
│   └── ...
├── tools/                            #   67 analysis and quality tools
└── tests/                            #   296 passing tests, 38 skipped in the latest local run
```

---

## Key Metrics

| Metric | Value |
|--------|-------|
| CN Rules | 21,144 |
| Tests | 296 passed, 38 skipped |
| Core Modules | 68 |
| MCP Tools | 18 |
| Unique Concepts | 31,749 |
| Source Anchor Coverage | 97.1% |
| Formal Spec Boundary | 94 unique Lean theorem names in legal-math-modeling; Python runtime is not Lean-proven end-to-end |
| Audit Rounds | 5 rounds Codex (14 findings, all fixed) |

---

## Quick Start

```python
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.types import IRState, LegalFact

# Load Chinese law rules
rules = load_rules_from_yaml("configs/zh_CN/rules.yaml")
ev = FixpointEvaluator(rules)

# Run inference
state = IRState()
state.facts["contract_formed"] = LegalFact(id="contract_formed", description="合同成立")
state.facts["breach_alleged"] = LegalFact(id="breach_alleged", description="违约事实")
result = ev.evaluate(state)

# Output: claims with confidence, trust labels, proof traces
for cid, claim in result.claims.items():
    print(f"{cid}: conf={claim.confidence:.2f}, trust={claim.get_trust_label()}")
```

---

## Four-Stage Pipeline

```python
from compiler_core.stratified_evaluator import StratifiedEvaluator

se = StratifiedEvaluator("configs/zh_CN/rules.yaml")
state = IRState()
state.facts["breach"] = LegalFact(id="breach", description="违约")

claims = se.evaluate(state)
# Each claim has: allowed_claim, forbidden_claim, agent_instruction, epistemic_status
```

**Stage 1** (Horn): Pure forward-chain, monotone (Tarski fixpoint exists).
**Stage 2** (AAF): Build attack graph from rules, exceptions, rebuttals, prohibitions.
**Stage 3** (GE): Dung grounded extension — deterministic acceptance/rejection.
**Stage 4** (Labels): Trust label projection + allowed/forbidden marking.

---

## MCP Tools (18)

| Tool | Function |
|------|----------|
| search_rules | Concept-aware rule search |
| evaluate_facts | Four-stage pipeline inference |
| calculate_damages | LPR-based damage calculation |
| analyze_strategy | Strategy analysis with adversarial pipeline |
| evaluate_dp_policy | DP privacy policy check |
| validate_source | Source manifest verification |
| evaluate_evidence | Evidence credibility scoring |
| track_burden | Burden of proof tracking |
| analyze_analogy | Analogical similarity + precedent force |
| predict_sentence | Criminal sentencing prediction |
| estimate_ip_value | IP valuation |
| check_compliance | Compliance monitoring |
| analyze_arbitration | Arbitration clause analysis |
| route_cross_jurisdiction | Obstruction-first routing |
| check_obstruction | Obstruction registry lookup |
| format_proof_trace | Proof trace → Chinese text |
| extract_elements | Legal element extraction |
| juris_query | Unified query entry point |

---

## Mathematical Foundation

Backed by the [legal-math-modeling](https://github.com/laubeing-droid/legal-math-modeling) companion repository:

| Claim | Status | Evidence |
|-------|--------|----------|
| Horn closure monotonicity/minimality | **Lean specification proved** | legal-math-modeling `HornFixedPoint.lean` + theorem manifest |
| Dung grounded extension existence/least fixed point | **Lean specification proved** | legal-math-modeling `DungFixedPoint.lean` + theorem manifest |
| JC spec shadow fixtures | **Runtime aligned** | `tests/unit/test_spec_shadow_harness.py`, 10 aligned fixtures |
| Independent checker-backed certificates | **Runtime tested** | `tests/test_independent_checker.py` + `compiler_core/certificate_checker.py` |
| Graph similarity as a metric | **Forbidden as a formal claim** | legal-math-modeling forbidden-claim boundary |
| DP/privacy guarantees | **Not established** | epsilon is config/policy input, not a theorem |

**Trust Label System (7 levels):**
UNVERIFIED → ENGINEERING_BASELINE → DATA_INSUFFICIENT → TOY_SYNTHETIC → TESTED_PROPERTY → SMT_PROVED → PROVED_FORMAL → PROVED_BY_EXHAUSTIVE_ENUMERATION

---

## Installation

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

---

## License

MIT
