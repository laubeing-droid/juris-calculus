"""Source manifest validator — verifies rule source anchors are registered.

Mathematical basis: source_manifest prevents unverified references from
propagating to legal conclusions.
"""
from dataclasses import dataclass, field
from typing import Dict, List
import yaml
import os
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class SourceEntry:
    source_id: str
    source_type: str  # statute / case / commentary / textbook
    title: str
    jurisdiction: str
    verified: bool = False
    verification_date: str = ""
    content_hash: str = ""

    @property
    def reasoning_eligible(self) -> bool:
        """只有显式verified且具备SHA-256内容hash的来源可支撑正式结果。"""

        return self.verified and bool(re.fullmatch(r"[0-9a-f]{64}", self.content_hash))


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
                verified=bool(entry.get('verified', False)),
                verification_date=entry.get('verification_date', ''),
                content_hash=str(entry.get('content_hash') or ''),
            )
            self.entries[se.source_id] = se
        self.loaded = True
        logger.info("SOURCE_MANIFEST_LOADED: %d entries", len(self.entries))
        return True

    def validate_anchor(self, anchor: str) -> dict:
        if not anchor:
            return {"status": "MISSING_ANCHOR", "registered": False}
        entry = self.entries.get(anchor)
        if entry is None:
            return {"status": "UNREGISTERED", "registered": False}
        if entry.reasoning_eligible:
            return {
                "status": "VERIFIED",
                "registered": True,
                "source": entry.source_id,
                "source_snapshot_id": f"{entry.source_id}@{entry.content_hash}",
            }
        return {"status": "REFERENCE_UNVERIFIED", "registered": True, "source": entry.source_id}

    def coverage_rate(self, anchors: List[str]) -> float:
        if not anchors:
            return 1.0
        registered = sum(1 for a in anchors if self.validate_anchor(a)["registered"])
        return registered / len(anchors)
