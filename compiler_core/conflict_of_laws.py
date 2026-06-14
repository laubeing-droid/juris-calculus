#!/usr/bin/env python3
"""Conflict of Laws — simplified jurisdiction selection.

When a case involves multiple jurisdictions, this module selects the
governing law based on:
  1. Explicit choice-of-law clause in facts (highest priority)
  2. Closest connection principle (fact-based heuristic)
  3. Default: jurisdiction specified by the caller

Design: Gemini audit — "lock the Session's jurisdiction at init"
"""
from typing import Dict, Optional


# Heuristic: which jurisdiction is closest based on fact presence
_FACT_JURISDICTION_SIGNALS = {
    "CN": [
        "contract_formed", "breach_alleged", "damages_claimed",
        "contract_invalid", "statute_barred",
    ],
    "HK": [
        "ContractOfSale_Exists", "Director_Acted_UltraVires",
        "Buyer_QuietPossession",
    ],
    "US": [
        "Consideration_Provided", "Arbitration_Agreement_Valid_Enforceable",
        "Punitive_Damages_Claimed",
    ],
}


def select_jurisdiction(
    facts: Dict,
    explicit_choice: Optional[str] = None,
    default_jurisdiction: str = "CN",
) -> str:
    """Select the governing jurisdiction for a set of facts.

    Priority:
    1. Explicit choice-of-law fact (e.g., "governing_law_hk")
    2. Closest connection (count fact signals per jurisdiction)
    3. Default jurisdiction

    Args:
        facts: dict of fact_id → LegalFact
        explicit_choice: override jurisdiction (e.g., from a choice-of-law clause)
        default_jurisdiction: fallback if no signals found

    Returns:
        jurisdiction code: "CN", "HK", or "US"
    """
    # Priority 1: explicit choice
    if explicit_choice:
        return explicit_choice.upper()

    # Check facts for explicit choice-of-law
    fact_ids = set(facts.keys())
    for choice_key in ["governing_law_cn", "governing_law_hk", "governing_law_us"]:
        if choice_key in fact_ids:
            return choice_key.replace("governing_law_", "").upper()

    # Priority 2: closest connection (count signals)
    scores = {}
    for jurisdiction, signals in _FACT_JURISDICTION_SIGNALS.items():
        score = sum(1 for s in signals if s in fact_ids)
        if score > 0:
            scores[jurisdiction] = score

    if scores:
        return max(scores, key=scores.get)

    # Priority 3: default
    return default_jurisdiction
