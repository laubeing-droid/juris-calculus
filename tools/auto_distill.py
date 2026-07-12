"""Auto-distillation script: extract rules from all 20 books' OCR JSON.

Reads all pages, identifies rule-containing paragraphs via keyword patterns,
extracts premise_atoms + head_claim + norm_modality, outputs YAML candidates.
"""
import json
import os
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = os.environ.get("JC_DISTILL_SOURCE_ROOT", str(REPO_ROOT / "下载存放区" / "全文json"))
OUTPUT_DIR = os.environ.get("JC_DISTILL_OUTPUT_DIR", str(REPO_ROOT / "过程文件" / "distill_candidates"))

# Book → prefix mapping
BOOK_PREFIX = {
    '民商事审判实务1': 'CM1', '民商事审判实务2': 'CM2', '民商事审判实务3': 'CM3',
    '民商事审判实务4': 'CM4', '民商事审判实务5': 'CM5', '民商事审判实务6': 'CM6',
    '刑事审判实务上册': 'XS1', '刑事审判实务下册': 'XS2',
    '审判监督实务上册': 'ZS1', '审判监督实务下册': 'ZS2',
    '涉外商事海事审判实务和国际司法协助': 'HS',
    '行政审判实务': 'XZ', '立案工作实务': 'LA',
    '涉港澳民商事审判实务和区际司法协助': 'HJ',
    '国家赔偿审判实务': 'PC', '未成年人审判实务': 'WCNR',
    '审判管理实务': 'GL', '知识产权审判实务': 'SJ',
    '执行案件办理实务': 'ZX', '环境资源审判实务': 'GA',
}

# Keywords that indicate actionable rules
OBLIGATION_KEYWORDS = ['应当', '必须', '需要', '有义务', '负有']
PROHIBITION_KEYWORDS = ['不得', '禁止', '严禁', '不准', '不允许']
PERMISSION_KEYWORDS = ['可以', '有权', '允许', '享有']
CONSTITUTIVE_KEYWORDS = ['构成', '认定为', '视为', '属于', '成立', '以...论处', '按...处理']

# Skip patterns (not rules)
SKIP_PATTERNS = [
    r'参见.*?\d+页', r'①②③', r'载.*?http', r'最后访问日期',
    r'^\d+$', r'^第.*?页$', r'^[\s]*$',
]


def is_rule_paragraph(text):
    """Check if a paragraph likely contains an actionable rule."""
    text = text.strip()
    if len(text) < 30:
        return False
    if len(text) > 1000:
        return False
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, text[:50]):
            return False
    # Must contain at least one rule keyword
    all_keywords = OBLIGATION_KEYWORDS + PROHIBITION_KEYWORDS + PERMISSION_KEYWORDS + CONSTITUTIVE_KEYWORDS
    return any(kw in text for kw in all_keywords)


def classify_modality(text):
    """Classify norm_modality based on keywords."""
    if any(kw in text for kw in PROHIBITION_KEYWORDS):
        return 'PROHIBITION'
    if any(kw in text for kw in OBLIGATION_KEYWORDS):
        return 'OBLIGATION'
    if any(kw in text for kw in PERMISSION_KEYWORDS):
        return 'PERMISSION'
    if any(kw in text for kw in CONSTITUTIVE_KEYWORDS):
        return 'CONSTITUTIVE'
    return 'UNKNOWN'


def extract_premise_atoms(text):
    """Extract premise conditions from rule text."""
    atoms = []
    # Pattern: 当/如果/在...情况下
    conditions = re.findall(r'(?:当|如果|在)(.{5,30}?)(?:时|的情况下|情形下)', text)
    for c in conditions[:3]:
        atom = re.sub(r'[，。、；]', '_', c.strip())[:30]
        atom = re.sub(r'[^a-zA-Z0-9_一-鿿]', '', atom)
        if atom and len(atom) >= 2:
            atoms.append(atom)
    # Pattern: X的 (conditions before 的)
    de_patterns = re.findall(r'([一-鿿]{4,15}的)', text[:100])
    for d in de_patterns[:2]:
        atom = d.replace('的', '')[:20]
        atom = re.sub(r'[^a-zA-Z0-9_一-鿿]', '', atom)
        if atom and len(atom) >= 3 and atom not in atoms:
            atoms.append(atom)
    return atoms[:3] if atoms else [text[:20].replace(' ', '_')]


def extract_head_claim(text):
    """Extract the main conclusion from rule text."""
    # Try to find the conclusion after keyword
    for kw in ['应当', '必须', '不得', '可以', '构成', '认定为', '视为']:
        idx = text.find(kw)
        if idx > 0:
            claim = text[max(0, idx-10):min(len(text), idx+80)]
            return claim.strip()[:100]
    return text[:100].strip()


def extract_chapter(text):
    """Try to extract chapter/section from text."""
    m = re.search(r'第[一二三四五六七八九十百千]+[章节编]', text[:30])
    return m.group() if m else ''


def process_book(book_name, book_path):
    """Process one book and extract rules."""
    with open(book_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    pages = data.get('pages', [])
    prefix = BOOK_PREFIX.get(book_name, 'XX')
    rules = []
    rule_counter = 1
    current_chapter = ''

    for page_idx, page in enumerate(pages):
        text = page.get('text', '')
        if not text:
            continue

        # Track chapter
        ch = extract_chapter(text)
        if ch:
            current_chapter = ch

        # Split into paragraphs
        paragraphs = re.split(r'(?<=[。！？])\s*', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        for para in paragraphs:
            if not is_rule_paragraph(para):
                continue

            modality = classify_modality(para)
            if modality == 'UNKNOWN':
                continue

            premises = extract_premise_atoms(para)
            claim = extract_head_claim(para)

            rule_id = f"{prefix}-{rule_counter:03d}"
            rule_counter += 1

            rules.append({
                'id': rule_id,
                'premise_atoms': premises,
                'head_claim': claim,
                'exception_chain': [],
                'concepts': premises[:2],
                'mechanical_exception': False,
                'head_type': 'HORN',
                'namespace': prefix[:2].lower(),
                'norm_modality': modality,
                'modality_confidence': 0.7,
                'modality_source': 'auto_distill',
                'source_anchor': f"{book_name}/{current_chapter}",
            })

    return rules


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    total_rules = 0

    for book_name, prefix in sorted(BOOK_PREFIX.items()):
        book_path = os.path.join(BASE_DIR, f'{book_name}_ocr.json')
        if not os.path.exists(book_path):
            print(f"SKIP: {book_name} (file not found)")
            continue

        print(f"Processing {book_name}...", end=' ', flush=True)
        rules = process_book(book_name, book_path)
        print(f"{len(rules)} rules extracted")

        # Write YAML
        output_path = os.path.join(OUTPUT_DIR, f'{book_name}_auto.yaml')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# {book_name} - auto-distilled rules\n")
            f.write(f"# Source: {book_name}_ocr.json\n")
            f.write(f"# Count: {len(rules)}\nrules:\n")
            for rule in rules:
                yaml.dump([rule], f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        total_rules += len(rules)

    print(f"\nTotal auto-distilled: {total_rules} rules from {len(BOOK_PREFIX)} books")


if __name__ == '__main__':
    main()
