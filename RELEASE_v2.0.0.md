# juris-calculus v2.0.1 Release Notes

## What's New

v2.0.1 introduces a complete MetaInfer-inspired engineering paradigm, adding structured experience contracts, knowledge graph audit, anti-degradation guards, performance infrastructure, and Harness constraint mechanisms.

## New Features

### Engineering Paradigm
- **Build Phases P1-P11**: Physical-dependency-ordered phase matrix with per-phase commands and auto spot check
- **Experience Contracts**: Structured knowledge with ref_docs/ref_code/ref_tests chain + pseudocode + dynamic parameters
- **Agent Collaboration Protocol**: Four physically isolated roles (implementer / spec reviewer / code quality reviewer / verification) with strict sequencing
- **Knowledge Layered Architecture**: 4-layer legal knowledge architecture (L0-L3)
- **Dual KG Audit**: correctness + completeness auditors, merged blueprint_repair_queue

### Anti-Degradation (7 Guards)
| Guard | Mechanism |
|-------|-----------|
| Scripts immutable | Agent modifies code, never tests |
| Phase gate strict | Phase N fails ? cannot enter N+1 |
| L0 import source guard | Modules must resolve to local worktree |
| Step 3.5 spot check | Replay random PASS command, compare stdout |
| Cross-phase regression | P3+ rerun all prior phases |
| E2E evidence chain | eval trace + timing + audit report |
| Anti-hardcoded reasoning | trust_label from evaluator, not hardcoded |

### Harness Constraints
- Shape Checker: verifies 8 core data class interfaces
- Module Interface Checker: verifies 5 key module interfaces
- Self-Healing Loop: perf regression ? harness diagnosis ? auto-suggest

### Performance Infrastructure
- perf_baseline captures 5 metrics (rules load, blueprint load, evaluator, router, collision)
- perf_compare detects regression at 1.2x WARN / 2x ERROR
- perf_to_blueprint feeds patterns into knowledge graph

### Cross-Platform Adaptation
- platform_check.py verifies all jurisdictions + import + OS
- jurisdiction_spec_template.yaml for new addon creation

### MultiJustice Integration
- L3: MoE route enhancement for criminal complexity (S1-S4 scenarios)
- L4: Criminal audit for missing actor-charge binding
- L5: StepVerifier downgrades unbound conclusions

## Breaking Changes
- None. v2.0.1 is fully backward compatible with v2.0.0 addon architecture.

## Migration
pip install -r requirements.txt  (no new dependencies)
