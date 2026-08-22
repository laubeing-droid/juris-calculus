# Project memory

## Current product boundary

- JC is a public, CLI-first, auditable legal-reasoning kernel.
- Formal path: structured request -> deterministic admission -> application service -> canonical result, audit bundle, graph, and replay.
- Optional WorkBuddy MCP is a four-tool, zero-resource stdio compatibility adapter. It delegates to the same services as the CLI.
- The public kernel provides neutral, stable, auditable output only. Private client data, legal workflows, strategy decisions, personal style, OCR/model pipelines, and proprietary rule packs remain outside.

## Protected semantics

- Never weaken `DecisionStatus`, `verified_fact`, Horn, attack, exception, permission, priority, checker acceptance, or fail-closed behavior.
- Route any proposed semantic change to the upstream `legal-math-modeling` specification work before changing JC.
- `UNKNOWN`, `DISPUTED`, and `USER_ASSUMED` cannot create formal certificates.

## Rule packs

- `cn-official` is intentionally blocked until first-party source snapshots exist.
- Legacy CN/HK/US material is candidate corpus for inspection, governance, and training export; it is not a silent formal fallback.
- Runtime inventory and manifests are the only count authority. Do not hard-code inventory numbers in public prose.
- Promotion is external and human-controlled; no automated promotion path exists.

## Audit and output

- Every evaluation writes an atomic bundle outside the Git worktree; replay verifies bytes and semantic output against cached pack material.
- `graph.json` derives from canonical events/result. Render reads a completed bundle and cannot re-evaluate or modify the result.
- Audit storage excludes raw narrative, arbitrary provenance, irrelevant rules, and absolute paths.

## Engineering constraints

- Supported Python: 3.11 and 3.12. Core dependency: PyYAML; optional profiles stay separate.
- `compiler_core.version.__version__` is the single package, CLI, audit, and MCP version source. Release tags must match it exactly.
- Supply-chain auditing uses `pip-audit --disable-pip` with hash-pinned lock profiles; vulnerability lookup and fail-closed PASS/FAIL/BLOCKED remain mandatory.
- Clean wheel checks must remove generated build caches first because stale `build/lib` can resurrect deleted modules.
- Tri-rail is an engineering harness only; without official reasoning-ready packs it remains review-only with `formal_kernel_used=false`.

## Legal compiler research baseline

- The efficient compiler shape is a dual-IR hourglass: provenance-bound `LegalSpec` lowers into a small `Legal-IVL`, then fans out to deterministic execution, proof-obligation, counterexample, and explanation targets.
- `Spec IR -> Impl IR -> Target` is incomplete without per-run translation validation, proof receipts, replay manifests, mutation/scenario oracles, and an external human-controlled rule-pack lifecycle.
- Keep responsibilities split: `legal-math-modeling` defines semantics and proof obligations; Deli-style research automation proposes, repairs, tests, and trains candidates; JC validates admitted artifacts and executes the protected fail-closed kernel.
- Strengthen legacy Horn candidates through source anchors, typed variables, temporal scope, modality, exception/attack/priority edges, static analysis, mutation tests, and proof receipts. Never promote candidates merely by changing manifest state.
- Neural components may retrieve, route, rank, propose, or repair candidates. They must not create `verified_fact`, decide `DecisionStatus`, or bypass checker acceptance.

## Laptop-repair handoff snapshot — 2026-07-29

- Added root `HANDOFF.md`. Before the handoff commit, `main` was clean and one commit ahead of `origin/main` at `4ddd718`.
- Restoring on another machine requires rerunning the stdio MCP test and full suite; the historical clean state is not a current transport or release PASS.

## Workspace path recheck — 2026-08-07

- Current checkout: `D:\Codex\1.法律工作区\juris-calculus`; no tracked machine path remains after replacing the obsolete upstream path in `HANDOFF.md` with the repository name.
- The v3 entrypoint and stdio MCP authority tests pass; in-process MCP smoke reports version `3.0.2`, four tools, zero resources, and does not claim readiness.
- Default Windows `%TEMP%` makes render artifact paths exceed the legacy path limit. The default-temp full run produced 349 passed, 28 skipped, and 6 path-length failures; a complete rerun with short `--basetemp` produced 355 passed and 28 skipped.
- Treat the short basetemp as a test-environment requirement on this machine, not a change to audit-bundle semantics or a reason to enable global long-path policy.

## 2026-08-15 W0/W1 formal-boundary closure

- Scope: completed only W0 baseline/inventory and W1 P0 blockers authorized by section 30 of `260810_juris-calculus重点升级施工方案.md`; W2-W8 remain unopened.
- External `CaseRequest` and legacy FactCoordinate payloads cannot self-issue `VERIFIED_FACT`; only trusted internal audit decoding preserves prior admission.
- Development packs are loadable for review/replay but never reasoning-ready; official formal readiness requires manifest-bound configs and SHA-256 build attestation. `cn-official` remains inactive/blocked.
- The independent grounded checker operates on one argument per applicable admitted rule. Claim-level audit events remain for compatibility; checker receipts persist argument witnesses, typed attack witnesses, AAF digest, and claim projection.
- Public Python API is `JCClient`; package root no longer exports low-level evaluation functions. LLM extraction is proposal-only with explicit real/regex providers and no mock fallback.
- Run identity binds complete execution inputs across early exits, audit, graph, bundle, and replay. Partial/truncated/candidate states remain visible and cannot produce formal certificates.
- Renderer paths use a 40-character filesystem key derived from the full result/profile/renderer binding digest; metadata retains the complete 64-character digest to avoid Windows path overflow without weakening content binding.
- Final acceptance: 384 passed, 28 skipped; MCP stdio 3 passed; in-process smoke status ok with readiness false; pip-audit PASS with 0 known vulnerabilities; fresh wheel/install smoke PASS. Wheel SHA-256: `cc14ff95c5c2fbb58b42c56ecf3f5b6f6f626a4e71a24a0eaa464e6fcc58d6d5`.
- Do not reinterpret protocol smoke, wheel import, or test PASS as proof of legal corpus/product readiness.

## 2026-08-19 V4 remediation planning correction

- Build and synchronize CodeGraph before assigning file dispositions. The 2026-08-19 baseline indexed 228 files (191 Python and 37 YAML), 3,029 nodes, 7,051 edges, with zero unresolved refs or parse errors; the 13.6 MB `configs/zh_CN/rules.yaml` was the sole tracked Python/YAML/YML file outside the graph and must be closed through Git blob, byte, and record inventory.
- CodeGraph is navigation evidence, not deletion authority. Confirm deletion-relevant edges in exact source/AST and supplement dynamic imports, entrypoints, package exports, tests, and assets. Empty callers/imports/impact never authorize deletion by themselves.
- Keep one JC source repository and one V4 production wheel throughout the current remediation. Non-production source tools, experiments, and candidate assets stay in the repository but out of the wheel/runtime; only the signed `cn-official` pack is an independent production artifact. Any later repository or distribution proposal is a post-release RFC and cannot alter the current remediation topology or completion result.
- Preserve semantics before removing files. The graph confirmed public consumers for rendering, analysis, governance, training, and legacy lookup, and formal-path reachability for `litigation_engineering` and the function-local `transformer.auto_patch`; cut or migrate those edges before moving/deleting paths. Keep companion-spec differential and independent oracle value outside production runtime.
- Report repository removal, relocation/replacement, true whole-system deletion, and dependency movement separately. Moving code or dependencies out of the production wheel is not ecosystem deletion, and LOC is not a production gate.
- User-directed exception: remove `configs/zh_CN/rules.yaml` from the current tree during W5 after freezing its exact SHA-256 `032206c349154d77eeef771d2b40dcfb62e1f7724c420ba4c09e69aaf88e8a44`, 13,620,766-byte size, 21,144 unique rule IDs, legacy manifest, Git locator, and exact signed deletion receipt. Disconnect every CLI/addon/config/collision/TriRail/builder/pipeline/benchmark/test/CI/pack/wheel consumer; delete the `cn-legacy-corpus` manifest; preserve path references only in historical evidence. Do not bulk-copy or auto-convert this candidate corpus into `cn-official`: H8 formal-source inventory and source/candidate/coverage/review/build/provenance dependency closure must be independent of the legacy asset, while independently deriving the same legal proposition from approved primary sources remains allowed. Any fingerprint drift requires renewed user authorization. Because the frozen tag/Git blob still retains the bytes, account this as a history-bound current-tree removal, not a true whole-system asset deletion.

## 2026-08-22 V4 remediation bootstrap invalidation

- The `a881f28` runner was a stub: it hard-coded `B00`, `B00-CG`, and `B01` as completed, then generated all 12 future gate requests without executing the DAG or verifying approvals.
- Treat B00 as failed and B00-CG/B01 as unverified. Reuse observations and the tracked-path enumeration only as inputs, never as closure evidence.
- The old temporary state root is preserved. Its 22 files and 12 requests are recorded as `INVALID_SUPERSEDED` under the persistent state root `D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-remediation-state`.
- The only recovery command is recorded with absolute repository, plan, runner, and state-root paths in `remediation/v4/STATUS.md` and the external goal ledger.

## 2026-08-22 W0-01 V4 target contract freeze

- The target registry contains 73 formal public types: 60 non-MCP types plus input/output/error envelopes for each of four MCP tools and `ToolSpecV4`. Object-shaped types are closed; runtime classes and generated schemas remain non-conformant until W1 implements the registry.
- Terminal classification enumerates 6,720 combinations across execution, decision, review, completeness, certificate, and transport; 115 combinations are reachable under the frozen constraints.
- `missing_required_fact`, review-only, hypothetical, conflict, and unknown are completed semantic outcomes with transport success. Only pre-evaluation blocked and internal engine failure use transport error.
- A formal certificate is legal only for `accepted_formal_result`; a conflict certificate is legal only for `conflict_certificate`. The W0 runner gate rejects missing, swapped, or open object definitions and illegal certificate/transport mutations.

## 2026-08-22 W0-02 V4 foundation contract freeze

- The original runner left B00, B02, and W0-01 receipts with `start_commit=result_commit`, empty `changed_paths`, and no artifact digests even though their result commits advanced beyond their dependencies; their task allowlists also omitted required proof/governance paths. Preserve those receipts as defective history. The 0.3 runner may append, never overwrite, a corrected receipt only when the task contract changed by strict allowlist addition alone; the correction names that fact, retains the original command streams, binds the exact historical commit delta, and records both task-definition digests. Dependent verification-only receipts may receive a separate input-digest-only correction only when their Git tree is exactly unchanged. A legacy gap that cannot satisfy those conditions is fatal.
- `DigestV4` has one wire grammar: `sha256:<64 lowercase hex>`. JC formal JSON adopts RFC 8785 string escaping, UTF-16 property ordering, no-whitespace output, and UTF-8 generation, plus a stricter safe-integer admission profile. This is not full RFC 8785 IEEE-754 number serialization; formal inputs reject every float token before canonicalization.
- Canonical time is uppercase UTC `Z` with optional one-to-nine-digit non-zero-terminated fractional seconds. Store and compare it as `(epoch_seconds, nanosecond)`; intervals are half-open `[start,end)`. Do not round through Python microseconds or JavaScript milliseconds.
- The committed Windows/CPython 3.12 probe freezes 13 inclusive request-admission limits and the enforcement order. Its payload digest is `sha256:13f79fdd6b5282f5aabfca9569aba6e69064f47765a0572bd8aa43f10c2c5ba1`; the raw file digest is `sha256:cfcca89034412b2eec9f8de60ae1e74661adfdceb1a4f72d4e59e1365eee0b35`.
- Artifact-page, solver, queue, in-flight-run, state-quota, and retention limits remain `DEFERRED_UNBENCHMARKED` with `value=null` and assigned closure tasks. Guessed production values are forbidden.
- Ubuntu/Windows on Python 3.11/3.12 is a target matrix only. Node 22/24 is an independent contract oracle; cross-platform runtime acceptance remains open until W6-05 attaches execution receipts.
