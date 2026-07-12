# Input and semantic boundary

JC is a public runtime kernel. Its fixed boundary is:

```text
LLM proposes -> verification gates decide -> formal kernel reasons
```

## Fact admission

| State | Meaning | Reasoning eligible |
|---|---|---|
| `candidate_fact` | proposed by an LLM, user, importer, or parser | no |
| `normalized_fact` | syntactically normalized but unverified | no |
| `source_bound_fact` | linked to a declared source anchor | no |
| `checked_fact` | passed deterministic local checks | no |
| `verified_fact` | passed the configured verification gate | yes |
| `rejected_fact` | failed verification or required-evidence checks | no |
| `stale_fact` | invalidated by source or version drift | no |

Only `verified_fact` may enter formal reasoning. A fact moves through deterministic gates; a missing source, schema error, failed checker, or contradiction stops promotion. LLM output cannot directly create `verified_fact`, override a failed checker, or fill missing evidence by narrative.

`UNKNOWN` produces missing-fact review data, `DISPUTED` produces review-only branches, and `USER_ASSUMED` produces hypothetical results. None may produce a formal certificate.

## Allowed LLM role

LLMs may propose candidate facts, candidate rule mappings or source anchors, draft explanations, fixture suggestions, and suspected inconsistencies. They must not directly produce accepted certificates, checker passes, formal proof claims, public release evidence, or protected semantic changes.

Before candidate material affects reasoning, the applicable deterministic gate must pass:

| Material | Required gate |
|---|---|
| fact | schema, source binding, verification |
| rule | schema, modality, source anchor, regression checks |
| certificate | certificate checker |
| MCP response | manifest dispatch and envelope tests |
| differential claim | spec-shadow harness |

If a gate fails or is blocked, the material remains candidate-only or is rejected.

## Route upstream before changing

Changes to the following belong first in `legal-math-modeling`:

- `DecisionStatus` or certificate acceptance;
- `verified_fact` eligibility;
- Horn closure, attack, exception, permission, or priority semantics;
- fail-closed behavior.

JC may handle presentation, manifest exposure, deterministic reporting, documentation, and bug fixes that restore the established specification. Before a change, ask whether it accepts previously rejected material, weakens checking, changes protected ordering, or hides a red-light failure. If yes, stop and route upstream.

## Evidence after a change

Record the command, result, affected boundary, upstream-decision need, and remaining risk. Runtime tests, differential fixtures, finite SMT checks, upstream Lean theorems, and empirical heuristics are distinct evidence classes; no empirical result is a formal proof.
