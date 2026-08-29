# 外仓协议

本页只描述当前 V4 公共消费边界。

## 入口

1. CLI：文件或 stdin 输入，stdout 只输出协议数据，stderr 输出日志，exit code 稳定。
2. `JCClient`：使用同一 application service 和 canonical contract。
3. MCP：四工具、零资源；stdio subprocess 是 transport authority。

| 外仓 | 允许入口 | 禁止 |
| --- | --- | --- |
| Deli | `JCClient`、版本化 CLI JSON 或 MCP 提交 candidate bundle | `sys.path` 导入内部模块；自签 attestation、certificate 或 `DecisionStatus` |
| Legal Harness | 公共接口提交 attestation/approval refs 与运行请求 | 组织 JC 内部工作流；绕过 fact admission |
| LMM | versioned semantic manifest、proof receipt、refinement fixtures | 直接改写 JC 正式内核语义 |

## V4 合同

- 请求：`CaseInputBundleV4`，权威为 `compiler_core/contracts.py` 与 `schemas/jc-v4.schema.json`。
- 来源：`SourceSnapshotV4` / `EvidenceManifestV4`。
- 事实：`FactAdmissionReceiptV4` 与 `compiler_core/fact_admission.py`。
- 规则：`RuleV4`、`compiler_core/legal_ir.py`、`compiler_core/rule_packs.py` 和 `compiler_core/rule_admission.py`。
- 证据：事实准入、规则晋级、翻译、求解器、checker 与 proof receipt 分开建模。

当前公共包没有 V3 兼容执行链或迁移入口。仓库测试与 differential fixture 不构成法律正确性证明。

[输入与语义边界](INPUT_AND_SEMANTIC_BOUNDARY.md) · [形式运行时一致性](FORMAL_RUNTIME_CONFORMANCE.md) · [文档索引](../README.md)
