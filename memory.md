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
