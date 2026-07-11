# juris-calculus

juris-calculus 是公开、可审计的法律推理运行时内核。它提供确定性规则求值、论证图、证书式报告、与上游规格的差分验证，以及 MCP/API 可审计接口。

它不是客户案件系统。客户数据、商业规则库、律师工作流、诉讼策略、私有 benchmark 默认不进入本公开仓库。

## 当前公开状态

| 项目 | 当前状态 |
|---|---|
| MCP 工具 | 33 个 manifest-dispatched tools |
| Python 测试 | 整改后已核验基线：359 passed, 38 skipped |
| 真实 stdio 门禁 | 已由子进程客户端/服务端生命周期回归通过 |
| 规格差分 fixture | 10 aligned, 0 diverged |
| 公开边界 | 只放 auditable runtime kernel |
| 私有边界 | 客户数据、商业规则、工作流、策略、私有 benchmark 全部排除 |

## 核心边界

安全模型固定为：

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

LLM 输出只能是 candidate。它不能直接进入 `verified_fact`，不能绕过确定性验证器，也不能被描述为形式证明。

不得削弱：

- `DecisionStatus`
- checker 接受标准
- `verified_fact` 准入门
- attack / exception 语义
- permission / priority 语义
- 红灯 fail-closed 行为

## 仓库结构

| 路径 | 用途 |
|---|---|
| `compiler_core/` | 确定性运行时内核与 post-freeze public surface |
| `mcp_server.py` | JSON-RPC/MCP dispatch 入口 |
| `mcp_manifest.json` | 公开工具 manifest |
| `configs/` | 公开规则、配置 fixture、typed-IR sidecar 区 |
| `runtime/` | 运行时差分证据与 spec-shadow 输出 |
| `tests/` | Python 回归、契约、surface 测试 |
| `docs/` | 公开契约、路线图、闭环证据、整改说明 |
| `reports/` | 审计报告与分析输出 |

本地可以有被 `.gitignore` 排除的下载区、源码暂存区、私有过程文件，但它们不属于公开内核。

## 本地验证命令

推荐基线：

```powershell
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
python -m pytest tests\unit\test_post_freeze_surface.py -q
python -m pytest tests\unit\test_spec_shadow_harness.py -q
python -m pytest tests\ -q
python mcp_server.py --test
git diff --check
```

整改后基线为 `359 passed, 38 skipped`，其中包含真实 MCP 客户端/服务端 stdio 交互；`python mcp_server.py --test` 仅是进程内功能 smoke，不能替代该门禁。

发布或推送前应运行供应链审计。若 PyPI 或 OSV 因代理、TLS、网络阻断无法访问，必须记录具体命令和错误，不得把阻断当成通过。

## 证据等级

| 标签 | 含义 |
|---|---|
| runtime regression evidence | pytest 或确定性本地命令输出 |
| differential evidence | 与 legal-math 规格边界的 fixture 对比 |
| finite SMT check | 有界求解器对特定性质的检查 |
| upstream formal proof | legal-math 规格仓中的 Lean theorem |
| empirical heuristic | 工程可用但无形式保证的经验机制 |

公开文档只能声称证据能支撑的内容。

## MCP Surface

MCP surface 由 `mcp_manifest.json` 驱动，并由 `mcp_server.py` dispatch。测试要求 post-freeze public surface 中的每个工具都在 manifest 中可见并能被 dispatch。

验证：

```powershell
python mcp_server.py --test
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
```

## 与 legal-math-modeling 的关系

legal-math-modeling 负责 canonical Lean specification。JC 负责运行时实现、MCP 暴露、差分 harness、可审计证据报告。

凡是会改变 attack、exception、permission、priority、checker acceptance、verified_fact 准入的事项，先回到 legal-math-modeling 明确规格，再改 JC。
