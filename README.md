# juris-calculus v2.0.1

Symbolic legal reasoning engine for Chinese law, with addon-based cross-jurisdiction support.

## Architecture

`
Layer 6: Neural leaf nodes (kill switch + cold start)
Layer 5: Dung AAF argumentation + StepVerifier (EVM + binding verification)
Layer 4: Adversarial pipeline (Reasoner / Auditor / Verifier)
Layer 3: MoE rule router (YAML-backed 14 domains) + criminal complexity
Layer 2: Horn clause fixpoint evaluator (2,117 CN rules)
Layer 1: Trust labels (epistemic status / data origin / red lines)
Layer 0: juris_blueprint.json (14 CN MoE domains, 5.7MB knowledge graph)

addons/
  hk/               Hong Kong SAR (Cap 26, 93+ Horn rules)
  us/               United States (53 titles, 266 courts, 419 federal terms)
  federation/       Common-law pair-wise comparison engine
`

## Engineering Paradigm

| Component | Description |
|-----------|-------------|
| configs/juris_phase_matrix.yaml | L0-L6 layers + P1-P11 build phases with physical dependency chain |
| configs/juris_contracts.yaml | Structured experience contracts: ref chain + pseudocode + dynamic params |
| configs/agent_collaboration_protocol.yaml | 4-role physically isolated collaboration protocol |
| configs/knowledge_layers.yaml | 4-layer knowledge architecture (L0 common to L3 deploy) |
| tools/phase_runner.py | Phase gate execution with auto step 3.5 spot check |
| tools/kg_audit_loop.py | Dual correctness/completeness knowledge graph audit |

## Build Phases (P1-P11)

`
P1_TYPES_TRUST          -> P2_CONFIG_RULE_PARSE -> P3_HORN_EVALUATOR -> P4_MOE_ROUTER
                                                                     -> P5_GATES_CONSTRAINTS
P6_STEP_VERIFIER_AAF    -> P7_ADVERSARIAL_REVIEW -> P8_MCP_INTERFACE
P9_ADDON_FEDERATION      -> P10_E2E_KG_AUDIT     -> P11_PERF_PRUNE_COLDSTART
`

## Anti-Degradation Guards

| Guard | Mechanism |
|-------|-----------|
| Scripts immutable | Agent fixes code, never tests |
| Phase gate strict | Phase FAIL blocks next phase |
| L0 import source guard | Modules must resolve to local worktree |
| Step 3.5 spot check | Replay one PASS command, compare stdout |
| Cross-phase regression | P3+ rerun all prior phases |
| E2E evidence chain | eval trace + timing + audit report |
| Anti-hardcoded reasoning | trust_label from evaluator execution |

## MCP Tools (15 total)

| Tool | Description |
|------|-------------|
| trirail_collide | HK x US x PRC collision detection |
| route_state | US state jurisdiction router |
| get_citation | Legal citation lookup |
| stratified_evaluate | 4-stage Horn + AAF pipeline |
| search_rules | Search 2,117 CN rules by keyword |
| evaluate_facts | Facts -> claims + confidence + trust |
| calculate_damages | Itemized damages with LPR/deposit checks |
| analyze_strategy | SWOT strategy from adversarial pipeline |
| extract_elements | Extract Horn premise atoms from facts |

## Quick Start

`
git clone https://github.com/laubeing-droid/juris-calculus.git
cd juris-calculus
pip install -r requirements.txt
pytest tests/                    # 75 tests
python tools/phase_runner.py --all-build   # P1-P11 verification
python mcp_server.py             # MCP service
`

## Personal YAML (Multi-Lawyer Shared Algorithm)

Set JURIS_CONFIG_DIR to point to personal YAML library. Same algorithm, each lawyer distills their own rules.

## License

MIT