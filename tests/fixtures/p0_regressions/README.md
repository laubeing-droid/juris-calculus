# P0 regression fixtures

本目录保存 W1/P0 阻断链的可执行回归索引。配套数据文件由 `p0_regression_matrix.json` 定义。

- `p0_regression_matrix.json`：每条回归的 scenario-id、输入、触发原因、预期状态、证据字段。
- 已执行聚焦回归：`python -m pytest tests/unit/test_fact_admission.py tests/unit/test_rule_pack_manifest.py tests/unit/test_application_service.py tests/unit/test_audit_bundle.py tests/unit/test_llm_proposal_boundary.py tests/unit/test_v3_entrypoint_boundary.py -q`
- 全量权威：`python -m pytest tests/ -q`
- MCP 传输权威：`python -m pytest tests/unit/test_mcp_stdio_protocol.py -q`

覆盖核心：
- P0-1：外部事实和旧坐标不得自报进入 formal
- P0-2/P0-9：development pack 与不完整配置不得 formal
- P0-3/P0-8：partial 状态和 candidate 规则保持可见但不执行
- P0-4：规则级 argument identity、typed attack witness、claim projection
- P0-6/P0-7：checker receipt 与全输入 run identity
- P0-10：LLM provider 显式选择，失败不得 mock fallback
- P0-11：公开 Python facade 不暴露低层求值入口
