# Rules Schema Specification

This document describes the public runtime rule schema used by JC fixtures and rule loaders. It is a runtime contract, not a replacement for canonical Lean specification work upstream.

## Required Fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | stable rule identifier |
| `premise_atoms` | list[string] | yes | facts required before the rule can fire |
| `head_claim` | string | yes | conclusion produced by the rule |
| `norm_modality` | string | yes | normative modality |

## Common Optional Fields

| Field | Type | Meaning |
|---|---|---|
| `exception_chain` | list[string] | exception rule IDs |
| `concepts` | list[string] | retrieval and audit tags |
| `mechanical_exception` | bool | whether exception handling is mechanical |
| `head_type` | string | rule head class, usually `HORN` |
| `namespace` | string | domain namespace |
| `modality_confidence` | float | classification confidence |
| `modality_source` | string | source of modality classification |
| `reparation_chain_pool` | list | candidate damages or repair paths |
| `source_anchor` | string | public source citation or anchor |
| `valid_from` | string | effective date |
| `valid_to` | string | expiry date |
| `jurisdiction` | string | jurisdiction code |
| `authority_rank` | string | authority category |
| `trust_label` | string | evidence/trust classification |
| `data_quality` | string | data quality classification |

## `norm_modality`

| Value | Meaning | Runtime caution |
|---|---|---|
| `OBLIGATION` | required action or duty | may produce negative-spec consequences |
| `PROHIBITION` | forbidden action or conclusion | must block downstream reasoning where configured |
| `PERMISSION` | allowed or discretionary action | must not be over-read as obligation |
| `CONSTITUTIVE` | definitional or status-creating rule | supports classification and predicates |

## `trust_label`

| Value | Meaning |
|---|---|
| `UNVERIFIED` | not verified for reasoning |
| `ENGINEERING_BASELINE` | accepted as engineering fixture or baseline |
| `DATA_INSUFFICIENT_FOR_PROOF` | insufficient for proof-level claim |
| `TESTED_PROPERTY` | covered by deterministic tests |
| `SMT_PROVED_FINITE` | finite solver check supports the stated property |

## `data_quality`

| Value | Meaning |
|---|---|
| `CLEAN` | curated and suitable for current public tests |
| `UNCERTAIN` | candidate or weakly sourced |
| `SPARSE` | missing fields or thin evidence |
| `PROVISIONAL` | temporary runtime fixture |

## Promotion Rules

Rules generated or repaired by an LLM remain candidate material until they pass:

- schema validation;
- source-anchor check;
- modality and priority review;
- deterministic regression tests;
- public/private boundary review.

Missing anchors or failed checks block promotion. They must not be papered over with narrative text.
