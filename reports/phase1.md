# 03 卡第一阶段只读盘点（phase 1，0b 冻结前）

- run-id: `full-20260919-015613-108316`
- 树: `.local/checkouts/full-20260919-015613-108316/juris-calculus`（HEAD `412c69c`，branch `jusbench/full-20260919-015613-108316-jc`，已带入集成检出未提交修改 `tools/run_installed_c06_probe.py`，理由见 `contract-contribution.md` 附录）
- 性质: 纯只读盘点 + 合同贡献；未做业务实现，未跑 Lean/数学构建。合同细节见同目录 `contract-contribution.md/.json`（含源码行号），本文不重复。

## A. 建树与基线（任务 A/B 结果）

| 项 | 结果 |
|---|---|
| worktree 建树 | 自集成检出 HEAD 建成，472 文件检出成功；分支 `jusbench/full-20260919-015613-108316-jc` |
| 未提交修改带入 | `git apply` 干净应用（7363 字节 patch），J 树 status 与源检出一致（仅该文件 M） |
| 412c69c 对象 | 在 J 树对象库中存在（= HEAD） |
| tag c2acea3 | commit 对象存在；`v1.0.3^{commit}` 精确解析至 `c2acea3589d14f25f5b8285117ce01276e87860b` |
| tag 两文件 | `legalos_services/legalos_pricing.py`、`legalos_services/peripheral_models.py` 在 tag 树中均在；当前工作树无 `legalos_services/`（母本判断成立） |

## B. §3.3.1 六项恢复范围 vs 现有 compiler_core

现行树 **六项全无**（无 BillingTier/无多因子计价/无批量衰减/无 Theil–Sen/无历史特征计数/无对照测试）；tag `c2acea3` 中 **六项全部实读确认存在**，步骤 1 提取计划可行：

| 恢复项 | tag 内位置（实读确认） | 现行树 |
|---|---|---|
| `BillingTier` 常数 | `legalos_pricing.py:37-47`（PARTNER 1.8 / SENIOR_ASSOCIATE 1.3 / ASSOCIATE 1.0 / PARALEGAL 0.5） | 无 |
| 单件多因子 | `LegalOSPricingEngine.predict_hours`（ne×α×地点×阶段+overhead；ALPHA=1.0、地点/阶段/差旅系数 getter） | 无 |
| 批量衰减历史行为 | `batch_decay_cost`（`legalos_pricing.py:183` 起；LAMBDA=0.65 指数、SIMILARITY_THRESHOLD=0.85） | 无 |
| Theil–Sen 旧分支 | `peripheral_models.py` `CoveragePricingEngine.calibrate_theilsen`（中位数斜率法、<3 样本分支、**历史默认 0.92 在此处**——按母本裁定不采纳入新默认） | 无 |
| 特征计数历史定义 | `PricingCase.effective_nodes/location/stage/batch_position`、`compute_graph_similarity/find_similar_cases`、`CoveragePricingEngine.calculate(D,T,H)`（D/T/H 语义在此） | 无 |
| 对照测试 | tag 树内（提取时随两文件与后续对照测试一并落地 `.local/pricing-baseline/`；对照测试按母本在新增单测中重建，不恢复旧平台） | 无 |

`h_policy="unwired-v1"` 纪律：历史 H 向量只作字段/展示保留，生产默认不乘入（现行树无任何可冲突实现，零风险落点）。

## C. §3.3.3 校准估计器现状

- 现行树 **无任何校准/α 拟合代码**。最接近的现存模式：`compiler_core/incremental.py:282-313` `EmpiricalEstimateV5/attach_empirical_v5`——无实证模型必须记 `absent_reason`（诚实缺省），新估计器落点应沿用该纪律；`EmpiricalResultV5.calibration_status` 枚举属求解器实证域，与工时校准无关。
- tag 中旧估计器（`calibrate` 上中位数 `med()`、`calibrate_theilsen`、`PricingConfig(base_fee/taint_hour/hard_hour)`、ra 的 0.05 下夹紧）已在 tag 实读确认——八条 PRICE 断言所需的"负斜率 abs 门、上中位数、夹紧 [0.05,2.0]、hard_hour 分支、<3 样本分支"全部有历史对照物；无来源的 0.92 与 δ 不引入（δ 在母本 §0b.5 不变量中恒 null，现行树无 δ 字段，一致）。
- 结论：估计器为**新写+历史对照**，不是"已有实现迁移"；版本四元组（feature_definition/estimator/model/factor_set）为全新登记面。

## D. §3.3.5 期限算法现状

- 现行 JC 树 **无法定期限/日历代码**：无 `CalendarSnapshot`、无 `calendar_coverage_missing`、无 `calculate_deadlines`（application/contracts 中 "deadline" 命中均为 `solver_deadline_ms` 资源限，与法定期限无关）。
- 提取来源 = Harness `providers.py::StatutoryDeadlineService`（**H 仓文件，本阶段未读**——属 02 卡仓，步骤 5 实施时从 H 树只读提取；此为跨仓输入依赖，需 H 树就绪）。
- 母本 §3.3.5 已给出日历代码骨架与十分支表（刑拘链不写固定 37/保全口径/法院指定日不推算等）；2027 日历为空占位、不得装 released=true；`DEADLINE.no_2027_guess` 无既有实现可依赖，全新。

## E. §4a issue-human-residual/1 现状

**零基础，全新域**（详见 contract-contribution §5）：无 pricing 模块、无任何报价/工时 DTO。卡文"本仓扩展 pricing 现有公开方法/DTO"的实读含义 = 在本轮新建的 pricing 域上扩展；旧 Z-v1-default 与全部冻结样例自步骤 1-2 起就按独立版本并存，天然满足"旧收据不改写"。可复用原语：`V4Contract` 基类、`DigestV4/ContentRefV4`、canonical decimal str 惯例；`DecimalText`（§0b 名）需在冻结中登记映射。

## F. §4b 数学成果/神经/概率接入现状

| 项 | 现状 |
|---|---|
| 217 接入来源 | 数学仓 spec 7 文件+BENCHMARKS_20(15中国/5美国)+BENCHMARK_DEMANDS_134_ORIGINAL 全部可读、计数核对通过（BINDINGS=217；详见 contract-contribution §7）。**只读未触碰** |
| 217 接入落点 | 尚无 acceptance-scope 行（01 平台，03 回填 provider 行）；math_export 现有 witness/pins/checker_gateway/consistency/fingerprint/subject 六模块为 JC-01—03 与数学 CI 证据链的既有基座 |
| 规则 YAML 消费 | 既有：`configs/packs/{cn-official, hk-legacy-corpus, us-federal-legacy-corpus, us-l0-adapter-legacy-corpus}`、`tools/build_rule_pack_manifests.py`、`verify_pack_manifest`、`rule_admission.py`、`rule_lookup/rule_router/rule_governance`。缺：机器决定适配（actor=machine）与 `admit_verified_rule_pack` 薄入口 |
| 神经训练 | `compiler_core/training.py` 仅有 `export_rules_as_jsonl`（含已实读确认的缺陷：`rng.shuffle` 无条件执行、`split_mode` 不生效，training.py:79-80 vs :103）；`tools/train_and_evaluate.py` 不存在（【新增】）；`compiler_core/backends/` 仅空 `__init__.py`——无任何已训练模型/向量服务（符合边界：向量归 08） |
| 概率预测 | `business_root/analytics.py`：给定权重的精确场景分析（E[C]/E[U]/E[R]、event_probability、公共信任区间）——卡文判断成立：**是给定模型权重的计算，不是训练出的现实裁判概率**；P01—P13/E01 训练/校准/评测代码不存在 |
| 实测上线 | 无（依赖上一行） |
| 增量求解 | 已真实存在且 fail-closed（详见 contract-contribution §6）；无全局开关，走 `incremental_parent` 逐请求路径 |
| 生产接线 | `predict_outcome/deviation_rank/terminal_state_stats` 不存在；MCP manifest 现 4 工具 |

## G. 测试在位情况

| 测试 | 状态 | 卡定位 |
|---|---|---|
| `tests/unit/test_rule_admission.py` | 在位 | 【既有】 |
| `tests/unit/test_training_export.py` | 在位 | 【既有】 |
| `tests/contract/test_business_root.py` | 在位 | 【既有】 |
| `tests/packaging/test_business_wheel_install.py` | 在位 | 【既有】 |
| `tests/unit/test_pricing_v1.py` | **缺** | 【新增】步骤 1-5 |
| `tests/unit/test_deadlines_v1.py` | **缺** | 【新增】步骤 1-5 |
| `tests/integration/test_knowledge_runtime.py` | **缺** | 【新增】§4b 全链 |
| `tests/contract/test_c06_witness_guard.py`、`test_harness_contract.py` 等 witness 面 | 在位 | JC-01/02 复跑基座；证据 run 34797682659/35124268367 身份保留待步骤 6 |

打包/入口：`pyproject.toml` 显式 packages 清单（见 contract-contribution §3）；console scripts `jc`/`jc-formal` 在位；wheel 步骤需同步新增资源进 `[tool.setuptools.package-data]`。

## H. 风险与依赖（供总控）

1. 期限算法提取依赖 H 树 `providers.py`（跨仓只读输入；02 建树进度影响 03 步骤 5，但日历骨架+十分支表可先按母本独立实现）。
2. `DecimalText` 名称映射需在 0b 冻结明确（现有代码为 canonical decimal str）。
3. 无 BLOCKED 项：本阶段全部任务（A-D）完成；业务实现等 0b 冻结+总控通知。
