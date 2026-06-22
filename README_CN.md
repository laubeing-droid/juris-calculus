# juris-calculus

**确定性符号法律推理引擎 — 四阶段 Pipeline + 跨法域 + 证据校准信任标签**

法域无关的 Horn 子句引擎，支持 Dung AAF 扩展、可废止道义逻辑（DDL）模态分类、跨法域障碍优先路由、7 级信任标签系统，背后有严格数学证明支撑。

*不是法律 App，是法律推理内核。*

---

## 做什么

juris-calculus 将成文法编译为可执行 Horn 规则，通过**四阶段 pipeline** 进行推理，输出携带信任标签的法律结论。

```
Stage 1: 单调 Horn 闭包（已证明：82,836 fixtures）
    ↓
Stage 2: Dung AAF 攻击图（已证明：66,066 图）
    ↓
Stage 3: 扩展集计算（确定性，有限收敛）
    ↓
Stage 4: 信任标签投影 + allowed/forbidden 标记
```

**三个法域，一个引擎：**

| 法域 | 规则数 | 来源 | 角色 |
|------|--------|------|------|
| CN（中国） | 21,144 | 20 本书（8,712 页，727 万字） | 主法域 |
| HK（香港） | 104 | 香港法例 | US↔CN 转换层 |
| US（美国联邦） | 123 | US Code + UCC + Restatement | 跨境争议 |

**跨法域架构（障碍优先）：**

```
US 术语 ──→ L0 原语 ←── HK 术语 ──→ L0 原语 ←── CN 术语
          (Status/Act/Defect/Power/Agent/Asset)

障碍注册表：
  MATCH       → 允许映射（保留法域标签）
  COLLISION   → 禁止自动映射
  ASYMMETRY   → 禁止自动映射
  UNVERIFIED  → 仅人工审核
```

---

## 核心指标

| 指标 | 数值 |
|------|------|
| CN 规则 | 21,144 |
| 测试 | 243 passed |
| 核心模块 | 68 |
| MCP 工具 | 18 |
| 唯一概念 | 31,749 |
| 来源锚定覆盖率 | 97.1% |
| 数学证明 | 10 proved, 3 refuted, 4 pending |
| Codex 审计 | 5 轮（14 发现，全部修复） |

---

## 快速开始

```python
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.types import IRState, LegalFact

# 加载中国法规则
rules = load_rules_from_yaml("configs/zh_CN/rules.yaml")
ev = FixpointEvaluator(rules)

# 推理
state = IRState()
state.facts["contract_formed"] = LegalFact(id="contract_formed", description="合同成立")
state.facts["breach_alleged"] = LegalFact(id="breach_alleged", description="违约事实")
result = ev.evaluate(state)

# 输出：含置信度、信任标签、推理轨迹的 claims
for cid, claim in result.claims.items():
    print(f"{cid}: conf={claim.confidence:.2f}, trust={claim.get_trust_label()}")
```

---

## 四阶段 Pipeline

```python
from compiler_core.stratified_evaluator import StratifiedEvaluator

se = StratifiedEvaluator("configs/zh_CN/rules.yaml")
state = IRState()
state.facts["breach"] = LegalFact(id="breach", description="违约")

claims = se.evaluate(state)
# 每个 claim 携带：allowed_claim, forbidden_claim, agent_instruction, epistemic_status
```

**Stage 1**（Horn）：纯前向链，单调（Tarski 不动点存在）。
**Stage 2**（AAF）：从规则、例外、反驳、禁止构建攻击图。
**Stage 3**（GE）：Dung 扩展集 — 确定性接受/拒绝。
**Stage 4**（标签）：信任标签投影 + allowed/forbidden 标记。

---

## 数学基础

由 [legal-math-modeling](https://github.com/laubeing-droid/legal-math-modeling) 仓库支撑：

| 命题 | 状态 | 证据 |
|------|------|------|
| Horn 闭包单调 | **已证明** | 82,836 fixtures |
| Dung 扩展存在+唯一 | **已证明** | 66,066 图 |
| Evaluator 非单调 | **已反证** | A={a}, B={a,b} |
| 有界操作终止 | **已证明** | 5 个操作边界 |
| Graph similarity 是度量 | **已反证** | CE-001, CE-002 |
| DP epsilon 可从法律推导 | **已反证** | two-model witness |
| 跨法域全函子存在 | **已反证** | obstruction witnesses |

**信任标签系统（7 级）：**
UNVERIFIED → ENGINEERING_BASELINE → DATA_INSUFFICIENT → TOY_SYNTHETIC → TESTED_PROPERTY → SMT_PROVED → PROVED_FORMAL → PROVED_BY_EXHAUSTIVE_ENUMERATION

---

## 安装

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

---

## 许可证

MIT
