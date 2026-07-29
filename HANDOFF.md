# `juris-calculus` 交接

核验时间：2026-07-29（Asia/Shanghai）

## Git 状态

公开、CLI-first、可审计法律推理内核。生成 handoff 前：`main...origin/main [ahead 1]`，工作树干净，HEAD `4ddd718`；该本地提交只补 `memory.md` 的法律编译器研究基线，尚未推送。

## 当前产品边界

版本口径为 3.0.2 Unreleased。正式链：结构化请求 → deterministic admission → application service → canonical result/audit bundle/graph/replay。可选 WorkBuddy MCP 只提供 4 tools、0 resources，共用同一服务，不是第二套 evaluator。

保护边界：

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

只有 `verified_fact` 可进入形式推理；`UNKNOWN`、`DISPUTED`、`USER_ASSUMED` 不产生证书。`cn-official` 在缺少第一方法源快照时继续 blocked。语义改动先进入 `D:\Codex\数学证明\legal-math-modeling`。

## 权威文件

- `AGENTS.md`
- `memory.md`
- `README.md`
- `CHANGELOG.md`
- `docs/contracts/`
- `mcp_manifest.json`

## 恢复验证

支持 Python 3.11/3.12。不要仅跑进程内 smoke 后宣告 MCP 正常；stdio subprocess test 才是传输权威。

```powershell
python -m pytest tests\unit\test_v3_entrypoint_boundary.py -q
python -m pytest tests\unit\test_mcp_stdio_protocol.py -q
python -m pytest tests\ -q
python mcp_server.py --test
python tools\supply_chain_gate.py --requirements requirements\core.lock
git diff --check
```

未获当前回合授权时不要 push、tag、release 或改变可见性。

