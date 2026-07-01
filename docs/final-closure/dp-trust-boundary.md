# DP Trust Boundary

Current classification: `PRIVACY_DIAGNOSTICS_ONLY`.

JC contains privacy diagnostics and policy plumbing. It does not currently make a formal differential privacy guarantee.

## What Can Be Claimed

- The runtime can carry privacy-related policy fields.
- Diagnostics can report configured values and boundary conditions.
- Public documentation can identify missing DP components.

## What Cannot Be Claimed

- tuple-level DP guarantee;
- person-level DP guarantee;
- epsilon/delta accounting;
- composition guarantee;
- Laplace or Gaussian mechanism proof;
- unbiased estimator guarantee after clipping.

## Missing Formal Components

| Component | Status |
|---|---|
| dataset space | not specified |
| adjacency relation | not fixed |
| protection unit | not formalized |
| query sensitivity | not computed |
| clipping bias theorem | not formalized in this repo |
| mechanism | no DP mechanism implemented |
| privacy accountant | not implemented |
| composition theorem | not implemented |

## Safe Runtime Behavior

Privacy diagnostics may inform engineering review, but they must not be promoted into a public DP claim. A failed or missing privacy check must be reported as blocked or diagnostics-only.

## Closure Requirement

At least one formal mechanism path must exist before any DP guarantee is claimed:

- sensitivity theorem plus mechanism theorem;
- clipping bias bound plus disclosed estimator limits;
- privacy accountant and composition rule;
- deterministic tests showing runtime values follow the formal contract.
