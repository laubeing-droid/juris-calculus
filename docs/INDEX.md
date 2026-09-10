# 文档索引

本页按读者意图组织 juris-calculus 的全部当前文档，每条附一句"读了能得到什么"。项目定位先读根目录 [README](../README.md)。当前版本 5.0.1（公共协议 jc/5.0），版本权威是 `compiler_core/version.py`。

## 入门：先跑起来、看懂项目

- [中文说明](guides/README_CN.md) — 安装、配置宿主材料、完成第一次评估，并理解这套内核的边界。
- [CLI 参考](guides/CLI.md) — 六个 `jc` 子命令、退出码、运行宿主环境变量和 `jc-formal` 入口的精确含义。
- [输入与语义边界](contracts/INPUT_AND_SEMANTIC_BOUNDARY.md) — 什么能进入正式推理、什么永远不能，一句话说清信任模型。
- [渲染与中立输出](contracts/rendering-and-profiles.md) — 如何把机器结果变成给人看的三种格式，以及渲染为何不能改变结论。

## 深入：理解与修改系统

- [运行路径清单](architecture/runtime-path-inventory.md) — 从四个公共入口到审计包的正式运行链，以及哪些模块不在正式链上。
- [合同权威](architecture/contract-authority-v4.md) — 合同、Schema 与协议版本的唯一权威是谁，改动该走哪条路。
- [V5 对象与状态矩阵（当前）](contracts/V5_OBJECT_STATE_MATRIX.md) — 当前合同注册表、六轴终态分类器和强制不变量。
- [V4 对象与状态矩阵（历史）](contracts/V4_OBJECT_STATE_MATRIX.md) — V4 时代 73 类型注册表的冻结记录，理解演进时对照用。
- [规范身份、时间、数值与限制](contracts/V4_CANONICAL_TIME_NUMERIC_LIMITS.md) — 规范化字节、时间戳、金额与准入上限的精确规则。
- [运行时声明与证据边界](contracts/FORMAL_RUNTIME_CONFORMANCE.md) — 每类证据能支撑什么声明、不能支撑什么，防止过度声称。
- [jc-business-root/1 能力契约](contracts/BUSINESS_ROOT.md) — 条件本金业务的公共入口、verify-only 双文件核验与保证分解（已安装实现）。
- [规则包与规则准入](contracts/RULE_PACKS.md) — 规则如何从语料变成推理可用，签名与晋级的边界在哪。
- [审计包与重放](contracts/AUDIT_BUNDLE.md) — 一次评估留下哪些证据文件，重放如何逐字节校验。
- [治理、训练与分析边界](operations/governance-training-analysis.md) — 哪些资产只是离线工具，不会成为已安装的 CLI 能力。

## 参考：集成与机器权威

- [JC ↔ Legal Harness 集成合同](contracts/HARNESS_INTEGRATION.md) — Harness 如何发请求、追加材料走增量、读结果与优先关系状态；三份可运行样本的位置。
- [外仓协议](contracts/EXTERNAL_PROTOCOL.md) — Deli、Legal Harness、LMM 三类外仓各自允许和禁止的接入方式。
- [Python 合同](../compiler_core/contracts.py) / [JSON Schema](../schemas/jc-v5.schema.json) / [MCP 工具清单](../mcp_manifest.json) — 字段与工具的机器权威，文档只解释不复制。
- [证明绑定](../proofs/lmm-binding.json) 与 [运行时义务映射](../proofs/runtime-obligation-map.json) — 运行时模块与上游 Lean 声明的对应登记。
- [模块权威注册表](architecture/module-authority.json) — 每个模块的正式/非正式分类与依赖方向。

## 维护与历史

- [V5 发布流程](operations/RELEASE_V5.md) — 构建、验收、CI 闭环、生产激活条件与撤回步骤。
- [V4 发布流程（历史）](operations/RELEASE_V4.md) — V4 时代同一机制的记录，含 `TEST_ONLY_NOT_PROMOTABLE` 与生产晋级条件的原始表述。
- [交接检查点](../HANDOFF.md) — 当前做到哪、还欠什么、下一执行面。
- [变更记录](../CHANGELOG.md) — 按版本发生了什么。
- [V5 升级最终验收报告（归档）](archive/FINAL_UPGRADE_REPORT.md) — 2026-09 一次性升级的完整工程证据，含独立核查修复。
- [V4 整改状态（历史）](../remediation/v4/STATUS.md) — V4 整改收尾时的验收范围记录。
- [安全策略](../SECURITY.md) — 漏洞私下报告渠道与支持版本线。
- 发布门禁：`.github/workflows/ci.yml` 验证发布构建产物；`.github/workflows/auto-release.yml` 只在额外授权和生产签名条件满足后晋级同一产物；`tools/build_provenance.py` 用测试密钥生成的证明不得冒充生产发布证明。

## Historical task definitions (not current authority)

`remediation/v4/tasks.json` 与 `task.schema.json` 只作为字节冻结的旧任务定义保留。当前 runner 只读取 `tasks.v3.json` 和 `task.v3.schema.json`；旧施工报告、旧回放指南和外部状态记录已从当前文档树删除。

本仓库不记录私有案件管理、客户数据、专有规则包、律师工作流或生产密钥；这些内容属于仓库外的部署环境。
