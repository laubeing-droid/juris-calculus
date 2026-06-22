# S6: Graph Similarity Mathematical Contract

**Baseline Evidence:**
- Range [0,1]: Z3 + Dafny SMT verified (SMT_PROVED_FINITE)
- Strict reflexivity: REFUTED — counterexample G=(v=1, e=0, features=∅) gives sim(G,G)=0.4
- Empty feature policy: conservative (jaccard=0.0)

## 12 Property Audit

| Property | Status | Evidence |
|----------|--------|----------|
| boundedness | PROVED | Z3 + Dafny: sim ∈ [0,1] |
| non-negativity | PROVED | Follows from boundedness proof |
| symmetry | EMPIRICAL_ONLY | jaccard + size_ratio are symmetric |
| strict reflexivity | REFUTED | Counterexample: empty features → sim=0.4 |
| weak reflexivity | PROVED | Non-empty features: sim(G,G)=1.0 |
| identity of indiscernibles | REFUTED | Same as strict reflexivity |
| shared-feature monotonicity | EMPIRICAL_ONLY | Feature count increases sim |
| triangle inequality (d=1-sim) | UNKNOWN | Not proven or refuted |
| PSD kernel property | UNKNOWN | Not verified |
| graph relabelling invariance | PROVED | By construction |
| deterministic ranking | PROVED | Fixed weights, deterministic |
| threshold stability | EMPIRICAL_ONLY | OAT analysis needed |

## Final Classification

**Bounded symmetric similarity** — not a metric (triangle inequality unproven), not a kernel (PSD unproven), not a similarity measure in the strict sense (strict reflexivity refuted). This is a task-specific engineering score with known limitations.