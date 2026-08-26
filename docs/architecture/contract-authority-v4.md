# V4 current contract authority

状态：W5-05 current。历史合同和迁移说明只存在于 Git 历史与审计证据，不构成当前接口。

## 唯一权威

- Python wire contract：`compiler_core/contracts.py`
- 生成的 JSON Schema：`schemas/jc-v4.schema.json`
- 生成器：`tools/generate_v4_schema.py`
- 协议版本：`compiler_core/version.py`

`contracts.py` 是字段、类型、状态矩阵和 closed-object 约束的唯一手写来源；Schema 是可复算发布物，不得手改。两者由 contract/schema round-trip 与 generated-publication gate 绑定。

## 公共边界

- Python：`compiler_core/client.py::JCClient`
- CLI：`compiler_core/cli.py::main`
- MCP：`compiler_core/mcp.py` 的四个 V4 工具
- 编排：`compiler_core/application.py`

所有公共入口只接受 V4 合同。旧版本 payload、未知字段、绝对主机路径和浮点金额在边界显式拒绝；不存在兼容转换入口。

## 权威分工

`docs/architecture/module-authority.json` 是唯一 current 模块分类注册表。正式合同、事实准入、规则包、后端、独立检查、证书、审计事件和审计包分别只有一个未版本化模块；候选、实验、离线 source tool 和标为 `REMOVE` 的文件不具有正式权威，也不进入生产 wheel。

## 相关文档

- [运行路径清单](runtime-path-inventory.md)
- [对象与状态矩阵](../contracts/V4_OBJECT_STATE_MATRIX.md)
- [输入与语义边界](../contracts/INPUT_AND_SEMANTIC_BOUNDARY.md)
- [文档索引](../README.md)
