#!/usr/bin/env python3
"""兼容CLI wrapper；训练导出唯一实现位于compiler_core.training。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from compiler_core.training import export_rules_as_jsonl, generate_model_card


def main() -> int:
    """运行旧参数表的显式离线导出。"""

    parser = argparse.ArgumentParser(description="Export training corpus from rule YAML files.")
    parser.add_argument("rule_paths", nargs="+")
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-card", action="store_true")
    parser.add_argument("--model-id", default="corpus-baseline")
    parser.add_argument("--model-version", default="0.1.0")
    parser.add_argument("--task", default="domain_routing")
    args = parser.parse_args()
    report = export_rules_as_jsonl(args.rule_paths, args.out, seed=args.seed)
    if args.model_card:
        card = generate_model_card(args.model_id, args.model_version, args.task, report["dataset_hash"])
        card_path = Path(args.out).parent / "model_card.json"
        card_path.write_text(json.dumps(card, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        report["model_card"] = card_path.name
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
