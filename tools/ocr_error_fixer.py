"""OCR error fixer — common OCR misrecognition corrections."""
import yaml, re

ERROR_MAP = {
    '—': '-',  # em dash → hyphen
    '–': '-',  # en dash
    '“': '"', '”': '"',  # smart quotes
    '‘': "'", '’': "'",
    '，': ',',  # fullwidth comma
    '：': ':',  # fullwidth colon
    '；': ';',  # fullwidth semicolon
}

with open('configs/zh_CN/rules.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

rules = data.get('rules', [])
fixed = 0
for r in rules:
    claim = r.get('head_claim', '')
    original = claim
    for old, new in ERROR_MAP.items():
        claim = claim.replace(old, new)
    if claim != original:
        r['head_claim'] = claim
        fixed += 1

with open('configs/zh_CN/rules.yaml', 'w', encoding='utf-8') as f:
    yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f"Fixed {fixed} rules with OCR errors")
