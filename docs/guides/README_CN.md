# juris-calculus

JC 是一个公开、可审计的法律推理内核，默认入口是 `jc` CLI。它只接受显式结构化事实，只让通过完整性和来源准入的规则进入正式推理，并为每次正式运行生成结果、相关事件日志、Graph JSON、校验和与可重放材料。

JC 不是案件管理系统。客户数据、商业规则包、律师工作流、诉讼执行和律师个人文风层不进入公开仓库；公开内核固定输出中性、稳定、可审计结果。

```text
LLM 提议 -> 确定性门禁决定 -> 正式内核推理
```

## 主要命令

```powershell
python -m pip install .
jc doctor --json
jc packs verify --all --json
jc evaluate --input case-request.json --json
jc replay --run <run-id> --json
jc render --run <run-id> --format markdown --json
```

`UNKNOWN` 生成缺失事实清单，`DISPUTED` 进入分支推理，`USER_ASSUMED` 只能生成假设结果；三者都不能产生正式 certificate。

## WorkBuddy 特例

JC 保持 CLI 优先。只有需要 WorkBuddy 自定义连接器时才注册可选 stdio 适配器。它只暴露 `jc_evaluate`、`jc_lookup_rule`、`jc_analyze_strategy`、`jc_analyze_similar_cases` 四项工具，resources 为零，不包含第二套规则加载或求值逻辑。

## 审计与可视化

正式运行总是生成 `events.jsonl` 和 `graph.json`。日志只记录相关事实、规则和语义事件，不记录整库无关规则；默认不保存原始案情文本或绝对路径。HTML 只有律师明确调用 `jc render --format html` 时才生成。

详细说明见 `CLI.md`、`../contracts/AUDIT_BUNDLE.md`、`../contracts/RULE_PACKS.md`、`../contracts/INPUT_AND_SEMANTIC_BOUNDARY.md`、`../contracts/FORMAL_RUNTIME_CONFORMANCE.md`、`WORKBUDDY.md` 和 `MIGRATION_V2_TO_V3.md`。

## 本地门禁

```powershell
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
python -m pytest tests\unit\test_v3_entrypoint_boundary.py -q
python -m pytest tests\unit\test_spec_shadow_harness.py -q
python -m pytest tests\ -q
python mcp_server.py --test
python tools\supply_chain_gate.py --requirements requirements/core.lock
git diff --check
```

每次本地验证必须记录实际 pass/skip；静态数字不构成发布证据。未实际运行的远端 CI 必须写 `NOT_EXECUTED`，不得写成通过。

## 许可证

[MIT](../../LICENSE) © 2026 laubeing-droid。
