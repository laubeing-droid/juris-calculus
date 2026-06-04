#!/usr/bin/env python3
"""Clean Armenian glossary noise from combined terms"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
TARGET = ROOT / "configs" / "en_US" / "state_combined_terms.json"

with open(TARGET, 'r', encoding='utf-8') as f:
    terms = json.load(f)

cleaned = []
arm_garbled = [';u', 'mw3', 'mh', 'nun', ';un', 'dar', ';e', 'oar', 'qae', '8ae', '7an', ';u3']

for t in terms:
    if len(t) > 60 or len(t) < 4:
        continue
    if any(g in t for g in arm_garbled):
        continue
    if any(c in t for c in ['C:\\', 'DOCUME', 'Temp\\']):
        continue
    # All-caps long strings
    if t == t.upper() and len(t.split()) > 5:
        continue
    # Sentence fragments
    words = t.split()
    if len(words) >= 5 and sum(1 for w in words if w[0].islower()) >= 3:
        continue
    cleaned.append(t)

print(f'Original: {len(terms)}, Cleaned: {len(cleaned)}')

with open(TARGET, 'w', encoding='utf-8') as f:
    json.dump(cleaned, f, indent=2, ensure_ascii=False)
print('Saved')
