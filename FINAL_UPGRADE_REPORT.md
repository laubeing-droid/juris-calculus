# JC V5 一次性升级 最终验收报告

**计划编号**：JC-UPGRADE-20260906-01
**施工分支**：`upgrade/ulm-bound-runtime-v5`（自 `008198955db39917e755b32e806d9a24a715c6d6` 起点）
**报告日期**：2026-09-06（2026-09-07 增补独立核查修复，见 §八）
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

---

## 八、2026-09-07 增补：独立核查（20260907jc_v5_upgrade_audit.md）三项阻断的修复

本节记录针对外部独立核查报告 `20260907jc_v5_upgrade_audit.md`（对象为固定提交 `7b75b42`）所列三项阻断的工程修复。理论仓库无需再扩展：Stable 定义本身足以指出并修复反例。

### 阻断一：stable 攻击方向已修复

`compiler_core/argumentation.py` 中 `evaluate_profile_v5` 的 stable 分支原先检查"集合外 → 集合内"，与 `ULM10DungProfiles.lean` 的定义（集合内攻击集合外）相反。已调换方向，最小反例 a→b 现在返回唯一 stable 扩展 `{a}`（反向 b→a 返回 `{b}`）。

新增回归（`tests/contract/test_v5_reference_enumeration.py`）：

- **穷举对照**：0–3 个论证的全部有向图（含自攻击）共 531 张，四类语义共 2,124 项比较，逐一对照本测试文件内独立编写的定义驱动参考实现（与生产代码零共享）。修复前该穷举会在 stable 上产生约 252 项不一致（与核查报告一致）；修复后全部一致。
- **最小反例、攻击链、分叉**的显式锚定用例。

### 阻断二：V5 语义校验器已改为定义驱动独立校验

`verify_profile_family_v5` 原先以重跑生产求解函数 `evaluate_profile_v5` 作为"参考结果"，无法识别求解器自身的算法错误。现已重写：参考实现基于攻击邻接独立计算冲突自由、防卫、特征函数与 stable 全外部攻击条件，**不再调用生产求解函数**。

- 每个 claimed 扩展必须逐一通过定义校验（错误扩展/非极大 preferred/自相冲突均被拒绝，`discovered_unsound`）。
- `exact` 覆盖必须等于独立重算的完整族（遗漏扩展 → `family_mismatch`）。
- 超出枚举预算时 fail-closed：exact 声明一律拒绝（`reference_incomplete`），不允许伪称完整。
- 审计报告 §四 的对照表已翻转并锁定为回归：`{{b}}` 声明被拒绝、`{{a}}` 声明被接受；monkeypatch 生产求解器返回谎言后，校验器结论不变（`tests/contract/test_v5_semantics.py::test_audit_verifier_*`）。

### 阻断三：新能力已接入唯一正式主链

公开请求合同 `CaseRequestV4` 新增闭合的可选 V5 阶段字段（缺省缺省等价于原行为，旧文档字节不变）：

| 字段 | 说明 |
|---|---|
| `defeat_policy_v5` | 准入的击败策略（`DefeatPolicyV5`），`request_ref` 必须绑定请求身份投影 `case_request_binding_ref(request).digest` |
| `profile_queries_v5` | 针对已检视图的 profile 查询（`QueryRequestV5`，≤64 条，query_id 唯一），mapping_version 必须为 `jc-aaf-mapping-v5/1`，scenario_ref 必须按请求绑定派生 |
| `composition_policy_v5` / `composition_choice_v5` / `composition_expression_v5` / `composition_operands_v5` | 同分支组合：候选由已评估 profile 族按 `compose_branch_key_v5` 派生，选择必须落在实际候选内，表达式经 `evaluate_expression_v5` 精确求值 |

`ApplicationV4` 在正式路径 checker 通过后执行 `_profile_stage_v5`：

1. 从**独立 checker 已核验的参数图**构建 `AttackRecordV5`（按 `ATTACK_KIND_MIGRATION_V5` 迁移；priority 派生边不自动成为 V5 击败，记入 envelope notice）。
2. `resolve_defeats_v5` 按准入策略解析击败边；`evaluate_profile_v5` 求解所请求 profile。
3. **每个完整族必须通过独立校验器**（coverage=exact）；求解器错误在链内被拒 → `APPLICATION_V5_VERIFICATION` engine error，不签发证书。
4. 每条查询经 `evaluate_query_v5` 得到 ULM11 多标志状态；每族经 `adjudicate_v5` 得到程序四路后果（无授权输入时诚实返回 `pending_legal_judgment`；族不完整返回 `solver_incomplete`）。
5. 组合（按请求）经 ChoiceWF 门控与精确算术；非整结果挂 `rounding_required` 义务。
6. 每 profile 生成 ULM14 保证信封（spec=proved/openObligations，implementation=crossCheckOnly，run_check=checked），同 profile 多查询经 `combine_assurance_v5` 保守聚合。
7. 阶段文档（`jc/profile-stage-v5/1.0`）注册为内容寻址工件，经 run 事件进入审计包（checker-receipts.json 内密封），可经 `jc_verify_run` / `jc_read_artifact` 外部读取；重复运行字节级一致（可重放）。

外部可观察性由端到端测试锁定（`tests/contract/test_v5_profile_chain.py`）：合成规则包 + 补充事实准入 → 异常规则攻击 positive 规则 → 四类 profile 族、查询状态、程序后果、组合金额（21/2 CNY + rounding 义务）、保证信封全部从**密封审计包**中读取断言；wrong-solver 注入在链内被独立校验器拒绝；无 AAF 图时 fail-closed（`APPLICATION_V5_STAGE`）；空图时以 `profile_queries_without_arguments` 理由可观察地延后。

配套修复：`compiler_core/certificates.py` 多 claim 形式证书对"同一 checker 回执被多条 claim 引用"不再误判为重复（一次运行一个 checker 回执，多规则适用是合法形态）；合同向量、schema/manifest 出版物、`jc-formal-profile.json` 工具清单摘要已同步再生。

### 范围声明（不在本次集成范围，保持禁用/不适用）

- **增量 add-only 快路径（`incremental.py`）**：默认关闭。主链不做增量优化派发；其 proved core（Horn 闭包）与全量重算对照保留于单元验收（JT40–JT43）。这是合法范围选择，不为凑满理论清单而强行启用。
- **Banach 经验通道**：不适用登记不变；经验接口保持只读、无模型即诚实返回。
- `incremental.py` 与其他四个 V5 模块不同，未接入主链派发路径；本报告 §四"add-only Horn 增量（默认关闭优化路径，功能与对照已交付）"按此精确含义理解。

### 本节验收状态

- **支持矩阵全量重跑**：Python 3.12.10 与 Python 3.11.9（Windows 本地）各执行 `tests/` 全套（除 tests/performance），两次均为 **1703 passed, 0 failed**；含新增 profile 链端到端、531 图穷举与校验器独立性回归。
- 合同固定向量、schema/manifest 出版物、`jc-formal-profile.json` 工具清单摘要全部再生并通过 `checks.py generated`、`build_file_disposition.py --check`、`checks.py manifest`、`checks.py cleanup`；模块权威 observed graph `require-clean` status=CLEAN。
- 新增回归已纳入 `remediation/v5/tasks.v1.json` V5-03 验收任务清单。
- **本地候选 wheel 已按 V5-06 重建**：修复以提交 `7b4e47b`（分支 `remediation/v5-audit-20260907`）为源，`git archive` 双提取 A/B 构建，字节一致；`juris_calculus-5.0.0-py3-none-any.whl`，SHA-256 `a7971e305002a1cd57ae7d2250e5da3504a935392214c65b65a1bf8ce29fc51d`（构建报告 `work/v5-audit-wheel/wheel-report-{a,b}.json`，wheel_gate status=PASS，authority 45 入口 / payload 39 名单）。构建环境 Python 3.11.9 + 固定构建依赖（setuptools 83.0.0 / wheel 0.47.0），与 CI package job 同规格。
- **补充验证运行在构建包上**（不依赖仓库源码）：解包该 wheel 后直接对包内代码执行——stable 反例返回 `{a}`；独立校验器拒绝 `{{b}}`、接受 `{{a}}`；2,124 项穷举对照全部一致；`_profile_stage_v5` 集成入口存在。
- **远端 CI 证据已取得（JT48 远端半）**：分支 `remediation/v5-audit-20260907` 已推送，PR [#5](https://github.com/laubeing-droid/juris-calculus/pull/5)。
  - CI run `34148046053`（pull_request，head `d89db08`，实际检出并测试 PR 与 main 的合并提交 `a287d8f55c09cb4efe4dcc3b9e2e590ff8a99d16` / tree `ed5706833874ce6e75687652cdf8359ee4b9e7f5`）：**全部任务成功**——generated/authority/lint/type/unit、四矩阵（windows/ubuntu × Python 3.11/3.12）、A-B build / installed wheel / release evidence；`Promote exact attested tag` 为 skipped（与 TEST_ONLY 状态一致）。
  - 工件 `release-candidate-a287d8f…`（artifact id `10028525966`）：ZIP SHA-256 `03625aa39d3278b56a7d2c8e3110c3f7a75044033aa1048737f196318981ac33`（463,748 字节）；A/B wheel 字节一致，`juris_calculus-5.0.0-py3-none-any.whl` SHA-256 `dddad2a6b6940962d5af284dbccf5853319146825091719efae8eaa32ae35240`（各 230,320 字节）；provenance `BYTE_IDENTICAL_REBUILD`，`test_only=true`、`production_release_claimed=false`、`promotion_status=TEST_ONLY_NOT_PROMOTABLE`，`companion_spec_commit` 仍为历史 `a3a01594…`（历史 oracle 回归，范围声明不变）。
  - `installed-wheel.json`：status=PASS，安装版本 5.0.0，fresh 环境导入通过、无源码树、安装与执行期间网络禁用，绑定 wheel 摘要 `dddad2a6…`。
  - **补充验证运行在 CI 构建的 wheel 上**：stable 反例返回 `{a}`；独立校验器拒错纳正；2,124 项穷举对照全部一致；`_profile_stage_v5` 集成入口存在。
  - 首次 CI 失败一次：新增测试文件使 `remediation/v4/file-disposition.json` 注册表漂移，已再生成并随 `d89db08` 提交；第二轮全绿。
- 剩余项仅为生产签名与激活（`environment: release` 密钥、有效规则包、部署信任），与 CI 颜色无关，仍属后续阶段。
