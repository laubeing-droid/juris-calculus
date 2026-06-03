# -*- coding: utf-8 -*-
"""
编译期 AST 重写器 — 单前提规则隐式上下文锚点注入。

当规则只有一个 premise_atoms 时，强制注入 Context.Domain.{domain_tag}
确保广义规则在多租户路由中获得空间隔离。

用法: 在 FixpointEvaluator.__init__ 中调用 patch_single_premise_rules()
"""
from typing import List
from compiler_core.types import LegalRule


def patch_single_premise_rules(rules: List[LegalRule], domain_tag: str = "general") -> List[LegalRule]:
    """
    编译期拦截单前提规则，注入隐式域锚点。

    原逻辑: If fact_A → then head_B
    改后:   If fact_A AND Context.Domain.{domain_tag} → then head_B

    domain_tag 来源于规则的 namespace 字段（如 contract/criminal/admin）。
    """
    patched = 0
    for rule in rules:
        if len(rule.premise_atoms) == 1:
            synthetic = f"Context.Domain.{domain_tag.upper()}"
            if synthetic not in rule.premise_atoms:
                rule.premise_atoms.append(synthetic)
                # 标记为编译期补丁
                if not hasattr(rule, "metadata"):
                    rule.metadata = {}
                rule.metadata["patched_single_premise"] = True
                rule.metadata["original_premise_count"] = 1
                patched += 1
    if patched:
        import logging
        logging.info(f"[Transformer] {patched} 条单前提规则已注入 Context.Domain.{domain_tag.upper()}")
    return rules


def auto_patch(rules: List[LegalRule]) -> List[LegalRule]:
    """
    自动按规则自身的 namespace 注入域锚点。
    如果规则没有 namespace 标记，使用 "general"。
    """
    from compiler_core.types import LegalRule
    import logging

    # 按 namespace 分组
    groups = {}
    for r in rules:
        ns = getattr(r, "namespace", "general") or "general"
        groups.setdefault(ns, []).append(r)

    patched_rules = []
    for ns, group in groups.items():
        if ns == "general":
            # general 规则不加锚点（它们是全局通用的）
            patched_rules.extend(group)
        else:
            patched_rules.extend(patch_single_premise_rules(group, ns))

    total_single = sum(1 for r in patched_rules if len(r.premise_atoms) == 1)
    if patched_rules:
        logging.info(f"[Transformer] 域注入后单前提率: {total_single}/{len(patched_rules)} ({total_single/len(patched_rules)*100:.1f}%)")
    return patched_rules
