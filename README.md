# juris-calculus v1.0.2

A jurisdiction-agnostic symbolic reasoning & actuarial pricing engine for legal practice.

**Fixpoint iteration + Theil-Sen robust regression + Differential Privacy.**

*Not a localized legal app. A universal legal reasoning kernel.*

> **This is PostgreSQL, not Windows.**
>
> juris-calculus is a *legal reasoning kernel* — it provides the engine for logic, audit, and actuarial analysis. It does not manage documents, emails, or scheduling. If you are looking for an all-in-one legal suite, this is the engine you would build it upon, not the interface you would use daily.

---

## Scope (v1.0.0)

**Supported**: UCC Article 2 (Sales) contract disputes + Equitable Remedies (Specific Performance).

**Roadmap**: Tort, Securities, Antitrust, Constitutional law. See [`concept-roadmap.md`](concept-roadmap.md) for the 39-concept expansion plan with community PR guides.

`HONEST_REFUSAL` on unsupported domains is a feature, not a bug.

---

## Quick Start

```bash
cp configs/ignite_config.example.yaml ./configs/ignite_config.yaml
```

> **Note**: `ignite.py` is the private production orchestrator and is not included in this open-source repository. This kernel is designed to be embedded into your own pipeline.

---

## Environment

```bash
git clone https://github.com/laubeing-droid/juris-calculus.git
cd juris-calculus
pip install -r requirements.txt
```

> Sensitive legal data is never committed. Manage your data in `./data/` (gitignored by default).

## Architecture

```
juris-calculus/
├── compiler_core/          # Fixpoint reasoning kernel
│   ├── types.py            #   LegalRule / LegalFact / LegalClaim / TaintNode
│   ├── evaluator.py        #   FixpointEvaluator with exception chain + CRITICAL_CLARITY_FAILURE
│   ├── domain_config.py    #   Civil / Criminal dual-domain routing
│   └── batch_processor.py  #   Bulk case processor + JSON audit export
│
├── legalos_services/       # Mathematical models
│   ├── peripheral_models.py   # M10-M17 + calibrate_theilsen()
│   ├── legalos_pricing.py     # DAG-weighted nodes + multi-factor matrix + batch decay
│   └── differential_privacy.py # Laplace DP with ratio-preserving geometry
│
├── extractors/             # Structured extraction pipeline
│   ├── zh_CN/              #   Chinese Civil Law Parser 3.0
│   └── en_US/              #   US Common Law IRAC skeleton (community PRs welcome)
│
├── configs/
│   ├── zh_CN/domain_config.example.yaml
│   └── en_US/
│       ├── domain_config.example.yaml
│       └── rules.yaml          #   US contract rules (YAML-configurable)
│
└── tests/
    ├── run_benchmark.py    #   10-case US Common Law benchmark
    └── us_complaints/      #   core/ + roadmap/ dual-layer test data
```

---

## Why This Is Different

Most legal AI tools are RAG wrappers around LLMs. juris-calculus takes the opposite approach.

| | Legal RAG (Most Repos) | juris-calculus |
|---|---|---|
| **Logic** | Probabilistic (LLM) | Deterministic (Fixpoint) |
| **Audit** | Blackbox (Prompt) | Whitebox (DAG Trace) |
| **Pricing** | Guesswork | Theil-Sen Calibration |
| **Hallucination** | High | Low (Honest Refusal) |
| **Paradigm** | Chatbot | Symbolic AI / Computational Law |

### Supported Jurisdictions

| Jurisdiction | Status | Config |
|---|---|---|
| China (Civil Code — Contract) | ✅ v1.0.0 | `configs/zh_CN/` |
| US (UCC Article 2 + Equitable Remedies) | ✅ v1.0.0 | `configs/en_US/` |
| US (Tort / Securities / Antitrust / Constitutional) | 🚧 Roadmap | See `concept-roadmap.md` |
| EU / HK / Others | 🔮 Community | PRs welcome |

## Cross-Jurisdictional Generalization

The `FixpointEvaluator` is built on first-order predicate logic and monotonic fixed-point iteration. It is natively compatible with the **IRAC** (Issue, Rule, Application, Conclusion) paradigm of Common Law jurisdictions.

By swapping the jurisdiction config package and re-running Theil-Sen calibration, international firms can:

- Dissect complex case citation networks (DAG topology)
- Audit associate billable hours across billing tiers (leverage vector **H**)
- Mitigate LLM hallucinations in Federal/State litigation

*For the philosophical lineage behind this project, read the [Chinese README (README_CN.md)](README_CN.md).*

---

## Pricing Model

```
Quote = (WeightedNodes x DEFAULT_ALPHA) x B_location x G_stage + T_overhead

B_location: Local=1.0  Cross-province=1.3  Cross-state=1.8
G_stage:    First Instance=1.0  Appeal=1.25  Enforcement=1.1
```

`DEFAULT_ALPHA` = 1.0 (demo value). Calibrate with your own timesheet data via `calibrate_theilsen()`.

See the [calibration guide](#calibrating-your-alpha) below.

---

## Calibrating Your Alpha

The default α = 1.0 is an academic placeholder. Your firm has its own muscle memory.

**Three steps:**

1. Pick 10-50 real cases you personally handled.
2. Build a timesheet: each row = (deterministic node count D, actual hours h).
3. Feed it to Theil-Sen:

```python
from legalos_services.peripheral_models import CoveragePricingEngine

timesheet = [
    {"D": 8, "T": 2, "H": 0, "h": 12.0},
    {"D": 15, "T": 3, "H": 0, "h": 25.0},
    # ... at least 10 rows
]

cfg = CoveragePricingEngine.calibrate_theilsen(timesheet)
print(f"Your alpha = {cfg.taint_hour:.2f} h/node")
```

Theil-Sen median regression strips out associate padding and extreme case travel premiums, leaving only your firm's pure legal reasoning "golden slope."

---

## Data Format

### Input: facts.json

```json
{
  "domain": "Civil_Contract",
  "event_date": "20240601",
  "party_names": ["Buyer", "Seller"],
  "core_elements": {
    "payment_rule": "Annual rent of 160,000 CNY, due by Jan 31",
    "deposit": "Security deposit of 30,000 CNY"
  },
  "rigid_clauses": {
    "liquidated_damages": "Late payment: LPR x 1.5",
    "dispute_resolution": "Jurisdiction: court of contract execution"
  }
}
```

### Output: ignite_report.json

```json
{
  "total_contracts": 10,
  "avg_coverage": 0.75,
  "halted_count": 0,
  "details": [
    {
      "contract_id": "case_001",
      "claims_found": 4, "tainted": 1, "critical": 0,
      "coverage": 0.75, "trace_id": "TRACE-ABCD1234"
    }
  ]
}
```

---

## FAQ

**Q: Importing `peripheral_models` fails?**
Upgrade to the latest version; the class name was updated from `LegalIREvaluator` to `FixpointEvaluator`.

**Q: Where is `ignite.py`?**
It is not included. `ignite.py` is the private production orchestrator. This kernel is designed to be embedded into your own pipeline using `FixpointEvaluator` and `LegalOSPricingEngine` directly.

**Q: The default alpha gives inaccurate pricing?**
Yes. `alpha=1.0` is a demo placeholder. Run `calibrate_theilsen()` with your firm's historical timesheet data to derive your own constant.

**Q: Can I use this for torts / securities / antitrust?**
Not yet. See [`concept-roadmap.md`](concept-roadmap.md). Contributions welcome.

---

## Citing This Work

If you use juris-calculus in academic research, please cite:

```bibtex
@software{juris-calculus,
  author = {Laupinco},
  title = {juris-calculus: A Jurisdiction-Agnostic Legal Reasoning Kernel},
  year = {2026},
  version = {1.0.2},
  url = {https://github.com/laubeing-droid/juris-calculus}
}
```

---

## License

Apache 2.0

## Author

Laupinco — Hokkien Computational Jurisprudence Enthusiast (Powered by Gemini & WorkBuddy & DeepSeek-V4 Pro)

[*中文说明 (README_CN.md)*](README_CN.md)
