"""Obstruction-first cross-jurisdiction router.

Mathematical basis: category_theory_rosetta.py — no universal functor exists.
COLLISION/ASYMMETRY -> block automatic mapping.
MATCH -> allow with jurisdiction tag preserved.
REFERENCE_UNVERIFIED -> human review only.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import yaml
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class ObstructionPair:
    source: str
    target: str
    concept: str
    status: str  # MATCH / COLLISION / ASYMMETRY / REFERENCE_UNVERIFIED
    note: str = ""


@dataclass
class CrossJurisdictionRouter:
    pairs: List[ObstructionPair] = field(default_factory=list)
    loaded: bool = False

    def load(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            logger.warning("OBSTRUCTION_REGISTRY_NOT_FOUND: %s", filepath)
            return False
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        for p in data.get('pairs', []):
            self.pairs.append(ObstructionPair(
                source=p['source'], target=p['target'],
                concept=p['concept'], status=p['status'],
                note=p.get('note', ''),
            ))
        self.loaded = True
        logger.info("OBSTRUCTION_REGISTRY_LOADED: %d pairs", len(self.pairs))
        return True

    def route(self, concept: str, source_jurisdiction: str, target_jurisdiction: str) -> dict:
        for p in self.pairs:
            if p.concept == concept and p.source == source_jurisdiction and p.target == target_jurisdiction:
                if p.status == "MATCH":
                    return {"allowed": True, "status": "MATCH", "note": p.note}
                elif p.status in ("COLLISION", "ASYMMETRY"):
                    return {"allowed": False, "status": p.status, "note": p.note, "action": "BLOCK"}
                elif p.status == "REFERENCE_UNVERIFIED":
                    return {"allowed": False, "status": "REFERENCE_UNVERIFIED", "note": p.note, "action": "HUMAN_REVIEW"}
        return {"allowed": False, "status": "UNMAPPED", "action": "HUMAN_REVIEW"}
