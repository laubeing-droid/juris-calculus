# 高危路径逻辑审计检查表 — 12 个收敛点 (已完成)
## 版本: v1.2.0 | source_hash: f7fc1b4e61db | 审计日期: 2026-06-04

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
| BLK_021_Discovery_Fishing | 1 | FV(FastPath) |
| PEN_002_Secondary_Sanction_Block | 1 | FORCE_SUPPRESS |
| PEN_004_OFAC_CounterCollision | 1 | FORCE_SUPPRESS |
| OVR_001_Plea_Bargaining_Restruct | 1 | MAPPING |
| OVR_006_Wrongful_Omission_Fill | 1 | MAPPING |
| PEN_005_Crypto_Prohibition | 1 | FORCE_VOID |
| PEN_003_Long_Arm_Interdiction | 1 | FORCE_SUPPRESS |
| CN_SPEC_001_Horizontal_Veil_Piercing | 1 | MAPPING |
| CN_SPEC_003_Algorithm_Filing | 1 | FORCE_SUPPRESS |
| BLK_019_AtWillEmployment | 1 | FORCE_VOID |

---

## 二、 逐条五维审计 (已填写)

### 1. [RED] TRI_001 — HK董事越权 + US Cloud Act数据请求

**HK**: SUPPRESSED (director ultra vires) | **US**: VALID | **CN**: 0 claims  
**PRC触发**: PEN_001 FORCE_VOID (数据出境安全)

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ✅ 正确。Cloud Act请求→数据出境→PEN_001一票否决 | 无需修复 |
| 2. 主权锚定 | ✅ PEN_001自带sovereignty_anchoring=True | 已满足 |
| 3. 证据链路 | ⚠️ CN=0 — 跨法域桥接未触发。事实流缺CN-native atoms | 桥接表可追加Cloud_Act→data_transfer映射 |
| 4. 战术一致性 | ✅ FORCE_VOID是最强响应，无过度牺牲 | 已满足 |
| 5. 版本溯源 | ✅ f7fc1b4e61db 为最新 | 已满足 |

### 2. [RED] TRI_002 — US诉前证据开示 + 资产混同

**HK**: ? | **US**: ? | **CN**: 0 claims  
**PRC触发**: BLK_021 FORCE_VOID (FastPath截获Discovery Fishing)

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ✅ Discovery被FastPath截获→直接CBL阻断。零毫秒响应 | 无需修复 |
| 2. 主权锚定 | ⚠️ FastPath绕过LegalTaskSchema校验，未显式声明 | FastPath应补充sovereignty日志 |
| 3. 证据链路 | ✅ FastPath不走Horn，零推理风险 | 已满足 |
| 4. 战术一致性 | ✅ Discovery钓鱼式开示—理应物理阻断 | 已满足 |
| 5. 版本溯源 | ✅ 最新 | 已满足 |

### 3. [RED] TRI_003 — OFAC制裁 vs 反外国制裁法第12条

**HK**: VALID (2 claims) | **US**: VALID | **CN**: 2 claims  
**PRC触发**: PEN_002 + PEN_004 FORCE_SUPPRESS

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ✅ 双轨阻断正确。OFAC→反制，次级制裁→阻断 | 无需修复 |
| 2. 主权锚定 | ✅ 两个算子均sovereignty_anchoring=True | 已满足 |
| 3. 证据链路 | ⚠️ HK输出2条claims但US=0——HK合同链触发但US未匹配 | HK-US事实空间不对齐，非PRC问题 |
| 4. 战术一致性 | ✅ FORCE_SUPPRESS而非FORCE_VOID——制裁场景下抑制更精准 | 已满足 |
| 5. 版本溯源 | ✅ 最新 | 已满足 |

### 4. [YEL] TRI_004 — 美国辩诉交易 → PRC认罪认罚从宽

**HK**: VALID | **US**: VALID | **CN**: 14 claims  
**PRC触发**: OVR_001 + OVR_006 MAPPING only

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ⚠️ 仅MAPPING无FORCE_VOID。辩诉交易在中国不非法，仅制度不同 | **不需改为FV**——MAPPING是正确的 |
| 2. 主权锚定 | ✅ 制度差异已标注，未误触发主权阻断 | 已满足 |
| 3. 证据链路 | ✅ CN=14——认罪认罚相关条文激活 | 已满足 |
| 4. 战术一致性 | ✅ MAPPING保留战术空间——可在认罪认罚框架内谈判 | 已满足 |
| 5. 版本溯源 | ✅ 最新 | 已满足 |

### 5. [GRN] TRI_005 — Ch11破产 + HK董事越权 ⚠️ 重点审计

**HK**: SUPPRESSED | **US**: VALID (DIP维持资产运作) | **CN**: 0 claims  
**PRC触发**: 无 (BLK_001门控: 无Foreign_Connected_Entity)

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ❌ 无PRC触发。但Ch11+越权是典型跨境高危场景 | **建议追加**：Ch11场景即使无Foreign_Connected_Entity也应至少触发Observation_Mode |
| 2. 主权锚定 | ❌ 未标记。系统判定无涉外主体故跳过 | 在TRI_005事实流中追加Foreign_Connected_Entity=NOMINEE(代持)以测试 |
| 3. 证据链路 | ⚠️ 事实流缺代持/隐名股东标识——这是真实跨境漏洞 | CN桥接需要识别代持结构的trigger fact |
| 4. 战术一致性 | ❌ RESONANCE意味着"安全"——但Ch11+越权不可能是安全的 | 改为至少YELLOW预警 |
| 5. 版本溯源 | ✅ 最新 | 已满足 |
| **修复优先级: HIGH** | **BLK_001应追加NOMINEE_STRUCTURE作为备选门控条件** |

### 6. [YEL] TRI_006 — 保理合同 vs US应收账款转让

**HK**: VALID | **US**: VALID | **CN**: 2 claims  
**PRC触发**: CN_SPEC_002 MAPPING only

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ✅ 保理在中国为独立有名合同——MAPPING是最优响应 | 无需改为FV |
| 2. 主权锚定 | ✅ 制度差异，不涉外 | 已满足 |
| 3. 证据链路 | ✅ CN=2——民法典保理章触发 | 已满足 |
| 4. 战术一致性 | ✅ 保留商业谈判空间 | 已满足 |
| 5. 版本溯源 | ✅ 最新 | 已满足 |

### 7. [RED] TRI_007 — 加密货币交易

**HK**: VALID | **US**: VALID | **CN**: 2 claims  
**PRC触发**: PEN_005 FORCE_VOID

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ✅ 全面禁止，一票否决 | 无需修复 |
| 2. 主权锚定 | ✅ sovereignty_anchoring=True, allow_settlement=False | 已满足 |
| 3. 证据链路 | ✅ CN=2——非法经营/洗钱相关规则 | 已满足 |
| 4. 战术一致性 | ✅ Crypto场景无妥协空间 | 已满足 |
| 5. 版本溯源 | ✅ 最新 | 已满足 |

### 8. [RED] TRI_008 — VIE架构穿透审查

**HK**: VALID | **US**: VALID | **CN**: 40 claims (最高)  
**PRC触发**: PEN_003 FORCE_SUPPRESS + CN_SPEC_001 MAPPING

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ✅ 双轨并发: 长臂阻断+横向否认 | 无需修复 |
| 2. 主权锚定 | ✅ 两个算子均强锚定 | 已满足 |
| 3. 证据链路 | ✅ CN=40——所有关联公司/代持/穿透规则触发 | 这是系统的典范响应 |
| 4. 战术一致性 | ✅ FORCE_SUPPRESS+MAPPING组合——最强的合法响应 | 已满足 |
| 5. 版本溯源 | ✅ 最新 | 已满足 |
| **审计结论: 典范场景。40条CN规则+2轨PRC阻断=系统最高防御状态。** |

### 9. [RED] TRI_009 — 算法备案阻断

**HK**: VALID | **US**: VALID | **CN**: 14 claims  
**PRC触发**: CN_SPEC_003 FORCE_SUPPRESS

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ✅ 算法未备案即运营→SUPPRESSED | 无需修复 |
| 2. 主权锚定 | ✅ 算法备案为中国独有制度 | 已满足 |
| 3. 证据链路 | ✅ CN=14 | 已满足 |
| 4. 战术一致性 | ✅ 无妥协——必须备案 | 已满足 |
| 5. 版本溯源 | ✅ 最新 | 已满足 |

### 10. [RED] TRI_010 — 任意雇佣

**HK**: SUPPRESSED | **US**: VALID | **CN**: 0 claims  
**PRC触发**: BLK_019 FORCE_VOID

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ✅ At-will employment→劳动合同法保护→一票否决 | 无需修复 |
| 2. 主权锚定 | ✅ sovereignty_anchoring=True | 已满足 |
| 3. 证据链路 | ⚠️ CN=0——劳动合同法条文未激活(可能需要specific CN atoms) | 桥接表追加employment→labor_contract映射 |
| 4. 战术一致性 | ✅ 无妥协空间 | 已满足 |
| 5. 版本溯源 | ✅ 最新 | 已满足 |

### 11. [YEL] TRI_011 — 纯境内保理 ⭐ 关键场景

**HK**: VALID | **US**: VALID | **CN**: 2 claims  
**PRC触发**: CN_SPEC_002 MAPPING only

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ✅ 纯境内场景准确无误触发跨境阻断 | 这是门控生效的铁证 |
| 2. 主权锚定 | ✅ 境内场景不需要主权锚定 | 已满足 |
| 3. 证据链路 | ✅ CN=2——民法典保理规则激活 | 已满足 |
| 4. 战术一致性 | ✅ 纯境内=正常商事行为 | 已满足 |
| 5. 版本溯源 | ✅ 最新 | 已满足 |
| **审计结论: BLK_001双重门控(Cross_Border_Context+Foreign_Connected_Entity)在此场景中正确生效——纯境内保理未误触发任何阻断。** |

### 12. [GRN] TRI_012 — CN桥接验证

**HK**: VALID (2 claims) | **US**: VALID | **CN**: 66 claims (峰值)  
**PRC触发**: 无

| 维度 | 结论 | 修复动作 |
|------|------|----------|
| 1. 算子完整性 | ✅ CN=66——跨法域桥接全通。合同+侵权+公司+程序规则全部激活 | 无需修复 |
| 2. 主权锚定 | ✅ 纯合同违约无主权问题 | 已满足 |
| 3. 证据链路 | ✅ 66条CN规则=桥接表26条映射全命中 | 已满足 |
| 4. 战术一致性 | ✅ 纯境内合同→正常履行 | 已满足 |
| 5. 版本溯源 | ✅ 最新 | 已满足 |
| **审计结论: CN桥接完美验证——跨法域事实→2,117条CN规则→66条主张。** |

---

## 三、 审计产出 → 补丁工厂

| 优先级 | 发现 | 场景 | 修复动作 |
|--------|------|------|----------|
| **HIGH** | Ch11+越权无PRC触发——缺NOMINEE代持门控 | TRI_005 | BLK_001追加 NOMINEE_STRUCTURE 作为备选门控条件 |
| MEDIUM | FastPath绕过LegalTaskSchema校验 | TRI_002 | FastPath补充sovereignty日志记录 |
| MEDIUM | CN桥接未覆盖Cloud Act→数据出境映射 | TRI_001 | 桥接表追加Cloud_Act→data_transfer |
| MEDIUM | CN桥接未覆盖employment→labor_contract | TRI_010 | 桥接表追加employment→labor_contract |
| LOW | EN-ALL 全部正确 | TRI_003/006/007/008/009/011/012 | 无需修复 |

## 四、 下迭代行动计划

1. **程序正义防御**: 送达违规(Order 11域外送达抗辩)/程序不透明
2. **代持/隐名结构识别**: TRI_005暴露的NOMINEE漏洞
3. **CN桥接表扩展**: 26→40+条，覆盖更多HK/US→CN原子映射
