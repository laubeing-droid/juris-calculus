# juris-calculus v1.2.0 — Tri-Rail

**跨法域符号化法律推理引擎 | 三轨对撞机**

---

## 核心特性

### 🔺 三轨对撞机 (Tri-Rail Collider)
将同一事实模式送入 PRC、HK、US 三条平行推理链，检测 **12 类跨法域冲突**：

| # | 冲突类 | 典型场景 |
|---|--------|---------|
| TRI-001 | 越权数据出境 | 中国子公司向美国母公司传输用户数据 |
| TRI-002 | 诉讼证据开示僵局 | US discovery 要求 vs 中国国家秘密 |
| TRI-003 | OFAC 制裁冲突 | 涉伊朗交易 vs 中国阻断法令 |
| TRI-004 | 跨境辩诉交易 | 美国 plea bargain vs 中国认罪认罚 |
| TRI-005 | Chapter 11 董事冲突 | 破产受托人 vs 中国公司法董事义务 |
| TRI-006 | 跨境保理 | UCC Article 9 vs 中国应收账款质押 |
| TRI-007 | 加密交易冲突 | 美国证券法 vs 中国虚拟货币禁令 |
| TRI-008 | VIE 架构审查 | 开曼控股 vs 中国外资准入 |
| TRI-009 | 算法备案阻断 | 美国出口管制 vs 中国算法备案 |
| TRI-010 | 任意雇佣冲突 | US at-will vs 中国劳动合同法 |
| TRI-011 | 纯国内 CN 案件 | 零跨法域要素 → 全部阻断 |
| TRI-012 | CN 桥接验证 | 跨法域事实桥接的准确度基准 |

---

### 🔐 PRC-US 语义对齐框架
防止美国法律概念污染中国法律推理的三层防御：

```
第一层：CBL 阻断规则 (60条)
       → 检测美国 L0 原语入侵，FORCE_VOID / SUPPRESS
第二层：SPC 裁判倾向 (23条)
       → 最高人民法院裁判规则 → 司法倾向 Horn 注入
第三层：程序正义防御 (10条)
       → 送达/证据/管辖的程序规则自动执行
```

**26 条跨法域事实桥接**: 自动将 HK/US 事实名映射为 CN 规则前提原子

---

### 🌏 法域覆盖

| 法域 | 规则 | 状态 |
|------|------|:----:|
| 中国 (13 领域) | 2,117 Horn | ✅ |
| 美国联邦 | 81 Horn + 86 约束 | ✅ |
| 美国州级威胁 | 24 FastPath 签名 (WI/NJ) | ✅ |
| 香港 (Cap 26/32/622/571/4A) | 93 Horn | ✅ |
| 英国 | 5 候选 | 🚧 |
| PRC-US 对齐 | 60 CBL + 23 SPC + 10 程序 | ✅ |

---

### 🛠️ 基础设施

- **MCP Server**: 9 资源 + 7 工具，`mcp_server.py`
- **Action Agent**: MemoCompiler + Jinja2 模板 → 合伙人级备忘录
- **Operator Registry**: 68 算子 bootstrap/snapshot/rollback
- **Shadow Runner**: 多实例对抗测试 + 逻辑哈希比对
- **Long-tail Engine**: 3,800 条跨法域反例饱和攻击
- **US 50-State Router**: 4 大拓扑聚类，24 条 FastPath 签名

---

## 架构

```
compiler_core/    不动点推理内核 (FixpointEvaluator + 例外链 + 熔断)
pipeline/         端到端推理管线 (PRC-US 看门狗 + 规则热加载)
adapter/          法域适配器 (PRC 三轨引擎: CBL + SPC + CN)
configs/          6 法域规则 (zh_CN/en_US/hk/prc_us_alignment/us/uk)
tools/            对撞测试 + 维护 + 蒸馏工作台
mcp_server.py     MCP 协议服务端
```

---

## 版本亮点

- **7 天，从零到 v1.2.0 全栈闭环**: v1.0.0-coldstart (HK 65 条) → v1.1.0 (65×81 矩阵) → v1.2.0 (三轨对撞)
- **12 类跨法域冲突**: 每类有完整的备忘录 + 对撞分析
- **Gemini 三轮审计**: R1(4 修复) + R2(4 修复) + R3(P0-P3 4 修复)
- **零盘符零隐私**: 全仓库 106 文件无硬编码路径、无个人身份信息

---

## 安装

```bash
git clone https://github.com/laubeing-droid/juris-calculus.git
cd juris-calculus
git checkout v1.2.0
pip install -r requirements.txt
```

```python
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.types import IRState, LegalFact

rules = load_rules_from_yaml("configs/hk/rules.yaml")
facts = IRState(facts=[
    LegalFact(atom="Seller_TransfersOrAgrees_Property", confidence=1.0),
    LegalFact(atom="Buyer_Pays_MoneyConsideration", confidence=1.0),
])
evaluator = FixpointEvaluator(rules)
result = evaluator.evaluate(facts)
```

---

## 从 v1.1.0 升级

```bash
git pull
pip install -r requirements.txt
python tools/run_trirail_matrix.py  # 验证三轨对撞机
```

---

**Full Changelog**: [v1.1.0...v1.2.0](https://github.com/laubeing-droid/juris-calculus/compare/v1.1.0...v1.2.0)

*Powered by Gemini & WorkBuddy & DeepSeek-V4 Pro*
