# juris-calculus 中文说明

JC 是公开、可审计的法律推理内核。输入必须是明确的结构化案件请求；输出是可回放的机器结果与审计包。

```text
LLM 提议 -> 验证门禁决定 -> 形式内核推理
```

它不处理原始卷宗摄取、不代替律师意见、不保存客户数据，也不包含诉讼工作流或个人文风。

## 开始使用

```powershell
git archive --format=tar HEAD -o source.tar
New-Item -ItemType Directory source
tar -xf source.tar -C source
$epoch = git show -s --format=%ct HEAD
python -B tools/wheel_gate.py --source source --out-dir dist --source-date-epoch $epoch
python -m pip install .\dist\juris_calculus-4.0.0rc1-py3-none-any.whl
$env:JC_RUNTIME_MANIFEST = "C:\path\to\runtime-manifest.json"
jc capabilities --json
jc evaluate --input case-request.json --json
```

运行宿主必须提供 `JC_RUNTIME_MANIFEST`。仅有 manifest 可以查询能力；执行
`evaluate` 还必须注入 V4 application、信任材料、已签名规则包和 artifact store。

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
- 当前 `cn-official` 尚未晋级；legacy 规则包已从当前运行时删除，不能检索、训练或回退使用。
- Horn、attack、exception、permission、priority、checker、`DecisionStatus` 与 fail-closed 语义不可在本仓库随意弱化。

## 接口

CLI、`JCClient` 与 stdio MCP 共用唯一 V4 application service；不存在 V3 或 WorkBuddy 兼容执行链。详见 [CLI](CLI.md)。

更多内容见 [文档索引](../README.md)。
