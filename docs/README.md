# Documentation

JC 是 CLI-first、可审计的 V4 法律推理内核。先读根目录 [README](../README.md)。

## 用户与集成方

- [CLI reference](guides/CLI.md)
- [中文说明](guides/README_CN.md)
- [Input and semantic boundary](contracts/INPUT_AND_SEMANTIC_BOUNDARY.md)
- [Rule packs](contracts/RULE_PACKS.md)
- [Audit bundle and replay](contracts/AUDIT_BUNDLE.md)
- [External repository protocol](contracts/EXTERNAL_PROTOCOL.md)

## 维护者

- [Contract authority](architecture/contract-authority-v4.md)
- [Module authority registry](architecture/module-authority.json)
- [Runtime path inventory](architecture/runtime-path-inventory.md)
- [V4 object and state matrix](contracts/V4_OBJECT_STATE_MATRIX.md)
- [Canonical identity, time, numeric and limits](contracts/V4_CANONICAL_TIME_NUMERIC_LIMITS.md)
- [V4 remediation status](../remediation/v4/STATUS.md)
- [V4 release procedure](operations/RELEASE_V4.md)

## Historical task definitions (not current authority)

`remediation/v4/tasks.json` 与 `task.schema.json` 只作为字节冻结的旧任务定义保留。当前 runner 只读取 `tasks.v3.json` 和 `task.v3.schema.json`；旧施工报告、旧回放指南和外部状态记录已从当前文档树删除。

本仓库不记录私有案件管理、客户数据、专有规则包、律师工作流或生产密钥。
