#!/usr/bin/env python3
"""v2.0 US legal assets lookup — reads from the bundled addon blueprint domain_assets.

Provides:
  - court_jurisdiction(name) → {level, category} or None
  - usc_title_exists(num) → bool
  - usc_chapter_name(title, chapter) → str or None
  - is_federal_court(name) → bool

Cold-start safe: all data comes from blueprint; no network calls.
"""
import json
from pathlib import Path
from typing import Optional, Dict, List

_BLUEPRINT = None


def _load():
    global _BLUEPRINT
    if _BLUEPRINT is not None:
        return _BLUEPRINT
    from pathlib import Path as _P; _BP = _P(__file__).resolve().parent / "blueprint.json"
    with open(str(_BP), "r", encoding="utf-8") as f:
        _BLUEPRINT = json.load(f)
    return _BLUEPRINT


def _us_assets() -> Dict:
    return _load().get("domain_assets", {}).get("united_states_code", {})


def _us_courts() -> Dict:
    return _load().get("domain_assets", {}).get("united_states_courts", {}).get("hierarchy", {})


def usc_title_exists(num: int) -> bool:
    """Check if a US Code title number exists in the index."""
    titles = _us_assets().get("titles", [])
    return any(t.get("title") == str(num) for t in titles)


def usc_title_name(num: int) -> Optional[str]:
    """Get the human-readable name of a US Code title."""
    for t in _us_assets().get("titles", []):
        if t.get("title") == str(num):
            return t.get("name")
    return None


def usc_chapter_name(title_num: int, chapter_num: str) -> Optional[str]:
    """Get chapter name within a US Code title."""
    for t in _us_assets().get("titles", []):
        if t.get("title") == str(title_num):
            for ch in t.get("chapter_list", []):
                if ch.get("num") == chapter_num:
                    return ch.get("name")
    return None


def court_jurisdiction(name: str) -> Optional[Dict]:
    """Look up a US court by name fragment. Returns {level, category, full_name} or None.

    Recognizes common abbreviations: ca9 → Ninth Circuit, sdny → Southern District of NY, etc.
    """
    name_lower = name.lower().replace(" ", "").replace(".", "")
    courts = _us_courts()

    # Direct match in each category
    for category, court_list in courts.items():
        if not isinstance(court_list, list):
            continue
        for full_name in court_list:
            fn_lower = full_name.lower().replace(" ", "").replace(".", "")
            if name_lower == fn_lower or name_lower in fn_lower:
                return {
                    "category": category,
                    "full_name": full_name,
                    "is_federal": category.startswith("federal_") or category.startswith("administrative"),
                }

    # Try common abbreviation mapping
    abbreviations = {
        "ca1": ("ca1", "federal_appellate"),
        "ca2": ("ca2", "federal_appellate"),
        "ca3": ("ca3", "federal_appellate"),
        "ca4": ("ca4", "federal_appellate"),
        "ca5": ("ca5", "federal_appellate"),
        "ca6": ("ca6", "federal_appellate"),
        "ca7": ("ca7", "federal_appellate"),
        "ca8": ("ca8", "federal_appellate"),
        "ca9": ("ca9", "federal_appellate"),
        "ca10": ("ca10", "federal_appellate"),
        "ca11": ("ca11", "federal_appellate"),
        "cadc": ("cadc", "federal_appellate"),
        "cafc": ("federal circuit", "federal_special"),
        "scotus": ("supreme court", "federal_special"),
    }
    if name_lower in abbreviations:
        mapped, cat = abbreviations[name_lower]
        return {"category": cat, "full_name": mapped, "is_federal": True, "abbreviation_match": True}

    return None


def is_federal_court(name: str) -> bool:
    """Check if a court name is a US federal court."""
    result = court_jurisdiction(name)
    return result is not None and result.get("is_federal", False)


def lookup_us_legal_term(term: str):
    """Look up a US federal legal term in the blueprint dictionary.
    Returns {l0_primitive, structural_chain} or None.
    """
    terms = _load().get("domain_assets", {}).get("en_US_legal_terms", {}).get("l0_mapped_terms", {})
    return terms.get(term.lower())

def is_known_us_term(term: str) -> bool:
    """Check if a term is known in either federal or state US legal dictionaries."""
    fed = _load().get("domain_assets", {}).get("en_US_legal_terms", {}).get("l0_mapped_terms", {})
    state = _load().get("domain_assets", {}).get("en_US_state_terms", {}).get("terms", [])
    t = term.lower()
    return t in fed or t in state

def terms_by_moe_domain(moe_domain: str):
    """Get US legal terms for a given CN MoE domain.
    Returns list of {term, l0} dicts or empty list.
    Used by rule_router for cross-jurisdiction MoE routing.
    """
    moe = _load().get("domain_assets", {}).get("en_US_legal_terms_moe", {}).get("by_moe_domain", {})
    domain_data = moe.get(moe_domain, {})
    return domain_data.get("terms", [])


def state_term_lookup(term: str, state_code: str = None):
    """Look up a US state-level legal term. Returns dict or None.
    
    Checks structured state_terms first, then falls back to vocabulary.
    If state_code is given, prefers exact state match.
    """
    assets = _load().get("domain_assets", {})
    
    # 1. Structured state terms
    structured = assets.get("en_US_state_terms", {}).get("by_state", {})
    t = term.lower()
    
    if state_code and state_code in structured:
        for entry in structured[state_code]:
            if entry.get("term", "").lower() == t:
                return entry
    
    if not state_code:
        for state, entries in structured.items():
            for entry in entries:
                if entry.get("term", "").lower() == t:
                    return entry
    
    # 2. Flat vocabulary fallback
    vocab = assets.get("en_US_state_vocabulary", {}).get("terms", [])
    if t in vocab:
        return {"term": term, "source": "state_vocabulary", "l0_primitive": "?"}
    
    return None


def terms_by_moe_and_state(moe_domain: str, state_code: str = None):
    """Two-tier lookup: MoE domain + optional state filter.
    Returns list of matching {term, l0} dicts.
    """
    assets = _load().get("domain_assets", {})
    moe_state = assets.get("en_US_state_terms", {}).get("by_moe_and_state", {})
    
    key = moe_domain
    if state_code:
        key = f"{moe_domain}_{state_code}"
    
    return moe_state.get(key, [])


def get_state_list():
    """Return list of US states with structured term data."""
    structured = _load().get("domain_assets", {}).get("en_US_state_terms", {}).get("by_state", {})
    return sorted(structured.keys())


def moe_domain_list():
    """Return list of all MoE domains with US term coverage."""
    moe = _load().get("domain_assets", {}).get("en_US_legal_terms_moe", {}).get("by_moe_domain", {})
    return sorted(moe.keys())


def l0_primitive_from_term(term: str):
    """Get L0 primitive for a US legal term from blueprint dictionaries.
    Falls back to ''?'' if unknown.
    """
    entry = lookup_us_legal_term(term)
    return entry.get("l0_primitive", "?") if entry else "?"


def validate_usc_citation(text: str) -> List[Dict]:
    """Scan text for US Code citations and validate against blueprint.

    Returns list of {citation, valid, title_name} dicts.
    """
    import re
    results = []
    # Match patterns like "28 U.S.C. § 1331" or "Title 11 § 362"
    patterns = [
        r'(\d+)\s+U\.?S\.?C\.?\s*[§§]\s*(\d+[a-z]?)',
        r'Title\s+(\d+)\s*[§§]\s*(\d+[a-z]?)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            title_num = int(m.group(1))
            section = m.group(2)
            title_name = usc_title_name(title_num)
            results.append({
                "citation": m.group(0),
                "title": title_num,
                "section": section,
                "valid": title_name is not None,
                "title_name": title_name or "UNKNOWN_TITLE",
            })
    return results
