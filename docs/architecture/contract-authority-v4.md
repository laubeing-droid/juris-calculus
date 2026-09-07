# 合同权威（当前公共协议 jc/5.0）

状态：current。本页文件名中的 v4 指公共合同对象的代次命名（`CaseInputBundleV4` 等）；公共协议自 2026-09 起为 jc/5.0，V5 对象组叠加在同一注册表上。本页回答：谁是合同、Schema 与协议版本的唯一权威，改动应走哪条路。历史合同和迁移说明只存在于 Git 历史，不构成当前接口。

## 唯一权威

- Python wire contract：`compiler_core/contracts.py`
- 生成的 JSON Schema：`schemas/jc-v5.schema.json`
- 生成器：`tools/generate_v4_schema.py`
- 协议版本：`compiler_core/version.py`

`contracts.py` 是字段、类型、状态矩阵和 closed-object 约束的唯一手写来源；Schema 是可复算发布物，不得手改。两者由 contract/schema round-trip 与 generated-publication gate 绑定。

## 公共边界

- Python：`compiler_core/client.py::JCClient`
- CLI：`compiler_core/cli.py::main`
- MCP：`compiler_core/mcp.py` 的四个工具（`jc_capabilities`、`jc_evaluate`、`jc_verify_run`、`jc_read_artifact`）
- 编排：`compiler_core/application.py`

所有公共入口只接受当前合同（V4 代次对象加 V5 扩展字段）。旧版本 payload、`jc/4.0` 与 4.x 引擎版本、未知字段、绝对主机路径和浮点金额在边界显式拒绝；不存在兼容转换入口（旧输入走离线迁移工具 `tools/migrate_v4_bundle.py`）。

## 权威分工

`docs/architecture/module-authority.json` 是唯一 current 模块分类注册表。正式合同、事实准入、规则包、后端、独立检查、证书、审计事件和审计包分别只有一个未版本化模块；候选、实验、离线 source tool 和标为 `REMOVE` 的文件不具有正式权威，也不进入生产 wheel。

## 相关文档

- [运行路径清单](runtime-path-inventory.md)
- [V5 对象与状态矩阵（当前）](../contracts/V5_OBJECT_STATE_MATRIX.md)
- [输入与语义边界](../contracts/INPUT_AND_SEMANTIC_BOUNDARY.md)
- [文档索引](../INDEX.md)
