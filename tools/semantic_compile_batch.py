#!/usr/bin/env python3
"""Batch semantic compiler for candidate legal rules and facts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.semantic_compiler_contract import (
    CandidateFact, CandidateRule, CandidateStatus,
    CompilerContract, CompilerRequest, CompilerResponse, CompilerTask, validate_response,
)


def mock_compile(request: CompilerRequest, _contract: CompilerContract) -> CompilerResponse:
    return CompilerResponse(
        request_id=request.request_id,
        status=CandidateStatus.CANDIDATE,
        facts=[
            CandidateFact(fact_id=f"{request.request_id}-F1", description="mock fact", source_span=request.text[:50], confidence=0.6),
        ],
        rules=[
            CandidateRule(
                rule_id_suggestion=f"R-{request.request_id}", premises=["mock_premise"], conclusion="mock_claim",
                source_span=request.text[:100], confidence=0.55, rationale="mock extraction",
            ),
        ],
        jurisdiction=request.jurisdiction,
        known_limitations=["mock provider — no real LLM call"],
        model={"provider": "mock", "model_id": "mock/v0", "version": "0.1"},
        input_hash=request.input_hash,
    )


def compile_batch(
    requests_path: str | Path,
    contract: CompilerContract,
    out: str | Path | None = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    req_path = Path(requests_path)
    raw_lines = req_path.read_text(encoding="utf-8").splitlines()
    responses: List[Dict[str, Any]] = []
    findings: List[Dict[str, Any]] = []
    total = 0
    passed = 0

    for line in raw_lines:
        if not line.strip():
            continue
        total += 1
        req_data = json.loads(line)
        request = CompilerRequest(
            request_id=req_data.get("request_id", f"REQ-{total}"),
            task=CompilerTask(req_data.get("task", "fact_extraction")),
            text=req_data.get("text", ""),
            jurisdiction=req_data.get("jurisdiction", ""),
            source_citation=req_data.get("source_citation", ""),
            extraction_mode=req_data.get("extraction_mode", "strict"),
            constraints=req_data.get("constraints", {}),
            input_hash=req_data.get("input_hash", ""),
        )
        if dry_run:
            response = CompilerResponse(request_id=request.request_id, status=CandidateStatus.NEEDS_CONTEXT, input_hash=request.input_hash)
        else:
            response = mock_compile(request, contract)
        validation = validate_response(response)
        responses.append({
            "request_id": response.request_id,
            "status": response.status.value,
            "facts": [{"fact_id": f.fact_id, "description": f.description, "source_span": f.source_span, "confidence": f.confidence} for f in response.facts],
            "rules": [{"rule_id": r.rule_id_suggestion, "conclusion": r.conclusion, "premises": r.premises, "source_span": r.source_span, "confidence": r.confidence} for r in response.rules],
            "limitations": response.known_limitations,
            "model": response.model,
            "validation": validation,
        })
        findings.extend(validation.get("findings", []))
        if validation["contract_status"] == "PASS":
            passed += 1

    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in responses), encoding="utf-8")

    return {
        "request_count": total,
        "response_count": len(responses),
        "passed_count": passed,
        "finding_count": len(findings),
        "status": "PASS" if passed == total else "FAIL",
        "findings": findings,
        "out": str(Path(out).resolve()) if out else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch semantic compiler for candidate legal IR.")
    parser.add_argument("requests")
    parser.add_argument("--out")
    parser.add_argument("--provider", default="mock")
    parser.add_argument("--model-id", default="mock/v0")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    contract = CompilerContract(provider=args.provider, model_id=args.model_id)
    report = compile_batch(args.requests, contract, out=args.out, dry_run=args.dry_run)
    print(json.dumps({k: v for k, v in report.items() if k != "findings"}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
