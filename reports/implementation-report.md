# 03 卡实现阶段交付报告（juris-calculus）

- run-id: `full-20260919-015613-108316` ｜ 树: `.local/checkouts/full-20260919-015613-108316/juris-calculus`
- 基线: 412c69c（集成检出）+ 带入探针修复 3cda281 ｜ 冻结: P 5a6aa99 contracts v1.0.0
- 数学仓只读未触碰；向量库未引入；mock 仅限独立单测（computation_surface 的注入 reader 为单测层 seam，集成态断言具名 not_compiled）。

## 步骤完成度

| 步骤 | 状态 | 提交 | 证据 |
|---|---|---|---|
| 1 工时精分恢复 | DONE | 5be9544 | `.local/pricing-baseline/c2acea3…/`（tag 两文件+origin.json）；六项在 tag 实读确认 |
| 2 生产定价核心 | DONE | 4ce33b4 | `compiler_core/pricing.py::estimate_default`；冻结样例 20.3125h/67031/93431/28.3 精确；批量 Σ=98.59±0.01 |
| 3 校准估计器 | DONE | 4ce33b4 | `fit_alpha`：上中位数成对斜率、负斜率 abs 门、[0.05,2.0] 夹紧、<3 样本候选+α=1 insufficient_data、未归因排除具名原因、特征定义隔离；八条 PRICE 断言全绿；无 0.92/δ，guaranteeLevel/delta 恒 null |
| 4 五公开入口 | DONE | 939f04e | `JCClient.calibrate/price/recompute_price/calculate_deadlines/read_argument_graph`；DecimalText 映射落 `contracts.py`（canonical decimal str，codec 在 pricing）；真实 local store 收据内容寻址、复算字节稳定 |
| 5 期限算法 | DONE | b0081ca | `compiler_core/deadlines.py`（母本日历骨架+H 树 StatutoryDeadlineService 提取）；十分支持法分支表；`configs/deadline_rules_cn.v1.yaml`（14 规则，刑拘链分阶段无 37 常数）；`DEADLINE.no_2027_guess`：跨界 dueDate=null+缺口步骤、未发布日历 typed 错误 |
| 4a issue-human-residual/1 | DONE | 939f04e | `JCClient.price_human_residual`（jc.price）+ recompute；零历史可报价；AI 完成→0 人时但专业核验独立成项不删除；共享单计；workItemId 重复拒绝；费率只改报价；整数分 half-up；初值 0.5/0.25/0.5/4h、10000/30000/0 分（同步 P config pricing.humanResidual） |
| 4b 知识运行时 | DONE* | 263269a | 训练切分修复（random/group/time 真实生效、不支持模式拒绝）；`compiler_core/prediction.py` 纯 Python L2 逻辑回归真实训练+泄漏纪律；`tools/train_and_evaluate.py` 薄入口（子进程实跑）；`JCClient.predict_outcome`（无 checkpoint=model_not_available，概率随输入变化）、`deviation_rank`/`terminal_state_stats`（只经注入 case.* 公共读面 seam，未接=具名 not_compiled/dataset_version_not_found）、`admit_verified_rule_pack`（verify_pack_manifest/本地包校验；机器决定 ref 逐字记录；同载荷重放同收据；版本/载荷冲突=revision_conflict） |

*4b 保留项见"对 01 的集成需求"。

## 测试（本次全绿）

| 套件 | 数 | 内容 |
|---|---|---|
| tests/unit/test_pricing_v1.py | 15 | 冻结样例+八条 PRICE 断言+DecimalText 往返 |
| tests/unit/test_deadlines_v1.py | 16 | 日历原语/分支表/刑拘链无 37/保全上限/续保不延长/中止中断/2027 缺口 |
| tests/unit/test_computation_surface.py | 17 | 五入口+human-residual+期限 client 面+rank/stats reader |
| tests/integration/test_knowledge_runtime.py | 11 | 准入落盘/重放/冲突、切分诚实、子进程真实训练（acc≥0.8、brier≤0.2）、checkpoint 消费、增量等价+具名回退 |
| 既有回归 | 41+ | rule_admission/training_export/business_root/business_wheel_install/local_runtime 全绿 |

## 公开入口清单（provider=jc 对冻结 12 方法的映射）

| 冻结方法 | JCClient 实现 | 状态 |
|---|---|---|
| calibrate.fit | `calibrate` | DONE |
| pricing.estimate | `price` | DONE |
| pricing.recompute / jc.recompute_price | `recompute_price`（两模型收据） | DONE |
| deadlines.calculate | `calculate_deadlines` | DONE |
| arguments.read | `read_argument_graph` | DONE（封存读取，不复算） |
| jc.evaluate_harness_bundle | 既有 `evaluate_harness_bundle`（keyword-only 保留） | 既有 DONE |
| jc.price | `price_human_residual` | DONE |
| jc.admit_verified_rule_pack | `admit_verified_rule_pack` | DONE |
| jc.deviation_rank | `deviation_rank`（reader seam；未接=not_compiled） | DONE（case 接线待 08） |
| jc.terminal_state_stats | `terminal_state_stats`（reader seam） | DONE（case 接线待 08） |
| jc.predict_outcome | `predict_outcome` | DONE（训练数据到位前 model_not_available 为合法态） |
| jc.business_capabilities | 既有 | 既有 DONE |

wheel：`juris_calculus-5.0.1-py3-none-any.whl`（`.local/dist/`），仓外干净 venv 验证：冻结样例精确、deadline 注册表 14 规则随 wheel 可读、prediction 模块可导入。

## 对 01 集成的需求

1. deadlines.calculate 的 `eventRef`/日历 overrides 由 02 登记事件 artifact（kind=procedure-event，scope=case）后 JC 从 store 解析；桥侧需在调用前完成注册。
2. deviation_rank/terminal_state_stats 需 01 注入 case.* 公共读面 reader（结构化结构 DTO/公共统计 DTO）；未接前具名状态即为当前真实行为。
3. predict_outcome 模型根经 `JC_PREDICTION_MODEL_ROOT` 或请求 `modelRoot` 提供；checkpoint 由 train_and_evaluate 产出（特征契约=featureOrder）。
4. admit 的 `admittedRoot` 由桥指定（默认包目录兄弟目录）；准入后重载 client 生效，不热切换。

## BLOCKED / 保留项

1. **MCP manifest 扩展（§4b.7 三方法）未在本轮单方面执行**：`mcp_manifest.json` 是字节冻结发布物，扩展牵动 schema 闭合计数(124)/vectors 向量库/tool_spec_digest 收据链/provenance attestor 钉定，须与 01 协同一次性再生成；三方法已全部在 JCClient 公开面可用。
2. deviation_rank/terminal_state_stats 的真实 case 数据路径依赖 08 公共读面（M3/M5 里程碑）；当前具名状态为冻结允许的合法行为。
3. 真实案料训练/留出评测属真实语料作业，另行报告（卡 §5）；本轮全部用合成验收材料。
