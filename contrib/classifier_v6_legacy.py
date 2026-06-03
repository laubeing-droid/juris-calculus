#!/usr/bin/env python3
"""V6: 证据载体A/B/C机械分类器 + 源锚定验证 + ATTEMPTED_HIJACK检测"""
import re
import yaml
import os
from typing import Dict, Tuple


class EvidenceClassifier:
    """纯机械证据分类器。严禁大模型调用。基于正则表达式的形式特征匹配。"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__), "..", "configs", "zh_CN", "classifier_rules.yaml"
            )
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.classifiers = self.config.get("evidence_classifiers", {})

    def classify(self, raw_text: str) -> str:
        """
        对原始文本进行A/B/C分级。
        返回 "A", "B", 或 "C"。
        """
        for level in ["A_HARD_EVIDENCE", "B_ALTERNATIVE_EVIDENCE"]:
            rules = self.classifiers.get(level, {}).get("rules", [])
            for rule in rules:
                pattern = rule.get("pattern", "")
                match_type = rule.get("match_type", "regex")
                if match_type == "catch_all":
                    continue
                try:
                    if re.search(pattern, raw_text, re.IGNORECASE):
                        return level[0]  # "A" or "B"
                except re.error:
                    continue
        return "C"  # default: weak signal

    def get_confidence_boost(self, carrier_level: str) -> float:
        """返回该载体级别的置信度调整值。"""
        for key, val in self.classifiers.items():
            if key.startswith(carrier_level):
                return val.get("confidence_boost", 0.0)
        return 0.0


# === 源锚定验证 (Source-Anchored Verification) ===

def levenshtein_distance(s1: str, s2: str) -> int:
    """编辑距离计算。"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def verify_raw_text(raw_text: str, full_document: str, context_prefix: str = "",
                    context_suffix: str = "", page_hint: int = 0) -> Tuple[str, str]:
    """
    V6 源锚定验证管道。
    返回 (status, detail):
      - ("OK", ""): 验证通过
      - ("VERBATIM_MISMATCH", detail): 编辑距离>3
      - ("NOT_FOUND", detail): 文本在文档中未找到
    """
    # Step 1: 绝对匹配
    if raw_text in full_document:
        return "OK", ""

    # Step 2: 前缀+核心+后缀三明治搜索
    search_window = (context_prefix or "") + raw_text + (context_suffix or "")
    if search_window in full_document:
        return "OK", ""

    # Step 3: 前缀定位后滑动窗口
    if context_prefix and context_prefix in full_document:
        prefix_positions = [m.start() for m in re.finditer(re.escape(context_prefix), full_document)]
        for pos in prefix_positions:
            end = min(pos + len(search_window) + 20, len(full_document))
            window = full_document[pos:end]
            if raw_text in window:
                return "OK", ""
            # 编辑距离容差
            for offset in range(len(window) - len(raw_text) + 1):
                candidate = window[offset:offset + len(raw_text)]
                dist = levenshtein_distance(raw_text, candidate)
                if dist <= 3:
                    return "OK", f"levenshtein={dist}"

    # Step 4: N-gram 盲搜兜底
    words = raw_text.split()
    if len(words) >= 3:
        trigrams = [" ".join(words[i:i+3]) for i in range(len(words)-2)]
        matched = sum(1 for tg in trigrams if tg in full_document)
        if matched / len(trigrams) >= 0.8:
            return "OK", "ngram_match"

    return "VERBATIM_MISMATCH", "text not found in source document"


# === ATTEMPTED_HIJACK 检测 ===

def detect_label_hijacking(fact_candidate: dict, classifier: EvidenceClassifier) -> bool:
    """
    检测大模型是否试图篡改carrier_level。
    如果事实候选中包含carrier_level字段且与机械分类不一致，标记为ATTEMPTED_HIJACK。
    """
    if "carrier_level" not in fact_candidate:
        return False
    declared_level = fact_candidate["carrier_level"]
    raw_text = fact_candidate.get("raw_text", "")
    mechanical_level = classifier.classify(raw_text) if raw_text else "C"
    if declared_level != mechanical_level:
        fact_candidate["taint_status"] = "ATTEMPTED_HIJACK"
        fact_candidate["mechanical_carrier_level"] = mechanical_level
        return True
    return False
