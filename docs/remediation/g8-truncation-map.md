 # G8 Truncation Map: evaluator.py Hardcoded Cutoff Points

 **Created**: 2026-06-23
 **Base Commit**: ab2ac6f
 **Goal**: Identify every truncation source that could silently cut Horn closure short.

 ## Truncation Sources

 | # | Line | Code | Semantic Stage | Pure Horn? | Can Cause Missed Derivation? | Has TRUNCATED Signal? | Fixed? |
 |---|------|------|---------------|------------|------|------|------|
 | 1 | 360 | `while state.iteration_count < state.max_iterations` | Full fixpoint evaluation | Mixed | YES - silent cutoff | No (only external wrapper) | **No (separate Horn path fixed, see #2)** |
 | 2 | 565 | `while state.iteration_count < state.max_iterations` | `evaluate_horn()` Horn closure | Pure Horn | YES - if max_iterations < derived_bound | No | **FIXED: uses min(derived_bound, max_iterations); sets horn_truncated when max_iterations < derived_bound** |
 | 3 | 514 | `if depth > self.config.k_max: return None` | Exception-chain traversal | No (non-monotonic) | NO - depth limit on exception chains, not Horn closure | No | No (intentional non-monotonic guard) |
 | 4 | 482 | `if low_streak >= self.config.critical_streak_max` | Streak-based early exit | No (non-monotonic) | YES - if triggered in Horn-only mode | No | No (separate concern: non-monotonic safety) |

 ## Horn-Specific Analysis

 ### evaluate_horn() (line 555, now fixed)

 Before fix: Used hardcoded `state.max_iterations` (default 100) as the only loop bound.
 After fix: Uses `min(derived_bound, state.max_iterations)` where `derived_bound = |distinct rule heads| + 1`.
 New signals: `horn_saturated`, `horn_truncated`, `horn_truncation_reason`, `horn_derived_bound`, `horn_iterations`.

 Derived bound formula:
 ```
 U = initial facts Union all possible ground rule heads
 max_strict_growth_steps = |distinct heads|
 derived_bound = max_strict_growth_steps + 1
 ```

 Guarantee: In pure Horn closure, T_H can produce at most one new ground atom per distinct head. If a rule has head H, once H is derived, it cannot be derived again. Therefore at most |distinct heads| growth steps before fixpoint. The +1 accounts for the initial iteration that may produce nothing new (empty rule set).

 ### evaluate() (line 347, not yet fixed for pure Horn)

 The full evaluator mixes Horn forward-chaining with non-monotonic rebuttal/constraint logic.
 For the pure Horn path, this should ideally also use derived_bound. However, because rebuttal
 and constraint rules can add complexity, the conservative approach is to keep max_iterations
 as a safety ceiling but add TRUNCATED signaling when it's hit before saturation.

 ## Resolution

 - evaluate_horn(): Fixed to use derived bound. If state.max_iterations is lower, it signals horn_truncated.
 - evaluate(): Retains max_iterations as safety ceiling, but the evaluate_horn path is the authoritative Horn closure.
 - config.k_max: Separate concern (non-Horn exception chain depth). Not a Horn completeness issue.
 - critical_streak_max: Separate concern (non-monotonic safety). Not a Horn completeness issue.

 ## Lean Verification

 The 8 G8 Horn Lean theorems (horn_operator_monotone, horn_iteration_monotone, finite_horn_termination, etc.) are in legal-math-modeling under `proofs/lean/juris_lean/JurisLean/HornCompleteness.lean`.
