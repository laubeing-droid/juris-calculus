"""US jurisdiction addon for juris-calculus.

Auto-registers on import. Load with:
    import addons.us
    adapter = registry.get("us")
"""
from compiler_core.plugin_registry import registry
from .adapter import USAdapter

registry.register(
    code="us",
    adapter_class=USAdapter,
    rules_path="configs/en_US/US_Adapter.yaml",
    overrides_path="configs/en_US/L0_overrides_us.yaml",
    blocking_path="configs/prc_us_alignment/blocking_rules.yaml",
    label="United States", legal_family="common_law",
)
