"""Semantic compiler contract: provider-agnostic interface for LLM->candidate IR."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CompilerTask(str, Enum):
    FACT_EXTRACTION = "fact_extraction"
    RULE_EXTRACTION = "rule_extraction"
    ONTOLOGY_MAPPING = "ontology_mapping"
    SOURCE_SPAN_ALIGNMENT = "source_span_alignment"


class CandidateStatus(str, Enum):
    CANDIDATE = "candidate"
    NEEDS_CONTEXT = "needs_context"
    UNSUPPORTED = "unsupported"
    ABSTAIN = "abstain"


@dataclass
class CompilerRequest:
    request_id: str
    task: CompilerTask
    text: str
    jurisdiction: str
    source_citation: str = ""
    target_ontology: List[str] = field(default_factory=list)
    extraction_mode: str = "strict"
    constraints: Dict[str, Any] = field(default_factory=dict)
    input_hash: str = ""


@dataclass
class CandidateFact:
    fact_id: str
    description: str
    source_span: str = ""
    source_span_start: Optional[int] = None
    source_span_end: Optional[int] = None
    formalizable: float = 1.0
    confidence: float = 0.7


@dataclass
class CandidateRule:
    rule_id_suggestion: str
    premises: List[str] = field(default_factory=list)
    conclusion: str = ""
    exceptions: List[str] = field(default_factory=list)
    source_span: str = ""
    source_span_start: Optional[int] = None
    source_span_end: Optional[int] = None
    valid_from: str = ""
    valid_to: str = ""
    authority_rank: str = ""
    confidence: float = 0.7
    rationale: str = ""


@dataclass
class CompilerResponse:
    request_id: str
    status: CandidateStatus
    facts: List[CandidateFact] = field(default_factory=list)
    rules: List[CandidateRule] = field(default_factory=list)
    jurisdiction: str = ""
    known_limitations: List[str] = field(default_factory=list)
    model: Dict[str, str] = field(default_factory=dict)
    input_hash: str = ""


@dataclass
class CompilerContract:
    provider: str
    model_id: str
    max_input_chars: int = 16000
    requires_source_span: bool = True
    output_must_include_uncertainty: bool = True
    candidate_only: bool = True


def validate_response(response: CompilerResponse) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    if response.status == CandidateStatus.CANDIDATE and not response.facts and not response.rules:
        findings.append({"request_id": response.request_id, "issue": "CANDIDATE_WITHOUT_OUTPUT"})
    if not response.request_id:
        findings.append({"request_id": response.request_id, "issue": "MISSING_REQUEST_ID"})
    for fact in response.facts:
        if not fact.fact_id.strip():
            findings.append({"request_id": response.request_id, "fact_description": fact.description, "issue": "FACT_MISSING_ID"})
    for rule in response.rules:
        if not rule.rule_id_suggestion.strip():
            findings.append({"request_id": response.request_id, "rule_conclusion": rule.conclusion, "issue": "RULE_MISSING_ID"})
        if not rule.conclusion.strip():
            findings.append({"request_id": response.request_id, "rule_id": rule.rule_id_suggestion, "issue": "RULE_MISSING_CONCLUSION"})
    blocking = [f for f in findings if "MISSING" in f["issue"]]
    return {
        "request_id": response.request_id,
        "status": response.status.value,
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "contract_status": "PASS" if not blocking else "FAIL",
        "findings": findings,
    }
