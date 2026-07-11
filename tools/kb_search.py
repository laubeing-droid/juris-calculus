#!/usr/bin/env python3
"""
tools/kb_search.py — 知识库检索 (Contextual Memory Tier)
══════════════════════════════════════════════════════════
三层架构中的 Contextual Memory 层:
  非算子化的法律上下文 → 全文关键词检索 → 返回最相关的标注

用法:
  from tools.kb_search import search_hk_library, search_prc_lexicon
  results = search_hk_library("Mareva")
══════════════════════════════════════════════════════════
"""

import yaml
import re
import os
from pathlib import Path
from typing import List, Dict

BASE = Path(__file__).resolve().parents[1]


def _load_hk() -> List[Dict]:
    override = os.environ.get("JURIS_HK_LIBRARY_PATH", "").strip()
    if not override:
        return []
    hk_lib = Path(override).expanduser().resolve()
    if not hk_lib.exists():
        return []
    with open(hk_lib, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("entries", [])


def search_hk_library(query: str, top_k: int = 5) -> List[Dict]:
    """
    在香港法库中检索最相关的标注。

    Args:
        query: 自然语言查询 (e.g. "Mareva 禁制令 境外资产")
        top_k: 返回条数

    Returns:
        [{id, citation, context, score}, ...]
    """
    entries = _load_hk()
    if not entries:
        return []

    query_lower = query.lower()
    scored = []

    for entry in entries:
        text = (entry.get("citation", "") + " " +
                entry.get("context", "") + " " +
                entry.get("trigger_scenario", "")).lower()
        # 简单词频匹配
        words = set(re.findall(r'\w+', query_lower))
        text_words = set(re.findall(r'\w+', text))
        overlap = len(words & text_words)
        score = overlap / max(len(words), 1) if words else 0

        if "operator_note" in entry:
            text += " " + entry["operator_note"].lower()

        # 全字段模糊匹配加分
        for part in [p.strip() for p in query_lower.split(",")]:
            if part and part in text:
                score += 0.3

        scored.append((score, entry))

    scored.sort(key=lambda x: -x[0])
    results = []
    for score, entry in scored[:top_k]:
        r = dict(entry)
        r["score"] = round(score, 2)
        results.append(r)
    return results


def search_all(query: str, top_k: int = 5) -> Dict:
    """跨库检索: HK Library + PRC Lexicon"""
    return {
        "hk_library": search_hk_library(query, top_k),
        "prc_lexicon": [],  # 待挂载
        "query": query,
    }
