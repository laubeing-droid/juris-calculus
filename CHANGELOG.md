# juris-calculus Changelog

## Unreleased (2026-07-01)

### Playbook closure: differential gate + public kernel surface

- Added `compiler_core/post_freeze_surface.py` for Playbook F1-F14 public-kernel outputs: certificate report, missing-evidence suggestions, attack graph trace, spec differential, batch audit, candidate gate, governance, impact, route guard, engineering damages baseline, sample-deviation guard, stress fixtures, and private-layer boundary contract.
- Expanded MCP manifest to 33 tools and aligned every manifest tool with `mcp_server.py` dispatch.
- Standardized MCP/API responses with the public envelope required by the Playbook.
- Added `runtime/spec_shadow_report.json` and `runtime/spec_shadow_report.md` differential evidence: 10 aligned fixtures, 0 divergences.
- Updated formal runtime conformance wording to the current legal-math four-slice boundary and removed stale theorem-count and ghost-file wording.

## v3.0.0 (2026-06-18)

### Full Math Model Landing + 21,144 Rules + 100 Optimization Tools

**Rules: 2,117 → 21,144** (20 books, 8,712 pages, 727万字全量蒸馏)

**Four-Stage Pipeline (runtime evidence + formal-spec boundary):**
- Stage 1: `evaluate_horn()` — pure monotone Horn closure (runtime fixture evidence: 82,836 fixtures)
- Stage 2: `build_attack_graph_from_evaluator()` — Dung AAF attack graph (runtime fixture evidence: 66,066 graphs)
- Stage 3: `grounded_extension()` — deterministic acceptance/rejection
- Stage 4: Trust label projection + `allowed_claim`/`forbidden_claim` marking

**15 New Modules:**
- `dp_policy_loader.py` — DP privacy policy (epsilon from config, not law)
- `source_manifest.py` — Source verification (20 books + statutes)
- `evidence_evaluation.py` — Evidence credibility: S(e) = reliability × independence × authenticity
- `burden_of_proof.py` — Burden allocation and completion tracking
- `legal_reasoning.py` — Analogical, precedent, interpretation, interest balancing
- `cross_jurisdiction_router.py` — Obstruction-first routing
- `criminal_sentencing.py` — Sentencing prediction
- `ip_valuation.py` — IP valuation
- `compliance_monitoring.py` — Compliance checks
- `arbitration_reasoning.py` — Arbitration clause analysis
- `proof_trace_renderer.py` — Proof trace → Chinese natural language
- `proof_trace_visualizer.py` — Proof trace → Mermaid flowchart
- `inference_cache.py` — LRU cache for inference results
- `result_exporter.py` — JSON/CSV/Markdown export
- `result_diff.py` — Result comparison

**13 New MCP Tools (total 18):**
evaluate_dp_policy, validate_source, evaluate_evidence, track_burden, analyze_analogy, predict_sentence, estimate_ip_value, check_compliance, analyze_arbitration, route_cross_jurisdiction, check_obstruction, format_proof_trace, juris_query

**31,749 Concepts** extracted from 21,144 rules

**Math Model Integration:**
- DataQuality enum (6 values) on types.py
- trust_label + data_quality fields on LegalRule
- ContextualOverlapScore (Jaccard, NOT a metric — CE-001/CE-002)
- Obstruction registry (13 concept pairs: CN↔HK, CN↔US)
- Source manifest (20 books + statutes registered)
- DP policy (4 default policies: state_secret/trade_secret/personal_info/public_record)

**Tests: 209 → 243** (34 new: 4 StratifiedEvaluator + 24 new modules + 4 adversarial + 2 nonmonotone regression)

**Code Review Fixes:**
- O(n×m) → O(1) rebuttal lookup (reverse index)
- Recursion depth limit on `_apply_rule_horn()`
- MCP server try/except on all v2.1 tools
- O(n²) attack edge elimination (filter confidence=0 instead)

**67 New Tools:**
rule_conflict_detector, rule_deduplicator, rule_coverage_analyzer, rule_quality_sampler, rule_freshness_checker, rule_version_tracker, auto_distill, calibrate_weights, ocr_error_fixer, concept_disambiguator, quality_dashboard, knowledge_graph_builder, rule_classifier, mdl_fp_analysis, multi_model_comparison, damage_estimator, + more

---

## v2.1.2 (2026-06-15)

### Debug Pass — 18 Issues from Socratic Analysis

- **PROHIBITION 阻断修复**：`_check_premises` 现在检查 `blocked_claims`，被阻断的 claim 不再被下游规则使用
- **执行顺序确定**：`sorted(triggered_rule_ids)` 保证可复现结果
- **Dead code 清理**：删除 ThinkMode、validate_transition、check_negative_specs、evaluate_with_full_gate、violation_consequence
- **L0 降级修正**：全部 premise 映射到 `?` 时跳过降级（跨法域无关的规则不被误伤）
- **PERMISSION 过度声称**：PERMISSION 规则产出的 claim 标记为 HYPOTHETICAL
- **Source anchor 警告**：`load_rules_from_yaml` 对缺少 source_anchor 的规则记录 WARNING
- **时间有效性**：`case_date` 参数过滤有效期内的规则
- **冲突法推理**：`compiler_core/conflict_of_laws.py` — 选择管辖法域
- **多法域编排器**：`compiler_core/multi_jurisdiction_orchestrator.py` — 跨法域评估
- **meta_constraints 消费**：`PRCCollisionEngine` 现在处理 meta_constraints 预处理
- **测试扩展**：159 → 209 个测试（+50），新增 DDL 模态门控、ConstraintValidator、PluginRegistry、LanguageRenderer、冲突法测试

### US L0 扩展

- `configs/us/term_L0_mappings.yaml`：567 条 US 术语→L0 映射（NJ 普通话 + WI 中文 + UCC 关键词）

### HK 阻断规则扩展

- `configs/hk/blocking_rules.yaml`：12 → 21 条（+家事 3 条 +雇佣 3 条 +财产 3 条）

### CN 命名标准化

- `configs/zh_CN/rules.yaml`：20 个 dot.notation atom → snake_case（690 处引用修正）

---

## v2.1.1 (2026-06-14)

### UCC + FRCivP + Restatement Contracts

- `configs/us/rules.yaml`：73 → 123 条 Horn 规则
  - UCC Article 2 Sales（19 条）：合同成立、battle of forms、保证、perfect tender、买方救济
  - UCC Article 9 Secured Transactions（9 条）：attachment、perfection、priority、default
  - FRCivP（9 条）：跨国送达、管辖权异议、证据开示、Rule 44.1 外国法查明
  - Restatement 2d Contracts（14 条）：consideration、promissory estoppel、good faith、breach、damages
- US L0 映射：39 → 138 条（从 term_L0_mappings.yaml 动态加载）

### auto-release.yml 修复

- 添加 `permissions: contents: write` 解决 GitHub Actions release 权限问题

---

## v2.1.0 (2026-06-14)

### 跨法域架构

- **ProofTree 输出格式** (`compiler_core/proof_tree.py`)：法域中立的证明树，只含 ID + 逻辑算子
- **语言渲染插件** (`compiler_core/language_renderer.py`)：ChineseRenderer / EnglishRenderer，后置渲染层
- **三轨对撞引擎** (`compiler_core/prc_collision_engine.py`)：CBL 阻断 + SPC 倾向 + CN 全量，阻断真正拦截下游
- **JurisdictionAdapter 增强** (`compiler_core/adapter_base.py`)：load_evaluator / get_legal_family / get_modal_mapping / get_priority_evaluator

### CN addon

- `addons/cn/`：CNAdapter + 三轨模式 + 106 条 L0 映射 + 99 条翻译表
- `configs/prc_us_alignment/`：60 条 CBL 阻断 + 25 条 SPC 倾向 + 199 条术语映射

### HK addon（转换层）

- `addons/hk/adapter.py`：动态加载 1,687 条 L0 + 三语桥接 + 12 条阻断规则
- `configs/hk/rules.yaml`：85 → 104 条（+7 雇佣 Cap 57 +5 家事 Cap 179 +7 财产 Cap 219）
- `configs/hk/term_L0_mappings.yaml`：1,729 条术语→L0（从律政司 78,912 条词汇表提取）
- `configs/hk/trilingual_alignment.yaml`：US↔HK↔CN 三语映射
- `configs/hk/blocking_rules.yaml`：12 条 US→HK 阻断规则

### US addon（7 个 Title）

- `addons/us/adapter.py`：USAdapter + 39 条 L0 映射 + 14 条模态映射
- `configs/us/rules.yaml`：73 条 Horn 规则
  - Title 9 仲裁（21 条）：FAA + 纽约公约 + 美洲公约
  - Title 28 管辖权（12 条）：FSIA + §1782 跨境取证 + 异籍管辖权
  - Title 50 制裁（5 条）：IEEPA + ECRA 实体清单
  - Title 11 破产（12 条）：Ch.7 清算 + Ch.11 重组 + Ch.15 跨境破产
  - Title 15 商事（7 条）：反垄断 + 证券 + 商标
  - Title 17 版权（16 条）：保护范围 + 侵权救济
  - Title 35 专利（16 条）：可专利性 + 侵权救济
- `configs/us/blocking_rules.yaml`：18 条 US→HK 阻断规则
- `configs/us/modal_mapping.yaml`：US DDL 模态词

### 测试

- 154 → 160 测试全绿（+6 三轨碰撞测试）

---

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
