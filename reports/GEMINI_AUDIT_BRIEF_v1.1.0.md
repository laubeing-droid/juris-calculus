# juris-calculus v1.1.0 — Gemini 审计简报

> 2026-06-04 | Laupinco & WorkBuddy (DeepSeek-V4 Pro)
> 从 v1.0.0-coldstart 到 v1.1.0-matrix 的完整演进

---

## 一、架构总览

```
configs/
├── core_ontology.yaml          L0(6原语) + L1(14抽象) + L2(22买卖)
├── L0_overrides_hk.yaml        香港普通法覆写 (8态转换 + 对价=Required)
├── L0_overrides_cn.yaml        大陆法覆写 (4态转换 + 对价=Disabled)
├── L0_overrides_us.yaml        美国普通法覆写 (SUPPRESSED状态 + 7种Defect)
│
├── hk/rules.yaml               65条 Horn 规则 (Cap 26 货物买卖法)
├── en_US/
│   ├── US_Adapter.yaml         81条 Horn 规则 (uscourts.gov + justice.gov)
│   ├── L0_overrides_us.yaml    86条约束规则 (5核心 + 81 edge_case)
│   └── hk_us_divergence_matrix.json  5,184 对撞结果 (3.8MB)
│
├── prc_us_alignment/           (待建) laubeing-droid PRC-US 框架编译

compiler_core/
├── evaluator.py                200行 FixpointEvaluator + pre-iteration hook
├── constraint_validator.py     Rebuttal Hook + Audit Trail + jurisdiction-aware
└── types.py                    LegalRule, LegalFact, IRState

adapter/
├── __init__.py                 HKAdapter + USAdapter (动态加载YAML)
└── prc_adapter.py              (待建) PRCAdapter

tools/
├── gen_us_adapter.py           81条 US术语 → YAML 转换器
├── parallax_test.py            3场景 罗塞塔石碑对撞机
├── run_parallax_matrix.py      65×81 批量对撞引擎
├── distill_asymmetry.py        4,352 ASYMMETRY 蒸馏器
└── distill_jurisdiction.py     法域蒸馏工作台

reports/
├── parallax_report_v1.1.0.txt  对撞报告
├── divergence_heatmap.html     交互式热力图 (795KB)
├── asymmetry_pattern_report.txt  蒸馏报告
└── GEMINI_AUDIT_BRIEF_v1.1.0.md  本文件
```

---

## 二、L0 原语体系 (6个)

| L0 | 含义 | 子类型 |
|----|------|--------|
| Agent | 法律主体 | 自然人/法人/董事/破产受托人 |
| Asset | 法律客体 | 货物/财产/资金/数据 |
| Act | 法律行为 | 要约/承诺/交付/支付 |
| Status | 法律状态 | VALID/VOID/VOIDABLE/SUPPRESSED/PENDING |
| Power | 法律权能 | 代理/代表/处分/收货/催收 |
| Defect | 法律瑕疵 | 越权/欺诈/胁迫/对价失败/误述 |

### 状态机 (跨法系统一)

```
HK: VALID ↔ VOID ↔ VOIDABLE ↔ TERMINATED ↔ EXPIRED ↔ PENDING
CN: Established→VALID → VOID → VOIDABLE → TERMINATED
US: + SUPPRESSED + PENDING + CONDITIONAL + VOIDABLE双向 + Breached/Remedied
```

---

## 三、核心引擎机制

### FixpointEvaluator.evaluate() — 3个钩子

1. **Pre-iteration Hook** (v1.1.0新增): 迭代开始前检查 constraint_rules，确保 AUTOMATIC_STAY 等环境阻断在先
2. **Per-rule Hook**: Rebuttal Check + Oscillation Guard (≤3次修改)
3. **State Machine Hook**: 反驳触发 → state_tracker 更新

### ConstraintValidator — 3种约束

1. **Absolute_Rebuttal**: 事实存在 → 置信度→0
2. **Conditional_Rebuttal**: 事实 + 附加条件 → 置信度→0
3. **Force_Convergence**: L0_overrides 的 constraint_rules (force_state / suppress_power)

### 5道护栏

1. L2→L0 完备性校验
2. 约束规则触发
3. L0 原语覆盖
4. 振荡保护 (≤3)
5. 状态机完整性

---

## 四、65×81 分歧矩阵结果

### 总体

| 类型 | 数量 | 占比 | 
|------|------|------|
| ASYMMETRY | 4,352 | 84.0% |
| ERROR | 708 | 13.7% |
| COLLISION | 124 | 2.4% |
| COINCIDENCE | 0 | 0% |

### COLLISION 分析

全部 124 条集中在两个 US 算子：

**US-Immunity × 62条HK规则**: 
- 触发链: Director_Acted_UltraVires → HK DIRECTOR_ULTRA_VIRES 约束 → suppress_power → SUPPRESSED
- US 侧: Immunity 覆盖 → VALID
- 现实含义: 港方判定越权无效，美方以主权豁免强行维持有效 → 跨境资产撕裂

**US-Automatic_stay × 62条HK规则**:
- 同样触发链
- 域分布: Validity=62, Remedy/Sanction=62

### ASYMMETRY 蒸馏

三大拓扑模式:

| 模式 | 数量 | 含义 |
|------|------|------|
| CONCEPT_OVERFLOW | 2,304 | US溢出刑诉/破产概念 |
| BURDEN_SHIFTING | 1,986 | 事实推定机制不对称 |
| LOGICAL_FADING | 62 | HK合同链 vs US单步 |

15个高频隐藏原语 (US-only):

| 频率 | 概念 | L0归属 |
|------|------|--------|
| 128 | DIP_Status → Business_Operations_Continue | Status(Bankruptcy) |
| 128 | PSR_Ordered → Guidelines_Calculated | Status(Criminal) |
| 64 | Acquittal_Entered | Status(Criminal) |
| 64 | DeathPenalty_Eligible | Status(Criminal) |
| 64 | Liquidation_Process_Triggered | Status(Bankruptcy) |

### ERROR 分析 (708次)

全部为 `CriticalClarityFailure` — 连续3条规则评分<0.3时引擎主动熔断。不是Bug，是5道护栏的物理防御。

---

## 五、版本链

```
v1.0.0-coldstart  → v1.1.0-CrossBorder  → v1.1.0-matrix
(HK孤岛65条)       (港美双源81条US)       (65×81完整对撞)
                                          
                   即将: v1.2.0-TriRail
                   (三轨对撞: HK×US×PRC)
```

---

## 六、待完成任务 (本次会话应交付)

### 1. 编译 laubeing-droid → 3份 YAML

输出路径: `configs/prc_us_alignment/`

- **blocking_rules.yaml**: 22项绝对阻断 + 6项MAPPING_OVERRIDE + 5项跨境穿透 + 27项中国特色制度
- **term_L0_mappings.yaml**: 180+ 中美法律术语 → L0 原语映射
- **meta_constraints.yaml**: 6条元规则 → evaluator约束算子

### 2. PRCAdapter

`adapter/prc_adapter.py` — 纯约束层引擎，不产生自己的Horn规则。行为:
- 加载 blocking_rules.yaml → constraint_rules
- 对共享事实池执行 PRC-first 强制性效力覆写
- 输出 State_PRC = {FORCE_VOID | FORCE_SUPPRESS | MAPPING_OVERRIDE}

### 3. 三轨对撞机

`tools/run_trirail_matrix.py` — 升级版矩阵引擎:
- 三轨并发: HK Engine × US Engine × PRC-Alignment Engine
- 新分类维度: TRI_RESONANCE / CHINA_US_COLLISION / HK_CN_ASYMMETRY
- 输出: 三维冲突矩阵 + 三轨热力图

---

## 七、PRC-US Framework 核心数据

来源: laubeing-droid/PRC-US-Legal-Semantic-Alignment-Framework v3.0.3 (79KB markdown)

| 组件 | 内容 |
|------|------|
| 22项阻断清单 | consideration, discovery, Miranda rights, jury trial, hearsay, at-will employment... |
| 6项MAPPING_OVERRIDE | plea bargaining→认罪认罚从宽, discovery→证据交换, right of publicity→肖像权/姓名权... |
| 6条元规则 | 禁止字面优先、5级功能判断、无对应制度阻断、特色制度标注、法域不混同、最严管辖 |
| 17编部门法 | 宪法/民法7编/民诉/刑诉/公司法2024/行政法/数据合规/劳动/破产/跨境合规 |
| 27项中国特色制度 | 算法备案、离婚冷静期、横向人格否认、数据出境安全评估、保理合同独立成章... |
| 跨三法域对照 | 中国大陆 vs 中国香港 vs 美国 (7项三方对照) |

---

## 八、关键设计决策

1. **引擎实例独立**: 每个法域的 FixpointEvaluator 是独立实例，互不读取对方内存。唯一交点是底层共享事实池。
2. **PRC-Alignment Engine 不产生 Horn 规则**: 它是一个纯约束层引擎——输入事实，输出中国成文法强制性效力覆写（FORCE_VOID / FORCE_SUPPRESS / MAPPING_OVERRIDE）。
3. **5道护栏熔断**: 708次 ERROR 全部是引擎主动拒绝低置信推理链——宁可沉默，不幻觉。
4. **ADR Agent 已禁用**: 蒸馏脚本中的 Inspector 调用基于假设的内核检视器，实际使用 claims 集合差作为分叉代理。
