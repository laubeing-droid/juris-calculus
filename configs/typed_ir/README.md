# Typed IR Sidecars

This directory is reserved for curated Legal IR v3 sidecars.

Current migration policy:

- Legacy rule YAML files remain the runtime source of truth.
- `tools/rule_to_ir_migrator.py` performs dry-run migration and writes sidecars/reports.
- Addon rule sources are discovered through `compiler_core.plugin_registry`.
- Third-party LLM APIs must not write here directly.
- Generated or repaired candidates must first pass local Codex validators before any curated sidecar is committed.

CI smoke intentionally migrates a tiny sample from:

- `configs/zh_CN/rules.yaml`
- `configs/hk/rules.yaml`
- `configs/en_US/US_Adapter.yaml`

Missing source anchors are reported as migration findings and block promotion, but they do not block the initial sidecar smoke.
