# juris-calculus

**Agnostic Symbolic Legal Reasoning Compiler — DDL + Multi-Jurisdiction + ProofTree**

A jurisdiction-agnostic Horn clause engine with fixed-point iteration, Defeasible Deontic Logic (DDL) modal classification, and cross-jurisdiction bridge layer.

*Not a legal app. A legal reasoning kernel.*

---

## What It Does

juris-calculus compiles statutory law into executable Horn rules, then reasons over them using fixed-point iteration with DDL modal gates (OBLIGATION / PROHIBITION / PERMISSION / CONSTITUTIVE).

**Three jurisdictions, one engine:**

| Jurisdiction | Rules | Coverage | Role |
|-------------|-------|----------|------|
| CN (China) | 2,117 | 13 domains | Primary jurisdiction |
| HK (Hong Kong) | 104 | 7 namespaces | US↔CN bridge layer |
| US (Federal) | 73 | 7 titles | Cross-border disputes |

**Cross-border architecture:**

```
US Terms ──→ L0 Primitives ←── HK Terms ──→ L0 Primitives ←── CN Terms
              (Status/Act/Defect/Power/Agent/Asset)
```

Hong Kong serves as the "Rosetta Stone" between US common law and Chinese civil law — it has official Chinese legislation within a common law system.

---

## Architecture

```
juris-calculus/
├── compiler_core/                    # Reasoning kernel
│   ├── evaluator.py                  #   FixpointEvaluator + DDL modal gate
│   ├── types.py                      #   LegalRule / LegalFact / IRState / NormModality
│   ├── proof_tree.py                 #   ProofTree — jurisdiction-neutral output format
│   ├── language_renderer.py          #   ChineseRenderer / EnglishRenderer (post-processing)
│   ├── prc_collision_engine.py       #   Three-track collision (CBL + SPC + CN)
│   ├── adapter_base.py              #   JurisdictionAdapter abstract base
│   └── plugin_registry.py           #   Auto-discovery addon system
├── addons/
│   ├── cn/                           #   China addon (civil_law)
│   ├── hk/                           #   Hong Kong addon (common_law, bridge layer)
│   └── us/                           #   US Federal addon (common_law)
├── configs/
│   ├── zh_CN/rules.yaml              #   2,117 Chinese law Horn rules
│   ├── hk/rules.yaml                 #   104 Hong Kong Horn rules
│   ├── us/rules.yaml                 #   73 US Federal Horn rules
│   ├── prc_us_alignment/             #   60 CBL blocking + 25 SPC tendency rules
│   └── hk/blocking_rules.yaml        #   12 US→HK blocking rules
└── tests/                            #   160 tests, all passing
```

---

## How It Works

1. **Compile**: Load statutory law YAML → `LegalRule` objects
2. **Infer**: `FixpointEvaluator.evaluate()` — Horn clause fixed-point iteration with DDL modal gates
3. **Output**: `ProofTree` — pure ID + logic operators, no natural language
4. **Render**: `LanguageRenderer` translates ProofTree → Chinese / English legal text

The compiler never outputs natural language directly. Language is a post-processing layer, decoupled from reasoning.

---

## Quick Start

```python
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.types import IRState, LegalFact

# Load Chinese law rules
rules = load_rules_from_yaml("configs/zh_CN/rules.yaml")
ev = FixpointEvaluator(rules)

# Run inference
state = IRState(facts={
    "contract_formed": LegalFact(id="contract_formed", description="", extraction_confidence=0.95),
    "breach_alleged": LegalFact(id="breach_alleged", description="", extraction_confidence=0.9),
})
result = ev.evaluate(state)

# Output: ProofTree with jurisdiction-neutral claims
```

---

## Cross-Jurisdiction Bridge

```python
from compiler_core.plugin_registry import registry

# Auto-discovered addons
cn = registry.get("cn")  # China
hk = registry.get("hk")  # Hong Kong (bridge layer)
us = registry.get("us")  # US Federal

# Trilingual bridge
result = hk.trilingual_bridge("Consideration")
# → {'alignment': 'CROSS_L0', 'us_l0': 'Power', 'hk_term': 'cash consideration', ...}

# Three-track collision (CBL + SPC + CN)
tree = cn.run_collision(facts)
# → ProofTree with blocked_claims, spc_tendencies, cn_claims
```

---

## Coverage

### China (CN) — 2,117 rules, 13 domains
Contract, Tort, Corporate, Family, Criminal, Administrative, IP, Procedure, Execution, State Compensation, Juvenile, Maritime, Court Management

### Hong Kong (HK) — 104 rules, 7 namespaces
Contract (Cap 26), Corporate (Cap 622), Employment (Cap 57), Family (Cap 179), Property (Cap 219), Arbitration (Cap 609), IP (Cap 528)

### US Federal — 73 rules, 7 titles
Arbitration (Title 9), Jurisdiction/FSIA (Title 28), Sanctions/IEEPA (Title 50), Bankruptcy (Title 11), Commerce/Antitrust (Title 15), Copyrights (Title 17), Patents (Title 35)

---

## Installation

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

---

## License

MIT
