# Typed IR Sidecars

This directory is reserved for curated Legal IR sidecars.

## Current Policy

- Legacy rule YAML files remain the runtime source of truth unless a promoted sidecar explicitly replaces them.
- `tools/rule_to_ir_migrator.py` may perform dry-run migrations and write review artifacts.
- Addon rule sources are discovered through `compiler_core.plugin_registry`.
- Third-party LLM APIs must not write curated sidecars directly.
- Generated or repaired candidates must pass deterministic validators before commit.

## Promotion Gate

A sidecar can be promoted only after:

- schema validation;
- source-anchor validation;
- modality and priority review;
- regression tests;
- public/private boundary review;
- explicit evidence entry in the relevant report or commit message.

## Candidate Handling

LLM-generated sidecars are candidate artifacts. They may be stored only in a candidate or review location until promoted. They must not become runtime source-of-truth material without deterministic checks.

## Smoke Sources

Current smoke migration sources:

- `configs/zh_CN/rules.yaml`
- `configs/hk/rules.yaml`
- `configs/en_US/US_Adapter.yaml`

Missing source anchors are migration findings. They block promotion, but they do not by themselves invalidate a dry-run smoke report.
