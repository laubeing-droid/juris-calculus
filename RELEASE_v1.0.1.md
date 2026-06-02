# juris-calculus v1.0.1

Bug fix release addressing all issues found in the first external audit.

## Changes since v1.0.0

### Bug Fixes
- Fix `LegalIREvaluator` → `FixpointEvaluator` import error — M10-M17 peripheral models now import correctly
- Add missing `requirements.txt`
- Replace production `print()` with `logging`
- Add README disclaimer for missing `ignite.py`

### Features
- `BatchProcessor.process_parallel()` with ThreadPoolExecutor (max_workers=8)
- `load_rules_from_yaml()` YAML rule configuration loader
- 5 unit tests for `FixpointEvaluator` (convergence, exception chain, honest refusal, critical clarity failure, transition validation)

### Docs
- Environment / Supported Jurisdictions / FAQ added to both README and README_CN
- Important notes and 10 contribution paths added to concept-roadmap.md

---

**Full Changelog**: https://github.com/laubeing-droid/juris-calculus/compare/v1.0.0...v1.0.1
