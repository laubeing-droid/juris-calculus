# Project memory

## 当前边界

- JC 当前只维护 V4：结构化请求 -> 确定性准入 -> application service -> canonical result、certificate、audit bundle、graph 和 replay。
- CLI、Python 与四工具 stdio MCP 共用同一合同和 application service。
- 私有案件、律师工作流、诉讼策略、OCR/模型流水线、生产密钥和专有规则包均在仓库外。
- 仓库内测试、wheel 和 test-only provenance 只能证明候选产物可复现，不能证明法律结论正确或生产已经部署。

## 正式权威

- 版本：`compiler_core/version.py`。
- 合同：`compiler_core/contracts.py` 与 `schemas/jc-v4.schema.json`。
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
