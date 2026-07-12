# v2 to v3 migration

v3 chooses correctness and auditability over compatibility. The old 33-tool/12-resource MCP surface is gone; there is no compatibility dispatcher.

| Previous intent | v3 interface |
|---|---|
| Evaluate structured facts | `jc evaluate` or `jc_evaluate` with a complete `CaseRequest` file. |
| Search rules/citations | `jc rules lookup` or `jc_lookup_rule`. |
| Inspect trace/check | `jc replay`, `result.json`, and `graph.json`. |
| Render/memo | `jc render`; fixed memo generation was removed. |
| Rule governance | `jc rules audit`. |
| Missing-evidence output | `missing_fact_review` in the canonical result. |
| Strategy/similar-case analysis | `jc analyze ...` from a completed run; always advisory. |
| LLM ingestion, neural promotion, document extraction, batch mutation | Removed from JC; candidate preparation belongs upstream. |

Python callers use the versioned contracts and the audited application path. Renderers receive completed run IDs only. Hidden dates, governing-law defaults, contract-validity defaults, and random public identifiers are not migrated.
