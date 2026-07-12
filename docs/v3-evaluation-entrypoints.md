# JC v3 求值入口与迁移台账

## 判定规则

[有理有据的][高等] 所有正式案件求值迁入唯一application；法域模块和可选MCP只作adapter；三轨、DACL/SMT对照工具降为CLI/CI；底层evaluator与独立语义校验允许测试直调；重复执行体及无消费者包装删除。

[有理有据的][高等] 名称包含`evaluate`、shadow、DACL或SMT并不等于正式产品入口。无差别迁移会把测试支撑误升格为产品路径，因此本台账同时记录正向入口和负向边界。

## 正式或产品可达入口

[计算生成的][高等] 下表来自全仓Python AST构造器扫描、符号反向引用和测试/文档消费者检索；每行均记录输入、规则、状态、输出、消费者和唯一处置。

| 文件/符号 | 输入、规则、状态、输出 | 当前消费者 | v3处置 |
|---|---|---|---|
| `compiler_core/evaluator.py::FixpointEvaluator` | 已解析`LegalRule[]`+配置；推进`IRState`并返回`IRState`，内部有规则索引、validator和audit log | 所有正式入口、harness及语义测试 | 仅application内部stage及低层差分测试可直调；产品代码禁止自行构造 |
| `compiler_core/stratified_evaluator.py::StratifiedEvaluator` | 规则路径+`IRState`；自行加载YAML并执行Horn→attack→grounded→trust；输出`LegalClaim[]` | MCP、multi-model工具、分层测试 | 必要stage迁入application；删除公开求值入口 |
| `mcp_server.py::_juris_evaluate_core/_sync` | 已删除 | 无 | 旧fixture测试改为断言wrapper不存在 |
| `mcp_server.py::juris_query(evaluate_facts/analyze_strategy)` | evaluate只接受完整`CaseRequest`并调用审计application；strategy只接受run ID | legacy工具名、manifest tests | 独立执行体已删除；旧工具名在Phase 7删除 |
| `mcp_server.py::stratified_evaluate` | 只接受完整`CaseRequest`并调用同一审计application | manifest和dispatch测试 | 独立分层执行体已删除；旧工具名在Phase 7合并 |
| `compiler_core/post_freeze_surface.py::certified_litigation_report` | 不再求值；明确返回`AUDITED_RUN_REQUIRED` | MCP旧surface tests | Phase 7随旧surface删除 |
| `mcp_server.py::_lazy_init/_tool_trirail_collide` | scenario/facts；惰性持有`TriRailCollider`；输出三轨envelope | MCP trirail工具及stdio/dispatch tests | 删除MCP；三轨保留CLI/CI harness |
| `compiler_core/automated_pipeline.py::run_automated_pipeline` | 已删除 | 无 | queue DTO与重复Horn/AAF/certificate一并删除 |
| `compiler_core/litigation_renderer.py::evaluate` | 已删除 | 无 | Phase 5由`compiler_core/rendering.py`的CanonicalResult/run ID renderer替换 |
| `pipeline/pipeline.py::ENGINE` | 已删除 | 无 | 导入时不再加载规则或建立全局案件状态 |
| `pipeline/pipeline.py::process_case/run_single/run_batch` | 只摄取并输出`CANDIDATE_ONLY`事实，不生成claim | 本文件single/batch CLI、LLM fallback摄取 | 正式求值仅由`jc evaluate`接收已验证CaseRequest |
| `compiler_core/adapter_base.py::load_evaluator` | 已删除 | 无 | adapter只保留法域映射、护栏和外围元数据 |
| `addons/cn/adapter.py::run_collision/load_evaluator` | CN配置→PRC collision或裸evaluator；输出ProofTree/evaluator | registry、多法域编排、addon API | 规则包解析保留；正式求值调application；collision降CLI/CI |
| `addons/hk/adapter.py::load_evaluator` | HK规则/override/L0→裸evaluator | federation、多法域编排 | 改产出pack/request |
| `addons/us/adapter.py::load_evaluator` | US规则/override/L0→裸evaluator | federation、多法域编排 | 改产出pack/request |
| `compiler_core/multi_jurisdiction_orchestrator.py::evaluate` | 已删除 | 无 | 跨法域正式分析必须组合多个canonical run |
| `addons/federation/common_law.py::FederatedReasoner.run` | 已删除 | 无 | 无消费者旧包装不保留 |
| `compiler_core/prc_collision_engine.py::PRCCollisionEngine` | CBL/meta/SPC/CN配置；长期持有SPC/CN evaluator；输出ProofTree | CN adapter、TriRail、collision tests | 三轨外围CLI/CI；SPC/CN正式轨改消费application |
| `tools/run_trirail_matrix.py::TriRailCollider` | HK/US规则+PRC engine；三个隔离state；输出三轨审计dict | 自身CLI、runtime tests | 保留CLI/CI，禁止作为正式结论入口 |
| `compiler_core/parallax_inference.py::ParallaxInference` | 已删除 | 无 | 与矩阵harness重复 |
| `compiler_core/multi_solver_router.py::route_and_solve` | 已删除 | 无 | SMT低层能力保留 |

## 开发harness、CLI/CI与批处理

[计算生成的][高等] 下表入口可以保留为开发、差分、性能或批量工具，但不得生成v3正式CanonicalResult，最终均应循环调用application或明确保持低层对照身份。

| 文件/符号 | 当前形态与消费者 | v3处置 |
|---|---|---|
| `compiler_core/spec_shadow_harness.py::_run_horn_shadow` | 内建fixture→临时evaluator→JC/spec payload；由spec-shadow工具和测试消费 | 允许低层直调，属于规范差分支撑 |
| `compiler_core/shadow_state.py` | 不运行evaluator，只隔离candidate或比较claim IDs | CLI/CI候选隔离支撑 |
| `compiler_core/batch_processor.py::BatchProcessor` | 已删除 | 私有trace测试已迁到规范内容ID |
| `tools/dacl_graph_runner.py::main` | YAML→DACL图；可选模式另建evaluator验证 | CLI/CI |
| `tools/smt_evaluator_compare.py::compare` | YAML+facts→Horn与SMT并行→差异dict；有CLI和测试 | CLI/CI |
| `tools/calibrate_weights.py` | 每组权重构造evaluator并评分 | CLI/CI |
| `tools/e2e_evidence_collector.py` | 固定规则/状态→临时evaluator→证据报告 | CLI/CI |
| `tools/multi_model_comparison.py` | 同一CN规则跑Horn与Stratified并比较耗时/claims | CLI/CI |
| `tools/perf_baseline.py` | 固定CaseRequest→正式审计application→预算/基线性能报告 | CLI/CI |
| `tools/relevance_sensitivity_runner.py` | fixture rules/facts→claim ID集合 | CLI/CI |
| `pipeline/pipeline.py::run_batch` | 枚举案卷并调用process_case | 摄取留CLI；求值迁application |

## DACL、SMT与底层语义支撑

| 文件/符号 | 当前形态 | v3处置 |
|---|---|---|
| `compiler_core/dacl_graph.py::build_dacl_graph` | rules/claims/facts/traces→`DACLGraph`，不运行evaluator | 低层可复用；正式案件图必须改从AuditEvent构建 |
| `compiler_core/smt_sidecar.py::SMTSidecar.check` | 结构约束→Z3或Python fallback→SAT/UNSAT/UNKNOWN | application内部或测试可直调；不能独立晋升案件结论 |
| `compiler_core/validity_state_machine.py::smt_backed_validate` | `ValidityPath`→SMT→状态dict；无消费者 | 删除，或有真实application消费者时才迁入 |
| `compiler_core/grounded_smt_verifier.py::GroundedSMTChecker` | claims/attacks/labels→有限SMT校验；不调用evaluator | 保留为grounded独立校验支撑 |
| `compiler_core/universal_grounded_smt.py` | 有限规模Z3检查；无调用者 | 研究/CI；不得包装成Lean证明或案件结论 |
| evaluator、DDL、nonmonotone、rule admission、v3 semantic baseline测试 | 直接构造低层evaluator以冻结正式语义 | 允许低层直调 |
| stratified、旧renderer、spec-shadow测试 | 锁定迁移前行为 | 保留为差分fixture，不保留旧产品API |
| trirail、DACL、SMT测试 | 消费低层对象 | 允许低层直调 |

## 闭合结论

- [计算生成的][高等] 正式产品路径中的全部直接`FixpointEvaluator`构造点已有处置；台账另补入MCP→TriRail、CN adapter→PRC engine、BatchProcessor注入及多法域/federation→adapter factory等间接持有点。
- [计算生成的][高等] 无代码调用方的独立入口已检查测试和文档消费者，没有仅凭单次`rg`判删。
- [有理有据的][高等] 迁移顺序固定为：语义fixture→application→逐入口adapter/differential→审计/graph完成后删除重复执行体。
- [有理有据的][高等] 本台账不改变Horn、attack、exception、permission、priority、checker或fail-closed语义，只改变调用边界、入口归属和输出分层。
- [计算生成的][高等] `tests/unit/test_v3_entrypoint_boundary.py`现以AST固定唯一application/bundle入口，并禁止非allowlist生产文件直接构造求值器。

## [我违规之处]

无。
