# S9: Robust Regression Estimator Contract

Current implementation: Theil-Sen with [0.01, 10.0] slope clipping.

## Analysis Required
- Translation equivariance: YES
- Scale equivariance: NO (clipping breaks it)
- Clipping bias: PRESENT; true slopes outside [0.01, 10.0] are pulled toward bounds
- Breakdown point: Original Theil-Sen is 29.3%%. Clipped version is a DIFFERENT estimator
- Comparison: Siegel repeated median has 50%% breakdown point — recommended replacement

## Status: HEURISTIC
The clipped Theil-Sen is an engineering heuristic, not a theoretically-grounded estimator.
Production upgrade requires held-out data comparison between:
- Unclipped Theil-Sen
- Clipped Theil-Sen (current)
- Siegel repeated median
Metrics: MAE, median absolute error, tail error, runtime, determinism.