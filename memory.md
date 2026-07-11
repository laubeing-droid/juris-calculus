# Project Memory

## 2026-07-03 LSC Boundary Absorption

- JC may absorb LSC only as engineering boundary mechanisms: fact trust envelopes, degradation statuses, provenance summaries, taint propagation, renderer firewalls, IO declarations, conflict certificates, and review packets.
- Route back to `D:\Codex\数学证明\legal-math-modeling` if a future change alters `verified_fact`, `DecisionStatus`, Horn closure, attack/exception/priority/permission semantics, certificate checker acceptance, formal proof claims, or fail-closed behavior.
- Do not migrate LSC business objects, object schemas, Deadline/Fee/Interest/Jurisdiction/Citation tools, AgentSkill, CLI/API wrappers, China-law concrete rules, or P1/P2 substantive judgments into JC.
- Local verification for the boundary layer used `python -m pytest`; direct `pytest` collection had a pre-existing import-path issue for top-level `tools`.
- `legal-math-modeling` was consolidated to `main` after documenting the LSC runtime-boundary route-back. JC can cite it as a specification boundary only; it cannot use legal-math CI as a claim that runtime metadata is Lean-proved.

## 2026-07-11 MCP / Tri-Rail / Rule Admission Closure

- MCP stdio must be client-driven: no startup output, initialize echoes the client request ID, notifications receive no response, and business calls before initialization fail with `-32002`.
- MCP stdio stdout is protocol-exclusive for the entire process lifetime. Library constructors such as `TriRailCollider` must remain silent; diagnostics belong in structured payloads, logging, or explicit CLI harness output. The transport gate must execute at least one real `tools/call`, not only handshake and listing.
- `python mcp_server.py --test` is only an in-process functional smoke. The authoritative transport gate is `tests/unit/test_mcp_stdio_protocol.py`, which launches a real subprocess.
- Tri-Rail has one implementation in `tools/run_trirail_matrix.py`; MCP, matrix generation, and long-tail pressure testing consume that shared core. Do not restore the removed `PRCAdapter` / `execute_prc_first_override` path.
- YAML rules without an explicit source anchor or an existing authority field are retained as `UNVERIFIED + CANDIDATE_ONLY` training corpus entries and excluded from `FixpointEvaluator` reasoning indexes. Never synthesize an anchor from a rule name or narrative description.
- Current generated inventory after the admission gate: HK 40/133 reasoning-eligible, US 0/81, PRC 21123/21209; the PRC CN track corpus remains 21,144 with 21,081 reasoning-eligible.
- Rule counts in public descriptions must come from runtime inventory. Static `2,117` / `21,145` literals are forbidden in active files; `configs/zh_CN/rules.yaml` length and `_meta.total` must agree.
- Supply-chain audit is fail-closed through `tools/supply_chain_gate.py`: PASS=0, FAIL=1, BLOCKED=2. Proxy/TLS/network failures are evidence of BLOCKED, never PASS.
- Verified local closure on Python 3.11.15 and 3.12.5: 360 passed, 38 skipped on each version; real stdio business calls passed; in-process MCP smoke passed; pip-audit reported zero known vulnerabilities on each version after bypassing a stale process-local proxy.

## 2026-07-11 JC v3 Phase 0 Baseline

- The protected v2 semantic baseline is `tests/unit/test_v3_semantic_baseline.py`; it freezes obligation, prohibition, permission, exception, attack, priority, unresolved conflict, truncation, and independent-checker rejection without retaining timestamps, paths, or random IDs.
- `docs/v3-evaluation-entrypoints.md` is the deletion/migration ledger for every direct production evaluator constructor plus indirect holders. Product paths migrate to one application service; adapters stop returning evaluators; harnesses stay CLI/CI; low-level semantic tests may still call evaluator stages directly.
- The v2 MCP migration inventory is exactly 33 tools and 12 resources, with one disposition per name in the full remediation plan. Do not add a runtime compatibility layer when Phase 7 removes them.
- Cross-platform tracked-file baselines must hash Git index blobs, not raw Windows worktree bytes; CRLF filters otherwise create false file-size and SHA-256 drift.
- Phase 0 closure baseline on Python 3.11.15 and 3.12.5 is 365 passed, 38 skipped on each version after adding five protected semantic fixtures.
- Phase 1 fact-admission bug closure: `classify_boundary_result()` no longer falls through to accepted status for candidate/normalized/source-bound/checked/rejected/stale facts. Formal acceptance now requires complete LegalFact admission plus explicit checker acceptance, formal certificate kind, and actual formal-kernel execution.
- `LegalFact` is the single runtime fact object. The old `FactTrustEnvelope` name is only a migration factory that returns `LegalFact`; fact status/creator enums and `can_enter_formal_kernel()` live with the authoritative object.
- `compiler_core/contracts.py` is the v3 status/request/result/schema fact source. `ResultStatus` and `ExecutionStatus` are separate; immutable semantic/canonical results reject illegal formal-success combinations; `schemas/jc-v3.schema.json` is generated from `schema_document()`.
