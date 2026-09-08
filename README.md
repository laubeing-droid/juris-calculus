# juris-calculus

juris-calculus 是一个确定性的符号法律推理内核——不是一个法律应用，而是一套可嵌入法律 AI 产品的推理引擎。它把成文法编译成可执行的规则，用形式化验证的流水线推理，给每个结论挂上可审计的信任标签。当前版本 5.0.1（公共协议 jc/5.0）。

## 它解决什么问题

法律 AI 今天最被诟病的是两件事：一本正经地胡说八道（结论看似权威却查无实据），以及结论无法审计（没人能说清一个答案是怎么推出来的）。传统做法把法律当成文本生成任务，让模型直接"产出答案"——引用、修辞和真实推理在输出里无法区分。

本项目贯彻的是计算法学方法：法律规则先被编译为结构化的可执行规则；只有通过验证门禁的事实和已准入规则才能进入形式推理；每个结论都附带独立校验的证书和可逐字节重放的审计包。**神经网络输出绝不决定法律结果——LLM 只能提议，验证门禁决定，形式内核推理。**（此定位承自项目所有者的口述表述。）

规则对齐目前覆盖中国大陆、香港、美国联邦三个法域：法域适配器保留在源码树 `addons/` 中用于规则对齐，正式 wheel 只含内核。

## 快速开始

需要 Python 3.11 或 3.12。

```powershell
python -m pip install .
jc --version        # 输出 jc 5.0.1 即安装成功
```

执行正式推理前，运行宿主需要提供三份本机材料（仓库刻意不内置任何生产部署状态或私有材料——内核本身不携带信任，信任由宿主配置与签名材料决定）：运行时清单 `JC_RUNTIME_MANIFEST`、配置完成的运行时工厂 `JC_RUNTIME_FACTORY`、生产配置 `JC_PRODUCTION_CONFIG`。各变量的确切作用见 [中文说明](docs/guides/README_CN.md)。配置好后：

```powershell
jc capabilities --json                              # 报告运行时身份与能力
jc evaluate --input case-input-bundle.json --json   # 评估一个结构化案件请求并写出审计包
```

正式输入是结构化案件请求包（`CaseInputBundleV4`），Schema 见 `schemas/jc-v5.schema.json`，由宿主准备；仓库测试夹具不是生产输入。全部命令与退出码见 [CLI 参考](docs/guides/CLI.md)。

## 工作原理

一次评估的数据流是单向的：结构化请求进来，先过三道准入门禁（来源、事实、规则），只有 `verified_fact` 和已准入规则能继续前进；形式内核按论证语义求解；独立 checker 复核后签发证书；全过程事件写入不可变审计包，可逐字节重放。

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

- **合同面**：105 个封闭合同类型（含 30 个 V5 对象组），`schemas/jc-v5.schema.json` 由代码确定性生成、禁止手改；MCP 侧是四工具 stdio 服务（`mcp_manifest.json`）。CLI、Python（`JCClient`）与 MCP 三个入口共用同一个 application service，语义完全一致。
- **状态空间**：六轴终态分类器把全部 6720 种组合收敛到 124 个可达终态，杜绝"看似成功"的模糊输出。
- **证明绑定**：91 个运行时模块对 452 条上游 Lean 声明的处置登记在 `proofs/` 目录；运行时实现的保证等级是 crossCheckOnly（交叉核验），不是 kernelVerified。
- **推理特性（5.0.1）**：同案件 add-only 后续请求默认复用密封的父 Horn 状态做真增量（非单调变化自动回退全量并留痕）；已准入优先关系要么按登记策略参与击败判定，要么正式阻断该问题的完整性声明（不签发证书）；程序四路结论（裁定/程序处置/待法律判断/求解未完成）全部由公开输入驱动；预算耗尽以类型化未决义务传播，不变成工程错误。

## 边界

- 不是法律应用：不摄取原始卷宗、不代替律师意见、不保存客户数据、不含诉讼工作流。
- 只有 `verified_fact` 进入正式推理；`UNKNOWN`、`DISPUTED`、`USER_ASSUMED` 只产生缺失事实清单、仅限复核的分支或假设结果，不会拿到正式证书。
- 求解未完成、事实有争议或 checker 失败时 fail-closed：不签发正式结论证书。
- 本地验收与 CI 通过不等于生产可用：生产激活需要宿主提供信任材料、规则包与存储配置，条件清单见 [V5 发布流程](docs/operations/RELEASE_V5.md)。
- 旧 `jc/4.0` 输入不进正式入口；离线迁移工具是 `tools/migrate_v4_bundle.py`。版本权威是 `compiler_core/version.py`。

更多边界与语义细节：[输入与语义边界](docs/contracts/INPUT_AND_SEMANTIC_BOUNDARY.md)。

## 文档导航

全部页面按读者意图整理在 [docs/INDEX.md](docs/INDEX.md)。

- 想先跑起来 → [中文说明](docs/guides/README_CN.md)：安装、配置宿主材料、第一次评估与常见边界。
- 想集成到产品 → [CLI 参考](docs/guides/CLI.md) 与 [外仓协议](docs/contracts/EXTERNAL_PROTOCOL.md)：命令、退出码和三个公共入口的消费方式。
- 想接 Legal Harness → [JC ↔ Legal Harness 集成合同](docs/contracts/HARNESS_INTEGRATION.md)：如何发请求、追加材料走增量、读结论与未决事项，附三份可运行样本（`examples/harness/`）。
- 想理解系统 → [运行路径清单](docs/architecture/runtime-path-inventory.md)：从公共入口到审计包的正式运行链。
- 想审计结果 → [审计包与重放](docs/contracts/AUDIT_BUNDLE.md)：审计包里有什么、重放如何校验。
- 维护与发布 → [V5 发布流程](docs/operations/RELEASE_V5.md) 与 [交接检查点](HANDOFF.md)：当前做到哪、还欠什么。

## 开发与验证

```powershell
python -B -m pytest -c tests/pytest.ini -q -p no:cacheprovider tests
python -B tools/verify_upgrade.py --plan remediation/v5/tasks.v1.json --output work/v5-acceptance
```

完整工程约束（模块边界、验证梯度、提交规则）见 [AGENTS.md](AGENTS.md)。正式 wheel 只能从干净 `git archive` 提取构建（CI `package` job 或上述验收计划）；`tools/build_provenance.py` 用测试密钥生成的证明不得冒充生产发布证明。

## License

[MIT](LICENSE) © 2026 laubeing-droid.
