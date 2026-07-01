# juris-calculus

juris-calculus is a public, auditable legal-reasoning runtime kernel. It exposes deterministic rule evaluation, argumentation, certificate-style reporting, differential checks against upstream specifications, and MCP/API surfaces for inspection.

It is not a private case-management system. Client data, commercial rule libraries, lawyer workflows, litigation strategy, and private benchmarks belong outside this public repository.

## Current Public Surface

| Area | Current status |
|---|---|
| MCP tools | 33 manifest-dispatched tools |
| Python tests | 312 passed, 38 skipped in the latest full local run |
| Spec shadow fixtures | 10 aligned, 0 diverged |
| Public boundary | auditable runtime kernel only |
| Private boundary | client data, business rules, workflows, strategy, private benchmarks excluded |

## Core Runtime Boundary

The project follows this safety model:

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

Raw LLM output is candidate material only. It cannot directly become `verified_fact`, cannot bypass deterministic validators, and cannot be represented as formal proof.

Do not weaken:

- `DecisionStatus`
- checker acceptance criteria
- `verified_fact` eligibility
- attack and exception semantics
- permission and priority semantics
- fail-closed behavior for red-light cases

## Repository Layout

| Path | Purpose |
|---|---|
| `compiler_core/` | deterministic runtime kernel and post-freeze public surface |
| `mcp_server.py` | JSON-RPC/MCP dispatch entrypoint |
| `mcp_manifest.json` | public tool manifest |
| `configs/` | public rule/configuration fixtures and typed-IR sidecar area |
| `runtime/` | runtime differential evidence and generated spec-shadow outputs |
| `tests/` | Python regression, contract, and surface tests |
| `docs/` | public contracts, roadmap, closure evidence, and remediation notes |
| `reports/` | audit reports and analysis outputs |

Ignored local folders may exist for downloads, raw source drops, and private workspace material. They are not part of the public kernel.

## Verification Commands

Recommended local baseline:

```powershell
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
python -m pytest tests\unit\test_post_freeze_surface.py -q
python -m pytest tests\unit\test_spec_shadow_harness.py -q
python -m pytest tests\ -q
python mcp_server.py --test
git diff --check
```

Supply-chain audits should be run before release or push when network access permits. If PyPI or OSV access is blocked by proxy or TLS failure, record the exact blocked command and error.

## Evidence Levels

| Label | Meaning |
|---|---|
| runtime regression evidence | pytest or local deterministic command output |
| differential evidence | fixture comparison against legal-math specification boundary |
| finite SMT check | bounded solver check for a stated property |
| upstream formal proof | Lean theorem in the legal-math specification repository |
| empirical heuristic | useful engineering behavior without formal guarantee |

This repository must not claim more than the evidence supports.

## MCP Surface

The MCP surface is manifest-driven. `mcp_manifest.json` and `mcp_server.py` must stay aligned. Tests require every post-freeze public surface tool to appear in the manifest and dispatch successfully.

Use:

```powershell
python mcp_server.py --test
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
```

## Formal-Spec Relationship

legal-math-modeling owns canonical Lean specification work. JC owns runtime implementation, manifest exposure, differential harnesses, and auditable evidence reports.

When a requested change would alter attack, exception, permission, priority, acceptance, or verified-fact semantics, route it upstream to legal-math-modeling before changing the runtime.

## Disclosure

Public reports should disclose:

- command run;
- commit or working-tree context when available;
- pass/fail result;
- skipped or blocked checks;
- remaining risks.

Do not remove failed evidence, bypass tests, or convert empirical output into proof language.
