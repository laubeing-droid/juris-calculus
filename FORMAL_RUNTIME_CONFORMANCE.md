# Formal Runtime Conformance

This document states what JC can and cannot claim about formal conformance.

## Scope Split

| Repository | Responsibility |
|---|---|
| legal-math-modeling | canonical Lean specification, DDL core, Horn-to-AAF contract, certificate checker theorem statements |
| juris-calculus | Python runtime, MCP/API exposure, deterministic tests, differential harnesses, auditable reports |

JC does not claim machine-checked coverage for every Python execution path. It claims runtime conformance only where deterministic tests, finite checks, or spec-shadow fixtures support that claim.

## Current Runtime Evidence

| Evidence | Current result | Claim supported |
|---|---|---|
| full Python tests | 484 passed, 38 skipped on Python 3.11 and 3.12 | full local regression suite passed on both supported versions |
| real MCP stdio gate | passed | subprocess client/server lifecycle, notification and error handling verified |
| optional MCP dispatch | 4 tools, 0 resources | WorkBuddy adapter surface is bounded and manifest-aligned |
| spec-shadow fixtures | 10 aligned, 0 diverged | selected runtime fixtures match upstream boundary expectations |
| audit/application boundary tests | pass in local targeted run | formal entrypoints remain centralized and fail closed |

## Non-Claims

JC does not claim:

- machine-checked proof for every Python implementation path;
- direct legal correctness for real client cases;
- DP guarantee from diagnostics-only privacy metrics;
- graph similarity is a metric or PSD kernel;
- robust regression heuristic has a formal breakdown guarantee after clipping;
- LLM output is verified evidence.

## Conformance Workflow

1. Upstream specification defines the canonical behavior.
2. JC implements deterministic runtime behavior.
3. Spec-shadow fixtures compare selected runtime outcomes against the upstream boundary.
4. Reports disclose aligned and diverged cases.
5. Divergences remain evidence, not something to delete or rename.

## Commands

```powershell
python -m pytest tests\unit\test_spec_shadow_harness.py -q
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
python -m pytest tests\ -q
python mcp_server.py --test
```

If any command cannot run, conformance reporting must say blocked and include the error.

The real MCP client/server stdio exchange passed as a subprocess regression gate. `python mcp_server.py --test` remains useful in-process evidence, but cannot satisfy that gate by itself.

Fact trust, taint, review packets, renderer firewalls, IO contracts, and provenance fields are runtime guardrails. They do not expand JC's formal-runtime claims. Changes that would accept a previously rejected certificate or alter protected semantics must be blocked and routed upstream.
