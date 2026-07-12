# Optional WorkBuddy adapter

JC is CLI-first. This adapter exists only for WorkBuddy clients that require a custom MCP connector. WorkBuddy's connector documentation describes custom MCP services and distinguishes MCP + CLI from Skill + CLI; this repository uses the former.

Run the stdio adapter from an installed JC package:

```text
python -m addons.workbuddy_mcp
```

The adapter exposes exactly four tools and no resources:

- `jc_evaluate`
- `jc_lookup_rule`
- `jc_analyze_strategy`
- `jc_analyze_similar_cases`

It returns compact structured summaries and logical `run://` references. It does not return full logs, whole corpora, tracebacks, or absolute paths; it delegates to the same application services as the CLI.

Use the connector UI of the installed WorkBuddy version to add the local stdio command. The repository verifies MCP stdio lifecycle and the four-tool schema. It does not claim WorkBuddy product-UI E2E until that version and configuration are exercised.

For Codex and capable local agents, use the CLI directly to avoid MCP schema/token overhead.

Official reference: [WorkBuddy connector documentation](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Connector).
