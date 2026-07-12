"""Legacy US plugin-registry placeholder for juris-calculus.

This module keeps the historical ``us`` registry slot alive for compatibility.
It is not reasoning-ready US support and does not imply a complete US addon.

Load with:
    import addons.us
    adapter = registry.get("us")
"""
from compiler_core.plugin_registry import registry
from addons.us.adapter import USAdapter

registry.register(
    code="us",
    adapter_class=USAdapter,
    rules_path="configs/us/rules.yaml",
    overrides_path="configs/L0_overrides_us.yaml",
    label="US Legacy Placeholder",
    legal_family="common_law",
)
