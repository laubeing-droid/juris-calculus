# CLAUDE.md - juris-calculus assistant rules

This file mirrors the repository-facing assistant rules in `AGENTS.md`. The repository is a public auditable kernel, not a container for private client material or commercial workflow logic.

## Hard Boundaries

- Work in the repository root unless a task names a different path.
- Keep private data, lawyer workflows, litigation strategy, private benchmarks, and commercial rule libraries outside this public repository.
- Do not push, tag, release, or change repository visibility unless the user explicitly asks in the current turn.
- Do not weaken runtime gates, checker acceptance, `DecisionStatus`, `verified_fact`, attack, exception, permission, or priority semantics.
- Red-light cases must fail closed.

## Runtime Contract

The safe architecture is:

`LLM proposes -> verification gates decide -> formal kernel reasons`

LLM-generated content can be recorded as a candidate only. It cannot directly become `verified_fact`, cannot bypass deterministic validators, and cannot be described as formal evidence.

## Development Practice

- Read the relevant code and tests before editing.
- Prefer existing patterns over new abstractions.
- Keep edits scoped to the requested closure.
- Use deterministic ordering for outputs that become evidence.
- Preserve failing artifacts and report them honestly.
- Avoid stale project numbers in documentation; verify counts from the tree.

## Verification Baseline

Common local checks:

```powershell
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
python -m pytest tests\unit\test_v3_entrypoint_boundary.py -q
python -m pytest tests\unit\test_spec_shadow_harness.py -q
python -m pytest tests\ -q
python mcp_server.py --test
git diff --check
```

When a check cannot run, record the exact command, error, and impact. Do not replace a blocked check with a weaker conclusion.

## Commit Practice

Local commits should close one verifiable unit. Commit messages should identify changed files, root cause, new project knowledge, impact scope, validation, and remaining risk.
