# Gemini 审计提示词 — juris-calculus v1.2.0 全栈投产报告

> 2026-06-04 | LegalOS Team
> 单日从 v1.0.0-coldstart 推进至 v1.2.0-TriRail

---

## 审计重点

1. **三轨对撞机架构**是否合理——PRC-Alignment Engine 作为纯约束层不产生 Horn 规则
2. **PRC blocking_rules.yaml** 的 41 条约束是否有逻辑黑洞
3. **CriticalClarityFailure 捕获**的 partial_state 降级是否安全
4. **BLK_001_Consideration** 的 additional_conditions 门控是否正确

---

## 架构全貌

```
│ ├── US_Adapter.yaml              81条 Horn 规则
│ ├── L0_overrides_us.yaml          86条约束规则  
│ ├── state_combined_terms.json     3,259条 合并术语库
│ ├── llm_distilled_full.json       419条 LLM 蒸馏(含 L0 链)
│ └── hk_us_divergence_matrix.json  3.7MB 65×81 对撞结果
│
├── configs/prc_us_alignment/
│   ├── blocking_rules.yaml    41条阻断 (22绝对+6映射+5跨境+8特色)
│   ├── term_L0_mappings.yaml  28项三方对照
│   ├── meta_constraints.yaml  6条元规则
│   └── long_tail_collision_matrix.json  3,259条三轨压榨结果
│
├── compiler_core/
│   ├── evaluator.py           200行 FixpointEvaluator
│   │   ├── pre-iteration hook (v1.1新增): 迭代前约束规则检查
│   │   ├── per-rule hook: Rebuttal + Oscillation Guard (≤3)
│   │   └── CriticalClarityFailure: 熔断时注入 partial_state
│   └── constraint_validator.py
│       ├── overrides_path 参数 (v1.1): 法域特定约束加载
│       ├── additional_conditions 交叉校验
│       └── resolve_L0_primitive(): L2→L1→L0 溯源
│
├── adapter/
│   ├── __init__.py             HKAdapter + USAdapter
│   └── prc_adapter.py          PRCAdapter (纯约束层,零污染输出)
│
└── tools/
    ├── run_parallax_matrix.py      65×81 双轨对撞 (5,184次)
    ├── run_trirail_matrix.py       HK×US×PRC 三轨对撞 (11场景)
    ├── press_long_tail.py          饱和攻击引擎 (3,259条)
    ├── distill_asymmetry.py        ASYMMETRY 蒸馏器 (3拓扑模型)
    ├── gen_us_adapter.py                        术语→YAML 编译器
    └── parallax_test.py           罗塞塔石碑对撞机
```

---

## 核心产出

### 65×81 双轨矩阵 (HK × US)

| 类型 | 数量 | 占比 |
|------|------|------|
| ASYMMETRY | 4,352 | 84.0% |
| COLLISION | 124 | 2.4% |
| ERROR | 708 | 13.7% |
| COINCIDENCE | 0 | 0% |

- 124 COLLISION 集中在 US-Immunity(62) 和 US-Automatic_stay(62) × HK 规则
- 触发链: Director_Acted_UltraVires → HK DIRECTOR_ULTRA_VIRES 约束 → suppress_power → SUPPRESSED
- 708 ERROR 全部为 CriticalClarityFailure 熔断 (非Bug)

### 三轨饱和攻击 (3,259条)

| 类型 | 数量 |
|------|------|
| COLLISION | 46 |
| ASYMMETRY | 67 |
| RESONANCE | 3,146 |

### ASYMMETRY 蒸馏

三大拓扑模式: CONCEPT_OVERFLOW(2,304) / LOGICAL_FADING(62) / BURDEN_SHIFTING(1,986)
15个隐藏原语: DIP_Status(128次)、PSR_Ordered(128次)、Acquittal_Entered 等

---

## 关键设计决策 (请审计)

1. **PRC-Alignment Engine 不产生 Horn 规则**: 是一个纯约束层引擎，加载 blocking_rules.yaml，对共享事实池输出 FORCE_VOID / FORCE_SUPPRESS / MAPPING_OVERRIDE。不参与事实改写。

2. **三轨独立内存空间**: 每个法域的 FixpointEvaluator 是独立实例，唯一交点是底层共享事实池。PRC 输出不污染 HK/US 推理。

3. **BLK_001_Consideration 门控**: `trigger_fact: Consideration_Provided` + `additional_conditions: [Cross_Border_Context]`，仅在跨境场景触发 FORCE_SUPPRESS。纯境内保理场景 (TRI_011) 验证通过——BLK_001 不触发。

4. **CriticalClarityFailure 降级**: 熔断时注入 `partial_state` (已收敛的残存 claims)，调用方 catch 后消费 partial 而非返回空。

5. **OVR_006_Wrongful_Omission_Fill**: 填补 US(Defect) vs HK(?) 的跨法系映射缺口，映射为 CN_Security_Breach_Or_BreachOfTrust。

---

## 待审计风险点

- BLK_021_Discovery_Fishing 触发了 45 次 ASYMMETRY——覆盖范围是否过宽？
- CN_SPEC_006_DataExportAssessment 触发了 28 次 COLLISION——"record"/"file"/"case file" 等通用术语被标记为数据出境是否合理？
- 3,259 条术语中含 ~1,173 条 OCR 噪音（Armenian garbled），未清洗影响后续使用

---

## 相关文件路径

```
juris-calculus/
├── reports/GEMINI_AUDIT_BRIEF_v1.1.0.md (详细架构)
├── reports/trirail_report_v1.2.0.txt
├── reports/trirail_heatmap_v1.2.0.html
├── reports/asymmetry_pattern_report.txt
├── configs/en_US/US_complete.json (合并产物, 已删除, 见 state_combined_terms.json)
└── configs/en_US/state_combined_terms.json (3,259条原始术语库)
```

Git 标签: v1.0.0-coldstart → v1.2.0-TriRail (9 tags)
