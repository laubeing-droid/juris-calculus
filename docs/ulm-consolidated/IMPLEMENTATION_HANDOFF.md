# JC施工报告：jc-business-root/1 第一批全量落地（2026-09-11）

本文件是**实际施工记录与交接清单**，取代 2026-09-10 的接线任务书。基线核查与批次方案见 `ROUTE1_JC_PLAN_20260910`（工作区同级目录）；本仓库施工基线 `e6be0c5`。能力契约详见 `docs/contracts/BUSINESS_ROOT.md`。

## 1. 版本元组（同次交付）

| 组件 | 值 |
|---|---|
| juris-calculus 包版本 | 5.0.1（`compiler_core/version.py` 唯一权威；能力沿仓库先例在版本内落地，下次发布随 5.1.0 出tag） |
| 公共协议 | `jc/5.0` |
| 业务能力 | `jc-business-root/1`（request 扩展 `business_tasks_v1`，省空不改变旧请求规范身份） |
| 业务 checker | `jc-business-checker/1` |
| 交付需求 | `SYNTHETIC_EXACT_PRINCIPAL_ANALYTICS_TWO_FILES/1` |
| 数学基线（J00） | LMM 工作分支 `codex/ulm-business-root-20260910` @ `88644bc`（核查基线 `0a5afdb` 之后新增 5 个 Lean 修复提交：`7af4e7e`、`9dcc498`、`17c1ea3`、`ef594d4`、`88644bc`）；`main` @ `23c5a31` 不代表本次 root |
| 数学 CI 范围 | Consolidated 模块在核查时构建成功；BusinessRoot Lean 在核查时失败（clipC/clipU 合取、Analytics rewrite/show 三处），修复已在本地分支推进、**kernelChecked 证据仍以 LMM GitHub CI 为准，本轮不取得** |

## 2. 已落地能力（J01–J07、J15、J16）

### 公共入口（全部免密钥，全部经唯一 ApplicationV4）

* `local_case_bundle(..., business_tasks=(...))` — 构造带 `business_tasks_v1` 的完整 bundle（J02）；
* `evaluate_harness_bundle(bundle, case_id=..., issue_queries=[])` — 一次请求恰一次 `Application.evaluate`，投影含 `business_results[]`（J03）；
* `local_read_run(run_ref)` — 读取密封 run（业务工件随审计包密封）；
* `business_delivery_documents(run_identity_ref=..., business_task_id=...)` — 从已核 run 只读导出两份受保护文件字节，**不求值**（J06）；
* `verify_business_delivery(run_identity_ref=..., business_task_id=..., selected_input_ref=..., artifacts={...})` — verify-only 双文件核验：恢复密封 I0/结果/见证 → 校验 selection 绑定 → 严格解析实际 bytes → 登记内容寻址交付记录，全程零求值（J06/J07）；
* `business_capabilities()` — 由已安装实现生成的能力清单（profile/requirement/文件名/checker 版本/证据范围），不读候选 manifest 自报（J01）。

### 模块与责任

| 模块 | 状态 | 责任 |
|---|---|---|
| `compiler_core/business_root/codec.py` | 新增（FORMAL_CORE） | 精确有理数字符串、20 维上下文、closed decode |
| `compiler_core/business_root/spec.py` | 新增 | 类型化 I0（spec/model）权威、无损 wire 往返 |
| `compiler_core/business_root/solver.py` | 新增（移植自 LMM reference @88644bc，MIT） | 编译 guard、栈机、自有枚举、max/clip |
| `compiler_core/business_root/checker.py` | 新增（同上移植） | 结构指称、位掩码全枚举、守恒行 C≥0、U≥0、C·U=0、C−U+recognized==principal |
| `compiler_core/business_root/analytics.py` | 新增（移植+生产扩展） | E[C]、E[U]、E[R]=E[C]−E[U]、阈值事件、共同信念区间、合法格；独立重算校验 |
| `compiler_core/business_root/delivery_checker.py` | 新增（同上移植） | 双文件封闭文法 verify-only，从未求值 |
| `compiler_core/business_root/wire.py` | 新增 | wire↔内部类型全转换 |
| `compiler_core/contracts.py` | 扩展 | 18 个 Business V5 合同类型入注册表（106→124）；`CaseRequestV4.business_tasks_v1`、`SemanticResultV4.business_results_v1` 为**省空扩展**：为空时整体不出现在规范字节中，旧请求/旧结果的规范摘要逐字节不变（测试钉扎） |
| `compiler_core/application.py` | 扩展 | `_business_stage_v1` 业务阶段：逐任务 求解→独立检查→分析→登记 I0/见证工件；business-only 注册路由（不造假规则/claim/签名，decision=hypothetical_result，review 门控，certificate=none）；混合请求业务行附加到终局结果，规范结果与业务结果互不冲销 |
| `compiler_core/local_runtime.py` | 扩展 | builder 接收 business_tasks；query-less bundle 放行；defeat policy 仅随查询生成 |
| `compiler_core/client.py` | 扩展 | 上述三个新公开方法 + 投影 |
| `compiler_core/rendering.py` | 扩展 | 只读业务投影（只引用密封行，不重算金额） |

### 保证分解（不合并为单一"已证明"）

每个 `BusinessTaskResultV5` 行独立携带：`completion`（exact/partial/inconsistent/failed/unsupported 五态，空Ω、预算未完、失败、不支持互不混装）、`checker_version`、`formal_evidence=CROSS_VALIDATED_GENERAL_ALGORITHM_PENDING_KERNEL`、`legal_basis_status=DECLARED_SYNTHETIC_BASIS_NOT_LEGAL_REVIEW`、`empirical_status=NO_REAL_DATA`、`open_obligations`、密封 `input_ref`/`witness_ref`。

## 3. 验收对照（shared/ACCEPTANCE_CASES.json 41 条中 JC 侧可执行部分）

| 用例 | 状态 | 证据 |
|---|---|---|
| BC01/BC02/BC03/BC10/BC16 | 通过 | `tests/contract/test_business_root.py`（15 例） |
| BC04/BC05/BC07/BC09/BC11/BC13/BC14/BC15/BC16/BC18/BC19/BC22/BC23/BC24/BC25/BC28/BC29/BC33/BC36 | 通过 | `tests/local/test_business_root_local.py`（28 例，真实本地 runtime 端到端） |
| BC12 | 通过 | `tests/packaging/test_business_wheel_install.py`（真实构建 wheel→仓外安装→断言 import 源→完整业务流 ACCEPTED） |
| BC26/BC27 | 部分开放 | JC 侧不改密封包、交付记录关联已验；原子终局事务与 DOCX 完整语义在 Harness（B08/H09-H11） |
| BC17/BC20/BC21/BC30/BC38/BC39/BC41 | 开放 | 对应 J10/J12/J13/J14/J17/M3（见 §5）；BC30 的规则包版本/元数据语义由既有 `rule_packs` 门控与 H03/H04 承接 |

冻结数值：主例 E[C]=880、E[U]=0、E[R]=880、P(C≥800)=3/5、区间[790,930]、eligible{850}、selected 850；超付例 E[C]=60、E[U]=80、E[R]=−20、P(C≥0)=1、P(R≥0)=3/5——与 `NUMERIC_FIXTURES.json` 及 LMM `root_witness.py` CROSS_CHECK_CONSTANTS 一致（SYNTHETIC_ONLY）。

## 4. 交付给 Harness 的最小物

1. 可安装 wheel：`python -m pip wheel . --no-build-isolation --no-deps`（业务实现已入 `pyproject.toml` packages；module-authority 登记 `compiler_core/business_root/` 为 FORMAL_CORE）；
2. 权威 schema：`schemas/jc-v5.schema.json`（新增 18 个 `$defs`）与 `mcp_manifest.json` 已重新生成；
3. 能力查询：`client.business_capabilities()`；
4. 请求/输出样例：`examples/harness/sample_local_business.py`（可运行，样例即契约）；
5. verify-only 接口：`verify_business_delivery`（§2 签名）；错误码：`SELECTION_REF_MISMATCH`、`BUSINESS_TASK_NOT_IN_RUN`、`BUSINESS_RUN_NOT_EXACT`、`SEALED_RESULT_FAILED_CHECK`、`SEALED_ANALYTICS_FAILED_CHECK`、`PRINCIPAL_FILE_READBACK`、`ANALYTICS_FILE_READBACK`、`EXACT_ARTIFACT_SET`、`ARTIFACT_BYTES_REQUIRED`，业务行内 `error_code/error_stage`（如 `FUTURE_PAYMENT`、`MODEL_WORLD_COVERAGE`、`PROBABILITY_SPACE`、`UNSUPPORTED_PROFILE`、`BUSINESS_MODEL_REQUIRED`、`BUSINESS_CHECKER_REJECT`）；
6. 本次 scope 与证据：§1/§3；数学 Lean 证据仅随 LMM CI 更新，固定实例定理不随参数化生产运行扩散（BC33）。

## 5. 未关闭清单（如实开放，不冒充完成）

| 任务 | 状态 | 依赖 |
|---|---|---|
| J08 二三路规则来源接入 | 既有 rule_packs/source_service 消费门控未动；route2/3 候选→作者结构→审核→编译的专用路径未建 | B09、H03/H04 |
| J09 业务增量语义 | 业务阶段每 run 全量重算（天然不复用旧 Analytics）；金额/权重变化的新 subject 登记与缓存 key 策略未建 | B11 |
| J10 结构论证扩展 | 未动（EXT03/05、ATMS、来源/布尔/概率三层支持） | H14 |
| J11 符号表示/关系约化/约束优化 | 未动（Exact/Inner/Outer、LP/凸/MILP） | B05/B10 |
| J12 概率/胜率/校准/因果 | 未动（有限 BN、消元、PAV/保形；无真实数据不签 calibrated） | B06/B10 |
| J13 全域证明责任 | 未动（民商刑行劳 requiredSlots 全域编译） | B03/B12 |
| J14 合法行动/有限序贯策略 | 未动（和解/补证/机制共用前序见证） | B06/B12 |
| J17 134 需求全量映射 | trace 表保留于方案包（trace/ORIGINAL_57_TO_ROUTE1.json 等），仓库侧 D001–D134 状态刷新待 M3 | B12 |
| generic 根 / DOCX 完整语义 / 真实法源与经验校准 | 开放 | LMM CI / H09 / J12 |

旧能力保持：local/1、CLI、MCP、增量、优先/程序全链回归通过（contract+packaging+local+formal_e2e 1100+ 用例；个别计时型用例在全量并发跑下偶发、隔离重跑通过，与本批无关，见交付报告）。
