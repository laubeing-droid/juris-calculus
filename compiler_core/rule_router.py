#!/usr/bin/env python3
"""v2.0 MoE Rule Router - blueprint/config-driven expert routing."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from compiler_core.config_paths import router_moe_path
from compiler_core.criminal_complexity import classify_criminal_complexity, is_criminal_case
from compiler_core.trust_labels import TrustLabel


FALLBACK_ROUTER_CONFIG = {
    "defaults": {"top_k": 2, "trust_label": TrustLabel.ENGINEERING_BASELINE.value},
    "expert_shards": {
        "刑事": {"keywords": ["刑事", "犯罪", "罪名", "被告人", "有期徒刑"]},
        "合同": {"keywords": ["合同", "违约", "定金", "买卖", "租赁"]},
        "程序": {"keywords": ["管辖", "时效", "证据", "再审", "送达"]},
    },
    "cross_rules": [
        {"experts": ["刑事", "程序"], "note": "刑事程序交叉"},
    ],
}


def load_router_config(path: str | None = None) -> Dict[str, Any]:
    cfg_path = Path(path or router_moe_path("zh_CN"))
    if not cfg_path.exists():
        return FALLBACK_ROUTER_CONFIG
    loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        return FALLBACK_ROUTER_CONFIG
    return loaded


class RuleRouter:
    def __init__(self, config_path: str | None = None):
        self.config = load_router_config(config_path)
        self.shards = self._load_shards(self.config)
        self.cross = self._load_cross_rules(self.config)
        self.default_top_k = int(self.config.get("defaults", {}).get("top_k", 2))

    def route(self, fact_texts: List[Any], top_k: int | None = None) -> Dict:
        raw_facts = fact_texts
        texts = [str(text) for text in fact_texts]
        selected_top_k = top_k or self.default_top_k

        scores: Dict[str, int] = {}
        for domain, keywords in self.shards.items():
            score = sum(1 for kw in keywords for text in texts if kw in text)
            if score > 0:
                scores[domain] = score

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        if ranked and len(ranked) > selected_top_k and ranked[selected_top_k - 1][1] == ranked[selected_top_k][1]:
            tie_score = ranked[selected_top_k - 1][1]
            ranked = [(domain, score) for domain, score in ranked if score >= tie_score]
        else:
            ranked = ranked[:selected_top_k]

        selected = [domain for domain, _ in ranked]
        criminal_complexity = {}
        if is_criminal_case(raw_facts):
            if "刑事" not in selected:
                selected.append("刑事")
            criminal_complexity = classify_criminal_complexity(raw_facts).to_dict()

        cross_experts = []
        for a, b, note in self.cross:
            if a in selected and b in selected:
                cross_experts.append({"pair": (a, b), "note": note})

        return {
            "selected_experts": selected,
            "cross_expert_conflicts": cross_experts,
            "all_scores": dict(ranked),
            "criminal_complexity": criminal_complexity,
            "trust_label": self.config.get("defaults", {}).get("trust_label", TrustLabel.ENGINEERING_BASELINE.value),
        }

    @property
    def domain_count(self) -> int:
        return len(self.shards)

    @property
    def cross_count(self) -> int:
        return len(self.cross)

    @staticmethod
    def _load_shards(config: Dict[str, Any]) -> Dict[str, List[str]]:
        shards: Dict[str, List[str]] = {}
        raw = config.get("expert_shards", {})
        if not isinstance(raw, dict):
            return FALLBACK_ROUTER_CONFIG["expert_shards"]
        for domain, spec in raw.items():
            keywords = spec.get("keywords", []) if isinstance(spec, dict) else spec
            shards[str(domain)] = [str(keyword) for keyword in keywords]
        return shards

    @staticmethod
    def _load_cross_rules(config: Dict[str, Any]) -> List[Tuple[str, str, str]]:
        result: List[Tuple[str, str, str]] = []
        for item in config.get("cross_rules", []):
            if not isinstance(item, dict):
                continue
            experts = item.get("experts", [])
            if len(experts) != 2:
                continue
            result.append((str(experts[0]), str(experts[1]), str(item.get("note", ""))))
        return result
