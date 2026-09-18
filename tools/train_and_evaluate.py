"""Thin training/evaluation entry (03 card §4b; NEURAL/PRED lanes).

Usage:
    python -B tools/train_and_evaluate.py --config <config.json> --output <registered-dir>

Config schema ``jc-train-eval/1``:

- task ``case_outcome``: labeled rows jsonl ({"features": {...}, "label": 0|1,
  optional "groupId"/"dateKey"}) -> real trained checkpoint + held-out
  evaluation under <output>/<event>/.
- task ``rule_export``: rule pack YAML files -> training.export_rules_as_jsonl
  with an effective split mode (random|group|time; unsupported modes are
  rejected, never silently shuffled).

The output directory must sit inside this repository's registered data
roots; the trainer writes only checkpoint/evaluation/split artifacts and
never touches the math source tree or case corpora.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Mapping

from compiler_core.prediction import train_and_save
from compiler_core.training import export_rules_as_jsonl

CONFIG_SCHEMA = "jc-train-eval/1"
SUPPORTED_TASKS = {"case_outcome", "rule_export"}
SUPPORTED_MODES = {"random", "group", "time"}


def _fail(message: str):
    print(f"train_and_evaluate: {message}", file=sys.stderr)
    raise SystemExit(2)


def _split_rows(rows: list[dict[str, Any]], split: Mapping[str, Any], seed: int):
    mode = str(split.get("mode", "random"))
    if mode not in SUPPORTED_MODES:
        _fail(f"unsupported split mode {mode!r}")
    train_frac = float(split.get("train", 0.7))
    dev_frac = float(split.get("dev", 0.15))
    if mode == "time":
        ordered = sorted(rows, key=lambda row: (str(row.get("dateKey") or "9999"), str(row)))
    elif mode == "group":
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault(str(row.get("groupId") or id(row)), []).append(row)
        keys = sorted(groups)
        random.Random(seed).shuffle(keys)
        ordered = [row for key in keys for row in groups[key]]
    else:
        ordered = list(rows)
        random.Random(seed).shuffle(ordered)
    total = len(ordered)
    train_end = int(total * train_frac)
    dev_end = train_end + int(total * dev_frac)
    return {
        "train": ordered[:train_end],
        "dev": ordered[train_end:dev_end],
        "test": ordered[dev_end:],
    }


def _run_case_outcome(config: dict[str, Any], output: Path) -> dict[str, Any]:
    dataset = Path(str(config["dataset"]))
    rows = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        _fail("dataset is empty")
    split = dict(config.get("split") or {})
    split_rows = _split_rows(rows, split, int(split.get("seed", 42)))
    feature_order = sorted(
        {name for row in split_rows["train"] for name in (row.get("features") or {})}
    )
    if not feature_order:
        _fail("no features found in the train split")
    result = train_and_save(
        output,
        event_definition=str(config["target"]["eventDefinition"]),
        rows=rows,
        feature_order=feature_order,
        split_rows=split_rows,
        model_config=dict(config.get("model") or {}),
        data_version=config.get("dataVersion"),
        rule_version=config.get("ruleVersion"),
    )
    splits_dir = output / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)
    for name, split_items in split_rows.items():
        (splits_dir / f"{name}.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in split_items),
            encoding="utf-8",
        )
    return result


def _run_rule_export(config: dict[str, Any], output: Path) -> dict[str, Any]:
    pack_root = Path(str(config["packRoot"]))
    rule_paths = sorted(pack_root.glob("**/*.yaml"))
    if not rule_paths:
        _fail(f"no rule YAML files under {pack_root}")
    split = dict(config.get("split") or {})
    manifest = export_rules_as_jsonl(
        rule_paths,
        output / "rules.jsonl",
        split_train=float(split.get("train", 0.8)),
        split_dev=float(split.get("dev", 0.1)),
        split_test=float(split.get("test", 0.1)),
        seed=int(split.get("seed", 42)),
        split_mode=str(split.get("mode", "random")),
        split_date=str(split.get("date", "2026-01-01")),
    )
    return {"export": manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="jc-train-eval/1 config json")
    parser.add_argument("--output", required=True, help="registered output directory")
    args = parser.parse_args()

    config_path = Path(args.config)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"unreadable config: {exc}")
    if not isinstance(config, dict) or config.get("schema_version") != CONFIG_SCHEMA:
        _fail("config schema_version must be jc-train-eval/1")
    task = str(config.get("task"))
    if task not in SUPPORTED_TASKS:
        _fail(f"unsupported task {task!r}")
    output = Path(args.output)
    if task == "case_outcome":
        result = _run_case_outcome(config, output / str(config["target"]["eventDefinition"]))
    else:
        result = _run_rule_export(config, output)
    print(json.dumps({
        "status": "PASS",
        "task": task,
        "output": str(output),
        "checkpoint": (result.get("checkpoint") or {}).get("checkpoint_id"),
        "evaluation": (result.get("evaluation") or {}).get("test"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
