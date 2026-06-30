# Formal-to-Runtime Conformance - juris-calculus

**Date:** 2026-07-01
**Upstream formal specs:** `legal-math-modeling` (Lean 4, mathlib)
**Control repo:** `deli-autoresearch` (source-bounded orchestration and evidence gates)

---

## 1. Provenance

| Layer | Source | Evidence |
|-------|--------|----------|
| Formal semantics | `legal-math-modeling/proofs/lean/juris_lean/` | GitHub Actions run `28465952314` on SHA `2ab6cda38f2392cd048bc0643e56fb5f9fc46708` completed successfully with `lake build --rehash` and scan |
| Theorem manifest | `legal-math-modeling/docs/formal-release/theorem_manifest.json` | `formal-core-v1-plus-four-slices`: 32 Lean files, 42 formal-core module theorems, 84 supporting results, 126 total checked results, 32 four-slice vertical results |
| Release boundary | `legal-math-modeling/docs/formal-release/ALLOWED_CLAIMS.md` and release reports | legal-math provides a formal specification boundary and checked vertical slices; it does not certify the full Python runtime end to end |
| Runtime conformance | `runtime/spec_shadow_report.json`, `runtime/spec_shadow_report.md`, and pytest | Spec shadow differential status `PASS`: 10 aligned fixtures, 0 divergences; full local pytest `312 passed, 38 skipped` |
| MCP/API contract | `mcp_manifest.json`, `mcp_server.py`, `tests/unit/test_mcp_manifest_dispatch.py` | Manifest tools and dispatch handlers are one-to-one and return the required public envelope |

---

## 2. Current Canonical Claims

### Claim 1: Lean checks the formal specification boundary

- The current formal release boundary is `formal-core-v1-plus-four-slices`.
- The checked Lean surface includes the prior formal core plus contract breach, license, permission, and priority vertical slices.
- `LegalSyntax.lean`, `DDLDefinitions.lean`, `CertificateChecker.lean`, `HornAAFContract.lean`, `AttackDecision.lean`, `SafetyTheorems.lean`, and `EndToEnd.lean` are real checked modules in the upstream repo.
- Custom-axiom disclosure remains a release boundary item; Lean built-in axioms are disclosed separately from project-level assumptions.

### Claim 2: JC runtime passes differential, checker, and MCP contract tests

| Test Suite | Status |
|------------|--------|
| `tests/unit/test_spec_shadow_harness.py` | PASS |
| `tests/unit/test_post_freeze_surface.py` | PASS |
| `tests/unit/test_mcp_manifest_dispatch.py` | PASS |
| `runtime/spec_shadow_report.json` | PASS, 10 aligned fixtures |

The StratifiedEvaluator pipeline remains an engineering runtime implementation: Horn closure -> AAF construction -> grounded extension -> trust-label projection.

### Claim 3: Trust-label and LLM gates fail closed

- LLM outputs are candidates only; they are marked `TAINTED`/`CANDIDATE_ONLY` and do not enter the kernel directly.
- Engineering estimates such as damages baselines use `ENGINEERING_BASELINE` and do not modify `DecisionStatus`.
- Cross-jurisdiction routing guards can block or mark risk, but they do not prove legal equivalence and do not change the formal kernel semantics.

### Claim 4: MCP/API outputs use the public envelope

Every manifest tool returns:

```json
{
  "status": "ok|error|blocked",
  "decision_status": "PROVED|REFUTED|UNDECIDED|TAINTED|null",
  "trace": {},
  "certificate": {},
  "risk_labels": [],
  "semantic_boundary": "ENGINEERING_ONLY|SEMANTIC_BOUNDARY",
  "public_private_classification": "PUBLIC_KERNEL|PRIVATE_LAYER|BLOCKED",
  "evidence": [],
  "payload": {}
}
```

---

## 3. What JC Does Not Claim

1. JC does not claim the full Python runtime is Lean-checked end to end.
2. JC does not let LLM confidence, case similarity, or empirical damages estimation override symbolic status.
3. JC does not treat cross-jurisdiction routing as a proof of legal equivalence.
4. JC does not publish customer evidence, private rule assets, lawyer workflow templates, or litigation strategy.

---

## 4. Verification Commands

```powershell
$env:LEGAL_MATH_MODELING_ROOT = "D:\Codex\数学证明\legal-math-modeling"
python -m pytest tests\unit\test_spec_shadow_harness.py -q
python -m pytest tests\unit\test_post_freeze_surface.py -q
python -m pytest tests\unit\test_mcp_manifest_dispatch.py -q
python -m compiler_core.spec_shadow_harness --spec-root "$env:LEGAL_MATH_MODELING_ROOT" --output .\runtime\spec_shadow_report.json --markdown-output .\runtime\spec_shadow_report.md
```
