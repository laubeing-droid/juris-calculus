# Robust Regression Contract

Current classification: empirical engineering heuristic.

The current estimator uses a clipped Theil-Sen-style path. Clipping changes the estimator's theoretical behavior, so claims about the unclipped estimator cannot be transferred silently.

## Current Position

| Property | Status |
|---|---|
| deterministic output | expected for fixed inputs |
| translation behavior | supported by estimator structure |
| scale equivariance | broken by clipping |
| clipping bias | present |
| formal breakdown guarantee | not claimed for clipped variant |
| production optimality | not established |

## Allowed Wording

- "robust-regression heuristic"
- "clipped estimator"
- "empirical baseline"
- "deterministic comparison feature"

## Prohibited Wording

- "formally robust estimator"
- "50 percent breakdown point" for the clipped current estimator
- "unbiased"
- "proved production estimator"

## Required Upgrade Path

Before stronger claims, compare at least:

- unclipped Theil-Sen;
- clipped Theil-Sen;
- Siegel repeated median or another explicitly defined robust estimator.

Metrics:

- MAE;
- median absolute error;
- tail error;
- runtime;
- determinism;
- behavior under outliers and scaling.

Any chosen estimator then needs a runtime contract, fixtures, and disclosure of its mathematical limits.
