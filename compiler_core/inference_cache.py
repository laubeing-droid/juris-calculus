"""Inference cache — LRU cache for evaluation results."""
from functools import lru_cache
from typing import Dict, Any, Optional
import hashlib
import json


class InferenceCache:
    def __init__(self, maxsize: int = 100):
        self._cache: Dict[str, Any] = {}
        self._maxsize = maxsize

    def _key(self, facts: Dict[str, str]) -> str:
        items = sorted(facts.items())
        return hashlib.md5(json.dumps(items, ensure_ascii=False).encode()).hexdigest()

    def get(self, facts: Dict[str, str]) -> Optional[Any]:
        return self._cache.get(self._key(facts))

    def put(self, facts: Dict[str, str], result: Any):
        key = self._key(facts)
        if len(self._cache) >= self._maxsize:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[key] = result

    def clear(self):
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)
