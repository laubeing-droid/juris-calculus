#!/usr/bin/env python3
"""Automated claim -> verification -> certificate pipeline.

Takes a case, runs the full litigation pipeline, and generates:
  - claim queue (what needs to be proved/refuted)
  - verification queue (what certificates need checking)
  - certificate queue (what certificates to emit)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from compiler_core.argumentation import grounded_extension
from compiler_core.canonical_serialization import content_id
from compiler_core.certificate_checker import (
    GroundedINCertificate,
    OUTCertificate,
    UNDECCertificate,
)
from compiler_core.evaluator import FixpointEvaluator
from compiler_core.domain_config import DomainConfig
from compiler_core.litigation_engineering import generate_certificate
from compiler_core.types import IRState, LegalDomain, LegalFact, LegalRule


@dataclass
class QueueItem:
    claim_id: str
    status: str
    queue_type: str  # claim | verification | certificate
    priority: int  # 1 = highest
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    case_id: str
    claim_queue: List[QueueItem] = field(default_factory=list)
    verification_queue: List[QueueItem] = field(default_factory=list)
    certificate_queue: List[QueueItem] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


def run_automated_pipeline(
    rules: list[LegalRule],
    facts: list[str],
    case_id: str = "",
) -> PipelineResult:
    """Run the full automated claim -> verification -> certificate pipeline."""
    evaluator = FixpointEvaluator(rules, DomainConfig(domain=LegalDomain.CIVIL))
    state = IRState(
        facts={f: LegalFact(id=f, description=f) for f in facts},
        domain=LegalDomain.CIVIL,
    )
    state.max_iterations = 50
    horn_state = evaluator.evaluate_horn(state)

    claims = [{"id": cid} for cid in sorted(horn_state.claims.keys())]
    attacks = _build_attacks(rules, claims)

    ge_result = grounded_extension(claims, attacks)
    accepted = set(ge_result["accepted"])
    rejected = set(ge_result["rejected"])
    undecided = set(ge_result["undecided"])

    result = PipelineResult(case_id=case_id or content_id("pipeline", {"facts": sorted(facts)}))

    # Build claim queue: what needs resolution
    priority = 1
    for claim in claims:
        cid = claim["id"]
        if cid in undecided:
            result.claim_queue.append(QueueItem(
                claim_id=cid, status="UNDECIDED", queue_type="claim", priority=priority,
            ))
            priority += 1

    # Build verification queue: what certificates need independent verification
    for claim in claims:
        cid = claim["id"]
        cert = generate_certificate(cid, claims, attacks, ge_result)
        if cert:
            result.verification_queue.append(QueueItem(
                claim_id=cid, status=cert.label, queue_type="verification", priority=1,
                metadata={"label": cert.label, "verifiable": cert.verifiable, "proof_depth": cert.proof_depth},
            ))

    # Build certificate queue: emit verifiable certificates
    for claim in claims:
        cid = claim["id"]
        if cid in accepted:
            result.certificate_queue.append(QueueItem(
                claim_id=cid, status="PROVED", queue_type="certificate", priority=1,
                metadata={"cert_type": "IN"},
            ))
        elif cid in rejected:
            result.certificate_queue.append(QueueItem(
                claim_id=cid, status="REFUTED", queue_type="certificate", priority=2,
                metadata={"cert_type": "OUT"},
            ))
        else:
            result.certificate_queue.append(QueueItem(
                claim_id=cid, status="UNDECIDED", queue_type="certificate", priority=3,
                metadata={"cert_type": "UNDEC"},
            ))

    result.summary = {
        "total_claims": len(claims),
        "proved": len(accepted),
        "refuted": len(rejected),
        "undecided": len(undecided),
        "claim_queue_size": len(result.claim_queue),
        "verification_queue_size": len(result.verification_queue),
        "certificate_queue_size": len(result.certificate_queue),
        "truncated": horn_state.horn_truncated or ge_result.get("truncated", False),
    }

    return result


def _build_attacks(rules: list[LegalRule], claims: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Build attack edges from rule metadata."""
    present = {c["id"] for c in claims}
    rule_by_id = {r.id: r for r in rules}
    attacks: list[tuple[str, str]] = []
    for rule in rules:
        if rule.head_claim not in present:
            continue
        for attacked in rule.attacks:
            target = rule_by_id.get(attacked)
            if target and target.head_claim in present:
                attacks.append((rule.head_claim, target.head_claim))
        for priority_rule in rule.priority_over:
            target = rule_by_id.get(priority_rule)
            if target and target.head_claim in present:
                attacks.append((rule.head_claim, target.head_claim))
    return attacks
