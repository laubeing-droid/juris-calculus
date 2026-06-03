#!/usr/bin/env python3
"""离线修补 48.7% 单前提规则 → AND 逻辑增强"""
import yaml, re, os
from pathlib import Path
from collections import Counter

RULES_YAML = Path(__file__).resolve().parents[1] / "configs" / "zh_CN" / "rules.yaml"
OUT_YAML = RULES_YAML  # 原地修改

# AND 增强规则：match_in_head → 追加的前提原子
AUGMENT_RULES = [
    # 违约类 → 追加标的物交付/款项到期
    (r'违约', ['Contract.Status.FORMED', 'Contract.Performance.PAYMENT_OVERDUE']),
    (r'解除合同|合同解除', ['Contract.Status.FORMED', 'Contract.Breach.OCCURRED']),
    # 利息/违约金 → 追加本金和违约前提
    (r'利息|违约金|LPR', ['Contract.Finance.PRINCIPAL', 'Contract.Breach.OCCURRED']),
    # 侵权 → 追加过错+损害
    (r'侵权|损害|赔偿', ['Tort.Fault.NEGLIGENT', 'Tort.Damage.PERSONAL_INJURY']),
    # 刑事 → 追加主/客观要件
    (r'故意伤害|杀人|强奸', ['Crim.Objective.SEVERE_INJURY', 'Crim.Subjective.DIRECT_INTENT']),
    (r'盗窃|抢劫|诈骗', ['Crim.Objective.SECRET_STEALING', 'Crim.Subjective.DIRECT_INTENT']),
    # 担保 → 追加主合同+违约
    (r'担保|保证|抵押', ['Contract.Status.FORMED', 'Contract.Breach.OCCURRED']),
    # 公司 → 追加出资/股权+违约
    (r'股东|股权|公司', ['Corp.Capital.CONTRIBUTION', 'Corp.Equity.TRANSFER']),
    # 婚姻 → 追加感情破裂+财产
    (r'离婚|婚姻', ['Family.Divorce.IRRETRIEVABLE_BREAKDOWN', 'Family.Property.JOINT']),
    # 继承 → 追加被继承人死亡+遗产
    (r'继承|遗嘱|遗产', ['Family.Estate.TESTATE', 'Family.Estate.INTESTATE']),
    # 执行 → 追加生效文书+财产
    (r'执行|查封|扣押', ['Enforce.Action.FORCED', 'Enforce.FREEZE.ASSET']),
    # 行政 → 追加行政行为+合法性
    (r'行政|处罚|许可', ['Admin.Legality.PROCEDURAL_VIOLATION', 'Admin.Action.PENALTY']),
    # 知产 → 追加侵权判定+权利基础
    (r'专利|商标|著作权', ['IP.Evidence.EXPERT_CONFIRMED', 'IP.Patent.ALL_ELEMENTS']),
]


def has_single_premise(rule):
    return len(rule.get('premise_atoms', [])) <= 1


def matches_augment(rule, head_text):
    for pattern, atoms in AUGMENT_RULES:
        if re.search(pattern, head_text):
            return atoms
    return None


def main():
    data = yaml.safe_load(RULES_YAML.read_text(encoding='utf-8'))
    rules = data.get('rules', data) if isinstance(data, dict) else data

    single_count = sum(1 for r in rules if has_single_premise(r))
    print(f"单前提规则: {single_count}/{len(rules)} ({single_count/len(rules)*100:.1f}%)")

    augmented = 0
    stats = Counter()

    for rule in rules:
        if not has_single_premise(rule):
            continue

        head = rule.get('head_claim', '') or ''
        extra = matches_augment(rule, head)
        if extra:
            existing = set(rule.get('premise_atoms', []))
            for atom in extra:
                if atom not in existing:
                    rule['premise_atoms'].append(atom)
                    augmented += 1
                    stats[atom] += 1

    after_count = sum(1 for r in rules if has_single_premise(r))
    print(f"修复后单前提: {after_count}/{len(rules)} ({after_count/len(rules)*100:.1f}%)")
    print(f"增强原子注入: {augmented} 次")
    print(f"\n增强原子分布:")
    for atom, cnt in stats.most_common():
        print(f"  {atom}: {cnt}次")

    # 写回
    out_data = {'rules': rules, '_meta': data.get('_meta', {}), 
                '_augmented': {'before': single_count, 'after': after_count, 'injections': augmented}}
    (OUT_YAML.parent / 'rules_augmented.yaml').write_text(
        yaml.dump(out_data, allow_unicode=True), encoding='utf-8')

    # 也直接覆盖 rules.yaml
    OUT_YAML.write_text(yaml.dump(out_data, allow_unicode=True), encoding='utf-8')
    print(f"\n✅ rules.yaml 已更新（原始备份: rules_augmented.yaml）")


if __name__ == "__main__":
    main()
