# Gemini 终局审计指令 — juris-calculus v1.2.0 全栈交付

## 审计范围
以下五个模块今天已完成并提交，请逐项审计架构正确性、逻辑完备性和安全边界。

---

## 一、三法域对接总表

```
法域    Horn规则        约束         术语          桥接状态
HK       93(生产)        —            —            Cap26+Cap32/622/571/4A
US       81            86(CBL)      3,084         WI/NJ联邦+州+OCR清洗
PRC    2,117(CN)       41(CBL)       131          三轨合一+跨法域事实桥接
          23(SPC)       6(meta)       27(CN_SPEC)
────────────────────────────────────────────────
总计    2,291         150+          3,215+
```

**请审计**: 各法域规则数是否合理。HK 93条是否覆盖了对抗US破产/长臂的核心算子。PRC 2,117条CN规则通过26条跨法域事实桥接表接入是否正确——CN引擎是否在TRI_012中正确触发了66条主张。

---

## 二、Gemini v1审计四项修正（已应用）

| # | 发现 | 修复 |
|---|------|------|
| 1 | BLK_001 Consideration门控过宽 | 追加 `Foreign_Connected_Entity` 双重门控 |
| 2 | CN_SPEC_006 DataExport 28次COLLISION误杀 | 追加 `Identified_Sensitive_Data_Or_State_Secret`；移除 record/file 映射 |
| 3 | CriticalClarityFailure 未反驳claims外泄 | 原子性降级：仅保留 confidence > 0.8 |
| 4 | 3,259条含ARM OCR噪音 | 175条硬剔除→3,084清洁 |

**请审计**: 修正后的三轨12场景结果为6 COLLISION / 4 ASYMMETRY / 2 RESONANCE（修正前为9/2/1）。这个降级方向是否正确？CN_SPEC_006收紧后是否有遗漏的真实跨境冲突？confidence > 0.8的阈值是否合适（0.8是否过高导致遗漏有效的partial_claims）？

---

## 三、新增模块

### 3.1 HK扩展规则（64→93条）
文件: `configs/hk/extended_rules.yaml`（300条标注，29条Horn规则已加载）
- Cap32: 清盘搁置(s.181)、临时清盘人(s.193)、欺诈交易(s.182)、不公平优惠(s.266)
- Cap622: 影子董事(s.2)、越权(s.116)、不公平损害(s.724)、衍生诉讼(s.725)、安排方案(s.670)
- Cap571: 内幕交易(s.270)、虚假交易(s.274)、操纵价格(s.275)、披露虚假信息(s.277)
- Cap4A: Mareva禁制令、Anton Piller令、Norwich Pharmacal令、Chabra冻结、禁诉令

**请审计**: 
- Cap32 s.181 Stay 的 `Power(Creditor_Action) → SUPPRESSED` 是否与US Automatic Stay (11 USC 362)形成正确对冲？
- Cap622 s.2 影子董事定义 `Agent(Directors_Accustomed_To_Act)` 是否与PRC CN轨影子董事规则兼容？
- Cap4A禁诉令(anti-suit injunction)在跨法系场景中是否会与PRC长臂阻断(PEN_003)产生振荡？

### 3.2 PRC术语满编（55→131条）
文件: `configs/prc_us_alignment/term_L0_mappings.yaml`
新增76条覆盖：合同15/侵权12/物权8/婚姻家庭10/民诉10/刑诉8/行政5/知产反垄断税法环境8

**请审计**:
- 证券特别代表人诉讼(PRC_SPEC_004)与US class action的拓扑差异是否准确（默示加入/明示退出 vs opt-out）？
- 第三人撤销之诉(PRC_ALIGN_Third_Party_Revocation)是否有对应的US/HK概念锚点？
- 131条中是否有遗漏的关键部门法术语（环境/反垄断/税法是否覆盖不足）？

### 3.3 US 50州拓扑路由器
文件: `configs/en_US/state_router.yaml` + `tools/distill_jurisdiction.py:route_state_law_to_backbone()`
- 4大骨干模型：DE_CORPORATE(10州)、LONG_ARM(17州)、CFA_PUNITIVE(12州)、DEFAULT_UCC(7州)
- WI验证LONG_ARM模型，NJ验证CFA_PUNITIVE模型
- 48州通过关键字+州代码自动路由

**请审计**:
- 路由优先级(state_code > fact_pattern > keyword)是否正确？DE州代码命中是否会错误覆盖CFA_PUNITIVE特征？
- DEFAULT_UCC降级策略——7个默认UCC州完全由81条联邦/通用算子接管是否足够？
- 加州同时出现在LONG_ARM和CFA_PUNITIVE中的理由（CA路由到CFA_PUNITIVE是否丢失了其长臂特殊性）？

### 3.4 威胁情报层
文件: `configs/us/threat_signatures/{nj_pen_signature.yaml, wi_enf_signature.yaml}`
- NJ: 12条（法人人格否认/CFA/影子控制/欺诈转移/RICO/破产/环境/上诉）
- WI: 12条（长臂/行政裁决/消费者/反敲诈/竞业限制/保险/生物识别/判决执行）
- `FastPathInterceptor` 集成至 `press_long_tail.py` 和 `distill_jurisdiction.py`

**请审计**:
- 24条签名中，CRITICAL级是否都有合理的法律依据（NF/NJ州法与PRC阻断规则的实际冲突点）？
- FastPathInterceptor.intercept() 的精确匹配（非fuzzy）策略是否正确？是否存在漏杀风险（如"consumer fraud"未匹配"Consumer Fraud Act"而需要更宽松的匹配）？
- 物理降维后的CBL指令 `IMMEDIATE_PRC_CBL_FORCE_VOID` 是否正确链接到 `blocking_rules.yaml` 中的实际规则ID？

---

## 四、三轨对撞现状

| 场景 | 分类 | HK | US | PRC(CBL+CN) |
|------|------|-----|-----|-------------|
| TRI_001 越权+数据出境 | COLLISION | SUPPRESSED | VALID | 1×FORCE_VOID |
| TRI_002 Discovery | ASYMMETRY | VALID | VALID | 2×MAPPING+24×CN |
| TRI_003 OFAC制裁 | COLLISION | VALID | VALID | 2×FORCE_SUPPRESS+2×CN |
| TRI_004 辩诉交易 | ASYMMETRY | VALID | VALID | 2×MAPPING+14×CN |
| TRI_005 Ch11+越权 | RESONANCE | SUPPRESSED | VALID(DIP) | 无PRC触发 |
| TRI_008 VIE架构 | COLLISION | VALID | VALID | 1×SUPPRESS+1×MAPPING+40×CN |
| TRI_011 纯境内保理 | ASYMMETRY | VALID | VALID | 1×MAPPING+2×CN |
| TRI_012 CN桥接验收 | RESONANCE | VALID | VALID | 66×CN |

**请审计**: TRI_005从COLLISION→RESONANCE（BLK_001双重门控：无Foreign_Connected_Entity → Consideration_Shield不触发）。这个结果是正确收敛还是过度收窄——Ch11+越权的跨境场景是否理应触发PRC阻断？

---

## 五、已知短板（请标注严重度）

1. HK扩展规则中仅29条Horn规则被加载（300条标注中大量是文档化定义），核心对抗算子密度是否足够？
2. PRC术语131/180（72%覆盖率），合同/侵权/婚姻继承已补齐，但知识产权/环境公益诉讼/税法领域仅各有1-2条
3. 饱和攻击3,084条全量重跑尚未完成（仅验证10条），长期运行稳定性未确认
4. FastPathInterceptor仅在press_long_tail中挂载，TriRailCollider主路径未集成

---

请逐项审计，输出格式：
```
[-] 模块名: 审计结果 (通过/风险/阻断)
    问题描述
    修复建议（如有）
```