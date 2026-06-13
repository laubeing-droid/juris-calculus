"""Evidence chain validator: carrier_level(A/B/C) → taint_status → source_anchor → fact → rule → claim audit."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from compiler_core.types import TaintStatus


CARRIER_LEVEL_ORDER = {"A": 1, "B": 2, "C": 3}


@dataclass
class EvidenceChainLink:
    link_id: str
    link_type: str  # evidence | fact | rule | claim
    source_anchor: str = ""
    carrier_level: str = ""
    taint_status: str = TaintStatus.CLEAR
    extraction_confidence: float = 1.0


@dataclass
class EvidenceChain:
    chain_id: str
    links: List[EvidenceChainLink] = field(default_factory=list)

    def add_link(self, link_type: str, link_id: str, source_anchor: str = "", carrier_level: str = "",
                 taint_status: str = TaintStatus.CLEAR, extraction_confidence: float = 1.0) -> EvidenceChainLink:
        link = EvidenceChainLink(link_id=link_id, link_type=link_type, source_anchor=source_anchor,
                                 carrier_level=carrier_level, taint_status=taint_status,
                                 extraction_confidence=extraction_confidence)
        self.links.append(link)
        return link


def validate_chain(chain: EvidenceChain) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []

    for idx, link in enumerate(chain.links):
        if link.link_type in {"evidence", "rule"} and not link.source_anchor.strip():
            findings.append({"link_index": idx, "link_id": link.link_id, "link_type": link.link_type,
                             "issue": "UNANCHORED", "severity": "BLOCKING"})
        if link.link_type == "rule" and link.carrier_level and CARRIER_LEVEL_ORDER.get(link.carrier_level, 99) > 2:
            findings.append({"link_index": idx, "link_id": link.link_id, "link_type": link.link_type,
                             "issue": "LOW_CARRIER_LEVEL", "carrier_level": link.carrier_level, "severity": "WARN"})
        if link.taint_status in {TaintStatus.TAINTED, TaintStatus.ATTEMPTED_HIJACK, TaintStatus.VERBATIM_MISMATCH}:
            findings.append({"link_index": idx, "link_id": link.link_id, "link_type": link.link_type,
                             "issue": f"TAINTED:{link.taint_status}", "severity": "BLOCKING"})
        if link.extraction_confidence < 0.5:
            findings.append({"link_index": idx, "link_id": link.link_id, "link_type": link.link_type,
                             "issue": "LOW_EXTRACTION_CONFIDENCE", "confidence": link.extraction_confidence,
                             "severity": "WARN"})

    link_types = [link.link_type for link in chain.links]
    if "evidence" not in link_types and "fact" in link_types:
        findings.append({"chain_id": chain.chain_id, "issue": "FACT_WITHOUT_EVIDENCE", "severity": "WARN"})
    if "rule" not in link_types and "claim" in link_types:
        findings.append({"chain_id": chain.chain_id, "issue": "CLAIM_WITHOUT_RULE", "severity": "WARN"})
    if "evidence" in link_types and "rule" in link_types and "fact" not in link_types:
        findings.append({"chain_id": chain.chain_id, "issue": "EVIDENCE_TO_RULE_WITHOUT_FACT", "severity": "WARN"})

    blocking = [f for f in findings if f["severity"] == "BLOCKING"]
    return {
        "chain_id": chain.chain_id,
        "link_count": len(chain.links),
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "status": "PASS" if not blocking else "FAIL",
        "findings": findings,
    }


def chain_from_ir_state(facts: Dict[str, Any], claims: Dict[str, Any], rules_applied: List[str]) -> EvidenceChain:
    from compiler_core.evidence_chain_validator import EvidenceChain, EvidenceChainLink
    chain = EvidenceChain(chain_id="ir_chain")
    for fid, fact in (facts or {}).items():
        anchor = getattr(fact, "source_anchor", "") or ""
        carrier = getattr(fact, "carrier_level", "") or ""
        taint = getattr(fact, "taint_status", TaintStatus.CLEAR) or TaintStatus.CLEAR
        conf = getattr(fact, "extraction_confidence", 1.0) or 1.0
        chain.add_link("evidence", fid, source_anchor=anchor, carrier_level=carrier, taint_status=taint, extraction_confidence=conf)
        chain.add_link("fact", fid, source_anchor=anchor, carrier_level=carrier, taint_status=taint, extraction_confidence=conf)
    for rule_id in rules_applied or []:
        chain.add_link("rule", rule_id)
    for cid in claims or {}:
        chain.add_link("claim", cid)
    return chain
