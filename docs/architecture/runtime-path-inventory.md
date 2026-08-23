# V4 current runtime path inventory

状态：W5-05 current。唯一人工分类来源为 `module-authority.json`；本页只给出公共运行链的可读投影。

## 公共入口

- `compiler_core/client.py` — 唯一 Python facade
- `compiler_core/cli.py` — `jc` CLI adapter
- `compiler_core/mcp.py` — 唯一四工具 MCP adapter
- `mcp_server.py` — installed stdio launcher

四个入口共同进入 `compiler_core/application.py`，不得直接调用候选、实验或离线 source tool。

## 正式运行链

`contracts.py` → `source_service.py` / `fact_admission.py` / `rule_packs.py` → `legal_ir.py` → `backend_router.py` / `backends/__init__.py` / `argumentation.py` → `independent_checker.py` → `certificates.py` → `audit.py` / `audit_bundle.py`。

支撑模块为 `canonical_serialization.py`、`trust.py`、`artifact_store.py`、`storage.py`、`resources.py` 和 `version.py`。`rendering.py` 只消费 `VerifiedAuditBundleV4`，不得重新求值。

## 发布物

- `schemas/jc-v4.schema.json` — 由 `contracts.py` 生成
- `mcp_manifest.json` — 由 V4 ToolSpec 生成
- `pyproject.toml` — 只声明 `jc` 公共脚本；wheel 精确清单由 W6-01 门禁管理

`addons/`、`pipeline/`、离线 source tools、候选资产、实验模块、测试和 remediation 工具均为非生产内容，不是 current formal authority。
