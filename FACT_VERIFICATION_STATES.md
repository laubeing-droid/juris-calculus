# Fact Verification States

This document defines the public fact-state boundary used by JC runtime and documentation.

## State Model

| State | Meaning | Reasoning eligible |
|---|---|---|
| `candidate_fact` | proposed by an LLM, user, importer, or parser | no |
| `normalized_fact` | syntactically normalized but not verified | no |
| `source_bound_fact` | linked to a declared source anchor | no |
| `checked_fact` | passed deterministic local checks | limited, only where the caller explicitly accepts this weaker state |
| `verified_fact` | passed the configured verification gate for reasoning | yes |
| `rejected_fact` | failed verification or contradicted required evidence | no |
| `stale_fact` | previously accepted but invalidated by source/version drift | no |

Only `verified_fact` is reasoning-eligible by default.

## Promotion Rules

A fact can move forward only through deterministic gates:

```text
candidate_fact -> normalized_fact -> source_bound_fact -> checked_fact -> verified_fact
```

Any missing source, schema failure, failed checker, or contradiction must stop promotion. The runtime must fail closed rather than silently downgrade the evidence requirement.

## LLM Boundary

LLM output can create `candidate_fact` only. It cannot:

- create `verified_fact` directly;
- override a failed checker;
- fill missing evidence by narrative;
- convert experience, analogy, or probability into formal proof;
- bypass source-bound requirements.

## Demotion Rules

A fact must be demoted or rejected when:

- its source anchor disappears or changes;
- a higher-priority exception applies;
- a deterministic checker reports failure;
- differential verification diverges;
- the fact was derived from private material that cannot be exposed in the public kernel.

## Public Reporting

Reports should disclose:

- input state;
- gate applied;
- output state;
- failure reason when rejected;
- evidence location;
- whether the fact is eligible for runtime reasoning.

Do not describe `candidate_fact`, `normalized_fact`, or `source_bound_fact` as verified.

## LSC Boundary Absorption Note

LSC terms are engineering boundary aliases only. `ADMITTED`, `VERIFIED`, `COURT_FIXED`, `USER_ASSUMED`, `DISPUTED`, and `UNKNOWN` can be mapped into JC fact-trust envelopes, but the formal meaning of `verified_fact` remains the one defined in this document.

`USER_ASSUMED`, `DISPUTED`, and `UNKNOWN` do not create formal proof. They trigger hypothetical, review-only, or missing-fact outputs unless a deterministic JC gate promotes the material under the existing verified-fact rules.

If an LSC absorption change would alter `verified_fact` eligibility, checker acceptance, Horn closure, or fail-closed behavior, the change must route back to `D:\Codex\数学证明\legal-math-modeling` before JC implementation.
