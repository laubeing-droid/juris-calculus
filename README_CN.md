# juris-calculus v2.0.1

中国法符号化推理引擎，基于 addon 插件的跨法域扩展，MetaInfer 范式的工程体系。

## 架构

> Layer 6: 神经叶子节点（Kill Switch + 冷启动保护）
> Layer 5: Dung AAF 论证 + StepVerifier（EVM + 人/罪名/法条绑定）
> Layer 4: 对抗管线（Reasoner / Auditor / Verifier + 刑事复杂案件审计）
> Layer 3: MoE 规则路由（YAML 配置 14 领域）+ 刑事复杂案件路由
> Layer 2: Horn 子句不动点评估器（2117 条中国法规则）
> Layer 1: 信任标签（EpistemicStatus / DataOrigin / 红线短语）
> Layer 0: juris_blueprint.json（14 个 CN MoE 领域，5.7MB 知识图谱）
>   addons/
>     hk/               香港特别行政区（Cap 26，93+ Horn 规则）
>     us/               美国（53 个 Title 索引，266 法院，419 联邦术语）
>     federation/       普通法系配对比较引擎

## MetaInfer 工程范式

| 组件 | 说明 |
|------|------|
| configs/juris_phase_matrix.yaml | L0-L6 层 + P1-P11 构建阶段矩阵 |
| configs/juris_contracts.yaml | 结构化经验契约：三级引用链 + 伪代码 + 动态参数 |
| configs/agent_collaboration_protocol.yaml | 四角色物理隔离协作 |
| configs/knowledge_layers.yaml | 四层知识架构 |
| tools/phase_runner.py | 阶段门禁执行器，自动 step35 防假 PASS |
| tools/kg_audit_loop.py | 知识图谱双审计 |

## 许可证

MIT