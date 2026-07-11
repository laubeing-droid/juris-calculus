# Project Memory

## 2026-07-03 LSC Boundary Absorption

- JC may absorb LSC only as engineering boundary mechanisms: fact trust envelopes, degradation statuses, provenance summaries, taint propagation, renderer firewalls, IO declarations, conflict certificates, and review packets.
- Route back to `D:\Codex\数学证明\legal-math-modeling` if a future change alters `verified_fact`, `DecisionStatus`, Horn closure, attack/exception/priority/permission semantics, certificate checker acceptance, formal proof claims, or fail-closed behavior.
- Do not migrate LSC business objects, object schemas, Deadline/Fee/Interest/Jurisdiction/Citation tools, AgentSkill, CLI/API wrappers, China-law concrete rules, or P1/P2 substantive judgments into JC.
- Local verification for the boundary layer used `python -m pytest`; direct `pytest` collection had a pre-existing import-path issue for top-level `tools`.
- `legal-math-modeling` was consolidated to `main` after documenting the LSC runtime-boundary route-back. JC can cite it as a specification boundary only; it cannot use legal-math CI as a claim that runtime metadata is Lean-proved.

## 2026-07-11 MCP / Tri-Rail / Rule Admission Closure

- MCP stdio must be client-driven: no startup output, initialize echoes the client request ID, notifications receive no response, and business calls before initialization fail with `-32002`.
- `python mcp_server.py --test` is only an in-process functional smoke. The authoritative transport gate is `tests/unit/test_mcp_stdio_protocol.py`, which launches a real subprocess.
- Tri-Rail has one implementation in `tools/run_trirail_matrix.py`; MCP, matrix generation, and long-tail pressure testing consume that shared core. Do not restore the removed `PRCAdapter` / `execute_prc_first_override` path.
- YAML rules without an explicit source anchor or an existing authority field are retained as `UNVERIFIED + CANDIDATE_ONLY` training corpus entries and excluded from `FixpointEvaluator` reasoning indexes. Never synthesize an anchor from a rule name or narrative description.
- Current generated inventory after the admission gate: HK 40/133 reasoning-eligible, US 0/81, PRC 21123/21209; the PRC CN track corpus remains 21,144 with 21,081 reasoning-eligible.
- Rule counts in public descriptions must come from runtime inventory. Static `2,117` / `21,145` literals are forbidden in active files; `configs/zh_CN/rules.yaml` length and `_meta.total` must agree.
- Supply-chain audit is fail-closed through `tools/supply_chain_gate.py`: PASS=0, FAIL=1, BLOCKED=2. Proxy/TLS/network failures are evidence of BLOCKED, never PASS.
- Verified local closure: 359 passed, 38 skipped; real stdio passed; Tri-Rail 12-scenario harness completed; pip-audit reported zero known vulnerabilities after bypassing a stale process-local proxy.
