# G8 Truncation Map

This remediation note identifies runtime locations where iteration limits can truncate reasoning. The public goal is fail-closed signaling, not silent completeness claims.

## Truncation Sources

| Source | Semantic stage | Pure Horn | Risk | Current handling |
|---|---|---|---|---|
| full evaluator loop | mixed runtime evaluation | no | safety ceiling may stop mixed reasoning | retain ceiling; disclose truncation risk |
| `evaluate_horn()` loop | pure Horn closure | yes | missed derivation if bound too low | derived bound plus truncation signal |
| exception-chain depth | non-monotonic exception traversal | no | cuts exception exploration | intentional guard |
| critical-streak early exit | non-monotonic safety behavior | no | can stop heuristic path | not a Horn-completeness claim |

## Horn Path Rule

For pure Horn closure, a derived bound is available:

```text
derived_bound = number_of_distinct_rule_heads + 1
```

The `+1` permits a no-growth saturation iteration. The pure Horn path should report whether it saturated or truncated.

## Required Signals

Reports and state objects should expose:

- `horn_saturated`;
- `horn_truncated`;
- `horn_truncation_reason`;
- `horn_derived_bound`;
- `horn_iterations`.

## Disclosure

`evaluate_horn()` is the authoritative pure-Horn completeness path. The full evaluator mixes Horn reasoning with non-monotonic rebuttal and constraint behavior, so it must not reuse pure-Horn proof language unless the mixed semantics have been specified and verified.

## Upstream Boundary

Formal Horn completeness theorem work belongs in legal-math-modeling. JC should cite it only as upstream specification evidence and should still keep runtime truncation signals observable.
