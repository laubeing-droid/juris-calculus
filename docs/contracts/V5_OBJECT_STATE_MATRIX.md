# V5 对象与状态矩阵

权威来源：`tests/fixtures/v4_contract/object-state-matrix.json`（fixture id `jc/v4-object-state-matrix/1.0`，V5 沿用同一 fixture 文件并在 `object_types` 中新增 `layer=v5` 条目）。Python 镜像：`compiler_core/contracts.py::_STATE_MATRIX`、`validate_state_matrix`。运行时注册表：`V4_TYPE_REGISTRY`（5.0.1 整改后 105 个类型条目；SPLIT-LOCAL-3 起新增 `LocalRecordV4`；jc-business-root/1 第一批（2026-09-11）新增 18 个 `Business*` 条目，共 124 个类型条目，其中对象 118、枚举 5、字符串模式 1）。

## 版本决定

- 公共协议：`jc/5.0`（`SCHEMA_VERSION_V5`）。正式引擎版本正则锁定 major 5；`jc/4.0` 输入与 4.x 引擎版本在准入处被拒绝，不做宽松读取。
- 引擎版本：`5.0.1`（`compiler_core/version.py` 是唯一版本源）。
- 生成出版物：`schemas/jc-v5.schema.json`、`mcp_manifest.json` 由 `compiler_core.mcp` 的确定性 emitter 产出，字节级校验。

## 六轴状态空间（继承 V4，不收敛为一个“大成功”）

| 轴 | 值 |
|---|---|
| execution | completed, admission_blocked, interrupted, unsupported, resource_exhausted, cancelled, engine_error |
| decision | accepted_formal_result, hypothetical_result, review_only_result, missing_required_fact, conflict_certificate, blocked, unknown, engine_error |
| review | not_required, required, pending, approved, rejected |
| completeness | complete, partial, truncated, interrupted |
| certificate | none, formal_verified, conflict_verified |
| transport | success, error |

笛卡尔组合 6720；可达终态组合 124（由 fixture `decision_constraints` 与 `tests/differential/test_self_contained_v4.py` 自动校验）。5.0.1 起 `accepted_formal_result` 允许 `completeness=partial` 且证书集为 `{formal_verified, none}`：当请求携带的 V5 查询存在未闭合的语义映射（如未登记策略的优先关系）或求解覆盖未完成时，结果降级为 partial 且**不签发证书**（证书门要求完整无污染的正式执行）。

## V5 强制不变量

- 输入畸形、越权或资源准入失败 → admission/transport error，不带正式证书；内部不变量破坏 → engine_error。
- 材料合法但缺必要事实 → missing_required_fact；需要人判断 → review_only_result，不是系统崩溃。
- 求解超时/预算耗尽 → unknown + incomplete，不签发正式结论证书；保留已验证部分结果与未完成义务（`EvalOutcomeV5.kind=incomplete` 必须携带非空 `open_obligations`）。
- NoExtension ≠ conflict_certificate：冲突证书必须有独立验证的冲突见证。
- `EvalOutcomeV5` 三种求解结果互斥且不可互替：`no_extension`（必须携带空族证据）、`extensions`（非空族 + exact 覆盖）、`incomplete`（discovered_only + 非空义务）。
- 假设驱动推导保持 hypothetical；假设依赖（`PremiseTokenV5.dependencies`）不可通过人工确认消除。
- `AssuranceEnvelopeV5.implementation=kernelVerified` 必须同时提供非空 `tcb_refs`；默认只授予 `crossCheckOnly`。

## V5 新对象组（layer=v5）

| 组 | 类型 |
|---|---|
| 请求/情景/查询 | ScenarioKeyV5, QueryRequestV5 |
| 前提 | PremiseTokenV5 |
| 结构化论证与攻击 | SupportHyperedgeV5, StructuredArgumentV5, TypedAttackV5, DefeatPolicyV5, DefeatEdgeV5 |
| 语义与分支 | ExtensionFamilyV5, EvalOutcomeV5, SemanticBranchV5 |
| 查询 | QueryWitnessV5, QueryResultV5 |
| 程序 | ProcedureAuthorityV5, ProcedureResultV5 |
| 组合/精确 | ExactQuantityV5, ExactExpressionV5, CompositionCandidateV5, CompositionPolicyV5, CompositionChoiceV5 |
| 保证 | NotApplicableEvidenceV5, AssuranceEnvelopeV5 |
| 增量/经验 | HornDeltaV5, EmpiricalResultV5 |
| 查询侧公开输入（5.0.1） | ClaimRefutationV5, QueryGateRequestV5 |
| 程序公开输入（5.0.1） | BurdenRuleOutcomeWireV5, ProceduralInputV5 |
| 增量父引用（5.0.1） | IncrementalParentV5 |
| 业务条件计算（jc-business-root/1，2026-09-11） | BusinessContextV1, BusinessFormulaV1, BusinessAtomStateV1, BusinessSourceSpanV1, BusinessPaymentV1, BusinessSpecV1, BusinessAtomPairV1, BusinessWorldV1, BusinessWorldWeightV1, BusinessModelInputsV1, BusinessTaskInputV1, BusinessTaskV1, BusinessCompletionV5, BusinessOutcomeRowV5, BusinessAnalyticsV5, BusinessTaskResultV5, BusinessDeliveryBindingV5, BusinessDeliveryVerificationV5 |

每一组到 ULM 证明模块的映射见 `proofs/runtime-obligation-map.json`；该映射是工程义务登记，不是运行时已被 Lean 证明的声明。
