# 高危路径逻辑审计检查表 — 12 个收敛点
## 版本: v1.2.0 | source_hash: f7fc1b4e61db

## 审计总览

| 分类 | 数量 |
|------|------|
| CHINA_US_COLLISION | 7 |
| HK_CN_ASYMMETRY | 3 |
| TRI_RESONANCE | 2 |

## 一、 逻辑收敛点聚类 (12 个)

| 阻断规则 | 触发次数 | 类型 |
|----------|----------|------|
| MAPPING:CN_SPEC_002_Factoring_Chapter | 2 | MAPPING |
| PEN_001_Data_CrossBorder_Security | 1 | FORCE_VOID |
| BLK_021_Discovery_Fishing | 1 | FORCE_VOID |
| PEN_002_Secondary_Sanction_Block | 1 | FORCE_VOID |
| PEN_004_OFAC_CounterCollision | 1 | FORCE_VOID |
| MAPPING:OVR_001_Plea_Bargaining_Restruct | 1 | MAPPING |
| MAPPING:OVR_006_Wrongful_Omission_Fill | 1 | MAPPING |
| PEN_005_Crypto_Prohibition | 1 | FORCE_VOID |
| PEN_003_Long_Arm_Interdiction | 1 | FORCE_VOID |
| MAPPING:CN_SPEC_001_Horizontal_Veil_Piercing | 1 | MAPPING |
| CN_SPEC_003_Algorithm_Filing | 1 | MAPPING |
| BLK_019_AtWillEmployment | 1 | FORCE_VOID |

## 二、 逐条五维审计

> 审计维度: 1.算子响应完整性 2.主权边界锚定 3.证据链路鲁棒性 4.对抗战术一致性 5.协议版本溯源

### 1. [RED] TRI_001_UltraVires_DataExport

**分类**: CHINA_US_COLLISION
**描述**: HK董事越权 + 美国Cloud Act数据请求 → PRC数据出境阻断
**HK状态**: SUPPRESSED | **US状态**: VALID | **CN主张**: 0条
**触发的PRC规则**: ['PEN_001_Data_CrossBorder_Security']

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

### 2. [RED] TRI_002_Litigation_Discovery

**分类**: CHINA_US_COLLISION
**描述**: 美国诉前证据开示 + 关联公司资产混同 → 横向否认+数据阻断
**HK状态**: ? | **US状态**: ? | **CN主张**: 0条
**触发的PRC规则**: ['BLK_021_Discovery_Fishing']

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

### 3. [RED] TRI_003_OFAC_Sanction_Deadlock

**分类**: CHINA_US_COLLISION
**描述**: OFAC制裁 vs 反外国制裁法第12条强制对撞
**HK状态**: VALID | **US状态**: VALID | **CN主张**: 2条
**触发的PRC规则**: ['PEN_002_Secondary_Sanction_Block', 'PEN_004_OFAC_CounterCollision']

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

### 4. [YEL] TRI_004_Plea_Bargaining_CrossBorder

**分类**: HK_CN_ASYMMETRY
**描述**: 美国辩诉交易 → PRC认罪认罚从宽映射 + 数据出境
**HK状态**: VALID | **US状态**: VALID | **CN主张**: 14条
**触发的PRC规则**: ['OVR_001_Plea_Bargaining_Restruct', 'OVR_006_Wrongful_Omission_Fill']

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

### 5. [GRN] TRI_005_Chapter11_Director_Conflict

**分类**: TRI_RESONANCE
**描述**: US Ch11 + HK越权 → 破产重组 vs 权力抑制 三维对撞
**HK状态**: SUPPRESSED | **US状态**: VALID | **CN主张**: 0条
**触发的PRC规则**: 无

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

### 6. [YEL] TRI_006_Factoring_CrossBorder

**分类**: HK_CN_ASYMMETRY
**描述**: 保理合同独立成章 vs US应收账款转让
**HK状态**: VALID | **US状态**: VALID | **CN主张**: 2条
**触发的PRC规则**: ['CN_SPEC_002_Factoring_Chapter']

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

### 7. [RED] TRI_007_Crypto_Transaction_Conflict

**分类**: CHINA_US_COLLISION
**描述**: US加密货币交易 vs PRC强制禁止
**HK状态**: VALID | **US状态**: VALID | **CN主张**: 2条
**触发的PRC规则**: ['PEN_005_Crypto_Prohibition']

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

### 8. [RED] TRI_008_VIE_Structure_Review

**分类**: CHINA_US_COLLISION
**描述**: VIE架构 vs 外商投资负面清单穿透审查
**HK状态**: VALID | **US状态**: VALID | **CN主张**: 40条
**触发的PRC规则**: ['PEN_003_Long_Arm_Interdiction', 'CN_SPEC_001_Horizontal_Veil_Piercing']

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

### 9. [RED] TRI_009_Algorithm_Filing_Block

**分类**: CHINA_US_COLLISION
**描述**: 算法未备案 + 数据出境 → PRC双阻断
**HK状态**: VALID | **US状态**: VALID | **CN主张**: 14条
**触发的PRC规则**: ['CN_SPEC_003_Algorithm_Filing']

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

### 10. [RED] TRI_010_AtWill_Employment_Conflict

**分类**: CHINA_US_COLLISION
**描述**: 美国任意雇佣 vs PRC劳动合同法解雇保护
**HK状态**: SUPPRESSED | **US状态**: VALID | **CN主张**: 0条
**触发的PRC规则**: ['BLK_019_AtWillEmployment']

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

### 11. [YEL] TRI_011_Pure_Domestic_CN

**分类**: HK_CN_ASYMMETRY
**描述**: 纯中国大陆境内保理合同——不应触发任何跨境阻断
**HK状态**: VALID | **US状态**: VALID | **CN主张**: 2条
**触发的PRC规则**: ['CN_SPEC_002_Factoring_Chapter']

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

### 12. [GRN] TRI_012_CN_Bridge_Verification

**分类**: TRI_RESONANCE
**描述**: 跨境合同违约 + 损害赔偿 → CN 2,117条规则触发验证
**HK状态**: VALID | **US状态**: VALID | **CN主张**: 66条
**触发的PRC规则**: 无

| 维度 | 审计问句 | 结论 | 修复动作 |
|------|----------|------|----------|
| 1. 算子完整性 | ASYMMETRY时是否有FORCE_VOID未被唤起? | | |
| 2. 主权锚定 | 是否显式标记is_prc_sovereign_boundary? | | |
| 3. 证据链路 | 低置信度根因是动议复杂还是证据不足? | | |
| 4. 战术一致性 | Action是否过度牺牲胜率? | | |
| 5. 版本溯源 | source_hash是否最新? | | |

---

## 三、 审计产出 → 补丁工厂

| 发现类型 | 修复路径 |
|----------|----------|
| 逻辑缺失(FORCE_VOID未触发) | blocking_rules.yaml 新增规则 |
| 数据缺失(证据不足) | Legal-CN 技能补充案例索引 |
| 推演路径错误 | OperatorRegistry 更新执行函数 |
| 程序正义缺口 | 下迭代 — 送达违规/程序不透明防御 |