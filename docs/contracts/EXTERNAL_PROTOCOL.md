# 外仓协议

本页描述当前 V4-only 公共消费边界。历史施工方案不是运行时权威。

## 入口约束

1. CLI：文件/stdin 输入，stdout 仅协议输出，stderr 日志，稳定 exit code。
2. `JCClient`：同一 application service、同一 canonical contract；只使用包内 release registry。
3. MCP：四工具、零资源边界；stdio subprocess 是 transport authority。

## 外仓消费协议

| 外仓 | 允许入口 | 禁止 |
| --- | --- | --- |
| Deli | `JCClient`、版本化 CLI JSON 或 MCP 提交 candidate bundle | `sys.path` 导入 `compiler_core` 内部模块；自签 attestation/certificate/DecisionStatus |
| Legal Harness | 公共接口提交 attestation/approval refs 与案件运行请求 | 组织 JC 内部工作流；绕过 fact_gate |
| LMM | versioned semantic manifest、proof receipt、refinement fixtures | 直接修改 JC 正式内核语义 |

## 版本化消费点（V4 合同）

- 请求：`CaseInputBundleV4`（`compiler_core/contracts.py` + `schemas/jc-v4.schema.json`）。
- 来源：`SourceSnapshotV4` / `EvidenceManifestV4`（`compiler_core/contracts.py`）。
- 事实：`FactAdmissionReceiptV4`（`compiler_core/contracts.py`）及
  `FactAdmissionServiceV4`（`compiler_core/fact_admission.py`）。
- 规则：公共 `RuleV4` 合同（`compiler_core/contracts.py`）、形式规则
  `RuleV4`（`compiler_core/legal_spec_ivl.py`）及中国法平台门禁
  （`compiler_core/rule_platform_cn.py`）。
- 收据：事实准入、规则晋级、翻译、求解器、checker 与 proof 收据均在
  `compiler_core/contracts.py` 中分离建模。

当前公共包没有 V3 兼容执行链或迁移入口。历史 V3 只允许通过隔离的离线回放流程读取。

## 证据等级声明

本仓测试为 runtime test 与 differential fixture 级别；不构成法律正确性证明。
独立 checker 只证明指定算法与输入的一致性；算法 checker 不等同于 Lean 定理证明。

## 相关文档

- [输入与语义边界](INPUT_AND_SEMANTIC_BOUNDARY.md)
- [形式运行时一致性](FORMAL_RUNTIME_CONFORMANCE.md)
- [历史 V3 回放](../operations/V3_HISTORICAL_REPLAY.md)
- [文档索引](../README.md)
