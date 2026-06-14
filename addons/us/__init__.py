"""US federal law addon for juris-calculus.

Covers: Title 9 (Arbitration), Title 28 (Jurisdiction/FSIA), Title 50 (Sanctions),
Title 11 (Bankruptcy), Title 15 (Commerce/Antitrust/Securities),
Title 17 (Copyrights), Title 35 (Patents).

Auto-registers on import. Load with:
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
    label="US Federal Law",
    legal_family="common_law",
)
