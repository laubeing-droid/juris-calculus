# Changelog

## 4.0.0 — Current V4

- CLI、Python、MCP、schema、application、certificate、verify 与 replay 统一到 V4。
- 删除 23 个零消费者旧模块、旧 pipeline 导入 shim、旧 runner 验证器和旧施工状态文档。
- remediation runner 改为小型通用 DAG 执行器，当前使用 3.0 任务定义；2.0 任务定义保持原字节不变。
- 正式 wheel 新增独立 `rule_admission.py`，完整支持 official YAML 规则准入正反验证。
- 生产链测试改为在 pytest 临时目录内生成材料；Git/子进程边界统一使用严格 UTF-8。
- 当前 authority 检查使用 Git 跟踪清单、本地 AST、入口点和 wheel 清单，不依赖外部 CodeGraph。
- CN/HK/US/federation addons 保留用于规则对齐，继续排除在正式 wheel 之外。
- CI 改用当前 V4 runner、authority、cleanup、文档链接、完整测试和隔离 wheel 门禁。

本版本条目只描述当前仓库可复现内容，不声明外部部署、远程发布或历史任务完成状态。
