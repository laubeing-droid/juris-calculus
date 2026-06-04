# juris-calculus v1.2.0 — 三轨对撞 · Tri-Rail

**跨法域符号化法律推理引擎，带跨法域冲突检测。**

不动点评估器 + 三轨对撞机（中国 × 香港 × 美国）+ PRC-US 法律语义对齐框架。

*不是本土化法律应用。是通用法律推理内核。*

[*English README*](README.md)

---

## v1.2.0 新特性

- **三轨对撞机**：将同一事实模式送入 PRC、HK、US 三条平行推理链，检测 12 类跨法域冲突
- **PRC-US 语义对齐框架**：60 条 CBL 阻断规则 + 23 条最高法裁判倾向 + 10 条程序正义防御 — 防止美国法律概念污染中国法律推理
- **香港法扩充**：从香港电子版法例蒸馏 93 条 Horn 规则（Cap 26、32、622、571、4A）
- **行动代理**：通过 Jinja2 模板将对撞机输出自动生成合伙人级法律备忘录
- **MCP 协议服务端**：9 个资源 + 7 个工具，支持 AI 助手集成
- **算子注册中心**：68 个算子的 bootstrap/snapshot/rollback，带 JSON Schema 校验

---

## 架构

```
juris-calculus/
├── compiler_core/            # 不动点推理内核
│   ├── evaluator.py          #   FixpointEvaluator + 例外链 + 关键清晰度熔断
│   ├── types.py              #   LegalRule / LegalFact / LegalClaim / NegativeSpec
│   ├── domain_config.py      #   民刑双域路由 + 自由裁量概念检测
│   ├── classifier.py         #   EvidenceClassifier（A/B/C 证据载体等级）
│   └── parallax_inference.py #   跨法域推理引擎
│
├── pipeline/                 # 端到端推理管线
│   ├── prc_us_alignment.py   #   PRC-US 对齐看门狗（三层门控）
│   ├── alignment_loader.py   #   YAML 规则热加载（含 FastPath）
│   └── guardian.py           #   NOMINEE 门控 + 错误分类器
│
├── adapter/
│   └── prc_adapter.py        #   PRC 三轨引擎（CBL 阻断 + SPC 倾向 + CN 2,117 条）
│
├── configs/
│   ├── zh_CN/                #   中国民法典：13 领域，2,117 条 Horn 规则
│   ├── en_US/                #   美国联邦法：81 条 Horn + 86 条约束
│   ├── hk/                   #   香港法：93 条 Horn（Cap 26/32/622/571/4A）
│   ├── prc_us_alignment/     #   PRC-US 桥接：阻断规则 + 裁判倾向 + 术语映射
│   └── us/threat_signatures/ #   美国州级 FastPath 签名（WI 12 + NJ 12）
│
├── tools/                    # 对撞测试 + 维护
│   ├── run_trirail_matrix.py #   三轨对撞机：12 种跨法域冲突场景
│   ├── press_long_tail.py    #   3,800 条长尾饱和引擎
│   ├── distill_jurisdiction.py#  法域蒸馏工作台
│   └── action_agent/         #   MemoCompiler：对撞输出 → 合伙人备忘录
│
├── mcp_server.py             # FastMCP 服务端（9 资源 + 7 工具）
└── mcp_manifest.json         # MCP 协议清单
```

---

## 支持的法域

| 法域 | 规则数 | 领域 | 状态 |
|------|--------|------|------|
| **中国**（民法典） | 2,117 | 13 领域（合同/侵权/公司/刑事/行政/知产…） | v1.2.0 |
| **美国**（联邦） | 81 Horn + 86 约束 | UCC 第2条、正当程序、衡平救济 | v1.2.0 |
| **美国**（州级威胁） | 24 签名 | WI 长臂管辖、NJ 惩罚性赔偿 | v1.2.0 |
| **香港**（法例） | 93 | Cap 26/32/622/571/4A | v1.2.0 |
| **英国** | 5 候选 | 货物买卖法 | 社区 |
| **PRC-US 对齐** | 60 CBL + 23 SPC + 10 程序 | 跨法域阻断 + 防御 | v1.2.0 |

---

## 为什么与众不同

| | 法律 RAG（多数仓库） | juris-calculus |
|---|---|---|
| **逻辑** | 概率式（LLM） | 确定性（不动点迭代） |
| **审计** | 黑箱（Prompt） | 白箱（DAG 追溯链） |
| **跨法域** | 无 | 三轨对撞机（12 类冲突） |
| **幻觉** | 高 | 低（诚实拒算 + 关键清晰度熔断） |
| **范式** | 聊天机器人 | 符号 AI / 计算法学 |
| **PRC-US 对齐** | 无 | 60 条 CBL 阻断规则 |

---

## 三轨对撞机

将同一事实送入三条平行的法律推理链：

```
事实 → [PRC 适配器（CBL 门控 + SPC 倾向 + CN 成文法）]
     → [HK 引擎（93 条 Horn 规则）]
     → [US 引擎（81 联邦 + 86 约束 + 州级 FastPath）]

     → 冲突矩阵（12 类冲突）
     → MemoCompiler（合伙人级备忘录）
```

**12 类检测冲突**：越权数据出境、诉讼证据开示僵局、OFAC 制裁冲突、跨境辩诉交易、Chapter 11 董事冲突、跨境保理、加密交易、VIE 架构、算法备案阻断、任意雇佣冲突、纯国内 CN 案件、CN 桥接验证。

---

## 快速开始

```bash
git clone https://github.com/laubeing-droid/juris-calculus.git
cd juris-calculus
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
print(f"推导主张: {len(result.claims)}, 污点: {len(result.tainted)}")
```

---

## 许可证

Apache 2.0

## 作者

Laupinco — Hokkien Computational Jurisprudence Enthusiast
