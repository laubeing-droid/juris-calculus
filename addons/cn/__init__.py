#!/usr/bin/env python3
"""CN addon — Chinese jurisdiction adapter with three-track collision mode.

三轨对撞:
  Track 1 (CBL): 成文法阻断 (60条, 一票否决)
  Track 2 (SPC): 最高法裁判倾向 (25条, non-blocking)
  Track 3 (CN):  运行时加载的成文法 Horn 规则

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
    rules_path="configs/zh_CN/rules.yaml",
    overrides_path="configs/L0_overrides_cn.yaml",
    label="PRC Mainland China",
    legal_family="civil_law",
)
