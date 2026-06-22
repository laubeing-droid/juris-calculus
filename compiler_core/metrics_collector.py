"""Metrics collector for MCP tool calls."""
import time
from collections import defaultdict
from typing import Dict, List


class MetricsCollector:
    def __init__(self):
        self._calls: Dict[str, List[dict]] = defaultdict(list)

    def record(self, tool_name: str, success: bool, duration_ms: float):
        self._calls[tool_name].append({
            "timestamp": time.time(),
            "success": success,
            "duration_ms": duration_ms,
        })

    def summary(self) -> dict:
        result = {}
        for tool, calls in self._calls.items():
            total = len(calls)
            success = sum(1 for c in calls if c["success"])
            avg_ms = sum(c["duration_ms"] for c in calls) / max(total, 1)
            result[tool] = {"total": total, "success": success, "success_rate": round(success/max(total,1), 3), "avg_ms": round(avg_ms, 1)}
        return result
