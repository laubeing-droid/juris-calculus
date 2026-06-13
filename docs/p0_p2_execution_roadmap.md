# P0-P2 Execution Roadmap

> v2.0.0 — 2026-06-14

## P0: Make the symbolic chain measurable and auditable ✅

- [x] Relevance-sensitive fixtures and runner: `tests/relevance_sensitivity/`, `tools/relevance_sensitivity_runner.py`
- [x] Claims carry stable execution trace ids: `compiler_core/proof_trace.py`
- [x] AAF attack edges from rule metadata: `compiler_core/argumentation.py`
- [x] Rule quality audit: `tools/rule_quality_auditor.py`
- [x] LLM batch acceptance: `tools/llm_batch_acceptor.py`, `tools/llm_batch_orchestrator.py`

## P1: Add minimal Typed Legal IR and constraint sidecar ✅

- [x] IR schema: `compiler_core/legal_ir_v3.py`
- [x] Type checker: `compiler_core/type_checker.py`
- [x] Source anchor: `compiler_core/source_anchor.py`
- [x] SMT sidecar: `compiler_core/smt_sidecar.py`
- [x] Typed IR migration: `tools/rule_to_ir_migrator.py` (conservative, sidecar-only)
- [x] Semantic compiler contract: `compiler_core/semantic_compiler_contract.py`

## P2: Prepare neural assistance without letting it decide ✅

- [x] Shadow state: `compiler_core/shadow_state.py`
- [x] Divergence report: `tools/shadow_divergence_report.py`
- [x] Neural contracts: `neural/contracts/feature_schema.yaml`, `output_schema.yaml`, `model_card_schema.yaml`, `promotion_policy.yaml`
- [x] Neural guardrails: `compiler_core/neural_leaf.py`, `neural_yaml_sync.py`, `step_verifier.py` (6/6 tests)
- [x] Model registry: `neural/registry/model_registry.yaml` (all models SHADOW_ONLY)

## DDL Modal Engine ✅

- [x] Norm modality annotations: 2,117/2,117 rules in `configs/zh_CN/rules.yaml`
- [x] DDL preclassifier: `compiler_core/ddl_preclassifier.py` (5-layer: keyword + structure + concept + namespace + LLM confirmed)
- [x] Confirmed modalities lookup: `neural/registry/ddl_confirmed_modalities.json` (825 rules)
- [x] Evaluator modal gate: `_apply_rule()` reads `norm_modality`
  - OBLIGATION missing → Negative Spec gap report
  - PROHIBITION hit → block conclusion chain
- [x] IRState: `negative_specs` + `blocked_claims` fields

## L1-L2 Guardrails ✅

- [x] L1 Evidence chain validator: `compiler_core/evidence_chain_validator.py` (pre-inference)
- [x] L2 De Jure auditor: `compiler_core/de_jure_auditor.py` (post-inference)
- [x] L2 Cross-jurisdiction: `cross_jurisdiction_compare.py`, `multi_solver_router.py`
- [x] L2 Invariance metrics: `invariance_metrics.py`, `validity_state_machine.py`
- [x] L2 Defeasible priority: `defeasible_priority.py`, `proleg_translator.py`
- [x] L2 Entity anonymizer: `entity_anonymizer.py`
- [x] L2 KG recall: `kg_recall.py`
- [x] All L1-L2 wired into `pipeline/pipeline.py`

## Non-goals (unchanged)

- No end-to-end neural adjudication
- No replacement of FixpointEvaluator
- No mandatory Z3 dependency
- No full migration of all YAML rules to IR v3
- No automatic promotion of neural output into official IRState
