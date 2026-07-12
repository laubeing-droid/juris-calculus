# juris-calculus repository rules

JC is a public, auditable runtime kernel. Keep it separate from private case data, commercial rule packs, lawyer workflow automation, litigation strategy, and private benchmarks.

## Non-negotiable boundary

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

Do not weaken `DecisionStatus`, `verified_fact` admission, Horn, attack, exception, permission, priority, checker acceptance, or fail-closed behavior. A change that would alter them belongs first in `legal-math-modeling`.

## Working rules

- Preserve deterministic ordering in results, manifests, audit events, graphs, and MCP dispatch.
- Keep public APIs stable unless the task explicitly changes them.
- Do not add machine paths, credentials, client facts, or proprietary rules to tracked files.
- Do not push, tag, release, or change GitHub visibility without current-turn authorization.
- Generated scratch data belongs in ignored directories, never in the tracked tree.
- Record blocked checks as blocked; do not delete evidence or reinterpret it as PASS.

## Verification

Use the narrowest relevant checks first, then broader checks for user-visible work:

```powershell
python -m pytest tests\unit\test_v3_entrypoint_boundary.py -q
python -m pytest tests\unit\test_mcp_stdio_protocol.py -q
python -m pytest tests\ -q
python mcp_server.py --test
git diff --check
```

Run supply-chain, privacy, stale-narrative, and disclosure checks when relevant. The stdio subprocess test is the MCP transport authority; `mcp_server.py --test` is only an in-process smoke.

## Documentation and commits

Document evidence level precisely: runtime test, differential fixture, finite SMT check, upstream Lean theorem, or empirical heuristic. Keep README, manifest, CLI, and MCP statements aligned with runtime behavior; never publish static rule or test counts as permanent facts.

Each local commit should state changed files, reason, new project knowledge, impact, verification, and remaining risk.
