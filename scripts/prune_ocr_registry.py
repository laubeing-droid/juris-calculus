#!/usr/bin/env python3
"""
种子字典过滤 OCR 概念注册表 — 零 API 调用，纯规则降噪。

算法：
  1. 从规则文件提取所有关键词 → seed_set
  2. OCR 候选词 ↔ 种子集双向包含性检测 → 保留命中词
  3. 词频 + 词长加权评分 → 补入 domain_config.yaml

用法: python scripts/prune_ocr_registry.py
"""
import json, yaml, re
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = Path(os.environ.get("JURIS_RULES_DIR", str(ROOT / "configs" / "zh_CN")))
OCR_CONCEPTS_PATH = ROOT / "configs" / "zh_CN" / "concept_registry_ocr.yaml"
DOMAIN_CONFIG_PATH = ROOT / "configs" / "zh_CN" / "domain_config.yaml"


def extract_seed_set() -> set:
    """从规则文件关键词字段提取种子字典"""
    seed = set()
    for fp in sorted(RULES_DIR.glob("*.json")):
        if fp.name.startswith("_"):
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        for r in data:
            kw = r.get("关键词", [])
            if isinstance(kw, list):
                for k in kw:
                    k = k.strip()
                    if 2 <= len(k) <= 20:
                        seed.add(k)
    return seed


def containment_filter(ocr_candidates: dict, seed_set: set) -> dict:
    """
    包含性检测：OCR 候选词必须包含或被种子词包含才保留。
    例如: seed="违约责任" → OCR="违约责任金" ✅; OCR="合同第十五条" ❌
    """
    passed = {}
    for ocr_word, freq in ocr_candidates.items():
        for seed in seed_set:
            if seed in ocr_word or ocr_word in seed:
                # 加权：命中种子词数量越多越好
                passed[ocr_word] = freq
                break
    return passed


def score_and_sort(passed: dict, seed_set: set) -> list:
    """词频 × 种子命中密度 × 词长加权 → 排序"""
    scored = []
    for word, freq in passed.items():
        lw = len(word)
        if lw < 3 or lw > 25:
            continue  # 太短/太长丢弃
        # 命中种子词数量
        hit_count = sum(1 for s in seed_set if s in word or word in s)
        # 评分 = 词频 × 命中密度 × log(词长)
        import math
        score = freq * hit_count * math.log(lw + 1)
        scored.append((word, score))
    scored.sort(key=lambda x: -x[1])
    return scored


def update_domain_config(new_concepts: list):
    """将精选概念合并到 domain_config.yaml"""
    dc = yaml.safe_load(DOMAIN_CONFIG_PATH.read_text(encoding="utf-8"))
    existing = set(dc.get("concept_registry", []))
    for word in new_concepts:
        existing.add(word)
    dc["concept_registry"] = sorted(existing)
    DOMAIN_CONFIG_PATH.write_text(yaml.dump(dc, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return len(existing)


def main(top_n: int = 50):
    print(f"=== 种子字典过滤 OCR 概念注册表 ===")

    # 1. 提取种子
    seed = extract_seed_set()
    print(f"[1] 种子集: {len(seed)} 个核心词")

    # 2. 读 OCR 候选词 (嵌套在 concepts/ 键下)
    ocr_raw = yaml.safe_load(OCR_CONCEPTS_PATH.read_text(encoding="utf-8")) if OCR_CONCEPTS_PATH.exists() else {}
    if isinstance(ocr_raw, dict) and "concepts" in ocr_raw:
        ocr_items = ocr_raw["concepts"]
        ocr_candidates = {k: v.get("frequency", 1) for k, v in ocr_items.items()}
    else:
        ocr_candidates = {}
    print(f"[2] OCR 候选词: {len(ocr_candidates)} 个")

    # 3. 包含性过滤
    passed = containment_filter(ocr_candidates, seed)
    print(f"[3] 通过过滤: {len(passed)} 个")

    # 4. 评分排序
    scored = score_and_sort(passed, seed)
    print(f"[4] 可供筛选: {len(scored)} 个")

    # 5. 取 Top N 合并
    top_words = [w for w, s in scored[:top_n]]
    print(f"[5] 取 Top {top_n} 个: {top_words[:10]}...")

    total = update_domain_config(top_words)
    print(f"[6] domain_config.yaml: {total} 个概念")

    # 输出摘要
    print(f"\n=== 推荐下一批 ({len(scored) - top_n} 个候选) ===")
    for w, s in scored[top_n:top_n + 20]:
        print(f"  {w} ({s:.0f})")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50, help="合并的概念数量")
    args = ap.parse_args()
    main(args.top)
