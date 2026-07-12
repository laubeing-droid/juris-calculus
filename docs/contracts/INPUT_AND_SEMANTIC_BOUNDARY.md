# Input and semantic boundary

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

## Fact admission

| State | Formal reasoning |
|---|---|
| `candidate_fact`, `normalized_fact`, `source_bound_fact`, `checked_fact` | not eligible |
| `verified_fact` | eligible |
| `rejected_fact`, `stale_fact` | not eligible |

An LLM, user, importer, or parser may propose a candidate. Only deterministic schema, source-binding, and verification gates can promote it to `verified_fact`. Narrative cannot override a failed gate.

`UNKNOWN` produces missing-fact data. `DISPUTED` produces review-only branches. `USER_ASSUMED` produces hypothetical results. None can create a formal certificate.

## LLM boundary

LLMs may propose facts, rule/source mappings, explanations, fixtures, or suspected inconsistencies. They may not create a checker pass, certificate, formal-proof claim, release evidence, or protected semantic change.

## Protected semantics

Route a proposed change to `legal-math-modeling` before changing `DecisionStatus`, verified-fact eligibility, Horn closure, attack, exception, permission, priority, certificate acceptance, or fail-closed behavior. JC may fix runtime defects, reports, manifests, and presentation only when doing so preserves those semantics.

## Evidence

Report the command, result, affected boundary, remaining risk, and any upstream-decision need. Runtime tests, differential fixtures, finite SMT checks, upstream Lean theorems, and empirical heuristics are distinct evidence classes.
