"""只读、有限量的规则包检索；检索结果不改变规则准入状态。"""

from __future__ import annotations

from typing import Any

import yaml

from compiler_core.rule_packs import RulePackRegistry
from compiler_core.types import normalize_rule_admission


def lookup_rules(
    registry: RulePackRegistry,
    pack_id: str,
    *,
    rule_id: str | None = None,
    query: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """在已通过完整性校验的corpus pack内做确定性有限检索。"""

    if bool(rule_id) == bool(query):
        raise ValueError("exactly one of rule_id or query is required")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    loaded = registry.load_corpus_pack(pack_id)
    needle = str(rule_id or query).casefold()
    exact = rule_id is not None
    matches: list[dict[str, Any]] = []
    for path in loaded.rule_paths:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rules = document.get("rules", []) if isinstance(document, dict) else []
        if not isinstance(rules, list):
            continue
        for raw_rule in rules:
            if not isinstance(raw_rule, dict):
                continue
            rule = normalize_rule_admission(raw_rule)
            current_id = str(rule.get("id", ""))
            searchable = "\n".join(
                str(rule.get(field, ""))
                for field in ("id", "head_claim", "description", "legal_basis", "citation", "source_ref", "authority_id")
            ).casefold()
            if (exact and current_id.casefold() != needle) or (not exact and needle not in searchable):
                continue
            source_refs = sorted({
                str(rule.get(field, "")).strip()
                for field in ("source_anchor", "legal_basis", "citation", "source_ref", "authority_id")
                if str(rule.get(field, "")).strip()
            })
            matches.append({
                "rule_id": current_id,
                "head_claim": str(rule.get("head_claim", "")),
                "admission": "reasoning_eligible" if rule.get("source_anchor") else "candidate_only",
                "source_refs": source_refs,
            })
    matches.sort(key=lambda item: (item["rule_id"], item["head_claim"]))
    verification = loaded.verification
    return {
        "status": "ok",
        "pack_id": verification.pack_id,
        "pack_version": verification.version,
        "pack_digest": verification.content_digest,
        "inventory": dict(verification.inventory),
        "match_count": len(matches),
        "results": matches[:limit],
    }
