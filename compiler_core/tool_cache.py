"""Tool result cache with TTL."""
import time
import hashlib
import json
from typing import Any, Optional, Dict


class ToolCache:
    def __init__(self, ttl: int = 300):
        self._cache: Dict[str, tuple] = {}
        self._ttl = ttl

    def _key(self, tool_name: str, args: dict) -> str:
        raw = json.dumps({"tool": tool_name, "args": args}, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, tool_name: str, args: dict) -> Optional[Any]:
        key = self._key(tool_name, args)
        if key in self._cache:
            value, ts = self._cache[key]
            if time.time() - ts < self._ttl:
                return value
            del self._cache[key]
        return None

    def put(self, tool_name: str, args: dict, result: Any):
        key = self._key(tool_name, args)
        self._cache[key] = (result, time.time())

    def clear(self):
        self._cache.clear()
