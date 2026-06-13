#!/usr/bin/env python3
"""Source anchor helpers for legal rules and facts."""
from __future__ import annotations

import hashlib


def make_source_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def make_source_anchor(authority_id: str, source_span: str) -> str:
    digest = make_source_hash(source_span)[:12]
    return f"{authority_id}#{digest}"


def validate_source_anchor(anchor: str) -> bool:
    if not isinstance(anchor, str) or not anchor.strip():
        return False
    return "#" in anchor or ":" in anchor or "_" in anchor
