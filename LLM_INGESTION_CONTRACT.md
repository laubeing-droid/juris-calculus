# LLM Ingestion Contract

Purpose: define exactly how LLM-generated outputs may enter `juris-calculus` without contaminating the formal reasoning kernel.

This contract assumes:

- the formal reasoning kernel remains deterministic
- only verified facts may enter the Horn / AAF / grounded pipeline as authoritative inputs
- LLMs are allowed in candidate generation and normalization layers

---

## 1. Core Principle

LLM output is never equal to a verified legal fact by default.

LLM output may be used to produce:

- candidate facts
- candidate claims
- candidate rule references
- candidate timelines
- candidate issue labels
- candidate argument structures

LLM output may not directly produce:

- authoritative facts
- final decision statuses
- accepted certificate verdicts
- trust-label upgrades

Short form:

- `LLM proposes`
- `verification gates decide`
- `formal kernel reasons`

---

## 2. Ingestion Pipeline

All LLM-assisted ingestion must pass through these stages:

1. raw source acquisition
2. LLM candidate extraction
3. schema normalization
4. verification state assignment
5. gate check for reasoning eligibility
6. formal reasoning on eligible facts only

No shortcut path is allowed from stage 2 to stage 6.

---

## 3. Allowed LLM Roles

LLM usage is explicitly allowed for:

- OCR cleanup support
- section segmentation
- issue spotting
- candidate fact extraction
- candidate statute extraction
- candidate exception or defense extraction
- terminology normalization suggestions
- weak supervision labels
- draft rule encoding proposals
- candidate timeline reconstruction
- candidate proof-trace summarization for human review

These are productive but non-authoritative roles.

---

## 4. Forbidden LLM Roles

LLM usage is forbidden for:

- directly asserting a candidate as `verified_fact` without gate logic
- directly setting `PROVED`, `REFUTED`, `UNDECIDED`, or `TAINTED`
- directly certifying an argument as accepted
- directly bypassing attack / exception / priority computation
- directly declaring a certificate valid
- directly upgrading uncertain output into definitive output

If a feature proposal needs one of the above, it must be treated as a semantic-boundary change.

---

## 5. Required Candidate Payload

Every LLM-generated candidate record must carry enough metadata for later review.

Minimum required fields:

```json
{
  "candidate_id": "string",
  "candidate_type": "fact|claim|rule_ref|timeline_event|issue",
  "normalized_text": "string",
  "source_document_id": "string",
  "source_spans": [
    {
      "start": 0,
      "end": 0,
      "text": "string"
    }
  ],
  "llm_model": "string",
  "llm_run_id": "string",
  "confidence": 0.0,
  "jurisdiction": "string|null",
  "extraction_timestamp": "ISO-8601 string",
  "verification_state": "see FACT_VERIFICATION_STATES.md"
}
```

Optional but recommended fields:

- `source_url`
- `prompt_hash`
- `normalization_notes`
- `supporting_rule_refs`
- `human_reviewer`
- `review_timestamp`

---

## 6. Canonical Schema Mapping

Before a candidate can be considered by the reasoning pipeline, it must be mapped into canonical schema fields.

Required checks:

- stable type mapping
- jurisdiction mapping
- party-role normalization
- time normalization
- duplicate candidate collapse
- terminology normalization against ontology or controlled vocabulary

If canonical mapping fails, the candidate must not enter the formal reasoning layer.

---

## 7. Eligibility Gate for Formal Reasoning

Only candidates in reasoning-eligible verification states may be converted into formal input facts.

Default allowed state:

- `verified_fact`

Default blocked states:

- `extracted_candidate`
- `normalized_candidate`
- `disputed_fact`
- `rejected_candidate`

Optional future states may be introduced, but they must preserve fail-closed behavior.

---

## 8. Confidence Is Not Enough

Model confidence alone is not sufficient for formal eligibility.

Examples:

- `0.98` confidence with no source span -> blocked
- `0.95` confidence with conflicting source evidence -> blocked
- `0.62` confidence with human confirmation and source trace -> may be allowed under `verified_fact`

Formal eligibility requires state transition, not just score threshold.

---

## 9. Multi-Source and Human Review Rules

The repository should support stricter gates for higher-risk candidate types.

Suggested policy:

- low-risk structured extraction may pass with source span + deterministic normalization
- medium-risk legal interpretation candidates require second-pass validation
- high-risk normative or dispositive candidates require human review

Examples of high-risk candidate types:

- exception applicability
- burden shift
- presumption trigger
- priority override
- constitutive status change

---

## 10. Fail-Closed Rules

The ingestion layer must fail closed in these situations:

- missing source span
- ambiguous party mapping
- unresolved time conflict
- schema mapping failure
- contradictory extraction without tie-break process
- model truncation
- unverifiable OCR corruption
- missing jurisdiction context when jurisdiction matters

Fail-closed means:

- candidate stays out of formal reasoning
- no automatic upgrade to authoritative fact
- downstream output may remain incomplete or tainted

---

## 11. Integration with Runtime Conformance

This contract aligns with the runtime boundary already documented in:

- `FORMAL_RUNTIME_CONFORMANCE.md`
- `SEMANTIC_BOUNDARY_CHECKLIST.md`
- `FACT_VERIFICATION_STATES.md`

If a proposed ingestion feature would change:

- allowed input fact meaning
- checker behavior
- trust-label semantics
- certificate validity criteria

the work must be classified as `SEMANTIC_BOUNDARY`.

---

## 12. Training Data Use

LLM-generated outputs may be used as:

- weak labels
- pre-annotation
- retrieval supervision
- candidate generation corpora

They must be distinguished from:

- authoritative labels
- human-curated gold labels
- formally validated reference cases

Recommended source tiers:

- `authoritative`
- `human_curated`
- `llm_weak_label`

Do not merge these tiers into a single undifferentiated truth source.

---

## 13. Merge Gate for LLM Features

Any PR introducing or modifying LLM ingestion must answer:

1. What is the candidate type?
2. What source spans are recorded?
3. What verification state is assigned initially?
4. What transition rule allows upgrade to `verified_fact`?
5. What fail-closed path exists?
6. Does any raw LLM output enter Horn directly?
7. Does this change public correctness claims?

Required answer to question 6:

- normally `no`

If `yes`, the PR is blocked pending semantic-boundary review.
