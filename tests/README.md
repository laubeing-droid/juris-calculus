# juris-calculus US Common Law Benchmark Suite

## Quick Start

```bash
# 1. Fill in US complaint facts
#    Edit tests/us_complaints/US-001_breach_contract.json
#    Replace "TODO" fields with actual extracted facts

# 2. Run benchmark
cd juris-calculus
python tests/run_benchmark.py

# 3. Review results
cat tests/results/Benchmark_10Cases_US.md
```

## Workflow

```
US Complaint (.pdf/.docx)
        │
        ▼
Manual IRAC extraction (human lawyer reads complaint)
        │
        ▼
US-XXX_*.json  ← Fill in premise_atoms
        │
        ▼
FixpointEvaluator (8 US contract rules)
        │
        ▼
Benchmark_10Cases_US.md  ← Convergence, missing concepts, α fit
```

## What to fill in for each case

| Field | Example | Status |
|-------|---------|--------|
| ContractFormed | "已成立" | If offer + acceptance + consideration evident |
| GoodsDelivered | "已交付" | If delivery completed |
| PaymentDue | "已到期" | If payment deadline passed |
| PaymentMade | "未支付" | If payment not made (breach trigger) |
| BreachAlleged | "违约" | Specific breach complained of |
| DamagesClaimed | "已主张" | If damages quantified |
| ActOfGod | — | Only if force majeure defense raised |
| ImpossibilityClaimed | — | Only if impossibility defense raised |

## Adding new cases

1. Copy `US-001_breach_contract.json` as `US-002_*.json`
2. Update `case_id`, `cause_of_action`, `governing_law`
3. Fill in `facts` with actual extracted facts
4. Run benchmark

## Rules being tested

8 US contract rules covering: formation → performance → breach → damages → remedies.
Force majeure and impossibility as exception chains.

## When to modify production code

**Do NOT modify evaluator.py** unless the benchmark reveals:
- A fundamental logic conflict (e.g., US adversarial structure cannot map to premise_atoms)
- A concept that requires new rule atoms in compiler_core

Changes should be driven by benchmark data, not assumptions.
