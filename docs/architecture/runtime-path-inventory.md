# Runtime path inventory

- root: `compiler_core`
  - path: `compiler_core/client.py` (唯一公开 Python facade；重建外部请求并使用随包配置)
  - path: `compiler_core/application.py` (main evaluation chain, run identity + gate checks)
  - path: `compiler_core/contracts.py` (semantic/result/fact contracts)
  - path: `compiler_core/rule_packs.py` (pack verification + descriptor)
  - path: `compiler_core/constraint_validator.py` (ontology/override loading)
  - path: `compiler_core/evaluator.py` (fixpoint and convergence outcome)
  - path: `compiler_core/stratified_evaluator.py` (shadow/compare path)
  - path: `compiler_core/argumentation.py` (argument node与attack关系构图)
  - path: `compiler_core/fact_trust_envelope.py` (fact 入场门禁与降级)
  - path: `compiler_core/types.py` (事实/结果类型系统)
  - path: `compiler_core/audit_bundle.py` (replay, cache policy, safe request)

- root: `configs/packs`
  - path: `configs/packs/cn-official` (official pack registry entry remains inactive/blocked)
  - path: `configs/packs` (pack manifests and runtime checks)
  - path: `configs/README.md`（配置根与配置入口说明）

- root: `tests`
  - path: `tests/fixtures` (baseline fixtures)
  - path: `tests/fixtures/p0_regressions` (P0 回归清单与待执行资产)
  - path: `tests/unit` (unit regression coverage)
  - path: `tests/e2e` (interface parity targets)

- root: `schemas`
  - path: `schemas/jc-v3.schema.json` (contract source of truth)

- root: `docs/contracts`
  - path: `docs/contracts/*.md` (single-source contract references)

- root: `addons`
  - path: `addons/workbuddy_mcp.py` (MCP protocol facade, advisory/read-write parity gate)

- root: `pipeline`
  - path: `pipeline/experimental/llm_client.py` (proposal-only；显式 `real` / `regex` provider，无 mock fallback)
  - path: `pipeline/llm_client.py` (兼容导入层，不进入 formal kernel)

公开包根仅导出 `JCClient`，不导出 `evaluate_case`、`evaluate_to_audit_bundle`、`evaluate_registered_case`。内部求值服务仍供 CLI、MCP、replay 使用。
