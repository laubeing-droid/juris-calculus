# JC v3 execution status

Updated: 2026-07-11

## P0 - Formal reasoning and admission

The protected Horn, attack, exception, permission, priority, checker, and fail-closed semantics remain fixed by differential and runtime tests. Formal evaluation accepts only an explicit `CaseRequest` and reasoning-ready pack through the single application service.

## P1 - Audit and visualization

Every completed evaluation writes a relevant-event audit bundle and deterministic Graph JSON. Replay verifies file and semantic hashes. Rendering is a separate, run-only command and cannot reach an evaluator.

## P2 - Governed peripheral capabilities

Rule governance, training export, missing-fact review, litigation-strategy advisory, similar-case analysis, and tri-rail engineering harnesses are outside the formal conclusion path. They remain review-required or candidate-only as appropriate.

## Public interfaces

The CLI is primary. The optional WorkBuddy adapter exposes four thin tools and zero resources. Old orchestration, fixed memo, whole-corpus MCP resources, and duplicate evaluation paths are not part of v3.

```powershell
python -m pytest tests\unit\test_v3_entrypoint_boundary.py -q
python -m pytest tests\unit\test_mcp_stdio_protocol.py -q
python -m pytest tests\ -q
```
