# Formal-to-Runtime Conformance — juris-calculus

**Date:** 2026-06-30
**Upstream formal specs:** `legal-math-modeling` (Lean 4, mathlib)
**Control repo:** `deli-autoresearch` (specs, evidence, release boundary)

---

## 1. Provenance

| Layer | Source | Evidence |
|-------|--------|----------|
| Formal semantics | `legal-math-modeling/proofs/lean/juris_lean/` | `lake build JurisLean` (2954 jobs, 0 errors) |
| Theorem manifest | `legal-math-modeling/docs/formal-release/theorem_manifest.json` | 100 entries / 94 unique theorem names / 43 core unique names |
| Release boundary | `legal-math-modeling/docs/formal-release/FORBIDDEN_CLAIMS.md` + `ALLOWED_CLAIMS.md` | Python runtime is not Lean-proven end-to-end |
| Runtime conformance | This document + test suite below | 296 passed, 38 skipped |

---

## 2. Four Canonical Claims

### Claim 1: Lean proves the mathematical specification

- 94 unique theorem names across 100 manifest entries
- 43 core unique theorem names in the released finite monotone / Horn / Dung / weighted-norm boundary
- Umbrella build `lake build JurisLean` succeeds (2954 jobs)
- `AxiomAudit` discloses only Lean built-in axiom dependencies (`propext`, `Classical.choice`, `Quot.sound`)
- Planned ghost files such as `LegalSyntax.lean`, `DDLDefinitions.lean`, and `CertificateChecker.lean` do not exist and are not claimed as built

### Claim 2: JC runtime passes differential, checker, and refinement tests

| Test Suite | Tests | Status |
|------------|-------|--------|
| `test_canonical_serialization.py` | 8 | PASS |
| `test_independent_checker.py` | 10 | PASS |
| `test_stratified_evaluator.py` | 4 | PASS |
| Full suite (`pytest tests`) | 296 | PASS (38 skipped: spacy deps) |

The StratifiedEvaluator's 4-stage pipeline (Horn closure → AAF construction → grounded extension → trust labels) is operational as of commit `8c802df`.

### Claim 3: Three deferred domain axioms are retained, not proven

The following are planned non-blocking domain axioms in `legal-math-modeling/SORRY_LEDGER.md`. `DDLDefinitions.lean` does not yet exist, so JC must not describe these as built or Lean-proven:

1. `violation_implies_norm_active`
2. `permission_no_direct_violation`
3. `constitutive_no_direct_violation`

Registered upstream as planned domain gaps. JC must NOT claim these are Lean-proven.

### Claim 4: Trust-label layer is fail-closed

The `DecisionStatus` enum (`PROVED`, `REFUTED`, `UNDECIDED`, `TAINTED`) follows a no-upgrade contract:
- TAINTED decisions always fail the certificate checker (returns false)
- Grounded extension only accepts arguments with confidence > 0
- The independent grounded checker (`independent_grounded_checker.py`) cross-validates JC's evaluator output

Fail-closed test: `tests/unit/test_litigation_renderer.py::test_fail_closed_boundary`

---

## 3. Runtime Contract Boundaries

### 3.1 Canonical Serialization

Module: `compiler_core/canonical_serialization.py`

- AAF: deterministic JSON with sorted arguments and attacks
- Horn: deterministic JSON with sorted rules
- Round-trip: serialize → deserialize → serialize produces identical output
- Tests: `tests/test_canonical_serialization.py` (8 tests)

### 3.2 Independent Grounded Checker

Module: `compiler_core/independent_grounded_checker.py`

- Reimplements Dung grounded extension from scratch (not importing JC evaluator)
- Cross-checks JC evaluator output against its own computation
- Detects wrong labels (IN/OUT/UNDEC mismatch)
- Tests: `tests/test_independent_checker.py` (10 tests)

### 3.3 Certificate Emission

Module: `compiler_core/certificate_checker.py`

- 4 certificate types: `HornCertificate`, `GroundedINCertificate`, `OUTCertificate`, `UNDECCertificate`
- Each embeds input hash, decision, and derivation witnesses
- Designed for independent verification (checker does not call production evaluator)

### 3.4 StratifiedEvaluator Pipeline

Module: `compiler_core/stratified_evaluator.py`

- Stage 1: `evaluate_horn()` — pure monotone Horn closure
- Stage 2: `build_attack_graph_from_evaluator()` — AAF attack edges from priority/exception
- Stage 3: `grounded_extension()` — Dung deterministic fixed-point
- Stage 4: Trust label projection + allowed/forbidden marking
- Returns `List[LegalClaim]`

---

## 4. What JC Does NOT Claim

1. JC runtime is NOT "fully Lean-proven." Lean proves the mathematical specification; JC implements it in Python with runtime tests.
2. The 3 deferred domain axioms are NOT proven. They are model structural gaps.
3. `UnifiedModel.lean` is a standalone composition proof (Kripke → Horn → AAF → Banach). It is not part of the JC runtime contract.
4. Safety conjuncts in `certified_end_to_end_refinement` are caller-provided premises, not derived from the checker.

---

## 5. Verification Commands

```bash
# Lean formal proof chain
cd legal-math-modeling/proofs/lean/juris_lean && lake build JurisLean

# JC full test suite
cd juris-calculus && python -m pytest tests -q -ra

# JC StratifiedEvaluator specifically
cd juris-calculus && python -m pytest tests/unit/test_stratified_evaluator.py -v

# JC canonical serialization
cd juris-calculus && python -m pytest tests/test_canonical_serialization.py -v

# JC independent checker
cd juris-calculus && python -m pytest tests/test_independent_checker.py -v
```
