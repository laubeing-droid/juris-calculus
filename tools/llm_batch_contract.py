#!/usr/bin/env python3
"""Create and validate isolated third-party LLM batch directories."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


BATCH_ROOT = Path(os.environ.get("JC_LLM_BATCH_ROOT", ".llm_batches"))
ALLOWED_TASKS = {
    "rule_extraction",
    "ir_migration_repair",
    "relevance_case_generation",
    "source_span_alignment",
    "ontology_mapping",
    "explanation_rewrite",
    "model_card_draft",
}
ALLOWED_STATUSES = {"candidate", "needs_context", "unsupported", "abstain"}
FORBIDDEN_GOVERNANCE_STATES = {
    "IMPORTED",
    "VALIDATED",
    "REPAIRABLE",
    "BLOCKED",
    "SHADOW_ONLY",
    "PROMOTABLE",
    "FINAL_AUTOMATED",
    "REVOKED",
}
REQUIRED_CANDIDATE_FIELDS = {
    "candidate_id",
    "batch_id",
    "request_id",
    "task",
    "status",
    "jurisdiction",
    "domain",
    "source_ref",
    "source_span",
    "source_span_start",
    "source_span_end",
    "input_hash",
    "output",
    "confidence",
    "known_limitations",
    "model",
}


def create_batch(batch_id: str, tasks: Iterable[str], out_root: str | Path = BATCH_ROOT) -> Dict[str, Any]:
    root = _batch_root(batch_id, out_root)
    for child in ("input", "input/source_texts", "input/schemas", "raw", "output", "repair", "notes"):
        (root / child).mkdir(parents=True, exist_ok=True)
    requests = []
    for index, task in enumerate(tasks, start=1):
        if task not in ALLOWED_TASKS:
            raise ValueError(f"unsupported task: {task}")
        request = {
            "request_id": f"{batch_id}-REQ-{index:04d}",
            "batch_id": batch_id,
            "task": task,
            "input": {},
            "constraints": {
                "write_only_under": str(root),
                "repo_write_allowed": False,
                "must_return_jsonl": True,
                "allowed_statuses": sorted(ALLOWED_STATUSES),
            },
            "input_hash": _hash_json({"batch_id": batch_id, "task": task, "index": index}),
        }
        requests.append(request)
    requests_path = root / "input" / "requests.jsonl"
    requests_path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in requests), encoding="utf-8")
    manifest = {
        "batch_id": batch_id,
        "batch_root": str(root),
        "request_count": len(requests),
        "allowed_write_dirs": [str(root / name) for name in ("raw", "output", "repair", "notes")],
        "repo_write_allowed": False,
    }
    (root / "input" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def validate_candidates(path: str | Path, batch_id: str | None = None) -> Dict[str, Any]:
    candidate_path = Path(path)
    findings: List[Dict[str, Any]] = []
    count = 0
    seen_ids: set[str] = set()
    for line_no, raw_line in enumerate(candidate_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        count += 1
        try:
            candidate = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            findings.append(_finding(line_no, "<json>", f"JSON_DECODE_ERROR:{exc}", True))
            continue
        cid = str(candidate.get("candidate_id", ""))
        missing = sorted(REQUIRED_CANDIDATE_FIELDS - set(candidate))
        for field in missing:
            findings.append(_finding(line_no, cid or "<missing>", f"MISSING_FIELD:{field}", True))
        if cid in seen_ids:
            findings.append(_finding(line_no, cid, "DUPLICATE_CANDIDATE_ID", True))
        seen_ids.add(cid)
        if batch_id and candidate.get("batch_id") != batch_id:
            findings.append(_finding(line_no, cid, "BATCH_ID_MISMATCH", True))
        task = candidate.get("task")
        if task not in ALLOWED_TASKS:
            findings.append(_finding(line_no, cid, f"UNKNOWN_TASK:{task}", True))
        status = candidate.get("status")
        if status not in ALLOWED_STATUSES:
            findings.append(_finding(line_no, cid, f"INVALID_STATUS:{status}", True))
        if status in FORBIDDEN_GOVERNANCE_STATES:
            findings.append(_finding(line_no, cid, f"FORBIDDEN_GOVERNANCE_STATE:{status}", True))
        confidence = candidate.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            findings.append(_finding(line_no, cid, "INVALID_CONFIDENCE", True))
        if not isinstance(candidate.get("known_limitations"), list):
            findings.append(_finding(line_no, cid, "KNOWN_LIMITATIONS_NOT_LIST", True))
        if not isinstance(candidate.get("output"), dict):
            findings.append(_finding(line_no, cid, "OUTPUT_NOT_OBJECT", True))
        if not isinstance(candidate.get("model"), dict):
            findings.append(_finding(line_no, cid, "MODEL_NOT_OBJECT", True))
        for forbidden in ("accepted", "validated", "promoted", "final", "legal_truth"):
            if forbidden in json.dumps(candidate, ensure_ascii=False).lower():
                findings.append(_finding(line_no, cid, f"FORBIDDEN_CLAIM:{forbidden}", True))
    blocking = [item for item in findings if item["blocking_issue"]]
    return {
        "path": str(candidate_path),
        "candidate_count": count,
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "status": "PASS" if count > 0 and not blocking else "FAIL",
        "findings": findings,
    }


def _finding(line_no: int, candidate_id: str, issue: str, blocking: bool) -> Dict[str, Any]:
    return {
        "line": line_no,
        "candidate_id": candidate_id,
        "issue": issue,
        "blocking_issue": blocking,
        "repair_instruction": "Return a schema-valid candidate JSONL line or abstain.",
    }


def _batch_root(batch_id: str, out_root: str | Path) -> Path:
    if not batch_id or any(ch in batch_id for ch in "\\/:*?\"<>|"):
        raise ValueError("batch_id must be a filesystem-safe name")
    return Path(out_root) / batch_id


def _hash_json(data: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Third-party LLM batch contract utility.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    create = sub.add_parser("create")
    create.add_argument("batch_id")
    create.add_argument("--task", action="append", required=True, choices=sorted(ALLOWED_TASKS))
    create.add_argument("--root", default=str(BATCH_ROOT))
    validate = sub.add_parser("validate")
    validate.add_argument("path")
    validate.add_argument("--batch-id")
    args = parser.parse_args()
    if args.cmd == "create":
        result = create_batch(args.batch_id, args.task, args.root)
        result["status"] = "PASS"
    else:
        result = validate_candidates(args.path, args.batch_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
