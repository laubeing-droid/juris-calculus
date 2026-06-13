#!/usr/bin/env python3
"""Export typed IR, DACL graphs, and relevance fixtures into JSONL training corpora."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.dacl_graph import build_dacl_graph
from compiler_core.types import LegalRule


def export_rules_as_jsonl(rule_paths: List[str | Path], out: str | Path, split_train: float = 0.8, split_dev: float = 0.1, split_test: float = 0.1, seed: int = 42, split_mode: str = 'random', split_date: str = '2024-01-01') -> Dict[str, Any]:
    all_items: List[Dict[str, Any]] = []
    for rp in rule_paths:
        data = yaml.safe_load(Path(rp).read_text(encoding="utf-8")) or {}
        raw_rules = data.get("rules", []) if isinstance(data, dict) else []
        for rule in raw_rules:
            if isinstance(rule, dict):
                rid = str(rule.get('id',''))
                valid_from = str(rule.get('valid_from',''))
                premise_sig = hashlib.sha256('|'.join(sorted(rule.get('premise_atoms',[]))).encode()).hexdigest()[:8]
                exception_sig = hashlib.sha256('|'.join(sorted(rule.get('exception_chain',[]))).encode()).hexdigest()[:8]
                split_tag = ''
                if split_mode == 'case': split_tag = f'case_head:{rule.get("head_claim","")[:20]}'
                elif split_mode == 'rule': split_tag = f'rule_prefix:{rid[:2]}'
                elif split_mode == 'structure': split_tag = f'struct:{premise_sig}_{exception_sig}'
                elif split_mode == 'counterfactual': split_tag = f'cf_premise:{premise_sig}'
                elif split_mode == 'temporal': split_tag = 'pre_threshold' if valid_from < split_date else 'post_threshold'
                digest = hashlib.sha256(rule.get("id", "").encode()).hexdigest()[:12]
                all_items.append({
                    "id": rule.get("id", ""),
                    "split_digest": digest,
                    "premise_atoms": rule.get("premise_atoms", []),
                    "head_claim": rule.get("head_claim", ""),
                    "exception_chain": rule.get("exception_chain", []),
                    "attacks": rule.get("attacks", []),
                    "priority_over": rule.get("priority_over", []),
                    "source_anchor": rule.get("source_anchor", ""),
                    "jurisdiction": rule.get("jurisdiction", ""),
                    "authority_rank": rule.get("authority_rank", ""),
                    "valid_from": rule.get("valid_from", ""),
                    "valid_to": rule.get("valid_to", ""),
                })
    rng = random.Random(seed)
    rng.shuffle(all_items)
    total = len(all_items)
    train_end = int(total * split_train)
    dev_end = train_end + int(total * split_dev)
    splits = {"train": all_items[:train_end], "dev": all_items[train_end:dev_end], "test": all_items[dev_end:]}
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    for split_name, items in splits.items():
        split_path = out_path.parent / f"{out_path.stem}_{split_name}.jsonl"
        split_path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items), encoding="utf-8")
    return {
        "total_items": total,
        "splits": {name: len(items) for name, items in splits.items()},
        "out": str(out_path.parent),
        "dataset_hash": hashlib.sha256(json.dumps(all_items, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "status": "PASS",
    }


def generate_model_card(model_id: str, model_version: str, task: str, dataset_hash: str, eval_metrics: Dict[str, float] | None = None) -> Dict[str, Any]:
    return {
        "model_id": model_id,
        "model_version": model_version,
        "task": task,
        "training_data_hash": dataset_hash,
        "allowed_outputs": ["candidate_claim", "candidate_rule", "source_span", "confidence", "uncertainty"],
        "promotion_status_suggestion": "SHADOW_ONLY",
        "evaluation_metrics": eval_metrics or {},
        "limitations": ["shadow_only — no direct legal conclusion authority", "requires source anchor validation", "must pass promotion gate before FINAL_AUTOMATED"],
        "audit_timestamp": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export training corpus from rule YAML files.")
    parser.add_argument("rule_paths", nargs="+")
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-card", action="store_true")
    parser.add_argument("--model-id", default="corpus-baseline")
    parser.add_argument("--model-version", default="0.1.0")
    parser.add_argument("--task", default="domain_routing")
    args = parser.parse_args()
    report = export_rules_as_jsonl(args.rule_paths, out=args.out, seed=args.seed)
    if args.model_card:
        card = generate_model_card(args.model_id, args.model_version, args.task, report["dataset_hash"])
        card_path = Path(args.out).parent / "model_card.json"
        card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
        report["model_card"] = str(card_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
