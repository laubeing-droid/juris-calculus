# juris-calculus 中文说明

JC 是公开、可审计的法律推理内核。输入必须是明确的结构化案件请求；输出是可回放的机器结果与审计包。

```text
LLM 提议 -> 验证门禁决定 -> 形式内核推理
```

它不处理原始卷宗摄取、不代替律师意见、不保存客户数据，也不包含诉讼工作流或个人文风。

## 开始使用

```powershell
python -m pip install .
jc --version
$env:JC_RUNTIME_MANIFEST = "<path-to-runtime-manifest.json>"
$env:JC_RUNTIME_FACTORY = "compiler_core.production_runtime"
$env:JC_PRODUCTION_CONFIG = "<path-to-production-config.json>"
jc capabilities --json
jc evaluate --input case-input-bundle.json --json
```

`jc --version` 应输出 `jc 4.0.0`。需要构建并验证正式 wheel 时，使用当前
3.0 验收计划或按 [V4 发布流程](../operations/RELEASE_V4.md) 操作，不要在工作树里手工拼装发布包。

运行宿主必须提供 `JC_RUNTIME_MANIFEST`。仅查询能力时可只读取 manifest；执行
`evaluate`、`verify`、`replay`、`read-artifact` 或 `render` 时，还必须通过
`JC_RUNTIME_FACTORY` 提供配置完成的 `JCClient`。生产宿主同时使用
`JC_PRODUCTION_CONFIG` 指定生产配置。

`evaluate` 会写入输入快照、相关语义事件、正式结果、图、manifest、校验和与完成标记。之后可执行：

```powershell
jc replay --input artifact-handle.json --json
jc render --input artifact-handle.json --format markdown --audience agent --json
```

`replay` 校验完整性并重放；`render` 只读取已经完成的审计包，不会重新推理。

## 边界

- 只有 `verified_fact` 能进入正式推理。
- `UNKNOWN`、`DISPUTED`、`USER_ASSUMED` 只能生成缺失事实、分支或假设结果，不能生成正式 certificate。
- 未具明确来源的规则只能作为候选语料，不会静默进入推理。
- 本机限定范围使用 `cn-official-local`；这不等于公共 `cn-official` 已完成远程晋级。legacy 规则包已从当前运行时删除，不能检索、训练或回退使用。
- Horn、attack、exception、permission、priority、checker、`DecisionStatus` 与 fail-closed 语义不可在本仓库随意弱化。

## 接口

CLI、`JCClient` 与 stdio MCP 共用唯一 V4 application service；不存在 V3 或 WorkBuddy 兼容执行链。详见 [CLI](CLI.md)。

更多内容见 [文档索引](../README.md)、[输入与语义边界](../contracts/INPUT_AND_SEMANTIC_BOUNDARY.md)和[发布边界](../operations/RELEASE_V4.md)。
