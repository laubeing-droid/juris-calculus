#!/usr/bin/env python3
"""v2.0 Legal Memory - two-class memory with TTL and archival.

CaseContextMemory: TTL 30 days or case-end immediate clear.
LegalKnowledgeMemory: permanent (de-identified sources only).
"""
import time
from typing import Dict, List, Any, Optional


class CaseContextMemory:
    def __init__(self, ttl_seconds: int = 30 * 86400):
        self.ttl = ttl_seconds
        self._store: Dict[str, Dict] = {}
        self._timestamps: Dict[str, float] = {}

    def put(self, key: str, value: Any) -> None:
        self._store[key] = value
        self._timestamps[key] = time.time()

    def get(self, key: str) -> Optional[Any]:
        ts = self._timestamps.get(key, 0)
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            self._timestamps.pop(key, None)
            return None
        return self._store.get(key)

    def archive(self, case_id: str) -> None:
        keys = [k for k in self._store if case_id in k]
        for k in keys:
            self._store.pop(k, None)
            self._timestamps.pop(k, None)

    def __len__(self) -> int:
        return len(self._store)


class LegalKnowledgeMemory:
    def __init__(self):
        self._store: Dict[str, Any] = {}

    def put(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def keys(self):
        return self._store.keys()
