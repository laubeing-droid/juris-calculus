# juris-calculus Changelog

## 3.0.0a1 - Unreleased

### Breaking architecture change

- Made `jc` the primary public interface and centralized formal evaluation in one application service.
- Replaced the legacy 33-tool/12-resource MCP surface with an optional four-tool WorkBuddy adapter and zero resources.
- Removed free-text formal evaluation, hidden legal defaults, duplicate evaluator holders, fixed memo generation, and renderer paths that could re-evaluate facts.
- Renamed the active engineering boundary to `reasoning_boundary`; the former external framework name remains only in dated migration evidence.

### Audit and visualization

- Added deterministic `CaseRequest`, semantic result, audit event, graph, bundle, checksum, completion, and semantic replay contracts.
- Added relevant-event-only logs, missing-fact review data, conflict/attack/exception/priority graph edges, and mandatory Graph JSON.
- Added explicit Markdown/Mermaid/HTML rendering from verified runs only. Profiles may change expression but not canonical fields or hashes.

### Rules, training, and advisory analysis

- Added versioned rule-pack manifests, file/source hashes, official admission gates, corpus/eligible/candidate inventories, and deterministic lookup.
- Kept 21,144 CN legacy rules candidate-only; the official CN pack remains empty and blocked pending first-party source snapshots.
- Added governed training export, missing-fact review, strategy advisory, and deterministic structural similar-case analysis. Advisory output never creates a formal certificate.

### Engineering gates

- Supports Python 3.11 and 3.12 only.
- Added hash-locked core dependencies, fail-closed `pip-audit`, clean-wheel stale-module detection, CycloneDX SBOM generation, build provenance, and a pinned upstream specification commit.
- Added numeric cold/warm/branch, memory, event-count, and audit-bundle performance budgets without omitting audit or checker work.
- Test and wheel results are release evidence only when recorded by the corresponding verification run; remote CI remains `NOT_EXECUTED` until pushed.

## Historical releases

Versions 1.x through 2.1.x were experimental runtime lines with broader MCP, adapter, renderer, and orchestration surfaces. Their interfaces are not runtime-compatible with v3; see `docs/guides/MIGRATION_V2_TO_V3.md`.
