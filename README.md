# juris-calculus

juris-calculus (JC) is a public, auditable legal-reasoning kernel. Its primary interface is the `jc` CLI. It accepts explicit structured facts, applies only integrity-checked and reasoning-eligible rules, writes a complete audit bundle, and returns machine-readable results.

JC is not a case-management system or a replacement for lawyer judgment. Private case data, commercial rule packs, drafting workflows, litigation operations, and lawyer-specific style overlays stay outside the public repository. The public kernel is fixed to neutral, stable, auditable output.

## Safety boundary

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

Candidate, unknown, disputed, and user-assumed facts cannot silently become `verified_fact`. Missing sources cannot silently become reasoning-eligible rules. Rendering and advisory analysis cannot modify a canonical result or generate a formal certificate.

## Install and inspect

Supported Python versions are 3.11 and 3.12.

```powershell
python -m pip install .
jc --version
jc doctor --json
jc packs list --json
jc packs verify --all --json
```

The bundled `cn-official` pack is intentionally not reasoning-ready until official first-party source snapshots are supplied. Legacy corpora remain available for governance, lookup, and training export, not formal reasoning.

## Primary workflow

```powershell
jc evaluate --input case-request.json --json
jc replay --run <run-id> --json
jc render --run <run-id> --format markdown --json
jc analyze strategy --run <run-id> --json
jc analyze similar-cases --run <run-id> --index case-index.json --json
```

`evaluate` always writes the semantic result, relevant event log, reasoning graph, checksums, and completion marker. Graph JSON is always produced; HTML is produced only when explicitly requested through `render`.

## Optional WorkBuddy adapter

JC is CLI-first. WorkBuddy may register the optional stdio adapter because WorkBuddy supports custom MCP connectors. The adapter exposes only four tools and zero resources:

- `jc_evaluate`
- `jc_lookup_rule`
- `jc_analyze_strategy`
- `jc_analyze_similar_cases`

The adapter delegates to the same application, audit, lookup, and advisory services. It does not contain another evaluator or rule loader. See [docs/WORKBUDDY.md](docs/WORKBUDDY.md).

## Auditing and visualization

Every completed run contains `input.json`, `events.jsonl`, `result.json`, `graph.json`, `manifest.json`, `checksums.sha256`, and `COMPLETE`. Replay verifies both file hashes and semantic digests. Logs include only relevant rules/events and exclude raw case narrative by default.

See:

- [CLI contract](docs/CLI.md)
- [Audit bundle and replay](docs/AUDIT_BUNDLE.md)
- [Rule packs and promotion](docs/RULE_PACKS.md)
- [Rendering and profiles](docs/rendering-and-profiles.md)
- [v2 to v3 migration](docs/MIGRATION_V2_TO_V3.md)

## Local verification

```powershell
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
python -m pytest tests\unit\test_v3_entrypoint_boundary.py -q
python -m pytest tests\unit\test_spec_shadow_harness.py -q
python -m pytest tests\ -q
python mcp_server.py --test
python tools\supply_chain_gate.py --requirements requirements-core.lock
git diff --check
```

`python mcp_server.py --test` is an in-process surface smoke, not a readiness claim. The authoritative transport test launches a real subprocess. Remote GitHub Actions results are not claimed until a branch is pushed and the workflow actually runs.

Current local baseline: `484 passed, 38 skipped` on both supported Python versions.

## Evidence levels

Runtime tests, differential fixtures, finite SMT checks, upstream Lean theorems, and empirical heuristics are distinct evidence classes. JC does not present empirical output as a formal proof.
