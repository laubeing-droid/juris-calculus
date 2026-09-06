# JC V5 一次性升级 最终验收报告

**计划编号**：JC-UPGRADE-20260906-01
**施工分支**：`upgrade/ulm-bound-runtime-v5`（自 `008198955db39917e755b32e806d9a24a715c6d6` 起点）
**报告日期**：2026-09-06
**性质**：工程验收报告。本地全部必需验收已通过（`work/v5-acceptance/acceptance-summary.json` all_passed=true），候选 wheel 已构建并字节核验；这不是发布、不是生产激活、更不是现实法律正确性认证。

---

## 一、结论（先读这里）

V5 升级已在本地完成并通过 `tools/verify_upgrade.py` 按计划 `remediation/v5/tasks.v1.json` 的全部六项必需验收（结果见 §三）。引擎版本 `5.0.0`、公共协议 `jc/5.0`；`jc/4.0` 与 4.x 引擎版本在正式入口被拒绝。

在声明的输入、规则、语义与资源范围内，运行结果经过独立校验并产出可回放证据链。事实认定、法律输入与经验预测的保证分别呈现，未被合并或互相升级。

**未做/未授权的事项**（精确阻塞，见 §六）：推送分支与 PR、GitHub Actions 四矩阵绿证据、生产密钥与生产激活、经验模型数据。

## 二、U00—U11 完成情况

| 包 | 内容 | 关键凭据 | 状态 |
|---|---|---|---|
| U00 | Windows 3.11 CI 失败修复 + 日志保全 | 根因 `icacls /setowner` 缺 WRITE_OWNER（D:\ 卷 DACL 仅授予 Authenticated Users Modify）；`storage.py` 校验 owner 后跳过冗余 setowner（fail-closed 保持）；runner 失败输出全量保全；CI 上传步骤；本地 py3.11 必需 runner 通过 | 完成 |
| U01 | 证明绑定与功能映射 | `proofs/lmm-binding.json`（91/91 源文件 LF 归一化哈希核验、4 个 artifact ZIP 摘要核验、阶段状态原文保留）；`proofs/runtime-obligation-map.json`（16 项 ULM 映射 + 91 模块处置）；`tests/contract/test_proof_binding.py` 6 项 | 完成 |
| U02 | V5 封闭合同 | `SCHEMA_VERSION_V5=jc/5.0`、引擎 major 5、25 个新对象组、注册表 100 类型、`schemas/jc-v5.schema.json` 再生、状态矩阵 fixture/向量/文档同步；JT04–JT07 | 完成 |
| U03 | 来源/事实/规则准入、IR | 既有三门槛准入链全部保留并通过（`tests/contract/test_fact_admission.py` 等）；`PremiseTokenV5` admitted/assumed 建模 + 依赖传递；IR loss accounting 保持 exact-zero-loss | 完成（既有能力复用 + V5 前提对象） |
| U04 | Horn 支持与结构化论证 | Horn 闭包（ proved core 复用）+ `StructuredArgumentV5` 完整支持结构 + 独立参考核验 `verify_profile_family_v5`；JT12–JT15 | 完成 |
| U05 | 攻击击败、四类语义、分支查询 | `resolve_defeats_v5`（策略门控，优先级不自动制造攻击）、四类有界语义（JT16–JT19 精确对照）、预算耗尽返回 Incomplete（JT20）、非极大 preferred 被参考核验拒绝（JT21）、`query_semantics.py`（JT23–JT27） | 完成 |
| U06 | 程序四路输出 | `procedure.py` 冻结决策表；JT28–JT31 | 完成 |
| U07 | 同分支组合与精确计算 | `domain_composition.py` ChoiceWF 门控 + lit/add/sub/scale 量纲精确算术；JT32–JT34 | 完成 |
| U08 | checker/保证/证书 | `assurance.py` ULM14 保守聚合（JT35–JT37）；独立语义重算拒绝错误输出（JT38）；kernelVerified 需 TCB（JT39）；V4 独立 checker 边界未动（不 import 生产语义算法） | 完成（V5 对象经参考核验通道） |
| U09 | 增量与经验接口 | `incremental.py`：固定宇宙 add-only 绑定全量重算对照（JT40）、七类非单调失效（JT41）、经验只读通道（JT42）、无模型诚实返回（JT43）；Banach 仅登记不适用 | 完成 |
| U10 | 公共入口/渲染/迁移 | 三入口（CLI/JCClient/MCP）继续汇接唯一 Application；`tools/migrate_v4_bundle.py` + 端到端 fixture（JT46）；渲染禁止润色短语清单（JT47）；JT44 由既有三入口矩阵测试覆盖 | 完成 |
| U11 | wheel/全链/交付 | `remediation/v5/tasks.v1.json`（6 任务）、`tools/verify_upgrade.py`、wheel 构建、`docs/operations/RELEASE_V5.md`、本报告 | 完成 |

## 三、本地验收证据（Python 3.11.9 / Windows）

- **`work/v5-acceptance/acceptance-summary.json`：run_status=PASS，V5-01…V5-06 全部 PASSED（all_required_tasks_passed=true）**：
  - V5-01 权威与生成物（3 项检查）、V5-02 V5 合同（19s）、V5-03 语义（13s）、V5-04 迁移 fixture、V5-05 生产链全量（653s，含 formal_e2e/mcp/security/windows/storage_chaos）、V5-06 wheel A/B 构建。
- **候选 wheel**：`juris_calculus-5.0.0-py3-none-any.whl`，A/B 两次独立 `git archive` 提取构建，**字节一致**，`sha256:761aba23aa145dbea1a662034b2acdad6ef071813a6bc7ef1e80ae215f15c9b6`（wheel_gate PASS，authority 45 入口 / payload 39 名单摘要绑定）。
- `py -3.11 -B tools/remediate_v4.py run --through V4-03-OFFICIAL-YAML`：PASS（U00 修复验证）。
- authority `require-clean` CLEAN；`checks.py generated/manifest` OK；`build_file_disposition --check` OK。

### JT → 证据映射（48 项）

| JT | 证据位置 |
|---|---|
| JT01 | `tests/windows_security/test_dacl.py`（回归测试）+ `work/baseline-evidence/`（复现与修复记录）+ runner 失败输出保全（`tools/remediation/runner.py`） |
| JT02/JT03 | `tests/contract/test_proof_binding.py`（6 项） |
| JT04 | `tests/contract/test_v5_contracts.py::test_jt04_*` + `tests/contract/test_contracts.py`（既有负向量） |
| JT05 | `tests/contract/test_v5_contracts.py::test_jt05_*` + `tests/contract/test_run_identity.py` |
| JT06 | `tests/contract/test_v5_contracts.py::test_jt06_*` |
| JT07 | `tests/contract/test_v5_contracts.py::test_jt07_*` |
| JT08/JT09/JT10 | `tests/contract/test_fact_admission.py`（三门槛、伪造、撤销/过期/跨请求）+ PremiseTokenV5 约束 |
| JT11 | `tests/contract/test_legal_ir.py`（loss accounting exact-zero） |
| JT12 | `tests/contract/test_backend_router.py`（Horn 闭包与顺序无关性） |
| JT13/JT14/JT15 | `tests/contract/test_v5_semantics.py` + `tests/contract/test_argumentation.py` |
| JT16–JT19 | `tests/contract/test_v5_semantics.py::test_jt16..19`（精确对照表） |
| JT20/JT21/JT22 | `tests/contract/test_v5_semantics.py::test_jt20/21/22` |
| JT23–JT27 | `tests/contract/test_v5_semantics.py::test_jt23..27` |
| JT28–JT31 | `tests/contract/test_v5_procedure_composition.py::test_jt28..31` |
| JT32–JT34 | `tests/contract/test_v5_procedure_composition.py::test_jt32..34` |
| JT35–JT37 | `tests/contract/test_v5_assurance.py::test_jt35..37` |
| JT38/JT39 | `tests/contract/test_v5_assurance.py::test_jt38/39` |
| JT40–JT43 | `tests/contract/test_v5_incremental.py` |
| JT44 | `tests/formal_e2e/test_three_entrypoint_error_matrix.py`（三入口同语义） |
| JT45 | `tests/unit/test_windows_utf8_git.py` + 安装包验收（CI `package` job / V4-04） |
| JT46 | `tests/contract/test_v5_migration_render.py` + `tests/formal_e2e/run_migration_fixture.py` |
| JT47 | `tests/contract/test_v5_migration_render.py::test_jt47_*` |
| JT48 | 推送后 CI：四矩阵 + `package`（A/B wheel + 安装包验收）+ `promote`；当前为待授权阻塞项 |
- JT48 的远端 CI 证据与固定主体绑定由推送后 CI 承担（见 §六）。

## 四、能力边界（如实声明）

**能做什么**：在已准入来源、事实与规则包上，按请求 profile（默认 grounded，四类有界语义按需）求解，输出封闭合同结果、独立 checker 回执、证书与审计包；同分支领域组合与精确量纲算术；程序/举证四路后果；分支查询多标志状态；add-only Horn 增量（默认关闭优化路径，功能与对照已交付）；只读经验结果通道。

**什么情况下不做确定判断**：求解未完成（Incomplete + 未完成义务）；无扩展证据不得宣称空族；事实有争议/仅假设（hypothetical）；程序认定缺授权（pending）；经验通道无模型/数据（明确返回"未提供经验证的经验估计"）；Checker 失败或超时不签正式结论证书。

**明确的非声明**：452 个 Lean 声明 ≠ 452 个产品能力；`crossCheckOnly` ≠ kernelVerified；Banach 未接入（不适用登记）；三组旧回执（JC c79e03b8）不作为 V5 全链证据。

## 五、保证呈现

按 ULM14 分坐标呈现（source/text/fact/proof/authority），字段分别聚合、不平均：spec=proved（引用固定 LMM 主体的具体命题）、implementation=crossCheckOnly（可信计算基列于 `AssuranceEnvelopeV5.tcb_refs`）、runCheck=checked（本次独立 checker 回执）、legalInput=pending/assumed 引用保留。

## 六、待授权/待宿主条件（精确清单）

1. `git push -u origin upgrade/ulm-bound-runtime-v5` + PR：需当次会话网络写授权；合并后 CI 四矩阵与 `package`/`promote` 任务产出 JT48 所需远端证据。
2. 生产 Ed25519 密钥、有效规则包与信任配置：宿主提供后按 `docs/operations/RELEASE_V5.md` 激活（此前只能报告 BUILD_ACCEPTED）。
3. 经验模型与校准数据：宿主提供后才可能返回经验估计；当前诚实返回。
4. LMM 侧无需变更：本次未修改任何 Lean 证明；未新增 `sorry`、未删前提、未改历史证据。

## 七、交付物清单

- 候选 wheel：`work/v5-acceptance/`（由 V5-06 wheel_gate 构建并校验）。
- 合同/schema/manifest：`schemas/jc-v5.schema.json`、`mcp_manifest.json`（确定性 emitter 再生）。
- 证明绑定：`proofs/lmm-binding.json`、`proofs/runtime-obligation-map.json`、`proofs/proof-inventory.json`。
- V5 对象组：`compiler_core/{query_semantics,procedure,domain_composition,assurance,incremental}.py` + `contracts.py` V5 段。
- 验收：48 项 JT 样本的对应测试文件（见 §二凭据列）与 `work/v5-acceptance/` 运行日志。
- 迁移：`tools/migrate_v4_bundle.py` + `tests/formal_e2e/run_migration_fixture.py`。
- 文档：`docs/contracts/V5_OBJECT_STATE_MATRIX.md`、`docs/operations/RELEASE_V5.md`、本报告。
