# juris-calculus v2.0.0 — Tri-Rail

**A multi-jurisdiction symbolic legal reasoning engine with cross-border collision detection.**

Fixpoint evaluator + Tri-Rail Collider (PRC × HK × US) + PRC-US semantic alignment framework.

*Not a localized legal app. A universal legal reasoning kernel that refuses to answer when it shouldn't.*

> **This is PostgreSQL, not Windows.**
>
> juris-calculus is a *legal reasoning kernel* — it provides logic, audit trails, and cross-jurisdiction collision analysis. It does not manage documents, emails, or scheduling.

---

## What's New in v2.0.0

- **Tri-Rail Collider**: Collide PRC, HK, and US parallel inference traces to detect 12 classes of cross-border conflict
- **PRC-US Semantic Alignment**: 60 CBL blocking rules + 23 SPC judicial tendency rules + 10 procedural justice defenses — prevents US legal concepts from contaminating PRC reasoning
- **HK Expansion**: 93 Horn rules distilled from HK e-Legislation (Cap 26, 32, 622, 571, 4A)
- **Action Agent**: Auto-generate partner-ready legal memos from collider output via Jinja2 templates
- **MCP Server**: Protocol-compliant server (9 resources, 7 tools) for AI assistant integration
- **Operator Registry**: Bootstrap/snapshot/rollback for 68 legal operators with JSON Schema validation

---

## Architecture

```
juris-calculus/
├── compiler_core/            # Fixpoint reasoning kernel
│   ├── evaluator.py          #   FixpointEvaluator + exception chain + critical clarity failure
│   ├── types.py              #   LegalRule / LegalFact / LegalClaim / NegativeSpec
│   ├── domain_config.py      #   Domain routing + discretionary concept detection
│   ├── classifier.py         #   EvidenceClassifier (A/B/C carrier levels)
│   ├── batch_processor.py    #   Bulk case processor + JSON audit export
│   └── parallax_inference.py #   Cross-jurisdiction inference engine
│
├── pipeline/                 # End-to-end reasoning pipeline
│   ├── pipeline.py           #   Text → facts → inference → report
│   ├── prc_us_alignment.py   #   PRC-US alignment watchdog (3-layer gate)
│   ├── schemas.py            #   Data contracts for the tri-rail pipeline
│   ├── alignment_loader.py   #   YAML rule loader with FastPath hot-load
│   ├── guardian.py           #   NOMINEE gate + error classifier
│   └── llm_client.py         #   LLM API client (env-var configured)
│
├── adapter/                  # Jurisdiction adapters
│   └── prc_adapter.py        #   PRC triple-rail engine (CBL + SPC + CN 2,117 rules)
│
├── configs/
│   ├── zh_CN/                #   PRC Civil Code: 13 domains, 2,117 Horn rules
│   ├── en_US/                #   US federal: 81 Horn rules + 86 L0 constraints
│   ├── hk/                   #   HK: 93 Horn rules (Cap 26/32/622/571/4A)
│   ├── prc_us_alignment/     #   PRC-US bridge: blocking rules + SPC + terms
│   ├── us/threat_signatures/ #   US state-level FastPath signatures (WI 12 + NJ 12)
│   ├── uk/                   #   UK: 5 candidate rules (community expansion)
│   └── core_ontology.yaml    #   L0 schema (6 primitives) + L1 (14 abstractions)
│
├── tools/                    # Collision testing + maintenance
│   ├── run_trirail_matrix.py #   Tri-Rail Collider: 12 cross-border scenarios
│   ├── run_parallax_matrix.py#   Parallax matrix: jurisdiction divergence heatmap
│   ├── press_long_tail.py    #   3,800-term long-tail saturation engine
│   ├── distill_jurisdiction.py# Jurisdiction distillation workbench
│   ├── operator_registry.py  #   Operator registry with bootstrap/snapshot/rollback
│   └── action_agent/         #   MemoCompiler: collider output → partner memo
│
├── extractors/               # Structured fact extraction
│   ├── zh_CN/                #   Chinese civil law parser
│   └── en_US/                #   US common law IRAC skeleton
│
├── legalos_services/         # Mathematical pricing models
│   ├── peripheral_models.py  #   Theil-Sen calibration + M10-M17 models
│   ├── legalos_pricing.py    #   DAG-weighted pricing + multi-factor matrix
│   └── differential_privacy.py#  Laplace DP with ratio-preserving geometry
│
├── tests/
│   ├── unit/                 #   Unit tests (evaluator, inspectors, PRC rules)
│   └── run_benchmark_zh.py   #   PRC benchmark (13 cases, 100% convergence)
│
├── mcp_server.py             # FastMCP server (9 resources, 7 tools)
└── mcp_manifest.json         # MCP protocol manifest
```

---

## Supported Jurisdictions

| Jurisdiction | Rules | Domains | Status |
|---|---|---|---|
| **PRC** (Civil Code) | 2,117 | 13 domains (Contract/Tort/Corporate/Criminal/Admin/IP...) | v2.0.0 |
| **US** (Federal) | 81 Horn + 86 constraints | UCC Art.2, Due Process, Equitable Remedies | v2.0.0 |
| **US** (State threat) | 24 signatures | WI long-arm jurisdiction, NJ punitive damages | v2.0.0 |
| **HK** (Ordinances) | 93 | Cap 26/32/622/571/4A | v2.0.0 |
| **UK** | 5 candidates | Sale of Goods Act | Community |
| **PRC-US Alignment** | 60 CBL + 23 SPC + 10 proc | Cross-jurisdiction blocking + defense | v2.0.0 |

---

## Tri-Rail Collider

The collider runs a single fact pattern through three parallel legal reasoning traces:

```
Facts → [PRC Adapter (CBL gate + SPC + CN rules)]
      → [HK Engine (93 Horn rules, Cap 26/32/622/571/4A)]
      → [US Engine (81 federal + 86 constraints + state FastPath)]

      → Collision Matrix (12 conflict classes)
      → MemoCompiler (partner-ready markdown)
```

**12 conflict classes detected**: ultra vires data export, litigation discovery deadlock, OFAC sanction conflict, plea bargaining cross-border, Chapter 11 director conflict, cross-border factoring, crypto transaction, VIE structure, algorithm filing, at-will employment, pure domestic CN, CN bridge verification.

---

## Why This Is Different

| | Legal RAG (Most Repos) | juris-calculus |
|---|---|---|
| **Logic** | Probabilistic (LLM) | Deterministic (Fixpoint) |
| **Audit** | Blackbox (Prompt) | Whitebox (DAG Trace) |
| **Cross-jurisdiction** | None | Tri-Rail Collider (12 classes) |
| **Hallucination** | High | Low (Honest Refusal + CRITICAL_CLARITY_FAILURE) |
| **Paradigm** | Chatbot | Symbolic AI / Computational Law |
| **PRC-US alignment** | None | 60 CBL blocking rules |

---

## Quick Start

```bash
git clone https://github.com/laubeing-droid/juris-calculus.git
cd juris-calculus
pip install -r requirements.txt
```

```python
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.types import IRState, LegalFact, LegalDomain

rules = load_rules_from_yaml("configs/hk/rules.yaml")
facts = IRState(facts=[
    LegalFact(atom="Seller_TransfersOrAgrees_Property", confidence=1.0),
    LegalFact(atom="Buyer_Pays_MoneyConsideration", confidence=1.0),
])
evaluator = FixpointEvaluator(rules)
result = evaluator.evaluate(facts)
print(f"Claims: {len(result.claims)}, Tainted: {len(result.tainted)}")
```

---

## MCP Server

```bash
# Start the MCP server for AI assistant integration
python mcp_server.py
```

Provides 9 resources (rule sets, ontologies, matrix reports) and 7 tools (evidence review, argument lint, contract review, memo compile, etc.).

---

## FAQ

**Q: Where is ignite.py?**
It is not included. `ignite.py` is the private production orchestrator. This kernel is designed to be embedded into your own pipeline.

**Q: Can I use this for torts / securities / antitrust?**
Not yet. See [`concept-roadmap.md`](concept-roadmap.md). Contributions welcome.

**Q: How do I add a new jurisdiction?**
Use `tools/distill_jurisdiction.py` — a 4-stage workbench: term extraction → Horn generation → L0 validation → YAML output. See `configs/uk/rules_candidates.yaml` for an example.

**Q: Is the pricing model production-ready?**
`alpha=1.0` is a demo placeholder. Run `calibrate_theilsen()` with your firm's historical timesheet data to derive your own constant.

---

## License

Apache 2.0

## Author

Laupinco — Hokkien Computational Jurisprudence Enthusiast

[中文说明 (README_CN.md)](README_CN.md)
