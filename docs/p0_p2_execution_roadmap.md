# P0-P2 Execution Roadmap

Updated: 2026-07-01

This roadmap records the public-kernel closure line for JC. It is not a promise that private client workflows, commercial rules, or litigation strategy are part of this repository.

## P0 - Auditable Runtime Chain

Status: closed for the current public-kernel baseline.

Closed items:

- deterministic Horn closure path;
- proof trace rendering;
- AAF attack-edge construction;
- rule quality audit hooks;
- LLM batch acceptance as candidate-only ingestion;
- candidate gate and verified-fact boundary;
- certificate-style public reports;
- fail-closed red-light behavior.

Required continuing checks:

```powershell
python -m pytest tests\unit\test_post_freeze_surface.py -q
python -m pytest tests\ -q
```

## P1 - Typed IR and Constraint Sidecars

Status: closed for smoke-level public sidecars; promotion remains gated.

Closed items:

- typed-IR sidecar area;
- dry-run migrator policy;
- schema and source-anchor checks;
- no direct LLM write to curated sidecars;
- migration findings reported without silent promotion.

Promotion requirements:

- deterministic schema validation;
- source anchor availability;
- regression tests;
- public/private boundary review.

## P2 - Cross-Jurisdiction Runtime

Status: closed for public runtime architecture.

Closed items:

- jurisdiction-neutral proof tree;
- post-hoc language renderer;
- plugin registry and adapters;
- conflict-of-laws module;
- multi-jurisdiction orchestrator;
- obstruction-first routing where applicable;
- public MCP/API exposure of runtime kernel outputs.

## Current Post-Freeze Surface

The post-freeze public surface is exposed through MCP and tested through manifest dispatch. Current manifest-dispatched tool count: 33.

Validation:

```powershell
python mcp_server.py --test
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
```

## Not in Public Scope

- private client data;
- commercial rule libraries;
- lawyer workflow automation;
- litigation strategy;
- private benchmark sets;
- unverified LLM output as reasoning input.

## Next Work Gate

New functionality should enter only when it preserves:

- candidate-only LLM ingestion;
- `verified_fact` gate;
- attack/exception/permission/priority semantics;
- manifest-dispatch alignment;
- disclosure of failed or blocked evidence.
