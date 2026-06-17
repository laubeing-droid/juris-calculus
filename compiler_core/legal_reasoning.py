"""Legal reasoning module: analogical, precedent, interpretation, interest balancing."""
from dataclasses import dataclass, field
from typing import Dict, List
from enum import Enum


class InterpretationMethod(Enum):
    LITERAL = "literal"
    SYSTEMATIC = "systematic"
    TELEOLOGICAL = "teleological"
    HISTORICAL = "historical"


def analogical_similarity(current_facts: List[str], precedent_facts: List[str]) -> float:
    if not current_facts or not precedent_facts:
        return 0.0
    shared = set(current_facts) & set(precedent_facts)
    total = set(current_facts) | set(precedent_facts)
    return len(shared) / len(total) if total else 0.0


def precedent_binding_force(court_level: str, jurisdiction_match: bool) -> float:
    levels = {"supreme": 1.0, "high": 0.8, "intermediate": 0.5, "basic": 0.3}
    base = levels.get(court_level, 0.1)
    return base if jurisdiction_match else base * 0.5


def balance_interests(interests: Dict[str, float]) -> dict:
    if not interests:
        return {"balanced": False}
    max_interest = max(interests, key=interests.get)
    total_weight = sum(interests.values())
    return {
        "balanced": True,
        "dominant_interest": max_interest,
        "dominant_ratio": interests[max_interest] / total_weight if total_weight else 0,
    }
