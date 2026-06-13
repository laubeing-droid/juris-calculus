"""Entity anonymizer: mask names/amounts/dates before sending to external LLMs."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


PERSON_PATTERN = re.compile(r'(?:原告|被告|申请人|被申请人|第三人|上诉人|被上诉人|再审申请人|法定代表人)[：:]\s*([^\s，。,\.]{2,10})')
AMOUNT_PATTERN = re.compile(r'(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\s*(?:元|万元|美元|港币|欧元)')
DATE_PATTERN = re.compile(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)')


def anonymize_text(text: str) -> Tuple[str, Dict[str, str]]:
    mapping: Dict[str, str] = {}
    person_count = 0
    amount_count = 0
    date_count = 0

    def _replace_person(match):
        nonlocal person_count
        mid = match.group(1)
        if mid in mapping:
            return match.group(0).replace(mid, mapping[mid], 1)
        person_count += 1
        placeholder = f"[PERSON_{person_count}]"
        mapping[placeholder] = mid
        return match.group(0).replace(mid, placeholder, 1)

    def _replace_amount(match):
        nonlocal amount_count
        amount_count += 1
        placeholder = f"[AMOUNT_{amount_count}]"
        mapping[placeholder] = match.group(0)
        return placeholder

    def _replace_date(match):
        nonlocal date_count
        date_count += 1
        placeholder = f"[DATE_{date_count}]"
        mapping[placeholder] = match.group(0)
        return placeholder

    result = PERSON_PATTERN.sub(_replace_person, text)
    result = AMOUNT_PATTERN.sub(_replace_amount, result)
    result = DATE_PATTERN.sub(_replace_date, result)

    return result, mapping


def de_anonymize_text(anonymized: str, mapping: Dict[str, str]) -> str:
    result = anonymized
    for placeholder, original in mapping.items():
        result = result.replace(placeholder, original)
    return result
