# juris-calculus Changelog

## v2.0.1 -- MetaInfer Engineering Paradigm (2026-06-13)

### New Engineering Infrastructure

- **Build Phases P1-P11**: Physical-dependency-ordered phase matrix (configs/juris_phase_matrix.yaml)
- **Experience Contracts**: Structured knowledge with ref_docs/ref_code/ref_tests + pseudocode + dynamic parameters (configs/juris_contracts.yaml)
- **Agent Collaboration Protocol**: Implementer / spec-compliance-reviewer / code-quality-reviewer / verification with strict sequencing (configs/agent_collaboration_protocol.yaml)
- **Knowledge Layered Architecture**: L0 common ? L1 legal family ? L2 jurisdiction ? L3 deploy (configs/knowledge_layers.yaml)
- **Phase Runner**: Gate execution with step35 spot-check anti-fake-PASS (tools/phase_runner.py)
- **Blueprint Contract Auditor**: Phase matrix + experience contract validation (tools/blueprint_contract_auditor.py)

### Knowledge Graph Audit System

- **Dual Auditor**: correctness (refs must exist) + completeness (contracts must have all fields)
- **Audit Loop**: merge findings, generate blueprint_repair_queue with root_cause_node
- Tools: kg_audit_common.py, kg_correctness_auditor.py, kg_completeness_auditor.py, kg_audit_loop.py

### Anti-Degradation Guards

- 7 guards enforced: scripts_immutable, phase_gate_strict, l0_import_source_guard, step35_spot_check, cross_phase_regression, e2e_evidence_chain, anti_hardcoded_reasoning
- Verification replay with stdout comparison (tools/verification_replay.py)
- Import source verifier prevents external module leaks (tools/import_source_verifier.py)

### Performance Infrastructure

- 5-metric baseline: rules_load, blueprint_load, evaluator_fixpoint, router_scan, cross_jurisdiction (tools/perf_baseline.py)
- Regression comparison with 1.2x WARN / 2x ERROR threshold (tools/perf_compare.py)
- Feed patterns back into knowledge graph (tools/perf_to_blueprint.py ? configs/perf_patterns.yaml)

### Harness Constraints (Section 7.4.3)

- Shape Checker: verify core data class interfaces (tools/shape_checker.py)
- Module Interface Checker: verify standard methods on key classes (tools/module_interface_checker.py)
- Self-Healing Loop: perf regression ? harness diagnosis ? auto-suggest (tools/self_healing_loop.py)

### Cross-Platform Adaptation

- OS/import/addon verification (tools/platform_check.py)
- Standardized jurisdiction addon spec template (configs/jurisdiction_spec_template.yaml)

### Final Gap Closure

- Blueprint completeness meter (tools/blueprint_completeness_meter.py)
- Test quality auditor (tools/test_quality_auditor.py)
- Recovery guard: max_iterations, hard_audit_threshold, fallback_config (tools/recovery_guard.py)

### MultiJustice Criminal Complexity

- L3: MoE route enhancement for single/multi-defendant x single/multi-charge scenarios
- L4: Adversarial audit for missing actor-charge binding
- L5: StepVerifier downgrades unbound criminal conclusions
- 4 configurable scenarios in configs/zh_CN/criminal_complexity.yaml

### MoE Router Decoupled

- RuleRouter now reads from configs/zh_CN/router_moe.yaml (14 domains, 9 cross rules)
- Minimal fallback config in code; full config in YAML for customization
- 75 tests passing, compileall clean

## v2.0.0 -- Addon Architecture (2026-06-12)

- Plugin registry with auto-discovery (scans addons/ directory)
- HK/US moved from core to addons/hk/ and addons/us/
- Blueprint split: core (14 CN MoE domains) + addon-local blueprints
- config_paths.py: all config paths parameterized via JURIS_CONFIG_DIR
- L0 concept degradation: unmapped concepts -> UNVERIFIED
- Federation by legal family: addons/federation/common_law.py
- US data: 53 titles, 266 courts, 419 federal terms, 3084 state vocabulary
- State term parser: ingest_state_terms.py + addons/us/parser.py
- NLNI cold start: cold_start_status() in neural_leaf.py

## v1.2.0 -- Tri-Rail (2026-06-04)

### Multi-Jurisdiction Collision Detection
- Tri-Rail Collider: 12 cross-border conflict classes
- PRC triple-rail engine: CBL gate (60 blocking rules) + SPC judicial tendency (23 rules) + CN statutory law (2,117 rules)
- PRC-US Semantic Alignment Framework
- Parallax Matrix: 65 PRC x 81 US divergence heatmap

### Jurisdiction Expansion
- HK: 93 Horn rules (Cap 26/32/622/571/4A)
- US: 50-state topological router + WI/NJ threat signatures
- UK: Distillation workbench output

## v1.0.3 (V6) -- 2026-06-03
- EvidenceClassifier, TaintStatus, NegativeSpec
- Discretionary concept auto-TAINTED
- MCP Server (initial)
- GitHub Actions CI/CD
