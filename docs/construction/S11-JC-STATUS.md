# S11 construction status (juris-calculus consumer side)

Baseline: `9ecb66c613e502b0111cc485b6bf255bfeacad57`, branch `feat/privacy-egress-consumer`.

Machine-readable state: `S11-JC-STATUS.json`.

## What was built

- `schemas/privacy-egress/jc-privacy-facts-v1.schema.json` — exact copy (hash-verified)
  of the anonymizer's public schema; JC never rewrites consumer schemas.
- `privacy_egress_adapter.py` — consumer adapter (OUTSIDE the formal kernel):
  - verifies the Ed25519 signature of a `jc-privacy-facts-v1` document against a
    pinned public key;
  - enforces closed-field facts: unknown fields (including any user self-claim such
    as "UserClaimsFullyAnonymous") are rejected — candidate/user-assumed facts can
    never enter reasoning;
  - emits ALLOW_EXTERNAL_MODEL_USE / REQUIRE_HUMAN_REVIEW / CLOSED_BLOCK with the
    approved wording only ("已满足本次声明范围内的去标识化与外发前置条件" etc.);
  - never claims a formal accepted result (`formal_result_claimed: false`).

## External blockers (honest, fail-closed)

- `CLOSED_BLOCK_EXTERNAL/jc_production_runtime_not_configured`: the V4 production
  runtime (identity, trust material, signed packs) is not present in this
  environment (`jc capabilities` → RUNTIME_NOT_CONFIGURED). Formal
  evaluate/verify/replay cannot run; the adapter reports REVIEW_ONLY scope.
- `CLOSED_BLOCK_EXTERNAL/upstream_rule_pack_scope`: no new formal semantics added.

## Checks

See `S11-JC-STATUS.json`. All 18 pre-existing V4 production-chain test failures
reproduce on the untouched baseline (missing production state) and are not caused
by this wave. `tests/packaging` + `tests/windows_security` (71) and the MCP smoke
test pass; `git diff --check` clean.
