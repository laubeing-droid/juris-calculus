# SORRY_LEDGER.md - placeholder and proof-gap ledger

JC is a Python runtime repository. Lean `sorry` terms belong in the upstream legal-math specification repository, not in this runtime tree. This ledger tracks runtime placeholders, stubs, and proof-gap wording that could affect public-kernel claims.

## Critical-Path Rule

Production-critical paths must not contain silent placeholders. Any intentional incomplete path must:

- be outside the acceptance-critical path, or fail closed;
- have a named ledger entry;
- have a closing task and verification command;
- avoid being described as formal proof.

## Critical-Path Components

| Component | Boundary | Placeholder tolerance |
|---|---|---|
| candidate gate | raw LLM and proposed facts | zero silent acceptance |
| verified fact gate | reasoning-eligible facts | zero silent acceptance |
| certificate checker | report/certificate acceptance | fail closed |
| MCP manifest dispatch | public tool exposure | zero undocumented dispatch |
| spec shadow harness | legal-math differential fixtures | divergences reported, not hidden |
| attack and priority semantics | exception/defeat ordering | no semantic weakening |

## Current Runtime Placeholder Entries

| Component | Location | Reason | Closing task | Status |
|---|---|---|---|---|
| none recorded | n/a | n/a | keep scans and tests current | closed |

## Non-Proof Evidence Registry

These items are useful engineering evidence but must not be represented as full formal proof:

| Evidence | Current classification | Disclosure requirement |
|---|---|---|
| Python pytest suite | runtime regression evidence | report command and result |
| spec-shadow fixtures | differential runtime evidence | report aligned/diverged counts |
| graph similarity checks | bounded task-specific score evidence | do not call it a metric or kernel |
| DP diagnostics | diagnostics only | do not claim DP guarantee |
| robust regression heuristic | empirical estimator evidence | disclose clipping and comparison limits |

## Scan Expectations

Search terms for this ledger include `sorry`, `TODO`, `stub`, `placeholder`, `NotImplemented`, `pass`, `formal proof`, `mathematically proved`, and equivalent Chinese overclaims.
