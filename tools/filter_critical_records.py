#!/usr/bin/env python3
"""
tools/filter_critical_records.py — 饱和攻击高危记录提取器
══════════════════════════════════════════════════════════
从 long_tail_collision_matrix.json 中提取最脆弱的50条记录，
按三因子聚类: 管辖权突破 / 逻辑冲突 / 行动熔断

用法:
  python tools/filter_critical_records.py
  python tools/filter_critical_records.py --limit 50 --focus PRC
══════════════════════════════════════════════════════════
"""

import json
import sys
from pathlib import Path
from typing import List, Dict
from collections import Counter

BASE = Path(__file__).resolve().parents[1]


def load_collision_data(path: str = None) -> Dict:
    if path is None:
        path = BASE / "configs" / "prc_us_alignment" / "long_tail_collision_matrix.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_critical_records(data: Dict, limit: int = 50, focus: str = None) -> List[Dict]:
    """
    三因子提取:
      A (Jurisdiction Breach): COLLISION + PRC CBL 触发
      B (Logic Collision):     COLLISION + 低置信度
      C (Action Suppression):  ASYMMETRY + SUPPRESSED 标记
    """
    collisions = data.get("collisions", [])
    asymmetries = data.get("asymmetries", [])

    factor_a = []  # 管辖权突破
    factor_b = []  # 逻辑冲突
    factor_c = []  # 行动熔断

    for c in collisions:
        overrides = c.get("prc_overrides", {})
        fv = overrides.get("force_void", [])
        fs = overrides.get("force_suppress", [])

        prc_hit = any("PEN_" in r or "CN_SPEC_" in r or "BLK_" in r for r in fv + fs)

        if prc_hit:
            factor_a.append({"factor": "A_Jurisdiction_Breach", **c})

        if c.get("hk_state") == "SUPPRESSED" or c.get("us_state") == "SUPPRESSED":
            factor_c.append({"factor": "C_Action_Suppression", **c})

    for a in asymmetries:
        overrides = a.get("prc_overrides", {})
        mo = overrides.get("mapping_override", [])
        if mo:
            factor_c.append({"factor": "C_Action_Suppression_ASYMM", **a})

    # 合并去重 + 排序 (A > C > B 优先级)
    seen_terms = set()
    critical = []

    for pool in [factor_a, factor_c, factor_b]:
        for rec in pool:
            term_key = rec.get("term", "").lower()
            if term_key not in seen_terms:
                seen_terms.add(term_key)
                critical.append(rec)
                if len(critical) >= limit:
                    break
        if len(critical) >= limit:
            break

    # PRC focus: 只保留 PRC 相关
    if focus == "PRC":
        critical = [r for r in critical if _is_prc_relevant(r)]

    return critical[:limit]


def _is_prc_relevant(record: Dict) -> bool:
    overrides = record.get("prc_overrides", {})
    fv = overrides.get("force_void", [])
    fs = overrides.get("force_suppress", [])
    mo = overrides.get("mapping_override", [])
    all_rules = fv + fs + mo
    return any(
        "PEN_" in r or "CN_SPEC_" in r or "BLK_" in r or "OVR_" in r
        for r in all_rules
    )


def cluster_records(records: List[Dict]) -> Dict:
    """按 PRC 阻断规则聚类"""
    clusters = Counter()
    for r in records:
        overrides = r.get("prc_overrides", {})
        for rule in overrides.get("force_void", []) + overrides.get("force_suppress", []):
            clusters[rule] += 1
        for rule in overrides.get("mapping_override", []):
            clusters[f"MAPPING:{rule}"] += 1
    return dict(clusters.most_common(20))


def generate_audit_report(records: List[Dict], clusters: Dict, output_path: str = None):
    """生成五维审计检查表"""
    lines = [
        "# 高危路径逻辑审计检查表",
        f"## 记录数: {len(records)} | 逻辑收敛点: {len(clusters)}",
        "",
        "## 一、 逻辑收敛点聚类",
        "| 阻断规则 | 触发次数 |",
        "|----------|----------|",
    ]
    for rule, count in clusters.items():
        lines.append(f"| {rule} | {count} |")

    lines += [
        "",
        "## 二、 高危记录明细 (五维审计)",
        "",
        "按以下五维度逐条审计:",
        "1. 算子响应完整性 — ASYMMETRY时是否有FORCE_VOID未被唤起?",
        "2. 主权边界锚定 — 是否显式标记is_prc_sovereign_boundary?",
        "3. 证据链路鲁棒性 — 低置信度根因是动议复杂还是证据不足?",
        "4. 对抗战术一致性 — Action是否过度牺牲胜率?",
        "5. 协议版本溯源 — source_hash是否最新?",
        "",
        "| # | 术语 | 因子 | 触发的PRC规则 | 审计结论 | 修复动作 |",
        "|---|------|------|-------------|----------|----------|",
    ]

    for i, rec in enumerate(records, 1):
        overrides = rec.get("prc_overrides", {})
        rules = overrides.get("force_void", []) + overrides.get("force_suppress", []) + overrides.get("mapping_override", [])
        factor = rec.get("factor", "?")
        term = rec.get("term", "?")[:50]
        lines.append(f"| {i} | {term} | {factor} | {', '.join(rules[:3])} | | |")

    lines += [
        "",
        "## 三、 审计产出 → 补丁工厂",
        "- 逻辑缺失 → blocking_rules.yaml 新增规则",
        "- 数据缺失 → Legal-CN 技能补充案例索引",
        "- 推演路径错误 → OperatorRegistry 更新执行函数",
    ]

    report = "\n".join(lines)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)

    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="提取高危饱和攻击记录")
    parser.add_argument("--limit", "-n", type=int, default=50)
    parser.add_argument("--focus", "-f", type=str, default=None, choices=["PRC", "HK", None])
    parser.add_argument("--output", "-o", type=str, default=None)
    parser.add_argument("--input", "-i", type=str, default=None)
    args = parser.parse_args()

    data = load_collision_data(args.input)
    records = extract_critical_records(data, args.limit, args.focus)
    clusters = cluster_records(records)

    print(f"提取 {len(records)} 条高危记录, {len(clusters)} 个逻辑收敛点")
    print(f"聚类:")
    for rule, cnt in list(clusters.items())[:10]:
        print(f"  [{cnt}] {rule}")

    out = args.output or str(BASE / "reports" / "critical_audit_checklist.md")
    report = generate_audit_report(records, clusters, out)
    print(f"\n审计检查表 → {out}")


if __name__ == "__main__":
    main()
