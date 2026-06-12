# juris-calculus v2.0.1

中国法符号化推理引擎，基于 addon 插件的跨法域扩展。

## 架构

`
Layer 6: 神经叶子节点（Kill Switch + 冷启动保护）
Layer 5: Dung AAF 论证 + StepVerifier（EVM + 人/罪名/法条绑定验证）
Layer 4: 对抗管线（Reasoner / Auditor / Verifier）
Layer 3: MoE 规则路由（YAML 配置 14 领域）+ 刑事复杂案件路由
Layer 2: Horn 子句不动点评估器（2117 条中国法规则）
Layer 1: 信任标签（EpistemicStatus / DataOrigin / 红线短语）
Layer 0: juris_blueprint.json（14 个 CN MoE 领域，5.7MB 知识图谱）

addons/
  hk/               香港特别行政区（Cap 26，93+ Horn 规则）
  us/               美国（53 个 Title 索引，266 法院，419 联邦术语）
  federation/       普通法系配对比较引擎
`

## 工程范式

| 组件 | 说明 |
|------|------|
| configs/juris_phase_matrix.yaml | L0-L6 层 + P1-P11 构建阶段物理依赖矩阵 |
| configs/juris_contracts.yaml | 结构化经验契约：三级引用链 + 伪代码 + 动态参数 |
| configs/agent_collaboration_protocol.yaml | 四角色物理隔离协作协议 |
| configs/knowledge_layers.yaml | 四层知识架构（L0 通用 → L3 部署） |
| tools/phase_runner.py | 阶段门禁执行器，自动步骤 3.5 抽查防假 PASS |
| tools/kg_audit_loop.py | 知识图谱双审计（正确性 + 完备性） |

## 防退化机制

| 机制 | 说明 |
|------|------|
| 测试脚本不可变 | Agent 改代码不改测试 |
| 逐阶段门禁 | 阶段 FAIL 阻止进入下一阶段 |
| L0 import 源验证 | 确认模块来自本地目录非外部泄漏 |
| 步骤 3.5 抽查 | 随机重跑已 PASS 命令，比对 stdout |
| 跨阶段回归 | P3+ 重跑前序全部阶段 |
| E2E 证据链 | 评估 trace + 耗时探针 + 契约审计报告 |
| 反假推理 | trust_label 来自评估器实际运行 |

## MCP 工具（15 个）

| 工具 | 说明 |
|------|------|
| trirail_collide | 香港/美国/中国大陆三轨碰撞检测 |
| route_state | 美国州级法域路由 |
| get_citation | 法条引用查询 |
| stratified_evaluate | 四阶段 Horn + AAF 管线 |
| search_rules | 关键词搜索 2117 条中国法规则 |
| evaluate_facts | 事实 → claims + confidence + trust |
| calculate_damages | 分项赔偿计算（LPR/定金/违约金/时效） |
| analyze_strategy | 对抗管线 SWOT 策略分析 |
| extract_elements | 从事实提取 Horn 规则要件 |

## 许可证

MIT