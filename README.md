# juris-calculus v2.0.1

Symbolic legal reasoning engine for Chinese law, with addon-based cross-jurisdiction support, MetaInfer-style engineering paradigm.

## Architecture

```
                                  ????????????????????????????????
                                  ?  Phase Matrix (P1-P11)      ?
                                  ?  blueprint_contract_auditor  ?
                                  ?  step35_spot_check           ?
                                  ?  anti_degradation guard      ?
                                  ????????????????????????????????
                                  ????????????????????????????????
                                  ?  KG Audit Loop               ?
                                  ?  correctness / completeness  ?
                                  ?  self_healing_loop            ?
                                  ????????????????????????????????
Layer 6: Neural leaf nodes (kill switch + cold start)
Layer 5: Dung AAF argumentation + StepVerifier (EVM + binding)
Layer 4: Adversarial pipeline (Reasoner / Auditor / Verifier)
Layer 3: MoE rule router (YAML-backed 14 domains) + criminal complexity
Layer 2: Horn clause fixpoint evaluator (2,117 CN rules)
Layer 1: Trust labels (epistemic status / data origin / red lines)
Layer 0: juris_blueprint.json (14 CN MoE domains, 5.7MB knowledge graph)

  addons/
    hk/               Hong Kong SAR (Cap 26, 93+ Horn rules)
    us/               United States (53 titles, 266 courts, 419 federal terms)
    federation/       Common-law pair-wise comparison engine
```

## Engineering Paradigm (MetaInfer-inspired)

| Component | Description |
|-----------|-------------|
| `configs/juris_phase_matrix.yaml` | L0-L6 layers + P1-P11 build phases with physical dependency chain |
| `configs/juris_contracts.yaml` | Structured experience contracts: ref_docs/ref_code/ref_tests + pseudocode + dynamic parameters |
| `configs/agent_collaboration_protocol.yaml` | Implementer / spec-compliance-reviewer / code-quality-reviewer / verification with strict sequencing |
| `configs/knowledge_layers.yaml` | 4-layer legal knowledge architecture (L0 common ? L1 family ? L2 jurisdiction ? L3 deploy) |
| `tools/phase_runner.py` | Phase gate execution with spot check replay anti-fake-PASS |
| `tools/kg_audit_loop.py` | Dual independent correctness + completeness audit with merged findings |
| `tools/self_healing_loop.py` | Performance regression detection ? harness diagnosis ? auto-suggest |
| `tools/shape_checker.py` | Harness: verify core data class interfaces (LegalFact, LegalClaim, IRState, etc.) |
| `tools/module_interface_checker.py` | Harness: verify standard methods on key classes |
| `tools/perf_baseline.py` | 5-metric performance baseline (rules load, blueprint load, evaluator, router, collision) |
| `tools/perf_compare.py` | Before/after comparison with regression threshold (1.2x WARN, 2x ERROR) |
| `tools/perf_to_blueprint.py` | Feed performance patterns back into knowledge graph |
| `tools/import_source_verifier.py` | L0 import guard: verify modules resolve to local worktree |
| `tools/verification_replay.py` | Step 3.5: replay one PASS command, compare stdout |

## Knowledge Graph Audit (Dual Reviewer)

```text
kg_correctness_auditor:  "Is what we said true?"  ? every ref_docs/ref_code/ref_tests must exist
kg_completeness_auditor: "Did we say enough?"      ? every contract must have inputs, outputs, failure modes, pseudocode, dynamic params
kg_audit_loop:           merges both, generates blueprint_repair_queue
```

## Agent Collaboration Protocol

```text
Sequence:
1. Implementer (spawned agent, writes code + tests + self-review)
   ? status: DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED
2. Spec Compliance Reviewer (independent PID)
   ? reads actual diff, does NOT trust implementer report
3. Code Quality Reviewer (independent PID, only if spec PASS)
4. Verification (local subprocess, runs phase commands + replay)
```

## Build Phases (P1-P11)

Phases ordered by physical dependency, verified by `phase_runner --all-build`:

```
P1_TYPES_TRUST           ? P2_CONFIG_RULE_PARSE ? P3_HORN_EVALUATOR ? P4_MOE_ROUTER
                                                                   ? P5_GATES_CONSTRAINTS
P6_STEP_VERIFIER_AAF    ? P7_ADVERSARIAL_REVIEW ? P8_MCP_OPERATION_INTERFACE
P9_ADDON_FEDERATION       ? P10_E2E_KG_AUDIT     ? P11_PERF_PRUNE_COLDSTART
```

Each phase has immutable test scripts (anti-degradation), cross-phase regression (P3+), and auto spot check.

## Anti-Degradation Mechanisms

| Guard | Mechanism |
|-------|-----------|
| Scripts immutable | Agent modifies code, never tests |
| Phase gate strict | Phase N fails ? cannot enter N+1 |
| L0 import source guard | Verify modules resolve to local worktree, not external leak |
| Step 3.5 spot check | Replay 1 random PASS command, compare stdout |
| Cross-phase regression | P3+ rerun all prior phases |
| E2E evidence chain | eval trace + rules timing + contract audit report |
| Anti-hardcoded reasoning | trust_label must come from evaluator, not hardcoded |

## MCP Tools (v2.0.0 manifest)

| Tool | Description |
|------|-------------|
| `trirail_collide` | HK x US x PRC collision detection |
| `check_threat` | FastPathInterceptor gateway |
| `generate_memo` | Partner-ready cross-border memo |
| `route_state` | Jurisdiction router |
| `get_citation` | Legal citation lookup |
| `stratified_evaluate` | 4-stage Horn + AAF pipeline |

## Quick Start

```bash
git clone https://github.com/laubeing-droid/juris-calculus.git
cd juris-calculus
pip install -r requirements.txt
pytest tests/                    # 75+ tests
python tools/phase_runner.py --all-build   # P1-P11 verification
python mcp_server.py             # MCP service
```

## Personal YAML (Multi-Lawyer Shared Algorithm)

Set `JURIS_CONFIG_DIR` to point at your personal YAML library. Same algorithm code, each lawyer maintains their own distilled rules.

```bash
set JURIS_CONFIG_DIR=C:/my-rules  # Windows
export JURIS_CONFIG_DIR=~/my-rules  # Linux/Mac
```

## License

MIT
