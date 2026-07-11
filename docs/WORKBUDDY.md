# WorkBuddy adapter

JC remains CLI-first. The adapter exists only for WorkBuddy-style clients that need a custom MCP connector. WorkBuddy's official documentation describes custom MCP connectors and also distinguishes MCP + CLI from Skill + CLI.

Install the package, then configure a custom stdio connector to run:

```text
python -m addons.workbuddy_mcp
```

Equivalent connector JSON commonly has this shape; enter it through the WorkBuddy custom connector UI for the installed version:

```json
{
  "mcpServers": {
    "juris-calculus": {
      "command": "python",
      "args": ["-m", "addons.workbuddy_mcp"]
    }
  }
}
```

The adapter exposes `jc_evaluate`, `jc_lookup_rule`, `jc_analyze_strategy`, and `jc_analyze_similar_cases`. It returns compact summaries and `run://` references, not full logs, whole rule libraries, tracebacks, or absolute paths. `resources/list` is empty.

For Codex and capable local agents, call the CLI directly to reduce schema/token overhead. For a lawyer without a downstream agent, the same CLI remains usable. WorkBuddy product-level E2E must be reported as BLOCKED unless the actual installed WorkBuddy version is exercised; stdio subprocess tests alone do not prove the product UI integration.

Official references: [WorkBuddy connectors](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Connector) and [WorkBuddy skills](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market).
