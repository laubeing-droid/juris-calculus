# juris-calculus Changelog

## v2.0.0 (2026-06-14)

### DDL 模态引擎

- 2,117 条 zh_CN 规则全量 `norm_modality` 标注（825 LLM + 633 关键词 + 18 正文 + 641 fallback）
- evaluator `_apply_rule()` 模态门控：OBLIGATION → Negative Spec，PROHIBITION → 阻断结论链
- `ddl_preclassifier.py`：关键词 + 结构 + 概念 + 命名空间 + LLM 确认五层分类
- `ddl_confirmed_modalities.json`：825 条 LLM 批量确认固化查找表
- 2,117/2,117 高置信度，0 UNKNOWN

### L1-L2 护栏模块

- `evidence_chain_validator.py`：L1 证据链推理前校验
- `de_jure_auditor.py`：L2 法定审计推理后校验
- `cross_jurisdiction_compare.py`：L2 跨法域比较引擎
- `multi_solver_router.py`：L2 多求解器路由（CN/CBL/SPC）
- `validity_state_machine.py`：L2 有效性状态机（118 行）
- `invariance_metrics.py`：L2 不变性度量
- `defeasible_priority.py`：L2 可废止优先级
- `proleg_translator.py`：L2 PROLEG→Horn 翻译器
- `entity_anonymizer.py`：L2 实体匿名化器
- `kg_recall.py`：L2 知识图谱召回
- L1-L2 全部接入 `pipeline/pipeline.py` 端到端管线

### 神经网络守卫层

- `neural/contracts/`：feature_schema、model_card_schema、output_schema、promotion_policy
- `neural/registry/model_registry.yaml`：模型注册表（SHADOW_ONLY）
- `neural_leaf.py`：神经叶子节点（201 行）
- `neural_yaml_sync.py`：YAML 同步（135 行）
- `step_verifier.py`：步骤验证器（121 行）
- 6/6 neural guardrail 测试通过

### LLM 批处理自动化

- `tools/llm_batch_acceptor.py`：批量验收（支持嵌套 R1 包格式）
- `tools/llm_batch_orchestrator.py`：批量编排
- `tools/llm_bridge.py`：LLM 桥接（隐私门控，PII 剥离）
- 5 批次 IR 迁移 + DDL 标注 → 无人值守闭环

### 构建与审计

- `tools/rule_quality_auditor.py`：规则质量审计
- `tools/smt_evaluator_compare.py`：SMT 求值器对比
- `tools/semantic_compile_batch.py`：语义编译批处理
- `tools/relevance_sensitivity_runner.py`：相关性敏感性分析
- `tools/relevance_dataset_builder.py`：相关性数据集构建
- `tools/export_training_corpus.py`：训练语料导出
- `tools/promotion_gate.py`：自动提升门控
- 154/154 测试全绿

### 仓库清理

- 删除 v1.0 遗留：`adapter/`、`legalos_services/`、`extractors/`（118 KB）
- 删除生成物：`reports/`（332 KB）、`scripts/`（11 KB）、`contrib/`（5 KB）
- 删除未使用：`suggested_exception_rules.yaml`（451 KB）、`hk_us_divergence_matrix.json`（3.8 MB）
- 清除全部 stale 引用（10 文件修改）

### 破坏性变更

- `legalos_services` 已删除，定价计算改为直接 alpha 常量
- `adapter/prc_adapter` 已删除，三轨逻辑移至 `addons/` 架构
- `extractors/` 已删除，事实提取移至 `pipeline/extract_concepts.py`
- `evaluator.py` 新增 `negative_specs` 和 `blocked_claims` 字段到 `IRState`
- `types.py` `LegalRule` 新增 `modality_confidence` 和 `modality_source` 字段

---

## v1.2.0 — Tri-Rail (2026-06-04)

### Multi-Jurisdiction Collision Detection

- **Tri-Rail Collider** (`tools/run_trirail_matrix.py`): 12 cross-border conflict classes
- **PRC triple-rail engine** (`adapter/prc_adapter.py`): CBL gate (60 blocking rules) + SPC judicial tendency (23 rules) + CN statutory law (2,117 rules)
- **PRC-US Semantic Alignment Framework** (`configs/prc_us_alignment/`): 60 CBL blocking rules, 23 SPC rules, 10 procedural justice defense rules
- **Parallax Matrix** (`tools/run_parallax_matrix.py`): 65 PRC × 81 US divergence heatmap

### Jurisdiction Expansion

- **HK**: 93 Horn rules (Cap 26/32/622/571/4A)
- **US**: 50-state topological router + WI/NJ threat signatures (24 total)
- **UK**: 5 candidate rules

### Tools & Infrastructure

- **Action Agent** (`tools/action_agent/`): MemoCompiler with Jinja2 templates
- **MCP Server** (`mcp_server.py`): 9 resources + 7 tools
- **Operator Registry** (`tools/operator_registry.py`): 68 operators with bootstrap/snapshot/rollback
- **Long-tail saturation engine** (`tools/press_long_tail.py`)
- **Shadow Runner** (`tools/shadow_runner.py`): Multi-instance adversarial testing

---

## v1.0.3 (2026-06-04)

- SPC ↔ juris-calculus bridge: v5.3 Schema + 13/13 benchmark convergence
- 2,117 rules, 93% HORN, 100% premises
- concept injection: +1,453 labels, avg 2.44/rule
- MCP Server: FastMCP + JSON-RPC dual channel

---

## v1.0.2 (2026-06-02)

- Fix LegalIREvaluator → FixpointEvaluator import
- Add requirements.txt
- Add 5 unit tests
- BatchProcessor parallel execution (ThreadPoolExecutor, max_workers=8)
- YAML rule loading from configs/en_US/rules.yaml
- Published to GitHub: https://github.com/laubeing-droid/juris-calculus
