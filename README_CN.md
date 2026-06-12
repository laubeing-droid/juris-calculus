# juris-calculus v2.0.1

中国法符号化推理引擎，基于 addon 插件的跨法域扩展。

## 架构

`
Layer 6: 神经叶子节点（Kill Switch + 冷启动）
Layer 5: Dung AAF + StepVerifier（符号 EVM + 绑定验证）
Layer 4: 对抗管线（Reasoner / Auditor / Verifier）
Layer 3: MoE 规则路由（YAML 14 领域）+ 刑事复杂案件（S1-S4）
Layer 2: Horn 不动点评估器（2117 条中国法规则）
Layer 1: 信任标签（EpistemicStatus / DataOrigin）
Layer 0: juris_blueprint.json（14 CN MoE 领域，5.7MB）

addons/          hk/ (Cap 26, 93+)    us/ (53 titles, 266 courts)    federation/
`

## 工程范式

P1-P11 构建阶段矩阵，物理依赖不可重排。阶段门禁 + 步骤 3.5 抽查防假 PASS。
知识图谱双审计（正确性 + 完备性），蓝图完备度 100%。

## 防退化机制（7 条）

测试脚本不可变、逐阶段门禁、L0 import 源验证、步骤 3.5 抽查、跨阶段回归、E2E 证据链、反假推理。

## MCP 工具（18 个）

符号推理 15 个：trirail_collide、route_state、get_citation、stratified_evaluate、search_rules、evaluate_facts、calculate_damages、analyze_strategy、extract_elements 等。

LLM 增强 3 个（隐私门禁）：evaluate_facts_llm、align_concepts_llm、generate_nlni_llm。
调用前自动脱敏，结果标记 TAINTED，零 API key 零网络调用。

## 隐私保障

核心引擎纯符号推理，LLM 集成完全可选。无脱敏不传数据，所有 LLM 结果携带 TAINTED 信任标签。

## 许可证

MIT