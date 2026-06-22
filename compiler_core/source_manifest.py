"""Source manifest validator — verifies rule source anchors are registered.

Mathematical basis: source_manifest prevents unverified references from
propagating to legal conclusions.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import yaml
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class SourceEntry:
    source_id: str
    source_type: str  # statute / case / commentary / textbook
    title: str
    jurisdiction: str
    verified: bool = True
    verification_date: str = ""


@dataclass
class SourceManifest:
    entries: Dict[str, SourceEntry] = field(default_factory=dict)
    loaded: bool = False

    def load(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            logger.warning("SOURCE_MANIFEST_NOT_FOUND: %s", filepath)
            return False
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        for entry in data.get('sources', []):
            se = SourceEntry(
                source_id=entry['source_id'],
                source_type=entry.get('source_type', 'unknown'),
                title=entry.get('title', ''),
                jurisdiction=entry.get('jurisdiction', ''),
                verified=entry.get('verified', True),
                verification_date=entry.get('verification_date', ''),
            )
            self.entries[se.source_id] = se
        self.loaded = True
        logger.info("SOURCE_MANIFEST_LOADED: %d entries", len(self.entries))
        return True

    def validate_anchor(self, anchor: str) -> dict:
        if not anchor:
            return {"status": "MISSING_ANCHOR", "registered": False}
        for sid, entry in self.entries.items():
            if sid in anchor or anchor.startswith(sid):
                if entry.verified:
                    return {"status": "VERIFIED", "registered": True, "source": sid}
                else:
                    return {"status": "REFERENCE_UNVERIFIED", "registered": True, "source": sid}
        return {"status": "UNREGISTERED", "registered": False}

    def coverage_rate(self, anchors: List[str]) -> float:
        if not anchors:
            return 1.0
        registered = sum(1 for a in anchors if self.validate_anchor(a)["registered"])
        return registered / len(anchors)
