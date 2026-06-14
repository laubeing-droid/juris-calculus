# juris-calculus

**法域无关符号法律推理编译器 — DDL + 跨法域 + ProofTree**

法域无关的 Horn 子句引擎，支持不动点迭代、可废止道义逻辑（DDL）模态分类、跨法域桥接层。

*不是法律 App，是法律推理内核。*

---

## 做什么

juris-calculus 将成文法编译为可执行的 Horn 规则，通过不动点迭代和 DDL 模态门控（OBLIGATION / PROHIBITION / PERMISSION / CONSTITUTIVE）进行推理。

**三个法域，一个引擎：**

| 法域 | 规则数 | 阻断规则 | L0 映射 | 角色 |
|------|--------|---------|---------|------|
| CN（中国） | 2,117 | 60 CBL | 106 | 主法域 |
| HK（香港） | 104 | 21 | 1,687 | US↔CN 转换层 |
| US（美国联邦） | 123 | 18 | 567 | 跨境争议 |
| **合计** | **2,344** | **99** | **2,360** | |

**跨法域架构：**

```
US 术语 ──→ L0 原语 ←── HK 术语 ──→ L0 原语 ←── CN 术语
          (Status/Act/Defect/Power/Agent/Asset)
```

香港定位为中美"罗塞塔石碑"——在普通法体系中拥有官方中文立法文本。

---

## 架构

```
juris-calculus/
├── compiler_core/                    # 推理内核
│   ├── evaluator.py                  #   FixpointEvaluator + DDL 模态门控
│   ├── types.py                      #   LegalRule / LegalFact / IRState / NormModality
│   ├── proof_tree.py                 #   ProofTree — 法域中立输出格式
│   ├── language_renderer.py          #   ChineseRenderer / EnglishRenderer（后置渲染）
│   ├── prc_collision_engine.py       #   三轨对撞（CBL + SPC + CN）
│   ├── conflict_of_laws.py           #   冲突法推理（法域选择）
│   ├── multi_jurisdiction_orchestrator.py  #  多法域编排器
│   ├── adapter_base.py              #   JurisdictionAdapter 抽象基类
│   └── plugin_registry.py           #   自动发现 addon 系统
├── addons/
│   ├── cn/                           #   中国 addon（civil_law）
│   ├── hk/                           #   香港 addon（common_law，转换层）
│   └── us/                           #   美国联邦 addon（common_law）
├── configs/
│   ├── zh_CN/rules.yaml              #   2,117 条中国法 Horn 规则
│   ├── hk/rules.yaml                 #   104 条香港法 Horn 规则（7 命名空间）
│   ├── hk/blocking_rules.yaml        #   21 条 US→HK 阻断规则
│   ├── hk/term_L0_mappings.yaml      #   1,729 条 HK 术语→L0
│   ├── us/rules.yaml                 #   123 条美国联邦法 Horn 规则（9 命名空间）
│   ├── us/term_L0_mappings.yaml      #   567 条 US 术语→L0
│   ├── us/blocking_rules.yaml        #   18 条 US→HK 阻断规则
│   ├── us/modal_mapping.yaml         #   US DDL 模态词
│   └── prc_us_alignment/             #   60 条 CBL + 25 条 SPC + 199 条术语映射
└── tests/                            #   209 个测试，全部通过
```

---

## 工作原理

1. **编译**：加载成文法 YAML → `LegalRule` 对象
2. **推理**：`FixpointEvaluator.evaluate()` — Horn 子句不动点迭代 + DDL 模态门控
3. **输出**：`ProofTree` — 纯 ID + 逻辑算子，不含自然语言
4. **渲染**：`LanguageRenderer` 将 ProofTree 翻译为中文/英文法律文书

编译器核心不输出自然语言。语言是后置渲染层，与推理解耦。

---

## 快速开始

```python
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.types import IRState, LegalFact

# 加载中国法规则
rules = load_rules_from_yaml("configs/zh_CN/rules.yaml")
ev = FixpointEvaluator(rules)

# 运行推理
state = IRState(facts={
    "contract_formed": LegalFact(id="contract_formed", description="", extraction_confidence=0.95),
    "breach_alleged": LegalFact(id="breach_alleged", description="", extraction_confidence=0.9),
})
result = ev.evaluate(state)

# 输出：ProofTree，法域中立的推理结论
```

---

## 跨法域桥接

```python
from compiler_core.plugin_registry import registry

# 自动发现的 addon
cn = registry.get("cn")  # 中国
hk = registry.get("hk")  # 香港（转换层）
us = registry.get("us")  # 美国联邦

# 三语桥接
result = hk.trilingual_bridge("Consideration")
# → {'alignment': 'CROSS_L0', 'us_l0': 'Power', 'hk_term': 'cash consideration', ...}

# 三轨对撞（CBL + SPC + CN）
tree = cn.run_collision(facts)
# → ProofTree，含 blocked_claims / spc_tendencies / cn_claims

# 冲突法 — 自动识别管辖法域
from compiler_core.conflict_of_laws import select_jurisdiction
jurisdiction = select_jurisdiction(facts)
# → "CN" 或 "HK" 或 "US"

# 多法域编排
from compiler_core.multi_jurisdiction_orchestrator import MultiJurisdictionOrchestrator
mjo = MultiJurisdictionOrchestrator()
tree = mjo.run(facts, jurisdictions=["CN", "HK", "US"])
```

---

## 覆盖范围

### 中国（CN）— 2,117 条规则，13 领域
合同、侵权、公司、家事、刑事、行政、知产、程序、执行、国赔、少年、海事、审管

### 香港（HK）— 104 条规则，7 个命名空间，21 条阻断规则
合同（Cap 26）、公司（Cap 622）、雇佣（Cap 57）、家事（Cap 179）、财产（Cap 219）、仲裁（Cap 609）、知产（Cap 528）

### 美国联邦（US）— 123 条规则，9 个命名空间，18 条阻断规则
- **Title 9** 仲裁（FAA + 纽约公约 + 美洲公约）— 21 条
- **Title 28** 管辖权/FSIA/§1782 — 12 条
- **Title 50** 制裁（IEEPA + ECRA）— 5 条
- **Title 11** 破产（Ch.7 + Ch.11 + Ch.15）— 12 条
- **Title 15** 商事/反垄断/证券/商标 — 7 条
- **Title 17** 版权 — 16 条
- **Title 35** 专利 — 16 条
- **UCC** Article 2（货物买卖）+ Article 9（动产担保）— 27 条
- **Restatement 2d** 合同法 — 14 条
- **FRCivP** 联邦民事诉讼规则 — 9 条

---

## 关键设计决策

| 决策 | 理由 |
|------|------|
| ProofTree 输出（无自然语言） | 语言是后置渲染层，与推理解耦 |
| L0 原语做桥接 | US↔HK↔CN 通过 6 个通用原语映射，不做文本互撞 |
| DDL 模态门控 | PROHIBITION 阻断 claim，OBLIGATION 标记缺口，PERMISSION 标记假设 |
| 三轨对撞 | CBL（阻断）> SPC（裁判倾向）> CN（成文法全量） |
| Addons 模式 | 新法域 = 新目录，核心引擎零改动 |
| 诚实拒绝 | CriticalClarityFailure 在连续低置信度时停止推理，拒绝幻觉 |

---

## 安装

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

---

## 许可证

MIT
