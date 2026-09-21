# 03 卡合同贡献 — juris-calculus（0b 冻结输入）

- run-id: `full-20260919-015613-108316`
- 贡献者: 03（juris-calculus）
- 树: `.local/checkouts/full-20260919-015613-108316/juris-calculus`，HEAD `412c69cecbc430cfe43308ff34d443750e9d5575`，branch `jusbench/full-20260919-015613-108316-jc`，自集成检出（`jusbench/full-20260916-183044-567611`）建树。
- 机读版: 同目录 `contract-contribution.json`（本文为其人读摘要，冲突时以实读源码行号为准）。
- 所有断言均来自本 J 树源码实读；未执行业务实现，数学仓只读未触碰。

## 1. jc-harness-local/1 现有真实合同（00 §8.5 "V4→JC 情景"行冻结依据）

**存在且真实。**

- 合同版本常量 `HARNESS_LOCAL_CONTRACT_VERSION = "jc-harness-local/1"`（`compiler_core/client.py:44`）。
- 入口 `create_local_client(state_root, rule_roots=(), *, clock=None, quota_bytes=None)`（`client.py:848`，委托 `compiler_core/local_runtime.py:1557`；无 key/信任包/签名 pack）。
- 方法 `JCClient.evaluate_harness_bundle(case_bundle, *, case_id, issue_queries) -> dict`（`client.py:369`）：
  - `case_bundle`: `CaseInputBundleV4 | Mapping | bytes | str`，先经 `validate_bundle`；
  - `case_id`: 非空 str，必须等于 bundle case scope，否则 `HARNESS_CASE_SCOPE_MISMATCH`；
  - `issue_queries`: 每项 `{issue_id, claim, profile[, excluded_branch_reasons]}`（或 `HarnessQueryInput`），必须与内核 `profile_queries_v5` 一一对应（claim+profile 逐项相等），缺失/多余 → `HARNESS_QUERY_MAPPING`，重复 issue_id → `INVALID_ISSUE_QUERY`；
  - 恰好一次 `ApplicationV4.evaluate`（计数强制，`EVALUATION_COUNT`）；运行时未装配 → `RUNTIME_NOT_CONFIGURED`。
- 返回：纯 JSON dict = `HarnessRunResultV5.to_dict()`（`compiler_core/harness_contract.py:198-250`：`harness_contract_version="jc-harness-contract/1"`、`case_id`、`run_status`、`decision_status`、`completeness`、`issues[]`、`procedure_kinds`、`open_obligations`、`missing_fact_keys`、`admitted_fact_keys`、`assumed_fact_keys`、`horn{mode,fallback_reason,parent_binding,solver_rule_evaluations,checker_rule_evaluations}`、`assurance_specs`、`composition`、`artifact_refs`、`audit_manifest_ref`）外加 `execution_mode="local"`、`signature_status="not_used"`、`evaluation_count=1`、`run_identity_ref`、`business_results[]`。

## 2. business_capabilities 真实结构与 case-bundle 构造路径

**存在且真实。**

- `JCClient.business_capabilities()`（`client.py:333`）返回（常量在 `compiler_core/business_root/codec.py:23-30`）：
  `capability="jc-business-root/1"`、`profiles=("SYNTHETIC-CONDITIONAL-PRINCIPAL/1",)`、`model_bases=("SYNTHETIC-SETTLEMENT-GRID/1",)`、`requirements=("SYNTHETIC_EXACT_PRINCIPAL_ANALYTICS_TWO_FILES/1",)`、`delivery_files=list(BUSINESS_DELIVERY_FILES_V1)`、`checker_version="jc-business-checker/1"`、`formal_evidence="CROSS_VALIDATED_GENERAL_ALGORITHM_PENDING_KERNEL"`、`semantic_scope=delivery_checker.SCOPE`、`request_extension="business_tasks_v1"`、`verify_method="verify_business_delivery"`、`verify_only=True`。列表由已安装代码生成，非候选 manifest。
- 构造路径：`JCClient.local_case_bundle(**kwargs)` → `LocalBundleBuilder.build_bundle(**)`（`local_runtime.py:1125`）：`case_id, decision_time, facts[LocalFactInput], queries[LocalQueryInput{query_id|issue_id, claim, profile}], source_id, request_id, allowed_attack_kinds, query_refutations, query_gates, procedural_input, incremental_parent, composition_*, business_tasks[BusinessTaskV1|Mapping], now`；至少 1 条 query 或 1 条 business_task。
- `BusinessTaskV1`（`compiler_core/contracts.py:3825`）：`task_id, issue_id, requirement_id(=SYNTHETIC_EXACT_PRINCIPAL_ANALYTICS_TWO_FILES/1), profile(=SYNTHETIC-CONDITIONAL-PRINCIPAL/1), selection_ref:DigestV4, input:BusinessTaskInputV1, source_refs[]`。

## 3. 现有公开 client 与 ApplicationV4 公开面

- `JCClient` 公开方法：`validate_request, validate_bundle, capabilities, evaluate, evaluate_for_mcp, verify_run, verify_for_mcp, read_artifact, render, local_pack, local_case_bundle, business_capabilities, evaluate_harness_bundle, verify_business_delivery, business_delivery_documents, local_read_run, local_horn_subject_state`。
- 模块函数：`create_local_client(...)`；`runtime_client()`（`JC_RUNTIME_FACTORY` 环境变量指定模块的 `create_client`，缺省 fail-closed）。
- `ApplicationV4`（`application.py:502`）公开方法仅两个：`evaluate`（:2907）与 `register_business_delivery_record`（:2814）；其余为私有 stage。
- MCP manifest 现有 4 工具：`jc_capabilities, jc_evaluate, jc_verify_run, jc_read_artifact`。
- 打包显式清单（`pyproject.toml:27-34`）：`packages=["compiler_core","compiler_core.business_root","compiler_core.backends","compiler_core.math_export","configs","schemas"]`；package-data 仅 `configs/render_profiles/neutral.yaml` 与 `schemas/*.json`；`include-package-data=false`——新增规则 YAML/资源必须显式加入清单并仓外验证。

## 4. rule_packs 准入入口真实位置与签名

**存在且真实。**

- `RulePackVerifierV4`（`compiler_core/rule_packs.py:300`）：
  - 构造：`(resolver: ArtifactResolverV4, source_service: SourceServiceV4, trust: TrustVerifierV4|LocalRecordTrustV4, *, expected_engine_api: str, expected_compiler_build_digest: DigestV4, expected_source_tree_digest: DigestV4, expected_schema_digest: DigestV4)`；
  - `verify(pack_ref: ContentRefV4(kind="pack-signature"), *, now: CanonicalTimeV4) -> VerifiedRulePackV4`（:769）；`VerifiedRulePackV4` 只能由 verifier 签发（构造被封）。
- YAML 规则包容器准入：`verify_pack_manifest(manifest_path: Path, config_root: Path, *, development_override=False, override_path_hash="") -> PackVerification`（`rule_packs.py:1414`）——manifest 字段/文件哈希/ID 唯一性/计数/正式来源准入。
- 辅助：`compiler_core/rule_admission.py`：`normalize_rule_admission(rule)`, `is_rule_reasoning_eligible(rule)`, `build_rule_inventory(rules)`, `resolve_rule_source_anchor(rule)`。
- 缺口：00 §8.5 的 `admit_verified_rule_pack` 薄公开适配**尚不存在**；实现必须包以上入口，不建第二准入门。

## 5. pricing 现状（对照 03 §4a issue-human-residual/1）

**JC 仓内不存在任何 pricing 模块或 DTO。** 全 compiler_core 无 `PricingInput/CalibrationSnapshot/QuoteSnapshot/TimeEntry/FeatureSnapshot/Bill/Payment`、无 `BillingTier`、无校准估计器代码；"pricing" 唯一命中是 `compiler_core/trust_labels.py` 的红线禁语 `"REAL_PRICING_VALIDATED"`（禁止越界主张）。相邻既有模式：`EmpiricalEstimateV5/attach_empirical_v5`（`compiler_core/incremental.py:282-313`）——无实证模型时必须记 `absent_reason`（诚实缺省），`EmpiricalResultV5.calibration_status ∈ {calibrated, uncalibrated, not_calibrated}` 属求解器域、非计价。

结论：**issue-human-residual/1 的全部字段均为新增**（workItemId/issueIds 绑定、动作类别、人时、AI 完成标志、人工核验/返工、共享动作单计、剩余人时合计、可编辑本地费率 100/300 元/h、直接成本默认 0、报价=未舍入剩余工时×费率+直接成本、整数分 half-up、逐项分解、随报价保存的模型/参数/特征版本）。可复用原语：`V4Contract` 基类（canonical JSON、from_dict/to_dict、_validate）、`DigestV4/ContentRefV4`、canonical decimal 字符串字段惯例。**注意：§0b 类型名 `DecimalText` 在现行代码中不存在**（现行做法是普通 str+显式校验），冻结时应记录该映射。母本 §3.3.2 亦把 `compiler_core/pricing.py` 标为【新增】，与本盘点一致；旧模型 Z-v1-default 及冻结样例属新建实现+tag 对照，不属"现有 DTO 保留"。

## 6. 增量求解公开路径现状

**存在且真实，无全局开关。**

- 逐请求选入：bundle 输入 `incremental_parent` → `CaseRequestV4.incremental_parent_v5`（`application.py:2051`）。
- 默认（无 parent）：`mode="full_recompute"`、`fallback_reason="no_parent_reference"`；`parent.mode=="force_full"` 为诊断强制全量。
- 资格检查（`application.py:2052-2092`）：parent 状态须可取回且已验证；`fact_deletion` / `rule_rewrite_or_removal` / `universe_growth` 各自具名回退全量；仅加法增量 → `mode="incremental"`（`compiler_core/incremental.py:131 incremental_horn_closure`）。
- 等价性：每次运行（含增量）都独立全量复算闭包，不一致即 `APPLICATION_HORN_INCREMENTAL_MISMATCH` fail-closed。
- 公开状态：`HarnessRunResultV5.horn{mode, fallback_reason, parent_binding, solver/checker work}` + 封存的 horn subject state artifact（`verified_complete`）——即 02/01 消费 `JC.incremental_enabled_and_equivalent` 的状态面；另有 `incremental_matches_full_recompute`（:230）、`requires_full_recompute`（:251）辅助。
- priority：请求字段 `priority_refs`（`contracts.py:1454/1524/1558`）；`priority_defeat` 攻击类型被有意不映射（`contracts.py:2759-2767`），只有经准入的优先关系才成为击败决定（`priority_edge_decisions_v5`、`PRIORITY_POLICIES_V5` 在 `argumentation.py:1036`）；`_v5_verify_priority_mapping`（`application.py:443`）独立复算优先调制击败集、反向即拒证。DEC21 的"增量开启/优先参与"落点=真实行使该路径+未完成状态传播，不是加布尔开关。

## 7. 数学仓只读核验（只读，未修改，未跑 Lean/构建）

数学仓 `legal-math-modeling`（工作区同级只读检出；原文写机器绝对路径，按machine-paths门改为具名引用，2026-09-22用户授权）：

| 文件 | 可读 | 条目 |
|---|---|---|
| `tools/full_math/spec/BINDINGS.json` | OK | **217 条**（`{"bindings":[...]}`；id 形如 `TARGET:F01`；行键 id/theorem/contract/proof_mode/algorithm/implementation_sources/test_ids/negative_test_ids/observation_contract/semantic_links/formal_scope/generality/external_assumptions/independent_semantics/proof_sources）= 57+9+134+10+7 ✓ |
| `DEMANDS_134.json` | OK | 134 条（requirement_id D001…，含 benchmark_ids/source_ids/guarantee_ids/proof_family_ids） |
| `TARGETS_57.json` | OK | 57 条（F01…） |
| `EXT_9.json` | OK | 9 条（EXT01…） |
| `GAPS_10.json` | OK | 10 条 |
| `ROOTS_7.json` | OK | 7 条（GENERIC_FINITE/SYMBOLIC_EXACT/STATISTICAL_COMPOSITION 等） |
| `EXPORT_AFTER_MATH.json` | OK | 3 行配置（required/output/do_not_run_now） |
| `tools/ulm_consolidation/plans/BENCHMARKS_20.json` | OK | 20 条；jurisdiction 自由文本分布=15 中国法/5 美国法，与 DEC20 一致 |
| `tools/ulm_consolidation/plans/BENCHMARK_DEMANDS_134_ORIGINAL.json` | OK | 134 条原始映射 |

同目录另有 DEFERRED_EXTERNAL / EXECUTION_ORDER / IMPLEMENTATION_JOBS.jsonl / LEGAL_FAMILIES_14 / ORIGINAL_LOCK / REQUIREMENTS / SCOPE / TASKS 可读。**217 是待接入集合，不是已生产化证明。**

## 附：带入的未提交修改及理由

源检出 `tools/run_installed_c06_probe.py` 的 1 个未提交修改**已带入**（`git diff` 原始字节经 Python subprocess 落 patch → J 树 `git apply`，7363 字节，干净应用）。理由：不是临时调试——无散置 print/硬编码路径/注释掉代码；是三项实质修复：① 三处 digest 缺省由空串改为 typed `EMPTY = "sha256:00…0"`；② 修 building client 与 console 探针 state_root 不一致（原 `local-state-console-src` vs 探针 `local-state-console`，这正是跨进程 `CASE_BUNDLE_INCOMPLETE` 的根因）；③ 把 keyless 面跨进程评估的 typed 拒绝（`CASE_BUNDLE_INCOMPLETE`/`RUNTIME_NOT_CONFIGURED`）逐字记录为能力边界并扩充 `--version`/keyless `capabilities` 探测，替换裸 "failed"。判定语义收紧（要求版本串与 typed code 匹配），不是放水。该探针属 JC-03 安装态验证链路，保留有利于后续实跑。

## 基线事实（任务 B）

- J 树对象库含 `412c69cecbc430cfe43308ff34d443750e9d5575`（rev-parse 通过，即 HEAD）。
- `c2acea3589d14f25f5b8285117ce01276e87860b` 在对象库中，类型 `commit`；`v1.0.3^{commit}` 精确解析到该 commit；tag 下 `legalos_services/legalos_pricing.py` 与 `legalos_services/peripheral_models.py` 均在（另含 `__init__/differential_privacy/external_context/inspectors`）。03 卡步骤 1 提取时对象可达。
- 当前工作树无 `legalos_services/` 目录（与母本"当前目录不存在"判断一致）。

## 缺口清单（供 0b 冻结与后续施工）

1. pricing 全域缺失（pricing.py、calibrate/price/recompute_price、BillingTier 恢复、校准估计器）——新写，基线自 tag c2acea3 提取。
2. `JCClient.calibrate/price/recompute_price/calculate_deadlines/read_argument_graph`（§3.3.4 五入口）不存在。
3. `admit_verified_rule_pack` 薄适配不存在（包 RulePackVerifierV4/verify_pack_manifest）。
4. `predict_outcome / deviation_rank / terminal_state_stats` 不存在（JCClient + MCP manifest 现 4 工具）。
5. 期限/日历域不存在（无 CalendarSnapshot/calendar_coverage_missing/calculate_deadlines）；须自 Harness `providers.py::StatutoryDeadlineService` 提取（H 仓输入，本阶段未读）；2027 日历为空占位。
6. `DecimalText`（§0b 名）不在现行代码；冻结需记录到 canonical decimal str 的映射。
7. `training.export_rules_as_jsonl` 的 `rng.shuffle`（`training.py:79-80`）无条件执行，`split_mode` 改值不改变切分——与 03 §4b 判断一致，须改为真实按组/时间切分或拒绝不支持模式。
8. 测试在位：`tests/unit/test_rule_admission.py`、`tests/unit/test_training_export.py`、`tests/contract/test_business_root.py`、`tests/packaging/test_business_wheel_install.py`（均为既有）。缺失（卡标【新增】）：`tests/unit/test_pricing_v1.py`、`tests/unit/test_deadlines_v1.py`、`tests/integration/test_knowledge_runtime.py`。
