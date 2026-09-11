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

## Local keyless interface (`jc-harness-local/1`, SPLIT-LOCAL-3)

The local direct-connect surface removes every key/activation prerequisite
while keeping the whole formal spine. It lives in
`compiler_core/client.py::create_local_client` (implemented by
`compiler_core/local_runtime.py`) and is verified by
`tests/local/test_local_runtime.py`; the runnable sample is
`examples/harness/sample_local.py`.

```python
from compiler_core.client import create_local_client

client = create_local_client(state_root, rule_roots)   # no keys, ever
pack = client.local_pack()              # rule ids + claim digests + sources
bundle = client.local_case_bundle(      # complete CaseInputBundleV4
    case_id="matter-1", decision_time="2026-09-01T00:00:00Z",
    facts=[{"fact_key": "x", "dispute_state": "UNDISPUTED"}],
    queries=[{"issue_id": "i1", "claim": pack["rules"][0]["claim"],
              "profile": "grounded"}],
)
result = client.evaluate_harness_bundle(
    bundle, case_id="matter-1", issue_queries=[...same rows...],
)
horn = client.local_horn_subject_state(result["run_identity_ref"])
record = client.local_read_run(result["run_identity_ref"])
```

Properties and honest boundaries:

- No `service_key_path`, trust bundle, signed pack, broker/probe, activation
  ledger, or generated key exists anywhere on this path. Every former Ed25519
  endorsement is replaced by an explicit `LocalRecordV4` local record
  (`algorithm = "LOCAL-RECORD"`, no signature field): it binds content, not
  signers. Every result reports `execution_mode="local"` and
  `signature_status="not_used"`.
- Structure, admission, solving, the independent checker, incrementality and
  the sealed audit bundle are the existing production machinery. `LocalRecordV4`
  says "recorded locally"; it never claims an external approval, and a signed
  envelope that reaches the local trust authority is a hard `TRUST_INPUT_TYPE`
  error.
- `rule_roots` are one or more directories each containing a
  `jc-local-pack.json` descriptor (schema `jc/local-pack/1.0`) with source and
  rule authoring documents. The loader rewrites nothing into an approximate
  rule: unsupported forms fail, and semantics the certified providers cannot
  run (e.g. permission relations on this profile) come back honestly as
  `BACKEND_UNSUPPORTED_SEMANTICS`. There is no fixed six-rule cap.
- `evaluate_harness_bundle` performs exactly one `ApplicationV4` evaluation
  (`evaluation_count` field), rejects `issue_queries`/case-scope mismatches by
  naming the fields (`HARNESS_QUERY_MAPPING`, `HARNESS_CASE_SCOPE_MISMATCH`),
  and returns every `HarnessRunResultV5` business field plus
  `execution_mode`, `signature_status`, `evaluation_count` and
  `run_identity_ref`.
- Incremental follow-ups: `local_horn_subject_state` returns ready-made
  `parent_run_ref`/`parent_state_ref`/`parent_subject_digest` for
  `IncrementalParentV5`; `mode="auto"` reuses the parent closure only when the
  add-only contract holds, otherwise `horn.mode="full_recompute"` records the
  exact `fallback_reason`.
- `local_read_run` reads a sealed run through public methods only (no
  capability key); integrity digests remain ordinary content checks, not
  third-party attestations.

The rules in `examples/harness/sample_local.py` are engineering test
material: they demonstrate the interface and none of it is a Chinese-law
capability. Real capability requires real source-backed rule packs supplied
through the same local directory format.

## Conditional business capability (`jc-business-root/1`, 2026-09-11)

`local_case_bundle` also accepts `business_tasks=(...)` (typed
`BusinessTaskV1` rows on `CaseRequestV4.business_tasks_v1`), and
`evaluate_harness_bundle` returns their sealed typed rows as
`business_results[]` beside — never merged into — `issues[]`. The local
surface gained three business-only methods: `business_capabilities()`
(installed-implementation capability query), `business_delivery_documents()`
(read-only protected two-file view of one sealed exact run) and
`verify_business_delivery()` (verify-only actual-bytes checking; zero
evaluations, sealed bundles are never rewritten). Their contract, error
codes and guarantee decomposition live in
[BUSINESS_ROOT.md](BUSINESS_ROOT.md); the runnable sample is
`examples/harness/sample_local_business.py`.
