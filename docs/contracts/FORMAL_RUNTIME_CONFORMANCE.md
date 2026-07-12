# Formal runtime conformance and placeholder boundary

## Scope

| Repository | Responsibility |
|---|---|
| `legal-math-modeling` | canonical Lean specification, DDL core, Horn-to-AAF contracts, certificate-checker theorem statements |
| `juris-calculus` | Python runtime, deterministic tests, audit/replay, CLI, and optional MCP exposure |

JC does not claim machine-checked proof for every Python execution path or direct legal correctness for real client cases. Runtime conformance claims require identified deterministic tests, finite checks, or spec-shadow fixtures.

## Evidence and non-claims

| Evidence | Disclosure |
|---|---|
| Python tests | runtime regression evidence; record command and result |
| spec-shadow fixtures | differential evidence; report aligned and diverged cases |
| finite SMT checks | bounded check, not a universal theorem |
| upstream Lean theorem | cite as upstream specification evidence |
| empirical heuristic or diagnostic | state its task-specific limits |

Do not call graph similarity a metric or kernel without proof, diagnostics-only privacy output a DP guarantee, a robust-regression heuristic a formal guarantee, or LLM output verified evidence.

## Placeholder rule

Acceptance-critical paths may not contain silent placeholders. Any intentional incomplete path must be outside the acceptance path or fail closed, name its closing task and verification command, and never be described as formal proof.

Critical paths include candidate admission, verified-fact admission, certificate checking, MCP dispatch, spec-shadow reporting, and attack/priority semantics. Divergences are evidence and must be reported, not deleted or renamed.

## Minimum conformance checks

```powershell
python -m pytest tests\unit\test_spec_shadow_harness.py -q
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
python -m pytest tests\ -q
python mcp_server.py --test
```

The subprocess stdio protocol test is the transport authority. `python mcp_server.py --test` is only an in-process smoke. If a required command is blocked, the report must say blocked and include the failure mode.
