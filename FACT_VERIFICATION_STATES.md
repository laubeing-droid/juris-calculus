# Fact Verification States

Purpose: define the lifecycle states for facts and fact-like candidates before they are allowed into the formal reasoning kernel.

This file pairs with:

- `LLM_INGESTION_CONTRACT.md`
- `SEMANTIC_BOUNDARY_CHECKLIST.md`
- `FORMAL_RUNTIME_CONFORMANCE.md`

---

## 1. State Machine Overview

Default lifecycle:

```text
raw text
  -> extracted_candidate
  -> normalized_candidate
  -> verified_fact

or

raw text
  -> extracted_candidate
  -> normalized_candidate
  -> disputed_fact
  -> verified_fact | rejected_candidate

or

raw text
  -> extracted_candidate
  -> rejected_candidate
```

No state other than `verified_fact` is reasoning-eligible by default.

---

## 2. Canonical States

## 2.1 `extracted_candidate`

Meaning:

- a model or parser proposed a candidate item from raw material
- the candidate has not yet been normalized into canonical schema
- the candidate is not authoritative

Requirements:

- source document id
- source span or equivalent provenance anchor
- candidate text
- extraction method or model id

Allowed downstream use:

- queue for normalization
- human review
- weak-label storage

Forbidden downstream use:

- Horn input
- AAF input
- certificate basis
- final legal status basis

## 2.2 `normalized_candidate`

Meaning:

- the candidate has been mapped into canonical schema fields
- normalization completed, but verification is still incomplete

Requirements:

- successful schema mapping
- normalized field values
- deduplication status
- provenance still attached

Allowed downstream use:

- verification workflow
- conflict detection
- review queue

Forbidden downstream use:

- direct formal reasoning
- certificate issuance

## 2.3 `verified_fact`

Meaning:

- the candidate passed the repository's fact-verification gate
- the candidate is eligible to become formal input to the reasoning kernel

Minimum requirements:

- canonical mapping succeeded
- provenance preserved
- no unresolved blocking conflict
- verification policy satisfied

Verification may come from:

- deterministic validation
- source-backed rule
- human review
- approved multi-stage validation workflow

Allowed downstream use:

- Horn input
- AAF construction basis
- certificate basis
- trust-label reasoning

## 2.4 `disputed_fact`

Meaning:

- there is a material conflict, ambiguity, or unresolved challenge
- the candidate cannot safely be promoted to verified input yet

Typical triggers:

- conflicting spans
- conflicting parties
- contradictory extracted statements
- uncertain temporal ordering
- multiple plausible legal interpretations

Allowed downstream use:

- human review queue
- dispute analysis
- taint propagation logic if the system models uncertainty explicitly

Forbidden downstream use:

- direct authoritative Horn input unless a future contract explicitly allows it

## 2.5 `rejected_candidate`

Meaning:

- candidate failed validation and must not enter the formal reasoning path

Typical triggers:

- unsupported hallucinated content
- schema mapping impossible
- OCR corruption too severe
- provenance missing
- duplicate collapsed into a different surviving record

Allowed downstream use:

- audit trail
- training error analysis

Forbidden downstream use:

- any formal reasoning role

---

## 3. Optional Future States

These are optional and should be added only if they solve a real workflow need:

- `human_review_required`
- `source_conflicted`
- `temporally_incomplete`
- `jurisdiction_unresolved`
- `verification_timeout`

Rule:

adding any new state that affects reasoning eligibility is a semantic-boundary change.

---

## 4. Transition Rules

## 4.1 Allowed Default Transitions

- `extracted_candidate -> normalized_candidate`
- `extracted_candidate -> rejected_candidate`
- `normalized_candidate -> verified_fact`
- `normalized_candidate -> disputed_fact`
- `normalized_candidate -> rejected_candidate`
- `disputed_fact -> verified_fact`
- `disputed_fact -> rejected_candidate`

## 4.2 Forbidden Default Transitions

- `extracted_candidate -> verified_fact` without explicit verification gate
- `rejected_candidate -> verified_fact` without full re-validation
- any blocked state directly into final legal conclusion

---

## 5. Reasoning Eligibility Matrix

| State | Horn Input | AAF Basis | Certificate Basis | Human Review | Weak Supervision |
| --- | --- | --- | --- | --- | --- |
| `extracted_candidate` | No | No | No | Yes | Yes |
| `normalized_candidate` | No | No | No | Yes | Yes |
| `verified_fact` | Yes | Yes | Yes | Optional | Yes |
| `disputed_fact` | No | No | No | Yes | Yes |
| `rejected_candidate` | No | No | No | Optional | Yes |

Default policy:

- formal kernel consumes `verified_fact` only

Any exception to that policy must be documented and reviewed as a semantic change.

---

## 6. Required Metadata by State

All states require:

- stable record id
- source provenance
- candidate or normalized content
- creation timestamp

Additional requirements:

- `normalized_candidate`: canonical field mapping
- `verified_fact`: verifier identity or rule
- `disputed_fact`: dispute reason
- `rejected_candidate`: rejection reason

---

## 7. Interaction with Trust Labels

Fact verification state is upstream of trust labels.

Meaning:

- a `verified_fact` may still lead to `UNDECIDED` or `TAINTED` results later
- a non-verified candidate cannot become authoritative merely because the downstream confidence is high

Trust labels do not replace fact verification.
Fact verification does not guarantee dispositive conclusion.

---

## 8. Human Review Guidance

Human review is especially recommended for:

- dispositive facts
- exception-triggering facts
- priority-triggering facts
- burden-shifting facts
- constitutive status facts
- temporal ordering facts that change the outcome

If missing human review would materially alter the legal result, keep the state below `verified_fact`.

---

## 9. Audit Requirements

For each promoted `verified_fact`, the system should be able to answer:

1. where did this come from
2. what text span supports it
3. who or what verified it
4. when was it promoted
5. what earlier state did it come from

If those answers are unavailable, promotion should be treated as invalid.

---

## 10. Implementation Guidance

When introducing code paths that manipulate these states:

- keep transitions explicit
- log transition reason
- preserve provenance
- preserve downgrade paths
- fail closed on missing metadata

A state machine table in code is preferred over scattered ad hoc conditionals.
