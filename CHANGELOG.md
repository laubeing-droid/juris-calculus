# juris-calculus Changelog

## Unreleased (2026-07-01)

### Public Kernel Closure

- Expanded the MCP public surface to 33 manifest-dispatched tools.
- Added post-freeze public-kernel outputs for certificate reporting, evidence suggestions, attack graph tracing, spec differential evidence, batch audit, candidate gating, governance, impact analysis, route guarding, damages baseline, sample-deviation checks, stress fixtures, and private-layer boundary reporting.
- Aligned MCP manifest entries with `mcp_server.py` dispatch and added regression tests that require every public surface tool to remain manifest-visible.
- Standardized API/MCP responses around auditable public envelopes.
- Preserved the boundary that LLM output is candidate material only and cannot directly become `verified_fact`.

### Differential Evidence

- Added JC spec-shadow differential evidence against the upstream legal-math boundary.
- Current local fixture report: 10 aligned fixtures, 0 divergences.
- Kept the report scoped to runtime conformance evidence; it is not a claim that the whole Python runtime has a machine-checked proof.

### Documentation and Disclosure

- Rewrote public documentation around current repository scope, source boundaries, verification states, LLM ingestion, and runtime/formal conformance.
- Removed stale version, path, and test-count claims that referred to earlier repository layouts.
- Clarified that public JC contains the auditable kernel only; private data, commercial rule libraries, lawyer workflows, litigation strategy, and private benchmarks stay outside the public tree.

### Verification Snapshot

- Full local Python suite: `312 passed, 38 skipped`.
- MCP manifest-dispatch self-test: 33 tools exposed.
- Supply-chain audit remains environment-dependent when external OSV/PyPI access is blocked by proxy or TLS failure; blocked commands must be reported instead of treated as passed.

## v3.0.0 (2026-06-18)

### Math-Model Landing

- Landed the four-stage runtime pipeline:
  - Horn closure
  - AAF attack graph construction
  - grounded extension
  - trust-label projection and claim marking
- Added modules for source manifests, evidence evaluation, burden tracking, legal reasoning, cross-jurisdiction routing, sentencing, valuation, compliance, arbitration, proof trace rendering, visualization, inference caching, export, and result diffing.
- Added public runtime evidence for large fixture runs while keeping the formal proof boundary in the upstream specification repository.

### Public Tooling

- Expanded MCP/API functionality for policy, evidence, analogy, cross-jurisdiction routing, proof trace formatting, and query workflows.
- Added optimization and audit utilities for rule conflict detection, deduplication, coverage, sampling, freshness, version tracking, distillation, calibration, OCR repair, concept disambiguation, dashboards, knowledge graphs, and model comparison.

## v2.1.x (2026-06-14 to 2026-06-15)

### Cross-Jurisdiction Runtime

- Added ProofTree output and post-hoc language rendering.
- Added CN, HK, and US adapters with jurisdiction-specific rule loading, L0 mappings, modal mapping, blocking rules, and plugin discovery.
- Added conflict-of-laws and multi-jurisdiction orchestration modules.
- Fixed prohibition blocking, deterministic execution order, L0 degradation behavior, source-anchor warnings, and CN atom naming consistency.

## v2.0.0 (2026-06-14)

### DDL and Guardrails

- Added DDL modality classification and runtime modality gates.
- Added evidence-chain validation, de-jure audit, cross-jurisdiction comparison, multi-solver routing, validity-state tracking, invariance metrics, defeasible priority, PROLEG translation, anonymization, knowledge-graph recall, and LLM batch acceptance.
- Added neural guardrail contracts and privacy-gated LLM bridge automation.

## v1.x (2026-06-02 to 2026-06-04)

### Early Runtime

- Added the original rule evaluator, PRC/US/HK routing experiments, MCP server, operator registry, long-tail saturation tooling, and shadow runner.
- Published the first public repository line with requirements, unit tests, and YAML rule loading.
