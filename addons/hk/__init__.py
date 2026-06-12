"""HK jurisdiction addon for juris-calculus.

Auto-registers on import. Load with:
    import addons.hk
    adapter = registry.get("hk")
"""
from compiler_core.plugin_registry import registry
from addons.hk.adapter import HKAdapter

registry.register(
    code="hk",
    adapter_class=HKAdapter,
    rules_path="configs/hk/rules.yaml",
    overrides_path="configs/L0_overrides_hk.yaml",
    label="Hong Kong SAR", legal_family="common_law",
)
