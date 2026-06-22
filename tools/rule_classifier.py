"""Rule auto-classifier — infer namespace and modality from head_claim keywords."""
import yaml

NAMESPACE_KEYWORDS = {
    'cm': ['合同', '违约', '借款', '担保', '抵押', '买卖', '租赁', '侵权', '赔偿', '公司', '股东', '破产', '保险', '劳动'],
    'xs': ['犯罪', '刑法', '有期徒刑', '罚金', '自首', '立功', '正当防卫', '量刑', '毒品', '诈骗'],
    'xz': ['行政', '行政行为', '行政处罚', '行政许可', '行政诉讼'],
    'ga': ['环境', '污染', '生态', '排污', '公益诉讼'],
    'sj': ['专利', '商标', '著作权', '知识产权', '商业秘密', '侵权判定'],
    'zx': ['执行', '查封', '扣押', '冻结', '拍卖', '被执行人'],
    'pc': ['国家赔偿', '赔偿义务', '赔偿请求'],
    'la': ['立案', '管辖', '受案范围', '受理'],
    'zs': ['再审', '审判监督', '抗诉', '检察建议'],
    'hs': ['涉外', '仲裁', '公约', '承运人'],
    'hj': ['港澳', '区际', '涉港', '涉澳'],
    'wc': ['未成年人', '未成年', '少年'],
    'gl': ['审判管理', '案件质量', '评查'],
}

MODALITY_KEYWORDS = {
    'PROHIBITION': ['不得', '禁止', '严禁', '不准'],
    'OBLIGATION': ['应当', '必须', '需要', '有义务'],
    'PERMISSION': ['可以', '有权', '允许', '享有'],
    'CONSTITUTIVE': ['构成', '认定为', '视为', '属于', '成立'],
}

with open('configs/zh_CN/rules.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
rules = data.get('rules', [])

reclassified = 0
for r in rules:
    claim = r.get('head_claim', '')
    # Re-classify namespace
    if r.get('namespace', '') in ('', 'unknown', 'general'):
        for ns, keywords in NAMESPACE_KEYWORDS.items():
            if any(kw in claim for kw in keywords):
                r['namespace'] = ns
                reclassified += 1
                break
    # Re-classify modality if UNKNOWN
    if r.get('norm_modality', 'UNKNOWN') == 'UNKNOWN':
        for mod, keywords in MODALITY_KEYWORDS.items():
            if any(kw in claim for kw in keywords):
                r['norm_modality'] = mod
                reclassified += 1
                break

print(f"Reclassified {reclassified} rules")
