# juris-calculus v2.0.1

Symbolic legal reasoning engine for Chinese law, with addon-based cross-jurisdiction support.

## Architecture

`
Layer 6: Neural leaf nodes (kill switch + cold start)
Layer 5: Dung AAF + StepVerifier (symbolic EVM + binding verification)
Layer 4: Adversarial pipeline (Reasoner / Auditor / Verifier)
Layer 3: MoE rule router (YAML 14 domains) + criminal complexity (S1-S4)
Layer 2: Horn fixpoint evaluator (2,117 CN rules)
Layer 1: Trust labels (EpistemicStatus / DataOrigin / red lines)
Layer 0: juris_blueprint.json (14 CN MoE domains, 5.7MB)

addons/          hk/ (Cap 26, 93+)    us/ (53 titles, 266 courts)    federation/
`

## Engineering Paradigm

| Component | Purpose |
|-----------|---------|
| juris_phase_matrix.yaml | L0-L6 + P1-P11 build phases with physical dependency chain |
| juris_contracts.yaml | Structured experience contracts (ref_docs/code/tests + pseudocode) |
| agent_collaboration_protocol.yaml | Implementer / spec-reviewer / quality-reviewer / verification |
| knowledge_layers.yaml | 4-layer legal knowledge architecture (L0 common → L3 deploy) |
| phase_runner.py | Phase gate execution + auto step 3.5 spot check |
| kg_audit_loop.py | Dual correctness + completeness KG audit |

## Build Phases (P1-P11)

`
P1 → P2 → P3 → P4 → P6 → P7 → P8 → P9 → P10 → P11
            ↘ P5 ↗
`

Run: python tools/phase_runner.py --all-build

## Anti-Degradation (7 Guards)

| Guard | Mechanism |
|-------|-----------|
| Scripts immutable | Agent fixes code, never tests |
| Phase gate strict | Phase FAIL blocks next phase |
| L0 import guard | Modules resolve to local worktree |
| Step 3.5 spot check | Replay one PASS command, compare stdout |
| Cross-phase regression | P3+ rerun all prior phases |
| E2E evidence chain | eval trace + timing + audit report |
| Anti-hardcoded reasoning | trust_label from evaluator execution |

## MCP Tools (18 total)

### Symbolic (15)
| Tool | Description |
|------|-------------|
| trirail_collide | HK x US x PRC collision |
| route_state | US state jurisdiction router |
| get_citation | Legal citation lookup |
| stratified_evaluate | 4-stage Horn + AAF |
| search_rules | Keyword search 2,117 rules |
| evaluate_facts | Facts → claims + confidence + trust |
| calculate_damages | Itemized damages (LPR/deposit/penalty/limitation) |
| analyze_strategy | SWOT from adversarial pipeline |
| extract_elements | Horn premise atoms from facts |

### LLM-Enhanced (3, privacy-gated)
| Tool | Description |
|------|-------------|
| evaluate_facts_llm | DeepSeek-enhanced fact extraction (TAINTED output) |
| align_concepts_llm | Cross-jurisdiction concept alignment |
| generate_nlni_llm | NLNI cold-start training data generation |

All LLM tools: PII stripped before call, results marked TAINTED, zero API key = zero network.

## Privacy Guarantee

Core engine is purely symbolic. LLM integration is optional, privacy-gated, and all LLM results carry TAINTED trust label.
No raw case data leaves the system without sanitization.

## License

MIT