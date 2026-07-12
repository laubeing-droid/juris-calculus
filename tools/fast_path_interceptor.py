#!/usr/bin/env python3
"""Deterministic fast-path threat interception for the tri-rail harness."""

from __future__ import annotations

import re
from typing import Any

from addons.us.us_lookup import validate_usc_citation


_DEFAULT_SIGNATURES: tuple[dict[str, Any], ...] = (
    {
        "signature_id": "THREAT_NJ_PEN_001_AlterEgo",
        "pattern": ("Alter-Ego", "piercing the corporate veil"),
        "threat_level": "CRITICAL",
        "action": "FORCE_SUPPRESS",
        "target_rule": "THREAT_NJ_PEN_001_AlterEgo",
        "description": "NJ法人人格否认威胁 — 触发CBL强制阻断",
        "source_file": "builtin:nj_alter_ego",
    },
    {
        "signature_id": "THREAT_WI_ENF_001_LongArm",
        "pattern": ("Long-Arm Statute 801.05", "Wis. Stat. 801.05"),
        "threat_level": "CRITICAL",
        "action": "FORCE_SUPPRESS",
        "target_rule": "THREAT_WI_ENF_001_LongArm",
        "description": "WI长臂管辖威胁 — 旁路Horn直接CBL阻断",
        "source_file": "builtin:wi_long_arm",
    },
)


class FastPathInterceptor:
    """TriRailCollider 的前置威胁哨兵；不依赖外部 YAML 签名目录。"""

    def __init__(self, signatures: tuple[dict[str, Any], ...] | None = None) -> None:
        self.signatures = tuple(signatures or _DEFAULT_SIGNATURES)

    @staticmethod
    def _fact_names(shared_facts: Any) -> list[str]:
        if isinstance(shared_facts, dict):
            return [str(name) for name in shared_facts]
        if isinstance(shared_facts, list):
            return [str(name) for name in shared_facts]
        return []

    @staticmethod
    def _matches(patterns: tuple[str, ...], fact_blob: str) -> str | None:
        for pattern in patterns:
            if re.search(re.escape(pattern), fact_blob, re.IGNORECASE):
                return pattern
        return None

    def intercept(self, shared_facts: Any) -> dict[str, Any] | None:
        """命中内建威胁或非法 USC 引用时，返回 review-only fast-path 指令。"""

        fact_names = self._fact_names(shared_facts)
        if not fact_names:
            return None
        fact_blob = " | ".join(fact_names)

        try:
            citations = validate_usc_citation(fact_blob)
        except OSError:
            citations = []
        for citation in citations:
            if not citation.get("valid"):
                title = citation.get("title", "?")
                return {
                    "intercepted": True,
                    "signature_id": "USC_INVALID_TITLE",
                    "threat_level": "HIGH",
                    "action": "FORCE_SUPPRESS",
                    "target_rule": citation.get("citation", ""),
                    "reason": f"Invalid US Code: Title {title}",
                    "method": "USC_VALIDATION",
                    "source_file": "addons.us.us_lookup",
                }

        for signature in self.signatures:
            matched = self._matches(tuple(signature.get("pattern", ())), fact_blob)
            if matched is None:
                continue
            return {
                "intercepted": True,
                "signature_id": str(signature["signature_id"]),
                "threat_level": str(signature.get("threat_level", "MEDIUM")),
                "action": str(signature.get("action", "FORCE_SUPPRESS")),
                "target_rule": str(signature.get("target_rule", "")),
                "reason": str(signature.get("description", "")),
                "method": "FAST_PATH_BYPASS",
                "source_file": str(signature.get("source_file", "builtin")),
                "matched_pattern": matched,
            }
        return None

    def get_threat_report(self, shared_facts: Any) -> list[dict[str, Any]]:
        """返回全部匹配命中，用于只读告警。"""

        fact_names = self._fact_names(shared_facts)
        if not fact_names:
            return []
        fact_blob = " | ".join(fact_names)
        hits: list[dict[str, Any]] = []
        for signature in self.signatures:
            matched = self._matches(tuple(signature.get("pattern", ())), fact_blob)
            if matched is None:
                continue
            hits.append(
                {
                    "signature_id": str(signature["signature_id"]),
                    "threat_level": str(signature.get("threat_level", "MEDIUM")),
                    "matched_pattern": matched,
                    "action": str(signature.get("action", "")),
                }
            )
        return hits
