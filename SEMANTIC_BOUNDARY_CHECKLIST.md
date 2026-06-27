# Semantic Boundary Checklist

Purpose: decide whether a proposed `juris-calculus` change is a pure engineering change or a semantic change that must be coordinated with `legal-math-modeling`.

This file exists to replace intuition-only judgment with a repeatable gate.

---

## 1. Core Rule

A change crosses the semantic boundary if it changes any of the following:

- what counts as a valid input fact
- what counts as a valid rule firing
- what counts as an attack, exception, or priority override
- what a decision status means
- what a certificate must prove
- what the checker is allowed to accept
- what the public correctness claim means

If none of those change, the work is usually an engineering change and can stay inside `juris-calculus`.

---

## 2. Two-Way Split

## 2.1 Pure Engineering Change

These normally stay in `juris-calculus` only:

- performance optimization
- caching
- concurrency
- storage or indexing changes
- API refactor with identical behavior
- UI or rendering changes
- logging and observability
- batch orchestration
- retrieval quality improvements
- reranking
- document chunking
- prompt improvements for candidate extraction
- incremental recomputation, if results remain identical to full recomputation
- certificate display or formatting changes

Required condition:

- same verified inputs
- same reasoning semantics
- same output meaning
- same certificate acceptance standard

## 2.2 Semantic Change

These must trigger review against `legal-math-modeling`:

- adding or redefining `DecisionStatus`
- changing the meaning of `PROVED`, `REFUTED`, `UNDECIDED`, or `TAINTED`
- changing trust-label escalation or fail-closed behavior
- changing Horn firing conditions
- changing what counts as an `Argument`
- changing what counts as an `Attack`
- changing exception handling semantics
- changing priority resolution semantics
- adding a new normative object such as burden shift, presumption, temporal override, or new modal operator
- changing certificate required fields in a way that changes verifiability
- changing checker verdict rules
- letting uncertain or truncated outputs upgrade into definitive conclusions
- promoting an engineering heuristic into a formal decision basis

---

## 3. The Four Questions

Before implementing a feature, answer these questions:

1. Would the same facts and rules produce a different legal conclusion after this change?
2. Would the proof trace or certificate standard change after this change?
3. Would the system use a different rule for what counts as valid derivation, attack, exception, or priority resolution?
4. Would the public claim about correctness, soundness, fail-closed behavior, or formal conformance change?

If any answer is `yes`, treat the work as a semantic-boundary change.

---

## 4. Eight-Field Pre-Change Gate

Every nontrivial feature should be classified with this template before implementation:

```text
Feature:
Inputs changed:
Outputs changed:
DecisionStatus changed:
Horn firing condition changed:
Attack / Exception / Priority changed:
Certificate / Checker contract changed:
Public correctness claim changed:
Classification: ENGINEERING_ONLY | SEMANTIC_BOUNDARY
```

Interpretation:

- all `no` -> `ENGINEERING_ONLY`
- any material `yes` -> `SEMANTIC_BOUNDARY`

---

## 5. Examples

## 5.1 Engineering Only

### Add caching to grounded extension

- inputs unchanged
- labels unchanged
- certificates unchanged

Result: `ENGINEERING_ONLY`

### Replace retrieval model for candidate statute recall

- candidate generation changes
- formal reasoning layer unchanged
- verified fact contract unchanged

Result: `ENGINEERING_ONLY`

### Add incremental recomputation for one changed fact

- allowed only if end result is guaranteed to match full recomputation

Result: `ENGINEERING_ONLY`

## 5.2 Semantic Boundary

### Auto-upgrade `TAINTED` to `PROVED` when confidence is high

- decision meaning changes
- fail-closed contract changes

Result: `SEMANTIC_BOUNDARY`

### Introduce a new priority rule where higher source authority defeats all lower rules

- priority semantics change
- attack resolution changes

Result: `SEMANTIC_BOUNDARY`

### Make LLM extracted facts enter Horn directly without verification state gate

- valid input fact meaning changes
- trust boundary changes

Result: `SEMANTIC_BOUNDARY`

### Add a new status `PRESUMED_TRUE`

- output semantics change
- certificate/checker obligations change

Result: `SEMANTIC_BOUNDARY`

---

## 6. LLM-Specific Rule

Using LLMs for extraction, summarization, normalization, weak labeling, or candidate generation is not itself a semantic change.

It becomes a semantic-boundary change when any of the following becomes true:

- raw LLM output is treated as verified fact
- LLM output directly determines final legal status
- LLM output bypasses certificate or checker gates
- LLM confidence is used as a substitute for formal or verified evidence

Short form:

- `LLM proposes` -> engineering layer
- `kernel decides` -> formal/runtime layer
- `LLM decides` -> semantic-boundary violation

---

## 7. Required Action When Boundary Is Crossed

If a change is classified as `SEMANTIC_BOUNDARY`, do all of the following before merge:

1. write down the exact semantic delta
2. update the relevant contract doc
3. check whether `legal-math-modeling` needs a spec update
4. check whether theorem manifest or forbidden claims need updates
5. add or update regression tests proving the new behavior
6. review public wording so the repo does not overclaim correctness

---

## 8. Default Bias

When uncertain, classify the change as `SEMANTIC_BOUNDARY` until proven otherwise.

The cost of an unnecessary spec review is lower than the cost of silent semantic drift.
