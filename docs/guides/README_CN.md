# juris-calculus 中文说明

JC 是公开、可审计的法律推理内核。输入必须是明确的结构化案件请求；输出是可回放的机器结果与审计包。

```text
LLM 提议 -> 验证门禁决定 -> 形式内核推理
```

它不处理原始卷宗摄取、不代替律师意见、不保存客户数据，也不包含诉讼工作流或个人文风。

## 开始使用

```powershell
python -m pip install .
jc doctor --json
jc packs list --json
jc evaluate --input case-request.json --json
```

`evaluate` 会写入输入快照、相关语义事件、正式结果、图、manifest、校验和与完成标记。之后可执行：

```powershell
jc replay <run-id> --json
jc render <run-id> --format markdown --audience agent --json
```

`replay` 校验完整性并重放；`render` 只读取已经完成的审计包，不会重新推理。

## 边界

- 只有 `verified_fact` 能进入正式推理。
- `UNKNOWN`、`DISPUTED`、`USER_ASSUMED` 只能生成缺失事实、分支或假设结果，不能生成正式 certificate。
- 未具明确来源的规则只能作为候选语料，不会静默进入推理。
- 当前 `cn-official` 因缺官方一手来源快照而 BLOCKED；legacy 规则包仅供检索、治理和训练导出。
- Horn、attack、exception、permission、priority、checker、`DecisionStatus` 与 fail-closed 语义不可在本仓库随意弱化。

## 接口

CLI 是默认接口。可选 WorkBuddy MCP 适配器只暴露四项工具、零 resources；它是兼容层，不是第二套推理器。详见 [CLI](CLI.md) 与 [WorkBuddy](WORKBUDDY.md)。

更多内容见 [文档索引](../README.md)。
