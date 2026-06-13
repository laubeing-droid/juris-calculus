#!/usr/bin/env python3
"""Semantic acceptance gates for isolated third-party LLM batches."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.llm_batch_contract import validate_candidates


def accept_ir_migration_repair_batch(batch_root: str | Path) -> Dict[str, Any]:
    root = Path(batch_root)
    requests_path = root / "input" / "requests.jsonl"
    candidates_path = root / "output" / "candidates.jsonl"
    if not requests_path.exists():
        raise FileNotFoundError(f"missing requests file: {requests_path}")
    if not candidates_path.exists():
        raise FileNotFoundError(f"missing candidates file: {candidates_path}")

    batch_id = root.name
    contract_report = validate_candidates(candidates_path, batch_id=batch_id)
    requests = _load_requests(requests_path)
    candidates = _load_jsonl(candidates_path)
    records: List[Dict[str, Any]] = []
    accepted: List[Dict[str, Any]] = []
    repairable: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []

    seen_request_ids: set[str] = set()
    for candidate in candidates:
        decision, issues = _validate_ir_migration_candidate(candidate, requests)
        record = {
            "candidate_id": candidate.get("candidate_id", ""),
            "request_id": candidate.get("request_id", ""),
            "decision": decision,
            "issues": issues,
        }
        records.append(record)
        if decision == "ACCEPTED_CANDIDATE":
            accepted.append(record)
        elif decision == "REPAIRABLE":
            repairable.append(record)
        else:
            blocked.append(record)
        seen_request_ids.add(str(candidate.get("request_id", "")))

    for request_id in sorted(set(requests) - seen_request_ids):
        repairable.append({
            "candidate_id": "",
            "request_id": request_id,
            "decision": "REPAIRABLE",
            "issues": ["MISSING_CANDIDATE_FOR_REQUEST"],
        })

    report = {
        "batch_id": batch_id,
        "batch_root": str(root),
        "contract_status": contract_report["status"],
        "request_count": len(requests),
        "candidate_count": len(candidates),
        "accepted_count": len(accepted),
        "repairable_count": len(repairable),
        "blocked_count": len(blocked),
        "status": _overall_status(contract_report, accepted, repairable, blocked),
        "records": records,
        "accepted": accepted,
        "repairable": repairable,
        "blocked": blocked,
    }
    notes = root / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "codex_acceptance_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if repairable:
        _write_repair_requests(root, candidates, requests, repairable)
    return report


def _validate_ir_migration_candidate(candidate: Dict[str, Any], requests: Dict[str, Dict[str, Any]]) -> Tuple[str, List[str]]:
    issues: List[str] = []
    request_id = str(candidate.get("request_id", ""))
    request = requests.get(request_id)
    if request is None:
        return "BLOCKED", ["UNKNOWN_REQUEST_ID"]
    output = candidate.get("output", {})
    patch = output.get("proposed_patch", {}) if isinstance(output, dict) else {}
    if candidate.get("status") != "candidate":
        issues.append("CANDIDATE_STATUS_REQUIRED")
    if candidate.get("task") != "ir_migration_repair":
        issues.append("TASK_MISMATCH")
    if candidate.get("source_ref") != request["input"].get("rule_id"):
        issues.append("SOURCE_REF_MISMATCH")
    if candidate.get("source_span") != request["input"].get("textual_exception"):
        issues.append("SOURCE_SPAN_MUST_EQUAL_TEXTUAL_EXCEPTION")
    if patch.get("parent_rule_id") != request["input"].get("rule_id"):
        issues.append("PARENT_RULE_MISMATCH")
    if patch.get("trigger") != request["input"].get("textual_exception"):
        issues.append("TRIGGER_MUST_EQUAL_TEXTUAL_EXCEPTION")
    if not patch.get("exception_rule_id_suggestion"):
        issues.append("EXCEPTION_RULE_ID_REQUIRED")
    if patch.get("suggested_rule_type") not in {"exception", "scoping_rule"}:
        issues.append("UNSUPPORTED_SUGGESTED_RULE_TYPE")
    if not isinstance(candidate.get("known_limitations"), list) or not candidate.get("known_limitations"):
        issues.append("LIMITATIONS_REQUIRED")
    confidence = candidate.get("confidence")
    if not isinstance(confidence, (int, float)) or confidence < 0.5:
        issues.append("CONFIDENCE_TOO_LOW")

    hard = [
        issue for issue in issues
        if issue in {
            "UNKNOWN_REQUEST_ID",
            "TASK_MISMATCH",
            "SOURCE_REF_MISMATCH",
            "SOURCE_SPAN_MUST_EQUAL_TEXTUAL_EXCEPTION",
            "PARENT_RULE_MISMATCH",
            "TRIGGER_MUST_EQUAL_TEXTUAL_EXCEPTION",
            "EXCEPTION_RULE_ID_REQUIRED",
        }
    ]
    if hard:
        return "REPAIRABLE", issues
    return "ACCEPTED_CANDIDATE" if not issues else "REPAIRABLE", issues


def _write_repair_requests(
    root: Path,
    candidates: List[Dict[str, Any]],
    requests: Dict[str, Dict[str, Any]],
    repairable: List[Dict[str, Any]],
) -> None:
    candidate_by_request = {str(candidate.get("request_id", "")): candidate for candidate in candidates}
    lines: List[str] = []
    for item in repairable:
        request_id = item["request_id"]
        original = requests.get(request_id, {})
        candidate = candidate_by_request.get(request_id, {})
        payload = {
            "request_id": f"REPAIR-{request_id}",
            "batch_id": root.name,
            "task": "ir_migration_repair",
            "status": "needs_context",
            "input": {
                "original_request": original,
                "candidate": candidate,
                "validator_issues": item["issues"],
            },
            "constraints": {
                "repo_write_allowed": False,
                "must_return_jsonl": True,
                "allowed_statuses": ["candidate", "needs_context", "unsupported", "abstain"],
            },
        }
        lines.append(json.dumps(payload, ensure_ascii=False))
    repair_dir = root / "repair"
    repair_dir.mkdir(parents=True, exist_ok=True)
    (repair_dir / "validator_repair_requests.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _overall_status(
    contract_report: Dict[str, Any],
    accepted: List[Dict[str, Any]],
    repairable: List[Dict[str, Any]],
    blocked: List[Dict[str, Any]],
) -> str:
    if contract_report["status"] != "PASS" or blocked:
        return "BLOCKED"
    if repairable:
        return "REPAIRABLE"
    if accepted:
        return "ACCEPTED"
    return "BLOCKED"


def _load_requests(path: Path) -> Dict[str, Dict[str, Any]]:
    requests = {}
    for item in _load_jsonl(path):
        request_id = str(item.get("request_id", ""))
        if request_id:
            requests[request_id] = item
    return requests


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(json.loads(line))
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Accept or repair isolated third-party LLM batch outputs.")
    parser.add_argument("batch_root")
    parser.add_argument("--task", default="ir_migration_repair", choices=["ir_migration_repair"])
    args = parser.parse_args()
    report = accept_ir_migration_repair_batch(args.batch_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ACCEPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
