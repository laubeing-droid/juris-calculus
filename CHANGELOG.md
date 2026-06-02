# Changelog

## v1.0.1 (2026-06-02)

### Bug Fixes

- Fix `LegalIREvaluator` → `FixpointEvaluator` import error in `peripheral_models.py` and `batch_processor.py` (M10-M17 models were unusable)
- Add missing `requirements.txt`
- Replace production `print()` with `logging` in evaluator
- Add README disclaimer: `ignite.py` is private and not included

### Features

- Add `BatchProcessor.process_parallel()` with ThreadPoolExecutor
- Add `load_rules_from_yaml()` for rule configuration
- Add 5 unit tests for FixpointEvaluator

### Documentation

- Add Environment / Supported Jurisdictions / FAQ sections to README (EN + CN)
- Add important notes and contribution paths to concept-roadmap.md
- Fix README cp path consistency

## v1.0.0 (2026-06-02)

### Initial Open-Source Release

First public release of the `juris-calculus` kernel — a jurisdiction-agnostic symbolic reasoning and actuarial pricing engine for legal practice.

**Core Components:**

- `compiler_core/` — Fixpoint legal reasoning engine with exception chain penetration, concept registry scoring, CRITICAL_CLARITY_FAILURE guard, and implicit dependency detection
- `legalos_services/` — Four mathematical models: DAG weighted node counter, multi-factor pricing matrix with billing tier leverage (vector H), batch exponential decay, and Laplace differential privacy
- `extractors/zh_CN/` — Chinese Civil Law fact extractor with graph topology causal analysis and stage auto-detection
- `extractors/en_US/` — US Common Law IRAC extractor skeleton (ready for community contribution)

**Dual Jurisdiction Example Configs:**

- `configs/zh_CN/domain_config.example.yaml` — Chinese Civil Law demo
- `configs/en_US/domain_config.example.yaml` — US Common Law demo with billing tier vector H

**Key Design Decisions:**

- All jurisdiction-specific parameters (α, thresholds) are set to demo defaults (1.0 / 0.0). Production users must calibrate via `calibrate_theilsen()` with their own timesheet data.
- Private business logic (entity maps, calibrated constants, raw case data) is physically isolated from the open-source tree.
- `LegalOSPricingEngine` class name preserved as API identifier (not branding).

**Author:**

Laupinco — Hokkien Computational Jurisprudence Enthusiast (Powered by Gemini & WorkBuddy & DeepSeek-V4 Pro)

---
*juris-calculus v1.0.0 is the open-source fork of the LegalOS private production system (v3.0+).*
