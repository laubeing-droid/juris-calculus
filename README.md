# juris-calculus v2.0.0

**符号法律推理编译器 — DDL模态 + 证据链 + 法定审计**

不动点评估器 + DDL（可废止道义逻辑）模态分类 + L1-L2 证据链/法定审计护栏 + 神经网络守卫层。

*不是法律 App，是法律推理内核。*

> **This is PostgreSQL, not Windows.**
>
> juris-calculus 提供逻辑、审计链、DDL 模态门控。不管理文书、邮件或日程。

---

## v2.0.0 新特性

### DDL 模态引擎
- **2,117 条全量 norm_modality 标注**：825 条 LLM 确认 + 633 条关键词 + 18 条正文匹配 + 641 条 fallback
- **evaluator 模态门控**：`OBLIGATION` 缺事实 → Negative Spec 缺口报告；`PROHIBITION` 命中 → 阻断结论链
- **DDL preclassifier**：关键词 + 结构 + 概念 + 命名空间 + LLM 确认五层分类
- **DDL 100% 高置信度**：0 UNKNOWN，0 需外部标注

### L1-L2 护栏模块（14 文件）
- **L1 证据链**：`evidence_chain_validator.py` — 推理前证据完整性校验
- **L2 跨法域**：`cross_jurisdiction_compare.py` / `multi_solver_router.py`
- **L2 De Jure 审计**：`de_jure_auditor.py` — 推理后法定合规审计
- **L2 不变性度量**：`invariance_metrics.py` / `validity_state_machine.py`
- **L2 可废止优先级**：`defeasible_priority.py` / `proleg_translator.py`
- **L2 实体匿名化**：`entity_anonymizer.py` / `kg_recall.py`

### 神经网络守卫层
- **contracts/**：输入特征白名单/黑名单、输出约束（禁止法律结论）、晋升策略（默认 SHADOW_ONLY）
- **registry/**：模型注册表 + DDL 确认查找表（825 条 zh_CN + 64 条 HK）
- **neural_leaf.py / neural_yaml_sync.py / step_verifier.py**：6/6 测试全绿

### LLM 批处理自动化
- 5 批次 IR 迁移 + DDL 标注 → 无人值守闭环
- `tools/llm_batch_acceptor.py` / `llm_batch_orchestrator.py` / `llm_bridge.py`

---

## 架构

```
juris-calculus/
├── compiler_core/                    # 推理内核
│   ├── evaluator.py                  #   FixpointEvaluator + DDL 模态门控 + 例外链 + 熔断
│   ├── types.py                      #   LegalRule / LegalFact / LegalClaim / NormModality / IRState
│   ├── domain_config.py              #   民刑双域路由 + 自由裁量概念检测
│   ├── classifier.py                 #   EvidenceClassifier（A/B/C 载体等级）
│   ├── batch_processor.py            #   批量处理 + JSON 审计导出
│   ├── ddl_preclassifier.py          #   DDL 五层模态分类器
│   ├── evidence_chain_validator.py   #   L1 证据链验证器
│   ├── de_jure_auditor.py            #   L2 法定审计器
│   ├── cross_jurisdiction_compare.py #   L2 跨法域比较
│   ├── multi_solver_router.py        #   L2 多求解器路由（CN/CBL/SPC）
│   ├── validity_state_machine.py     #   L2 有效性状态机
│   ├── neural_leaf.py                #   神经网络叶子节点
│   └── step_verifier.py              #   神经网络步骤验证器
│
├── pipeline/                         # 端到端推理管线
│   ├── pipeline.py                   #   案卷 → 事实 → 证据链校验 → DDL 推理 → 法定审计 → 报告
│   ├── prc_us_alignment.py           #   PRC-US 对齐看门狗
│   ├── guardian.py                   #   白名单校验 + 5 级强度门控
│   └── llm_client.py                 #   LLM API 客户端
│
├── configs/
│   ├── zh_CN/                        #   中国民法：2,117 条 Horn 规则（含 norm_modality）
│   ├── en_US/                        #   美国联邦：81 条 Horn + 86 条约束
│   ├── hk/                           #   香港：93 条 Horn
│   ├── prc_us_alignment/             #   PRC-US 桥接：60 CBL + 23 SPC + 10 程序正义
│   └── core_ontology.yaml            #   L0 本体（6 原语）
│
├── neural/
│   ├── contracts/                    #   输入/输出/晋升策略契约
│   └── registry/                     #   模型注册表 + DDL 确认查找表
│
├── addons/
│   ├── us/                           #   美国法 addon（lookup + adapter + alignment）
│   ├── hk/                           #   香港法 addon
│   └── federation/                   #   法系联邦路由
│
├── tools/                            # 审计 + 构建 + LLM 批处理
│   ├── rule_quality_auditor.py       #   规则质量审计器
│   ├── llm_batch_acceptor.py         #   LLM 批量验收
│   ├── llm_batch_orchestrator.py     #   LLM 批量编排
│   ├── llm_bridge.py                 #   LLM 桥接（隐私门控）
│   ├── smt_evaluator_compare.py      #   SMT 求值器对比
│   ├── rule_to_ir_migrator.py        #   规则→Typed IR 迁移
│   └── semantic_compile_batch.py     #   语义编译批处理
│
├── mcp_server.py                     # MCP 双通道服务端
└── tests/                            # 154 个测试全绿
```

---

## 法域覆盖

| 法域 | 规则数 | DDL 状态 |
|------|:------:|:--------:|
| 中国（13 领域） | 2,117 | 100% 高置信度 |
| 美国联邦 | 81 Horn + 86 约束 | 部分 |
| 香港 | 93 | 64 DDL |
| PRC-US 对齐 | 60 CBL + 23 SPC + 10 程序 | — |
| 英国 | 5 候选 | — |

---

## 快速开始

```bash
# 安装
git clone https://github.com/laubeing-droid/juris-calculus.git
cd juris-calculus
pip install -r requirements.txt

# 运行推理
python -c "
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.types import IRState, LegalFact, LegalDomain
from compiler_core.domain_config import get_domain_config

rules = load_rules_from_yaml('configs/zh_CN/rules.yaml')
config = get_domain_config(LegalDomain.CIVIL)
engine = FixpointEvaluator(rules, config)
state = IRState()
state.facts['loan_contract'] = LegalFact(id='loan_contract')
state.facts['breach_alleged'] = LegalFact(id='breach_alleged')
result = engine.evaluate(state)
print(f'Claims: {len(result.claims)}')
print(f'Negative specs: {len(result.negative_specs)}')
"

# 运行测试
python -m pytest tests/ -q
# 154 passed
```

---

## DDL 模态行为

```python
# OBLIGATION 规则：缺事实 → Negative Spec
# "应当承担损害赔偿责任" 但没有 damages_suffered 事实
# → 系统标记 OBLIGATION_GAP，记录 missing premises

# PROHIBITION 规则：命中 → 阻断结论链
# "不得强制执行" 且强制执行事实存在
# → 结论链切断，记录 PROHIBITION_BLOCK

# PERMISSION 规则：正常推理
# "可以要求赔偿" → 正常推理，不特殊处理

# CONSTITUTIVE 规则：构成性规则
# "法人成立应当具备..." → 正常推理
```

---

## 测试

```bash
python -m pytest tests/ -q
# 154 passed in 21s
```

---

## 版本演进

| 版本 | 日期 | 核心 |
|------|------|------|
| v1.0.0 | 2026-06-02 | 开源版，35 文件 |
| v1.0.1 | 2026-06-02 | 导入修复 + 5 测试 |
| v1.0.2 | 2026-06-02 | YAML 规则加载 + 批量并行化 |
| v1.0.3 | 2026-06-04 | SPC 桥接 + 概念注入 + 2,117 条 |
| v1.1.0 | 2026-06-04 | HK-US 分歧矩阵 |
| v1.2.0 | 2026-06-04 | 三轨对撞 + PRC-US 对齐 |
| **v2.0.0** | **2026-06-14** | **DDL 模态 + L1-L2 护栏 + 神经守卫** |

---

## License

MIT