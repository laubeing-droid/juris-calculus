# 正式运行路径清单

状态：current（协议 jc/5.0；合同对象沿用 V4 代次命名）。本页回答：一次请求从公共入口到审计包经过哪些模块，哪些路径不是正式链。唯一人工分类来源为 `module-authority.json`；本页只给出公共运行链的可读投影。

## 公共入口

- `compiler_core/client.py` — 唯一 Python facade
- `compiler_core/cli.py` — `jc` CLI adapter
- `compiler_core/mcp.py` — 唯一四工具 MCP adapter
- `mcp_server.py` — installed stdio launcher

四个入口共同进入 `compiler_core/application.py`，不得直接调用候选、实验或离线 source tool。`compiler_core/formal_bridge.py` 是 `jc-formal` 的正式桥接入口；`compiler_core/production_runtime.py` 负责装配受配置约束的本机生产宿主。

## 正式运行链

`contracts.py` → `source_service.py` / `fact_admission.py` / `rule_packs.py` → `legal_ir.py` → `backend_router.py` / `backends/__init__.py` / `argumentation.py` → `independent_checker.py` → `certificates.py` → `audit.py` / `audit_bundle.py`。

支撑模块为 `canonical_serialization.py`、`trust.py`、`artifact_store.py`、`storage.py`、`resources.py` 和 `version.py`。`rendering.py` 只消费 `VerifiedAuditBundleV4`，不得重新求值。

## 发布物

- `schemas/jc-v5.schema.json` — 由 `contracts.py` 生成
- `mcp_manifest.json` — 由 V4 ToolSpec 生成
- `pyproject.toml` — 声明 `jc` 与 `jc-formal` 两个公共脚本；wheel 精确清单由发布门禁管理

`addons/`、`pipeline/`、离线 source tools、候选资产、实验模块、测试和 remediation 工具均为非生产内容，不是 current formal authority。

## 相关文档

- [合同权威图](contract-authority-v4.md)
- [形式运行时一致性](../contracts/FORMAL_RUNTIME_CONFORMANCE.md)
- [V5 发布流程](../operations/RELEASE_V5.md)
- [文档索引](../INDEX.md)
