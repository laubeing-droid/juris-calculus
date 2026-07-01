#!/usr/bin/env python3
"""Prepare unattended follow-up batches from Codex LLM batch acceptance reports."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.llm_batch_acceptor import accept_ir_migration_repair_batch


def gate_and_prepare_next(batch_root: str | Path, max_round: int = 5) -> Dict[str, Any]:
    root = Path(batch_root)
    report = accept_ir_migration_repair_batch(root)
    result: Dict[str, Any] = {
        "batch_id": root.name,
        "batch_root": str(root),
        "gate_status": report["status"],
        "accepted_count": report["accepted_count"],
        "repairable_count": report["repairable_count"],
        "blocked_count": report["blocked_count"],
        "next_batch_root": None,
        "status": report["status"],
    }
    if report["status"] != "REPAIRABLE":
        return result
    round_no = _next_round_no(root.name)
    if round_no > max_round:
        result["status"] = "BLOCKED"
        result["reason"] = "MAX_REPAIR_ROUNDS_EXCEEDED"
        return result
    repair_requests = root / "repair" / "validator_repair_requests.jsonl"
    if not repair_requests.exists():
        result["status"] = "BLOCKED"
        result["reason"] = "REPAIR_REQUESTS_MISSING"
        return result
    next_root = root.parent / f"{root.name}_R{round_no}"
    _create_repair_batch(root, next_root, repair_requests)
    result["next_batch_root"] = str(next_root)
    result["next_requests"] = str(next_root / "input" / "requests.jsonl")
    result["status"] = "NEXT_BATCH_READY"
    return result


def _create_repair_batch(previous_root: Path, next_root: Path, repair_requests: Path) -> None:
    for child in ("input/source_texts", "input/schemas", "raw", "output", "repair", "notes"):
        (next_root / child).mkdir(parents=True, exist_ok=True)
    requests = _load_jsonl(repair_requests)
    next_batch_id = next_root.name
    normalized: List[Dict[str, Any]] = []
    for index, request in enumerate(requests, start=1):
        item = dict(request)
        item["batch_id"] = next_batch_id
        item["request_id"] = f"{next_batch_id}-REQ-{index:04d}"
        item["status"] = "needs_context"
        normalized.append(item)
    (next_root / "input" / "requests.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in normalized),
        encoding="utf-8",
    )
    work_order = previous_root / "input" / "third_party_llm_work_order.md"
    if work_order.exists():
        shutil.copy2(work_order, next_root / "input" / "third_party_llm_work_order.md")
    manifest = {
        "batch_id": next_batch_id,
        "previous_batch": previous_root.name,
        "batch_root": str(next_root),
        "task": "ir_migration_repair",
        "request_file": str(next_root / "input" / "requests.jsonl"),
        "repo_write_allowed": False,
        "expected_output": str(next_root / "output" / "candidates.jsonl"),
        "repair_output": str(next_root / "repair" / "repair_candidates.jsonl"),
    }
    (next_root / "input" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (next_root / "input" / "START_HERE.md").write_text(_start_here(next_root, previous_root), encoding="utf-8")


def _start_here(next_root: Path, previous_root: Path) -> str:
    return f"""# START HERE

You are processing repair batch: {next_root.name}

Read first:

1. {next_root}\\input\\third_party_llm_work_order.md
2. {next_root}\\input\\manifest.json
3. {next_root}\\input\\requests.jsonl

Previous batch:
{previous_root}

Important:

- Do not read or write the juris-calculus repository checkout.
- Use only files under this batch directory plus embedded request data.
- Write normalized candidates to:
  {next_root}\\output\\candidates.jsonl
- Fix exactly the validator_issues listed in each request.
- If evidence is still insufficient, return 
eeds_context` or `abstain`.
- Output JSONL only.
"""


def _next_round_no(batch_id: str) -> int:
    if "_R" not in batch_id:
        return 1
    suffix = batch_id.rsplit("_R", 1)[-1]
    try:
        return int(suffix) + 1
    except ValueError:
        return 1


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate a batch and prepare the next unattended repair batch.")
    parser.add_argument("batch_root")
    parser.add_argument("--max-round", type=int, default=5)
    args = parser.parse_args()
    result = gate_and_prepare_next(args.batch_root, max_round=args.max_round)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"ACCEPTED", "NEXT_BATCH_READY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
