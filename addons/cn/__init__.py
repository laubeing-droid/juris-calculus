#!/usr/bin/env python3
"""CN addon — Chinese jurisdiction adapter with bounded CBL+SPC experiment.

双轨实验:
  Track 1 (CBL): 成文法阻断 (60条, 一票否决)
  Track 2 (SPC): 最高法裁判倾向 (25条, non-blocking)

Auto-registers on import. Load with:
    import addons.cn
    adapter = registry.get("cn")
    proof_tree = adapter.run_collision(facts)
"""
from compiler_core.plugin_registry import registry
from addons.cn.adapter import CNAdapter

registry.register(
    code="cn",
    adapter_class=CNAdapter,
    overrides_path="configs/L0_overrides_cn.yaml",
    label="PRC Mainland China",
    legal_family="civil_law",
)
