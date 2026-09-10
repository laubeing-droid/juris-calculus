# Project memory

## 当前边界

- JC 当前只维护 V5（公共协议 jc/5.0，版本 5.0.1）：结构化请求 -> 确定性准入 -> application service -> canonical result、certificate、audit bundle、graph 和 replay。5.0.1 完成 JC-FINAL-FIX-20260908 六项最终整改（分支身份、查询反驳、typed incomplete、priority 登记/阻断、真增量默认启用、程序四路）并冻结：后续主线是 Legal Harness 集成，JC 侧读写接口是 `compiler_core/harness_contract.py`（jc-harness-contract/1）与 `docs/contracts/HARNESS_INTEGRATION.md`，不再做 JC 独立集中施工。2026-09-11 起 `jc-business-root/1`（有限情景条件本金，`compiler_core/business_root/`）已作为第一批业务能力接入同一主链：request 扩展 `business_tasks_v1`（省空、不改旧摘要）、verify-only `verify_business_delivery` 双文件核验、能力查询 `business_capabilities()`；保证分解与未关闭清单见 `docs/ulm-consolidated/IMPLEMENTATION_HANDOFF.md`。
- CLI、Python 与四工具 stdio MCP 共用同一合同和 application service。
- 私有案件、律师工作流、诉讼策略、OCR/模型流水线、生产密钥和专有规则包均在仓库外。
- 仓库内测试、wheel 和 test-only provenance 只能证明候选产物可复现，不能证明法律结论正确或生产已经部署。

## 正式权威

- 版本：`compiler_core/version.py`。
- 合同：`compiler_core/contracts.py` 与 `schemas/jc-v5.schema.json`。
- application：`compiler_core/application.py`。
- certificate issuer：`compiler_core/certificates.py`。
- independent checker：`compiler_core/independent_checker.py`。
- 模块分类：`docs/architecture/module-authority.json`。
- 正式 wheel 文件集合由 module-authority 与 `tools/wheel_gate.py` 共同校验。

## 工程约束

- 不弱化 `DecisionStatus`、`verified_fact`、Horn、attack、exception、permission、priority、checker acceptance 或 fail-closed 行为。
- official YAML 准入只依赖正式模块 `compiler_core/rule_admission.py`；不得重新把旧 `types.py` 塞回 wheel。
- 中港美 addons 用于规则对齐，保留源码、保持 smoke，但不进入正式 wheel。
- Windows 子进程和 Git 输出使用严格 UTF-8；测试材料在 `tmp_path` 内自建，不依赖固定机器目录。
- 当前 authority 只用 Git、AST、入口点与 wheel 清单；不依赖外部 CodeGraph 数据库。
- `remediation/v4/tasks.json` 与 `task.schema.json` 字节冻结；新增路径只能新建任务定义版本。
- 当前 runner 只执行 `tasks.v3.json`，失败后修当前代码并从头重跑，不恢复或修补旧 receipt。
- 不在未获授权时执行 push、tag、release 或 deploy。
