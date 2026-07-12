# Changelog

## 3.0.0a1 — Unreleased

### Public boundary

- CLI is the primary interface.
- Optional WorkBuddy MCP exposes four tools and zero resources.
- Legacy 33-tool/12-resource MCP compatibility dispatch was removed.

### Auditing

- Evaluation writes an atomic audit bundle with events, result, graph, manifest, checksums, and replay support.
- Rendering is read-only, opt-in, and bound to the canonical result.

### Rule governance

- Pack manifests bind resources, inventory, source metadata, and content digest.
- Candidate-only rules remain available for governance and training export but cannot enter formal reasoning.
- `cn-official` remains blocked until first-party source snapshots are supplied.

### Engineering

- Supported Python is 3.11 and 3.12.
- Core dependency auditing uses the hash-pinned lock profile and fails closed.
- Public documentation now describes the CLI-first, auditable boundary without static test or rule-count claims.

## Earlier lines

Versions 1.x–2.1.x were experimental interfaces. They are not runtime-compatible with v3. See [v2 migration](docs/guides/MIGRATION_V2_TO_V3.md).
