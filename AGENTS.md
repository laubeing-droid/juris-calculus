# AGENTS.md - juris-calculus repository rules

This repository is the public, auditable runtime kernel for juris-calculus. It must stay separate from private client data, commercial rule packs, lawyer workflow automation, litigation strategy, and private benchmarks.

## Operating Boundaries

- Work from the repository root unless a command explicitly targets another directory.
- Keep generated scratch files out of the tracked tree. Use ignored local folders for downloads, raw source drops, and private notes.
- Do not add absolute machine paths, credentials, client names, private facts, or proprietary business rules to tracked files.
- Do not push, tag, create releases, or change GitHub visibility unless the user asks for that action in the current turn.
- Local commits are allowed when they close a verifiable unit of work.

## Verification Model

The runtime boundary is:

`LLM proposes -> verification gates decide -> formal kernel reasons`

Raw LLM output is always a candidate. It must not enter `verified_fact` or any reasoning-eligible state without deterministic validation.

Do not weaken:

- `DecisionStatus` semantics
- checker acceptance standards
- `verified_fact` gate rules
- attack, exception, permission, and priority semantics
- fail-closed behavior for red-light cases

If a change appears to require weakening one of these rules, stop and route the issue back to the upstream legal-math specification work before changing JC runtime behavior.

## Coding Rules

- Prefer existing modules, types, and test patterns.
- Keep public APIs stable unless the task explicitly requires an API change.
- Preserve deterministic ordering in evaluators, reports, manifests, and MCP dispatch.
- Add comments only where they explain non-obvious design intent or safety boundaries.
- Do not wrap empirical output as a formal proof.
- Do not delete failing evidence to make a run look green.

## Required Local Checks

Use the narrowest meaningful checks during development, then run broader checks before committing user-visible work.

Recommended baseline:

```powershell
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
python -m pytest tests\unit\test_v3_entrypoint_boundary.py -q
python -m pytest tests\unit\test_spec_shadow_harness.py -q
python -m pytest tests\ -q
python mcp_server.py --test
git diff --check
```

For pre-release work, also run the applicable supply-chain, privacy, stale-narrative, and disclosure scans. If a scan is blocked by network or proxy failure, record the exact command and failure mode instead of bypassing it.

## Documentation Rules

- State evidence level precisely: runtime test, differential fixture, SMT finite check, upstream Lean theorem, or empirical heuristic.
- Keep public documentation aligned with the current MCP manifest count and test baseline.
- Explain private-layer boundaries without naming private clients, strategies, or closed datasets.
- Update generated evidence reports only from the corresponding local harness when possible.

## Git Commit Standard

Each local commit for a closed unit should include:

- modified files
- root cause or reason for change
- new project knowledge
- impact scope
- verification commands and results
- remaining risks

Do not mix unrelated cleanup, feature work, and documentation rewrites in one commit unless they are part of the same verified closure.
