# AGENTS.md — juris-calculus 开发全史

> CCD→Codex 桥接。来源：Codex归档(41)/活跃区(30+)/CCD(6)/开发日志(18天,560KB)。

---

## 项目定位

juris-calculus = 法域无关的符号法律推理编译器。核心设计：大模型只做"摘原文+贴标签"，确定性规则引擎做"裁判"。

GitHub: https://github.com/laubeing-droid/juris-calculus
版本: v1.2.0-TriRail → V2.0 升级中 (107文件)
Tag: v1.0.0 / v1.0.1 / v1.0.2 / v1.0.3 / v1.1.0 / v1.2.0

---

## 开发时间线总览 (5/23—6/13, 22天)

| 日期 | 核心 | 产出 |
|------|------|------|
| 5/23 | liuweibin-legal-skills 技能库重构 | 13个Skill + 4个检查门 |
| 5/27 | 论文V1.0初稿(380案) + 交通事故计算器 | 初版论文 |
| 5/29 | WorkBuddy首启 + v4.0法律产品库路线图 | 6仓库全局扫描 |
| 5/30 | v4.0完整设计(22决策+47🔴+23修正) | 5份审计文档 |
| 5/31 | SPC裁判规则数据库全量构建 | 20本教材→2,891→2,117条规则 |
| 6/1 | LegalOS重构设计(13h) + juris-calculus点火 | 内核三件套+380案T1=100% |
| 6/2 | juris-calculus v1.0.2发布 + 论文V1.2投稿 | 开源版35文件 |
| 6/3 | SPC↔juris桥接(v5.3 Schema) + 13/13基准收敛 | 2,117条93%HORN |
| 6/4 | v1.0.3发布 + v1.2.0-TriRail三轨对撞 | 107文件+49/49测试+68算子 |
| 6/5 | Harvey Benchmark实验 + ULA并库版权清洗 | R1→R4四轮实验 |
| 6/6 | 14项算法改进 + pre-release-auditor + 法律蒸馏v2 | P0-P2执行方案 |
| 6/7 | Win11 Home→Pro + Claude Desktop 3p安装 | 工具链准备 |
| 6/8 | Claude全量数学逆向工程(8报告+20定理) | 47公式+23算法 |
| 6/9 | Codex形式化验证(12门类) + Claude 20→46证明收敛 | PASS 0→20/20 |
| 6/10 | 数据归档+8报告翻译+Codex审计7FAIL→全修复 | 实验数据统一 |
| 6/11 | 数学模型深挖(P0-P4) + V2.0架构重设计 | 10深挖方向+8周计划 |
| 6/12 | Claude算法升级方案 + V2.0工程融合 | 7-2目录+4报告 |
| 6/13 | HK DDL+模态分类+De Jure审计+CI | 2,117→2,129规则 |

---

## SPC裁判规则数据库 (5/31, 2,891→2,117条, 13领域)

### 五Agent流水线
```
Agent1 拆章: 20本OCR→189章
Agent2 蒸馏: 4组并行(DeepSeek V4 Flash), ~$0.09/轮
Agent3 向量化: bge-large-zh, 2,117×1024维 ChromaDB, 7分40秒
Agent5 去重+QC: 2,891→1,926→2,063→2,117条
Agent6 终审: 6维度91%通过(LDQ 58%因codices缺库)
```

### 质量倒查12维度
- 中文标点643处→0 | rule_id冲突188→0 | 编码污染0
- 增量补空: 裁判规则52%→0.1% | 法条依据47.8%→1.9%
- 版权清洗: 去书名+教辅措辞+碎片过滤1,504条

### 领域覆盖
民商事600/刑事410/知产192/涉外商事188/行政150/立案100/环境96/国赔81/未成年75/审判监督63/执行51/审判管理65/涉港澳43

---

## LegalOS重构设计 (6/1, 13h全天)

### 豆包6轮架构对话 → 三层形式语义
- Legal Type System (base/normative/procedural)
- Legal IR Operational Semantics (State→Transition→Input→Output组合子)
- Rule Algebra (compose/conflict/derive)

### 内核设计 (15:27-16:56, 93分钟)
- P0-2: bounded non-monotonic reasoning(有界非单调推理)
- Kripke程序状态模型: K=(W,R,V_Σ), |W|≤3, 分叉≤2, 质证循环≤3
- FixpointEvaluator + TaintChain + TransitionGuard
- M1-M9九数学模型全部定义
- 配置驱动封板: YAML驱动+Schema封板

### 全产业链扩展 (19:15-22:00, ~180分钟)
- M10-M17八外围模型Python实现全跑通
- EvidenceCopilot/ArgumentLint/LiabilityShield/ContractReviewCore四模块确定

### juris-calculus点火 (23:00-次日01:30)
- v1.0首次点火: 19案 T1=19/19 T2=29%
- v2.0全量盲测: 225案 T1=225/225 T2=26%
- v3.0系统修复: P0-1映射层+P0-2反向索引+CRITICAL_CLARITY_FAILURE熔断
- 380案全量: T1=380/380 T3=0.92h
- α常数终极校准: 刘律师标注10案→Theil-Sen中位数回归 α=1.43h/节点
- Parser 3.0升级: 6类因果弧+审级自动识别+DP影子节点
- v1.0.0开源版: 35文件, 0pycache, 0个人信息

---

## juris-calculus版本演进

### v1.0.0→v1.0.2 (6/2凌晨)
- 5项导入修复(evaluator→FixpointEvaluator)
- performance: ThreadPoolExecutor并行+LRU→原生dict
- 5单元测试全通过, 发布v1.0.2

### v1.0.3发布 (6/4, 32轮对话, 5.5h)
**核心: SPC桥接+算法增强**
- domain_schemas.py新增4推理字段
- convert_to_juris_rules.py: 谓词21→68组, 13域84%覆盖
- ontology_map.yaml v4.0: 13法域物理隔离, 132+事实原子
- 概念注入: 1,453次标签, 概念1,921, 平均2.44/条
- 基准测试: 13/13收敛100%
- 推GIT: 71 files +36,733/-895

### v1.2.0-TriRail三轨对撞 (6/4下午, 6h)
**三轨: CN(2,117条) + CBL(60条阻断) + SPC(23条裁判倾向)**
- US_Adapter: 81条Horn+86条约束, 69KB
- 12场景三轨对撞: 7COLLISION+3ASYMMETRY+2RESONANCE
- Gemini三轮审计: 15项修复(P0-3)
- OperatorRegistry: 68算子自举(bootstrap_from_yaml)
- MCP Server: 9资源+7工具
- ShadowRunner: 多实例+对抗生成+逻辑哈希比对
- 49/49测试通过 | Tag: v1.2.0

---

## Harvey's Long Horizon Legal Agent Benchmark (6/5)

3轮×2法域×2模式=12格+R4评分校准
- CN侧: 反向索引使原子数+11.5x(4.9→56.4), 收敛率+6.8pp(38.8%→45.6%)
- US侧: 任务覆盖100%, 原子+28x
- 结论: JC(符号推理)与LLM是两种不可通约的推理范式

---

## 14项算法改进方案 (6/6)

| P0(4项) | 问题 | 方案 |
|:--:|------|------|
| #0 | 单前提规则31.9% | Context Guard注入namespace锚点 |
| #1 | 结论200+→砍97.7% | BM25+BGE混合评分Top-5~8 |
| #2 | 语义匹配器T1=0% | 英文谓词ID→中文描述 |
| #3 | T2诚实拒算=0% | 补16自由裁量概念, 阈值0.4 |

| P1(5项) | #4链式推导 | #5CBL/SPC入reverse_index | #6US阈值子句 | #7CN桥接健康度 | #13MCP独立进程 |
| P2(5项) | 交叉下毒/增量流式/OCR概念/R1映射扩展/质量审计 |

执行顺序: #2→#1→#9→#3→#0→#4/#5/#6/#7/#13→#10/#11/#12

---

## 形式化证明全线

### Claude数学逆向工程 (6/8-6/10, 两个子代理)
- Subagent1: 104KB英文数学逆向工程报告 (47公式+23算法+38常量)
- Subagent2: 中文翻译版
- 关键发现: Theil-Sen斜率裁剪[0.01,10.0]破坏崩溃点 | λ=0.65缺乏依据 | DP floor裁剪O(1/x0²)偏置

### 20项定理→46/46收敛 (6/9)
- 第一轮8项: Galois连接/k≤3 Horn编译/证据公理/Kripke互斥/LTL/Policy复杂度/GV soundness/TriRail 8-SAT
- 第二轮6项: Rule Algebra+Tribunal+Horn-Dung+Counts-as+RoughSet+层次贝叶斯+范式不可通约+道义逻辑
- 第三轮6项: 非干涉信息流+范畴论反罗塞塔+Banach压缩+DPε↔特权+抽象解释统一+20项目录
- 总计: 84定理, exit code 0全通过

### Codex对抗性审计 (6/9, 12门类工具链)
- 7FAIL披露: Banach c=1.0(非c<1) | Horn-Dung代码反驳定理 | 自然变换is_natural=True | GV简化模型≠真实引擎 | DP can_share_with方向反 | 信息流allows_flow方向反 | Counts-as缺GV规则
- 4轮自修复→20/20 PASS
- 12验证门类: Python/Hypothesis/Z3/CrossHair/TLA+/Alloy/Lean/Dafny/py_compile/unit_tests

### 目前可信度矩阵
- graph similarity严格自反性: **REFUTED** (sim(G,G)=0.4)
- graph similarity范围[0,1]: SMT_PROVED_FINITE (Z3+Dafny)
- Fixpoint收敛: MIXED (TESTED+MODEL_CHECKED)
- DP ratio-preserving: EMPIRICAL_HYPOTHESIS
- Galois connection: LEAN_PROVED_SKELETON only
- Banach contraction c=0.5: 解析证明(仅effective_nodes)

---

## 数学模型深挖方向 P0→P4 (6/11)

| P0: 数学根基 | P1: 模型校准 | P2: DP形式化 | P3: 跨法域 | P4: 论文叙事 |
|------|------|------|------|------|
| Lean Galois有限域证明 | 38常量→YAML+OAT敏感性 | DP tuple-level隐私语义 | Alloy自然变换证明 | Dung AAF形式化defeasibility |
| graph similarity公理化 | Theil-Sen→Siegel重复中位数(50%崩溃点) | floor clipping偏置修正 | Kripke互斥性SMT推广 | 三轨博弈论建模 |

执行原则: **先反例发现→有限域证明→模型检查→机器数学证明。** 禁止把Hypothesis"未发现反例"写成数学证明。

---

## V2.0 六层架构

```
Layer 1: 大模型编码对接层 (MCP/CLI接口)
Layer 2: 事实梳理层 (证据A/B/C分类+源锚定+编辑距离硬校验)
Layer 3: 法律预推理层 (Negative Spec反向要件缺口+自由裁量毒化标记)
Layer 4: 要件计算层 (Horn子句+Fixpoint不动点迭代, k≤3坍缩)
Layer 5: 规则群混合专家模式 (MoE for YAML,按领域门控)
Layer 6: 神经网络强化层 (末段小型NN节点,自适应升级)
```

### 核心模块
- EvidenceCopilot: Negative Spec + carrier_level A/B/C + 源锚定
- ArgumentLint: 意图声明 + required_type + 反模式
- LiabilityShield: SHA-256哈希链 + 双轨日志 + 微摩擦RSK
- ContractReviewCore: 博弈姿态 + 行业惯例 + 交叉下毒六模式

### 参考仓库
- MetaInfer/MetaInfer: LLM编译器优化
- RUC-NLPIR/LawThinker-agent: 15个法律推理工具
- 陈石/legalwiki: 43,000+篇LLM Wiki方法论

### 已确认决策
- 数据出境: DeepSeek-V4远程API
- 法律数据来源: 自己找权威资料蒸馏
- 跨法域: 优先中文版
- 新增模块: 文书模板工厂+当事人沟通+法院策略库
- 推迟模块: 运营驾驶舱+定价辅助

---

## 技术工具栈

| 工具 | 版本 | 用途 |
|------|------|------|
| OpenCLI | 1.8.0 | 150+站点CLI |
| browser-harness | 0.1.0 | CDP浏览器操控 |
| codegraph | 0.9.9 | 语义代码索引 |
| Understand-Anything | — | 8个代码理解skill |
| CLI-Anything | 0.3.0 | 80个GUI→CLI |
| PaddleOCR | 2.9.1 | OCR文档解析 |
| liteparse | 2.0.0 | PDF文档解析 |
| Z3 | 4.16.0 | SMT求解器 |
| Dafny | 4.11.0 | 形式化验证 |
| Lean 4 | 4.30.0 | 定理证明 |
| TLA+ | — | 模型检查 |
| Alloy | — | 关系逻辑 |

---

## 关键路径速查

| 用途 | 路径 |
|------|------|
| 项目源码 | D:\Codex\juris-calculus\源码\ |
| 实验数据 | D:\同步网盘\软件开发\论文\实验数据\ (1~7-2) |
| 开发日志 | D:\同步网盘\软件开发\日志\ (5/23-6/12, 18天, 560KB+) |
| 升级方案 | D:\同步网盘\软件开发\论文\实验数据\7-2.20260612 Claude算法升级方案\ |
| CCD会话 | ~/.claude/projects/D--Codex-juris-calculus/ (11条已注册, 17MB+) |
| Codex归档 | ~/.codex/archived_sessions/ (41条) |
| Codex活跃 | ~/.codex/sessions/2026/06/ (30+条) |
| Codex sqlite | ~/.codex/backups/*/state_5.sqlite.before (75线程,7副本) |
| 代理ccswitch | AppData/Local/com.ccswitch.desktop |
| codex++配置 | AppData/Local/com.bigpizzav3.codexplusplus.manager |
| 论文V1.2 | 存疑即熔断:约束大模型法律幻觉的符号推理机制建模与初步验证 |
| 投稿目标 | 2026年福建律师论坛(截止7/20) |
