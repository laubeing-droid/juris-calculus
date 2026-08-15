# 外仓协议（W9）

依据：20260815 施工方案 §15。

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

## 版本化消费点（v4 合同）

- 请求：`CaseRequestV4`（`compiler_core/contracts_v4.py` + `schemas/jc-v4.schema.json`）。
- 来源：`SourceSnapshotV2` / `EvidenceManifestV1` / `SourcePathV1`（`source_service_v2.py`）。
- 事实：`FactAdmissionAttestationV1`（`fact_admission_v1.py`）。
- 规则：`RuleV4`（`legal_spec_ivl.py`）+ 平台门禁（`rule_platform_cn.py`）。
- 收据：Admission/Translation/Checker/Solver/Proof/HumanApproval 六类分离（`certificate_v1.py`）。
- 兼容：v3/W1b 只能经 `compat_v3_v4.py` 投影，输出 MigrationReceiptV1。

## 证据等级声明

本仓测试为 runtime test 与 differential fixture 级别；不构成法律正确性证明。
独立 checker 只证明指定算法与输入的一致性；算法 checker 不等同于 Lean 定理证明。
