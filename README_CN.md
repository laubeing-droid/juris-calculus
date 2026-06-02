# juris-calculus v1.0.2 — 中文说明

> 一个跨法域通用的法律符号化推理与精密精算引擎。
>
> Fixpoint 不动点迭代 + Theil-Sen 稳健中位数回归 + 拉普拉斯差分隐私。
>
> **不是本土化法律应用。是通用法律推理内核。**

> **这是 PostgreSQL，不是 Windows。**
>
> juris-calculus 是一个*法律推理内核*——它提供逻辑引擎、审计追踪和精算分析。它不管理文档、邮件或日程。如果你在找一站式律师办公套件，这是你可以构建它的引擎，不是你可以日常使用的界面。

[*English README*](README.md)

---

## 为什么与众不同

大多数法律 AI 工具是 LLM 的 RAG 外壳。juris-calculus 走了相反的路。

| | Legal RAG（多数仓库） | juris-calculus |
|---|---|---|
| **逻辑** | 概率式（LLM） | 确定性（Fixpoint） |
| **审计** | 黑箱（Prompt） | 白箱（DAG 追溯链） |
| **定价** | 凭感觉 | Theil-Sen 中位数回归校准 |
| **幻觉** | 高 | 低（诚实拒算） |
| **范式** | Chatbot | 符号 AI / 计算法学 |

---

## 技术底色

### FixpointEvaluator — 不动点推理内核

这不是一个调用大模型 API 的 Prompt 包装器。FixpointEvaluator 是 200 行纯 Python 的确定性推理状态机，包含：

- **例外链穿透**：规则之间的例外关系被建模为有向无环图（DAG），引擎在遇到例外时会递归穿透至最底层
- **概念注册表评分**：每条规则的 formalizable_score 由其深度、Horn 类型、概念覆盖率和机械例外性四维加权决定
- **CRITICAL_CLARITY_FAILURE 熔断**：连续 N 条低置信度推理自动触发诚实拒算，拒绝在不可靠的推理链上继续推进
- **隐式依赖检测**：跨例外链边界的"另有规定/除非"等隐式依赖被前置扫描并告警

### 四大数学模型

| 模型 | 功能 |
|------|------|
| DAG 加权节点 | 因果弧线密度替代词汇计数：入度/出度 × 法域穿透系数 |
| 多因子精算矩阵 | B_location × Γ_stage × H（人力杠杆向量）+ T_overhead |
| 批量指数衰减 | Cost_n = N × α × n^(-0.65)，类案复制自动折扣 |
| 拉普拉斯差分隐私 | 金额加噪 + 本金/利息/罚息比例保持（误差 0.00%） |

### 10 案美国法基准测试

juris-calculus 附带一份基于真实美国联邦法院判例的基准测试集：

- **核心测试 (core/)**：Twitter v. Musk (C.A. No. 2022-0613-KSJM, Del. Ch.) — 合同强制履行
- **路线图测试 (roadmap/)**：Google 反垄断、SEC v. Ripple 证券法、NRA v. Vullo 第一修正案等 9 个标志性案件

执行 `python tests/run_benchmark.py` 即可重现完整基准测试报告。

v1.0.0 仅支持 UCC Article 2 货物买卖合同 + 衡平法救济。侵权、证券、反垄断、宪法等领域已编入 [`concept-roadmap.md`](concept-roadmap.md)，欢迎社区提交规则集 PR。

---

## 环境配置

```bash
git clone https://github.com/laubeing-droid/juris-calculus.git
cd juris-calculus
pip install -r requirements.txt
```

> 敏感法律数据永不提交。管理本地数据在 `./data/`（已由 .gitignore 屏蔽）。

---

## 支持的法域

| 法域 | 状态 |
|------|------|
| 中国（民法典 - 合同纠纷） | ✅ v1.0.0 |
| 美国（UCC Article 2 + 衡平法救济） | ✅ v1.0.0 |
| 美国（侵权/证券/反垄断/宪法） | 🚧 路线图 |
| 欧盟/香港/其他 | 🔮 社区贡献 |

---

## FAQ

**Q: 导入 peripheral_models 报错？**
升级到最新版，类名已从 `LegalIREvaluator` 更新为 `FixpointEvaluator`。

**Q: ignite.py 在哪？**
本开源版不含此文件。`ignite.py` 是私有生产总控台，本内核设计为嵌入你的自有管线使用。

**Q: 默认 alpha 定价不准？**
`alpha=1.0` 是学术演示值。用你的团队历史工时数据运行 `calibrate_theilsen()` 反算专属常数。

**Q: 能用于侵权/证券/反垄断吗？**
暂不支持。参见 [`concept-roadmap.md`](concept-roadmap.md)，欢迎贡献。

---

## α 常数的意义

α = 1.0 是开源版的学术演示值。

如果你的团队有自己的肌肉记忆——挑 10 个你亲自经手、记得耗时的案子，喂给 `calibrate_theilsen()`，系统会自动反算出专属于你的 α。

---

## 引用

如在学术研究中使用 juris-calculus，请引用：

```bibtex
@software{juris-calculus,
  author = {Laupinco},
  title = {juris-calculus: A Jurisdiction-Agnostic Legal Reasoning Kernel},
  year = {2026},
  version = {1.0.2},
  url = {https://github.com/laubeing-droid/juris-calculus}
}
```

---

## 许可证

Apache 2.0

## 作者

Laupinco — Hokkien Computational Jurisprudence Enthusiast (Powered by Gemini & WorkBuddy & DeepSeek-V4 Pro)
