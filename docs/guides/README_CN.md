# juris-calculus 中文说明

> 本页回答：juris-calculus 是什么、怎么在本地跑起来、它的边界在哪里。面向第一次接触本项目的法律 AI 开发者与集成方——概念解释在前，内部名词在后。

juris-calculus 是一个确定性的符号法律推理内核：把成文法编译成可执行的规则，用形式化验证的流水线推理，给每个结论挂上可审计的信任标签。它贯彻的是计算法学方法——法律规则是可计算的对象，推理过程是可验证的过程，结论是可审计的产物。它不是一个法律应用：不摄取原始卷宗、不代替律师意见、不保存客户数据。

输入必须是明确的结构化案件请求；输出是可回放的机器结果与审计包。

```text
LLM 提议 -> 验证门禁决定 -> 形式内核推理
```

神经网络输出绝不决定法律结果：模型可以提议事实或规则映射，但只有通过验证门禁的材料才能进入形式推理。

## 开始使用

支持 Python 3.11 和 3.12。

```powershell
python -m pip install .
jc --version   # 应输出 jc 5.0.1
```

执行正式推理前，运行宿主需要提供三份本机材料——仓库不内置任何生产部署状态或私有材料，这是刻意设计：内核本身不携带信任，信任由宿主的配置和签名材料决定。

| 环境变量 | 作用 |
|---|---|
| `JC_RUNTIME_MANIFEST` | 运行时清单，声明能力、工具与限制；查询能力只需它 |
| `JC_RUNTIME_FACTORY` | 指向一个已安装模块，其 `create_client()` 返回配置完成的 `JCClient`；执行 `evaluate`、`verify`、`replay`、`read-artifact`、`render` 时必需 |
| `JC_PRODUCTION_CONFIG` | 生产配置（存储 state_root、资源预算等）；生产宿主使用 |

配置好后：

```powershell
jc capabilities --json
jc evaluate --input case-input-bundle.json --json
```

`evaluate` 会写入输入快照、语义事件、正式结果、图、manifest、校验和与完成标记。之后可以：

```powershell
jc verify --input artifact-handle.json --json
jc replay --input artifact-handle.json --json
jc render --input artifact-handle.json --format markdown --audience agent --json
```

`replay` 校验完整性并语义重放；`render` 只读取已完成的审计包，不会重新推理。全部命令、参数与退出码见 [CLI 参考](CLI.md)。

## 它是怎么工作的

一次评估按固定顺序流过四层：

1. **准入**：来源快照、事实、规则分别过确定性门禁。只有 `verified_fact` 能进入正式推理；没有明确权威来源的规则只能当候选语料，不会静默进入推理。
2. **形式求解**：准入后的材料编译为法律中间表示，按论证语义求解（默认 grounded profile，另有四类有界语义按需启用）。
3. **独立校验**：独立 checker 复核求解结果；失败或超时就 fail-closed，不签发正式结论证书。
4. **证据落盘**：证书与不可变审计包写出，支持逐字节重放。

这套流程的设计底线是：`DecisionStatus`、事实准入、Horn、attack、exception、permission、priority、checker 验收与 fail-closed 语义不可弱化——它们是"结论可信"的来源。这些术语的精确定义见 [输入与语义边界](../contracts/INPUT_AND_SEMANTIC_BOUNDARY.md)；CLI、`JCClient` 与 stdio MCP（四工具）共用唯一 application service（协议 jc/5.0），三个入口语义完全一致。

## 边界

- `UNKNOWN`、`DISPUTED`、`USER_ASSUMED` 只生成缺失事实清单、仅限复核的分支或假设结果，拿不到正式证书。
- 本机限定范围使用 `cn-official-local`；这不等于公共 `cn-official` 已完成远程晋级。legacy 规则包已从当前运行时删除，不能检索、训练或回退使用。
- 本地验收与 CI 通过不等于生产可用，更不是法律正确性认证。
- 当前版本 5.0.1 的版本权威是 `compiler_core/version.py`；正式 wheel 只能从干净 `git archive` 构建并由发布门禁核验。

## 从 jc/4.0 输入迁移

正式入口拒绝 `jc/4.0` 与 4.x 引擎版本，不做宽松读取。旧输入包用离线工具迁移（不自己签名、不复用旧证书）：

```powershell
python -B tools/migrate_v4_bundle.py --input <v4-bundle.json> --output <v5-bundle.json> --report <migration-report.json>
```

## 下一步去哪

- 想看命令细节 → [CLI 参考](CLI.md)：子命令、退出码与 `jc-formal` 入口。
- 想理解输入合同 → [输入与语义边界](../contracts/INPUT_AND_SEMANTIC_BOUNDARY.md) 和 [V5 对象与状态矩阵](../contracts/V5_OBJECT_STATE_MATRIX.md)。
- 想审计一次运行 → [审计包与重放](../contracts/AUDIT_BUNDLE.md)。
- 想把外仓接进来 → [外仓协议](../contracts/EXTERNAL_PROTOCOL.md)。
- 想浏览全部文档 → [文档索引](../INDEX.md)。
