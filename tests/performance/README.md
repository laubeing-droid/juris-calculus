# V4 performance tests

Local/test RC metric completeness, numeric budgets, regression thresholds, and non-promotion boundaries. Target-provider SLO approval remains external.

`py -3.12 -B tools/perf_baseline.py --metrics metrics.json --budgets budgets.yaml`
validates a measured report. It does not generate or approve production SLOs.
