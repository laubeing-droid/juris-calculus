"""DDL preclassifier: deterministic norm_modality classification for 2117 Chinese legal rules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# Path to confirmed modalities from LLM batch validation
_CONFIRMED_MODALITIES_PATH = "neural/registry/ddl_confirmed_modalities.json"
_CONFIRMED: Dict[str, Any] = {}
try:
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / _CONFIRMED_MODALITIES_PATH
    if p.exists():
        _CONFIRMED = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    pass

def _get_confirmed(rule_id: str) -> "NormModality | None":
    from compiler_core.types import NormModality
    entry = _CONFIRMED.get(rule_id)
    if entry and "modality" in entry:
            return NormModality(entry["modality"])
    return None


from compiler_core.types import NormModality


OBLIGATION_KEYWORDS = ["\u5e94\u5f53", "\u5fc5\u987b", "\u8d1f\u6709", "\u627f\u62c5", "\u8d1f\u8d23", "\u5e94\u4e88"]
PROHIBITION_KEYWORDS = ["\u4e0d\u5f97", "\u7981\u6b62", "\u4e25\u7981", "\u4e0d\u51c6", "\u4e0d\u8bb8"]
PERMISSION_KEYWORDS = ["\u53ef\u4ee5", "\u6709\u6743", "\u5141\u8bb8", "\u7ecf\u2026\u2026\u540c\u610f", "\u7ecf\u2026\u2026\u6279\u51c6"]
CONSTITUTIVE_SIGNALS = [
    "\u672a\u7ecf\u767b\u8bb0\uff0c\u4e0d\u5f97\u5bf9\u6297",
    "\u672a\u7ecf\u6279\u51c6\uff0c\u4e0d\u53d1\u751f\u6548\u529b",
    "\u4e0d\u6210\u7acb",
    "\u65e0\u6548",
    "\u89c6\u4e3a",
    "\u63a8\u5b9a",
    "\u4e0d\u4ea7\u751f\u2026\u2026\u6548\u529b",
    "\u81ea\u59cb\u65e0\u6548",
    "\u4e0d\u53d1\u751f\u6cd5\u5f8b\u6548\u529b",
    "\u6cd5\u5f8b\u53e6\u6709\u89c4\u5b9a\u7684\u9664\u5916",
]
FORBIDDEN_CHAIN_SIGNALS = [
    "\u6216\u8005", "\u4efb\u9009\u5176\u4e00",
    "\u7b49\u8fdd\u7ea6\u8d23\u4efb", "\u7b49\u4fb5\u6743\u8d23\u4efb", "\u7b49\u884c\u653f\u8d23\u4efb"
]


@dataclass
class DDLPreclassResult:
    rule_id: str
    modality: NormModality = NormModality.UNKNOWN
    confidence: float = 0.0
    reason: str = ""


def preclassify_rule(rule: Dict[str, Any]) -> DDLPreclassResult:
    rid = str(rule.get("id", ""))
    confirmed = _get_confirmed(rid)
    if confirmed:
        return DDLPreclassResult(rule_id=rid, modality=confirmed, confidence=0.90, reason="confirmed via LLM batch validation")

    head = str(rule.get("head_claim", ""))
    premises = [str(p) for p in rule.get("premise_atoms", []) or []]
    concepts = [str(c) for c in rule.get("concepts", []) or []]
    namespace = str(rule.get("namespace", ""))
    full_text = head + " " + " ".join(premises) + " " + " ".join(concepts)

    for signal in CONSTITUTIVE_SIGNALS:
        if signal in full_text:
            return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.CONSTITUTIVE,
                                     confidence=0.95, reason="matched constitutive signal")

    has_obligation = any(kw in head for kw in OBLIGATION_KEYWORDS)
    has_prohibition = any(kw in head for kw in PROHIBITION_KEYWORDS)
    has_permission = any(kw in head for kw in PERMISSION_KEYWORDS)
    has_forbidden_chain = any(sig in head for sig in FORBIDDEN_CHAIN_SIGNALS)

    if has_obligation and not has_prohibition and not has_permission and not has_forbidden_chain:
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.OBLIGATION,
                                 confidence=0.85, reason="obligation keyword in head_claim")
    if has_prohibition and not has_obligation and not has_permission and not has_forbidden_chain:
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.PROHIBITION,
                                 confidence=0.85, reason="prohibition keyword in head_claim")
    if has_permission and not has_obligation and not has_prohibition and not has_forbidden_chain:
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.PERMISSION,
                                 confidence=0.75, reason="permission keyword in head_claim")

    if any(kw in full_text for kw in OBLIGATION_KEYWORDS):
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.OBLIGATION,
                                 confidence=0.55, reason="obligation keyword in rule text, ambiguous")
    if any(kw in full_text for kw in PROHIBITION_KEYWORDS):
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.PROHIBITION,
                                 confidence=0.55, reason="prohibition keyword in rule text, ambiguous")

    concept_str = " ".join(concepts)
    if u"\u56fd\u5bb6\u8d54\u507f" in concept_str or u"\u6267\u884c" in namespace or u"\u6267\u884c" in concept_str:
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.CONSTITUTIVE,
                                 confidence=0.55, reason="concept-based: foundational definition")
    if any(kw in concept_str for kw in [u"\u8d54\u507f", u"\u8fdd\u7ea6", u"\u4fb5\u6743", u"\u635f\u5bb3", u"\u8d23\u4efb"]):
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.OBLIGATION,
                                 confidence=0.50, reason="concept-based: liability-linked concept")
    if any(kw in concept_str for kw in [u"\u6743\u5229", u"\u8bb8\u53ef", u"\u6388\u6743"]):
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.PERMISSION,
                                 confidence=0.50, reason="concept-based: right/permit concept")

    # Tertiary cross-check for namespace-only rules

    # Structure-based fallback: exception_chain implies obligation
    if rule.get("exception_chain"):
        ns = namespace.lower()
        if ns in ("criminal",):
            return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.PROHIBITION,
                                     confidence=0.80, reason="structure: exception_chain in criminal context")
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.OBLIGATION,
                                 confidence=0.80, reason="structure: exception_chain implies defeasible obligation")

    # Namespace-based fallback
    ns = namespace.lower()
    if ns in ("contract", "tort", "general", "juvenile", "family"):
        if any(kw in head for kw in OBLIGATION_KEYWORDS):
            return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.OBLIGATION,
                                     confidence=0.75, reason="namespace+keyword: obligation domain matched keyword")
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.OBLIGATION,
                                 confidence=0.55, reason="namespace fallback: substantive law context")
    if ns in ("admin", "corporate", "procedure", "enforcement"):
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.CONSTITUTIVE,
                                 confidence=0.50, reason="namespace fallback: structural/procedural context")
    if ns in ("criminal", "ip"):
        if any(kw in head for kw in PROHIBITION_KEYWORDS):
            return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.PROHIBITION,
                                     confidence=0.75, reason="namespace+keyword: prohibition domain matched keyword")
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.PROHIBITION,
                                 confidence=0.55, reason="namespace fallback: criminal/IP prohibition context")

    # Tertiary cross-check: text signals in head_claim
    if any(kw in head for kw in ["应", "有义务", "承担", "负责", "履行"]):
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.OBLIGATION,
                                 confidence=0.70, reason="tertiary: obligation-related terms in head_claim")
    if any(kw in head for kw in ["管理", "职权", "程序", "范围", "属于", "包括", "是指"]):
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.CONSTITUTIVE,
                                 confidence=0.70, reason="tertiary: structural/procedural terms in head_claim")
    if any(kw in head for kw in ["犯罪", "处罚", "刑事", "违法", "禁止"]):
        return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.PROHIBITION,
                                 confidence=0.70, reason="tertiary: criminal/violation terms in head_claim")
    return DDLPreclassResult(rule_id=str(rule.get("id", "")), modality=NormModality.UNKNOWN,
                             confidence=0.0, reason="no modal keyword or known concept")


def preclassify_batch(rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    results: List[DDLPreclassResult] = []
    counts: Dict[str, int] = {m.value: 0 for m in NormModality}

    for rule in rules:
        if isinstance(rule, dict):
            result = preclassify_rule(rule)
            results.append(result)
            counts[result.modality.value] += 1

    high_confidence = [r for r in results if r.confidence >= 0.75]
    needs_candidate = [r for r in results if r.confidence < 0.75]

    return {
        "rule_count": len(results),
        "by_modality": counts,
        "high_confidence_count": len(high_confidence),
        "needs_candidate_count": len(needs_candidate),
        "high_confidence": [{"rule_id": r.rule_id, "modality": r.modality.value, "confidence": r.confidence, "reason": r.reason} for r in high_confidence],
        "needs_candidate": [{"rule_id": r.rule_id, "modality": r.modality.value, "confidence": r.confidence, "reason": r.reason} for r in needs_candidate],
        "status": "PASS" if not needs_candidate else "PARTIAL",
    }
