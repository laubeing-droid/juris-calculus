# juris-calculus v2.0.0 Release Notes

## Overview

v2.0.0 introduces the addon architecture: the core engine is China-law only,
and all other jurisdictions (HK, US) are optional plugins loaded via
plugin_registry.discover().

## Breaking Changes

- HKAdapter, USAdapter, FederatedReasoner moved from adapter/__init__.py
  to addons/hk/ and addons/us/. Import via plugin_registry instead.
- juris_blueprint.json split: non-CN data moved to addon-local blueprints.
- compiler_core/us_lookup.py moved to addons/us/us_lookup.py.
- configs/ paths now resolved through compiler_core/config_paths.py.
  Set JURIS_CONFIG_DIR to override.

## New Features

- Addon auto-discovery: add addons/{code}/ and it auto-registers.
- L0 concept degradation: unmapped concepts get UNVERIFIED trust label.
- Federation by legal family: common-law pair-wise comparison engine.
- NLNI cold start: neural nodes dormant until training data arrives.
- State term parser: auto-extract terms from state statute directories.

## Migration from v1.2

1. If you imported HKAdapter or USAdapter directly, switch to:
   from compiler_core.plugin_registry import registry
   registry.get("hk")
2. If you used compiler_core/us_lookup.py, import from addons/us/us_lookup.py.
3. Set JURIS_CONFIG_DIR if you use a custom config path.
4. Reinstall requirements (no new dependencies).
