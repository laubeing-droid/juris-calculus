#!/usr/bin/env python3
"""Shared helpers for knowledge graph audit tools."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml


ROOT = Path(__file__).resolve().parent.parent


def resolve_ref(ref: str) -> Path:
    path = ref.split("#", 1)[0]
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p


def load_yaml(path: str | Path) -> Dict[str, Any]:
    p = resolve_ref(str(path))
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def make_report(role: str, findings: List[Dict[str, Any]], metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "role": role,
        "status": "PASS" if not findings else "FAIL",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "findings": findings,
        "metadata": metadata or {},
    }


def write_json(path: str | Path, payload: Dict[str, Any]) -> None:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def finding(contract_id: str, field_path: str, issue: str, root_cause_node: str,
            suggestion: str, severity: str = "ERROR") -> Dict[str, str]:
    return {
        "severity": severity,
        "contract_id": contract_id,
        "field_path": field_path,
        "issue": issue,
        "root_cause_node": root_cause_node,
        "blueprint_patch_suggestion": suggestion,
    }
