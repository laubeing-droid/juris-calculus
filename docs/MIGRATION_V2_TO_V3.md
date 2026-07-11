# v2 to v3 migration

v3 prioritizes correctness and auditability over runtime compatibility. There is no compatibility dispatcher for the former 33 MCP tools or 12 whole-corpus resources.

## Tool mapping

| v2 tool group | v3 path |
|---|---|
| `stratified_evaluate`, `evaluate_facts`, `evaluate` | `jc evaluate` or `jc_evaluate` with a complete `CaseRequest` file. |
| `search_rules`, `get_citation` | `jc rules lookup` or `jc_lookup_rule`. |
| `analyze_strategy` | `jc analyze strategy` or `jc_analyze_strategy` from a verified run. |
| `case_deviation` | `jc analyze similar-cases` or `jc_analyze_similar_cases`. |
| `trace`, `check` | `jc replay`; inspect the run's `graph.json` and verified result. |
| `render`, `generate_memo` | Explicit `jc render`; fixed action memo generation was removed. |
| `governance` | `jc rules audit`. |
| `minimum_evidence` | `missing_fact_review` in the canonical evaluation result. |
| `trirail_collide`, `check_threat`, `batch`, `diff`, `stress_fixtures` | Explicit CLI/CI harnesses only; not public MCP tools. |
| `route_state`, `rule_router`, `route` | Internal pack/rule resolution or bounded lookup. |
| `calculate_damages`, `damages_baseline`, `impact` | Advisory/private downstream analysis; no standalone formal MCP result. |
| `extract_elements`, `ingest_candidate`, `evaluate_facts_llm`, `align_concepts_llm`, `generate_nlni_llm` | Offline candidate preparation governed by promotion gates. |
| `get_operator_schemas`, `generate_task_schema`, `private_layer_contract` | Static schemas and documentation. |
| `neural_leaf_status` | CI-only neural contract audit. |

All former `legal://...` resources were removed. Use pack list/verify/lookup for bounded metadata and rules; architecture and schemas are static package documents.

Python callers should construct `CaseRequest`, select a verified `RulePackRegistry`, and call the audit application entrypoint. Renderers accept only completed run IDs. Old hidden dates/governing law/contract-validity defaults and random public identifiers are not migrated.
