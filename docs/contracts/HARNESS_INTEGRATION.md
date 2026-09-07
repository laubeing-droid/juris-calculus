# JC ↔ Legal Harness Integration Contract

Status: **frozen interface for the Harness integration phase** (JC-FINAL-FIX-20260908).
The closed surface is `compiler_core/harness_contract.py`
(`jc-harness-contract/1`); the three runnable samples live in
`examples/harness/`.

## Division of responsibility (fixed)

```
Legal Harness  = case orchestration (materials, fact candidates, legal
                 research, issue spotting, human confirmation, drafting,
                 adversarial review, final natural-language delivery)
juris-calculus = formal reasoning kernel (admission, Horn, attack/priority/
                 defeat, Dung semantics, query, procedure, exact composition,
                 assurance, audit)
```

The Harness never re-implements JC's formal algorithms; JC never drafts
documents. Both talk exclusively through this contract and the existing
public entries (Python `JCClient`, CLI `jc`, stdio MCP), which share one
`ApplicationV4` spine.

## How to issue a normal evaluation

Python surface (CLI/MCP carry the same bundle):

```python
from compiler_core.harness_contract import (
    HarnessQueryInput, HarnessRunRequest, evaluate_for_harness,
)

request = HarnessRunRequest(
    case_id="case-2026-0117",
    request=case_request,           # CaseRequestV4 (admission-sealed upstream)
    queries=(HarnessQueryInput(
        issue_id="issue-breach",
        claim=claim_digest,          # an argument conclusion identity
        profile="grounded",
    ),),
    refutations=(),                 # ClaimRefutationV5 rows (claim-level!)
    gates=(),                       # QueryGateRequestV5 rows (basis required)
    procedural=None,                # ProceduralInputV5 (see four routes)
    incremental_parent=None,        # IncrementalParentV5 (see below)
)
result = evaluate_for_harness(
    application, request,
    request_ref=request_ref, run_ref=run_ref, case_scope="case-2026-0117",
)
```

Facts and rules enter through the existing admission chain (signed
attestations, verified rule packs). The samples mint synthetic admission
material via `examples/harness/_adapter.py`; production replaces only that
adapter.

## How to append material and trigger the incremental fast path

1. Run the parent request; read the sealed Horn state from its audit bundle
   (`artifact_kind = horn-subject-state-v5`) or keep the run/state refs the
   first result points at.
2. Build the child request with the newly admitted add-only facts and set:

```python
IncrementalParentV5(
    parent_run_ref=parent_run_ref,
    parent_state_ref=parent_state_ref,
    parent_subject_digest=parent_subject_digest,
    mode="auto",                    # or "force_full" for diagnostics
)
```

3. Default behavior is automatic: a qualified add-only child reuses the
   parent closure through the incremental worklist and reports
   `horn.mode = "incremental"` in the result; anything else (fact deletion,
   rule rewrite, universe growth, missing/foreign parent state, forced full)
   full-recomputes with `horn.fallback_reason` recorded. Two separate service
   instances sharing only the persistent audit store still increment —
   `examples/harness/sample_incremental.py` demonstrates exactly that.

## How priority relations are handled

- Admitted priority relations participate only through a **registered**
  priority policy declared on `DefeatPolicyV5`
  (`target-preferred-rebut/1` is the registered engineering test strategy).
- With a registered policy the mapping decision is computed and audited per
  edge (`stage.priority.decisions`).
- Without one (or for input the policy cannot explain) the run still
  succeeds, but the affected questions cannot be presented as completely
  solved: `mapping_coverage.status = incomplete`, queries answer
  `gate=incomplete`, procedures stay pending, assurance switches to
  `openObligations`, the result completeness is `partial` with reason
  `v5_mapping_incomplete`, and no certificate is issued.

## How to read the final result

Every field is on `HarnessRunResultV5` / `HarnessIssueResultV5`
(`to_dict()` is the wire form). The reading positions:

| Question | Field |
|---|---|
| run outcome | `run_status`, `decision_status`, `completeness` |
| per-issue conclusion | `issues[].conclusion_status()` (accepted/refuted/possible/undecided/inconsistent/excluded/incomplete) |
| accepted / common / possible | `issues[].accepted`, `possibly_accepted` |
| refuted status | `issues[].refuted`, `possibly_refuted`, `refutation_witnesses` |
| scenario/profile/branch | `issues[].profile`, `issues[].branch_refs` |
| key dependency facts | `admitted_fact_keys`, `issues[].acceptance_witnesses` |
| assumptions | `assumed_fact_keys` (empty in this spine; assumption inputs exit before the formal path) |
| missing facts | `missing_fact_keys` |
| open obligations | `open_obligations[]` (typed code+detail) |
| procedure status | `procedure_kinds[]` per query |
| exact calculation | `composition` (exact rational; null when absent) |
| assurance | `assurance_specs[]` (proved / openObligations) |
| incremental provenance | `horn.mode`, `horn.fallback_reason`, `horn.parent_binding`, `horn.solver_rule_evaluations`, `horn.checker_rule_evaluations` |
| audit artifact reference | `audit_manifest_ref`, verified bundle via `jc verify`/`jc_verify_run` |

## What the Harness may display

`issues[].conclusion_status()` plus the witnesses and obligations are
human-facing; when `completeness != "complete"` the display must carry the
open obligations verbatim (see `human_projection` in the samples) and must
never be reworded into an unconditional conclusion.

## Samples (runnable)

```bash
python examples/harness/sample_normal.py            # normal request + projection
python examples/harness/sample_incremental.py       # parent -> incremental child
python examples/harness/sample_priority_blocked.py  # unresolved priority -> blocked answer
```

All three are executed by `tests/contract/test_harness_contract.py`.
