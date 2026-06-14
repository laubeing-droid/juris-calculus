# Execution Roadmap

> Updated: 2026-06-14

## P0: Symbolic chain measurable and auditable ✅

- [x] Relevance-sensitive fixtures: `tests/relevance_sensitivity/`
- [x] Proof trace: `compiler_core/proof_trace.py`
- [x] AAF attack edges: `compiler_core/argumentation.py`
- [x] Rule quality audit: `tools/rule_quality_auditor.py`
- [x] LLM batch acceptance: `tools/llm_batch_acceptor.py`

## P1: Typed Legal IR + constraint sidecar ✅

- [x] IR schema: `compiler_core/legal_ir_v3.py`
- [x] Type checker: `compiler_core/type_checker.py`
- [x] SMT sidecar: `compiler_core/smt_sidecar.py`
- [x] Semantic compiler contract: `compiler_core/semantic_compiler_contract.py`

## P2: Cross-jurisdiction architecture ✅

- [x] ProofTree output: `compiler_core/proof_tree.py`
- [x] Language renderer: `compiler_core/language_renderer.py`
- [x] Three-track collision: `compiler_core/prc_collision_engine.py`
- [x] JurisdictionAdapter base: `compiler_core/adapter_base.py`
- [x] Plugin registry auto-discovery: `compiler_core/plugin_registry.py`

## P3: Three jurisdictions complete ✅

- [x] CN addon: 2,117 rules, 13 domains, DDL modal classification
- [x] HK addon: 104 rules (contract/corporate/employment/family/property/arbitration/ip), 1,729 term mappings
- [x] US addon: 73 rules (arbitration/jurisdiction/sanctions/bankruptcy/commerce/copyrights/patents)
- [x] Blocking rules: 60 CBL + 12 HK + 18 US→HK = 90 total
- [x] Term mappings: 1,832 L0 entries across 3 jurisdictions

## P4: Next steps (not started)

- [ ] UCC Article 2 + 9 (state law, not in US Code)
- [ ] Restatement (Second) of Contracts compilation
- [ ] FRCivP Rule 4/26/44.1 integration
- [ ] US term mapping expansion (currently 39, target 300+)
- [ ] HK employment/family/property blocking rules
- [ ] 三轨对撞端到端测试扩展
