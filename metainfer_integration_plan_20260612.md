# MetaInfer Integration Record

This file records the historical MetaInfer-to-JC integration plan and its current public-kernel status. It is not an active instruction to import private or third-party material into the public repository.

## Integration Boundary

Allowed public-kernel imports:

- structural ideas that can be implemented as original JC code;
- audit methodology described without private data;
- deterministic verification contracts;
- neutral schema metadata that does not contain client facts or proprietary strategy.

Disallowed imports:

- private client records;
- closed commercial rules;
- lawyer workflow automation;
- litigation strategy;
- proprietary benchmarks;
- unlicensed third-party source material.

## Historical Tasks

| Task | Original intent | Current status |
|---|---|---|
| `juris_blueprint.json` | capture navigation, compiler passes, gates, and failure modes | superseded by public runtime contracts and manifest-driven MCP surface |
| agent skill rules | add phase gates and false-PASS checks | absorbed into repository verification and pre-release discipline |
| blind reconstruction audit | test whether public blueprint can reconstruct expected legal conclusions | retained as audit methodology; current report is evidence, not proof |

## Current Closure Standard

Any future MetaInfer-derived work must satisfy all of the following:

- clean-room implementation in JC-owned code;
- deterministic local tests;
- no direct route from LLM candidate to `verified_fact`;
- explicit evidence labels in reports;
- fail-closed behavior on missing evidence or invalid certificates;
- no private-layer material in public commits.

## Verification Hooks

Recommended checks for related work:

```powershell
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
python -m pytest tests\unit\test_spec_shadow_harness.py -q
python -m pytest tests\ -q
python mcp_server.py --test
```

If a future task reintroduces a blueprint artifact, the artifact must include its provenance, schema version, expected consumers, and promotion gate.
