#!/usr/bin/env python3
"""End-to-end litigation reasoning chain renderer.

Takes a case (facts + legal rules) and produces a comprehensive,
lawyer-readable reasoning chain covering:
  - Horn closure: which rules fired, what was derived
  - AAF construction: arguments, attacks, attack kinds
  - Grounded extension: IN / OUT / UNDEC labels
  - Minimal support: why an argument is IN
  - Minimal rebuttal: what would defeat an argument
  - Missing evidence: what evidence would change the conclusion
  - Fail-closed boundary: where the analysis stops

Outputs both machine-readable JSON and human-readable Markdown.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from compiler_core.argumentation import grounded_extension, proof_trace
from compiler_core.certificate_checker import (
    GroundedINCertificate,
    OUTCertificate,
    UNDECCertificate,
)
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator
from compiler_core.horn_completeness import (
    ConclusionProvenance,
    compute_minimal_rebuttal,
    compute_minimal_support,
    compute_missing_evidence,
    analyze_rule_impact,
)
from compiler_core.litigation_engineering import (
    LabelCertificate,
    SCCCorrectnessResult,
    generate_certificate,
    generate_all_certificates,
    find_minimal_intervention,
    check_scc_correctness,
)
from compiler_core.types import IRState, LegalDomain, LegalFact, LegalRule


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class HornStep:
    """A single step in Horn closure computation."""
    iteration: int
    rule_id: str
    premises: list[str]
    derived: list[str]


@dataclass
class ArgumentRecord:
    """An argument in the AAF layer."""
    argument_id: str
    conclusion: str
    support_facts: list[str]
    rule_id: str


@dataclass
class AttackRecord:
    """An attack in the AAF layer."""
    source: str
    target: str
    kind: str  # REBUTTAL | EXCEPTION | PRIORITY_DEFEAT
    reason: str


@dataclass
class ClaimAnalysis:
    """Full analysis of a single claim."""
    claim_id: str
    status: str  # PROVED | REFUTED | UNDECIDED
    label: str  # IN | OUT | UNDEC
    horn_derivation: List[HornStep] = field(default_factory=list)
    attacks_against: List[str] = field(default_factory=list)
    attacks_from: List[str] = field(default_factory=list)
    minimal_support: List[str] = field(default_factory=list)
    minimal_rebuttal: List[Dict[str, Any]] = field(default_factory=list)
    missing_evidence: List[Dict[str, Any]] = field(default_factory=list)
    certificate: Optional[Dict[str, Any]] = None
    fail_closed_note: Optional[str] = None


@dataclass
class LitigationReport:
    """Top-level litigation reasoning report."""
    case_id: str
    schema_version: str = "litigation-v1"
    facts: List[str] = field(default_factory=list)
    rules_applied: List[str] = field(default_factory=list)
    horn_closure: List[str] = field(default_factory=list)
    arguments: List[ArgumentRecord] = field(default_factory=list)
    attacks: List[AttackRecord] = field(default_factory=list)
    grounded_summary: Dict[str, Any] = field(default_factory=dict)
    claim_analyses: List[ClaimAnalysis] = field(default_factory=list)
    impact_analysis: Optional[Dict[str, Any]] = None
    truncation_warning: Optional[str] = None
    fail_closed_boundary: Dict[str, bool] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core renderer
# ---------------------------------------------------------------------------

class LitigationChainRenderer:
    """Render a complete litigation reasoning chain from facts and rules."""

    def __init__(self, rules: list[LegalRule], facts: list[str], domain: LegalDomain = LegalDomain.CIVIL):
        self.rules = rules
        self.facts = facts
        self.domain = domain
        self._state: Optional[IRState] = None
        self._claims: list[dict[str, Any]] = []
        self._attacks: list[tuple[str, str]] = []
        self._ge_result: dict[str, Any] = {}
        self._attack_records: list[AttackRecord] = []
        self._argument_records: list[ArgumentRecord] = []

    def evaluate(self) -> LitigationReport:
        """Run the full evaluation pipeline and return a structured report."""
        evaluator = FixpointEvaluator(self.rules, DomainConfig(domain=self.domain))
        init_state = IRState(
            facts={f: LegalFact(id=f, description=f) for f in self.facts},
            domain=self.domain,
        )
        init_state.max_iterations = 50

        horn_state = evaluator.evaluate_horn(init_state)
        self._state = horn_state

        # Build claims and attacks
        self._claims = [{"id": cid} for cid in sorted(horn_state.claims.keys())]
        self._argument_records = [
            ArgumentRecord(
                argument_id=cid,
                conclusion=cid,
                support_facts=[p for r in self.rules if r.head_claim == cid for p in r.premise_atoms],
                rule_id=next((r.id for r in self.rules if r.head_claim == cid), "unknown"),
            )
            for cid in sorted(horn_state.claims.keys())
        ]

        # Build attacks from rule metadata
        rule_by_id = {r.id: r for r in self.rules}
        present = set(horn_state.claims.keys())
        for rule in self.rules:
            if rule.head_claim not in present:
                continue
            for attacked_rule_id in rule.attacks:
                target = rule_by_id.get(attacked_rule_id)
                if target and target.head_claim in present:
                    self._attacks.append((rule.head_claim, target.head_claim))
                    self._attack_records.append(AttackRecord(
                        source=rule.head_claim,
                        target=target.head_claim,
                        kind="EXCEPTION",
                        reason=f"{rule.head_claim} defeats {target.head_claim}",
                    ))
            for priority_rule_id in rule.priority_over:
                target = rule_by_id.get(priority_rule_id)
                if target and target.head_claim in present:
                    self._attacks.append((rule.head_claim, target.head_claim))
                    self._attack_records.append(AttackRecord(
                        source=rule.head_claim,
                        target=target.head_claim,
                        kind="PRIORITY_DEFEAT",
                        reason=f"{rule.id} has priority over {priority_rule_id}",
                    ))

        # Grounded extension
        self._ge_result = grounded_extension(self._claims, self._attacks)
        truncation = "truncated" if self._ge_result.get("truncated") else None

        # Build claim analyses
        claim_analyses = []
        for claim in self._claims:
            cid = claim["id"]
            label, status = self._resolve_label(cid)
            analysis = ClaimAnalysis(
                claim_id=cid,
                status=status,
                label=label,
                horn_derivation=self._horn_steps_for(cid),
                attacks_against=[a.source for a in self._attack_records if a.target == cid],
                attacks_from=[a.target for a in self._attack_records if a.source == cid],
            )
            claim_analyses.append(analysis)

        # Enrich with completeness analysis
        self._enrich_completeness(claim_analyses, horn_state)

        # Build certificates
        for analysis in claim_analyses:
            cert = generate_certificate(analysis.claim_id, self._claims, self._attacks, self._ge_result)
            if cert:
                analysis.certificate = {
                    "label": cert.label,
                    "witnesses": cert.witnesses,
                    "attackers": cert.attackers,
                    "proof_depth": cert.proof_depth,
                    "verifiable": cert.verifiable,
                }

        # Fail-closed boundary
        fail_closed = {
            "horn_truncated": horn_state.horn_truncated,
            "grounded_truncated": self._ge_result.get("truncated", False),
            "no_uncertainty_upgrade": not self._check_uncertainty_upgrade(claim_analyses),
        }

        report = LitigationReport(
            case_id=f"case::{hash(tuple(self.facts)) & 0xFFFF:04x}",
            facts=list(self.facts),
            rules_applied=sorted(horn_state.rules_applied),
            horn_closure=sorted(horn_state.claims.keys()),
            arguments=self._argument_records,
            attacks=self._attack_records,
            grounded_summary={
                "accepted_count": len(self._ge_result["accepted"]),
                "rejected_count": len(self._ge_result["rejected"]),
                "undecided_count": len(self._ge_result["undecided"]),
                "truncated": self._ge_result.get("truncated", False),
            },
            claim_analyses=claim_analyses,
            truncation_warning=truncation,
            fail_closed_boundary=fail_closed,
        )
        return report

    def evaluate_with_impact(self, baseline_report: LitigationReport) -> LitigationReport:
        """Evaluate and include rule change impact analysis vs a baseline."""
        report = self.evaluate()
        # Compute impact by comparing rule sets
        old_rules = set(baseline_report.rules_applied)
        new_rules = set(report.rules_applied)
        added = new_rules - old_rules
        removed = old_rules - new_rules

        changed_claims = []
        old_claims = {a.claim_id: a.status for a in baseline_report.claim_analyses}
        for a in report.claim_analyses:
            old_status = old_claims.get(a.claim_id, "NEW")
            if old_status != a.status:
                changed_claims.append({"claim_id": a.claim_id, "old": old_status, "new": a.status})

        report.impact_analysis = {
            "rules_added": sorted(added),
            "rules_removed": sorted(removed),
            "claims_changed": changed_claims,
            "total_claims_affected": len(changed_claims),
        }
        return report

    # -- internal helpers --

    def _resolve_label(self, cid: str) -> tuple[str, str]:
        accepted = set(self._ge_result["accepted"])
        rejected = set(self._ge_result["rejected"])
        if cid in accepted:
            return "IN", "PROVED"
        if cid in rejected:
            return "OUT", "REFUTED"
        return "UNDEC", "UNDECIDED"

    def _horn_steps_for(self, cid: str) -> list[HornStep]:
        if self._state is None:
            return []
        steps: list[HornStep] = []
        relevant_claims = self._backward_closure(cid)
        for rule in self.rules:
            if rule.head_claim in relevant_claims and rule.head_claim in self._state.claims:
                steps.append(HornStep(
                    iteration=0,
                    rule_id=rule.id,
                    premises=list(rule.premise_atoms),
                    derived=[rule.head_claim],
                ))
        return steps

    def _backward_closure(self, target: str) -> set[str]:
        """Compute the set of claims that contribute to deriving target."""
        if self._state is None:
            return {target}
        visited = set()
        queue = [target]
        rule_index: dict[str, list[LegalRule]] = {}
        for r in self.rules:
            for p in r.premise_atoms:
                rule_index.setdefault(p, []).append(r)
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for rule in self.rules:
                if rule.head_claim == current:
                    for p in rule.premise_atoms:
                        if p not in visited:
                            queue.append(p)
        return visited

    def _enrich_completeness(self, analyses: list[ClaimAnalysis], horn_state: IRState) -> None:
        """Enrich claims with minimal support, rebuttal, and missing evidence."""
        rules_dict = {r.id: r for r in self.rules}

        for analysis in analyses:
            try:
                support = compute_minimal_support(analysis.claim_id, horn_state, rules_dict)
                analysis.minimal_support = sorted(support.evidence) if support.evidence else []
            except Exception:
                pass

            try:
                rebuttal = compute_minimal_rebuttal(
                    analysis.claim_id,
                    horn_state.claims,
                    rules_dict,
                    self._claims,
                    self._attacks,
                    self._ge_result,
                )
                analysis.minimal_rebuttal = [
                    {"target": r.target, "evidence": sorted(r.evidence), "cost": r.cost}
                    for r in rebuttal
                ]
            except Exception:
                pass

            try:
                missing = compute_missing_evidence(analysis.claim_id, horn_state, rules_dict)
                analysis.missing_evidence = [
                    {"type": m.type, "evidence": sorted(m.evidence), "status": m.status}
                    for m in missing
                ]
            except Exception:
                pass

    def _check_uncertainty_upgrade(self, analyses: list[ClaimAnalysis]) -> bool:
        """Check if any UNDECIDED claim got upgraded to PROVED/REFUTED."""
        for a in analyses:
            if a.status == "PROVED" and a.missing_evidence:
                return True
        return False

    def render_markdown(self, report: LitigationReport) -> str:
        """Render the report as lawyer-readable Markdown."""
        lines = [
            f"# Litigation Reasoning Report: {report.case_id}",
            "",
            "## Case Facts",
            "",
            *[f"- {f}" for f in report.facts],
            "",
            "## Rules Applied",
            "",
            *[f"- {r}" for r in report.rules_applied],
            "",
            "## Grounded Summary",
            "",
            f"- Accepted (IN): {report.grounded_summary['accepted_count']}",
            f"- Rejected (OUT): {report.grounded_summary['rejected_count']}",
            f"- Undecided: {report.grounded_summary['undecided_count']}",
            "",
        ]

        if report.truncation_warning:
            lines.append(f"> **Warning**: {report.truncation_warning}")

        for a in report.claim_analyses:
            lines.extend([
                f"## Claim: {a.claim_id}",
                "",
                f"**Status**: {a.status}  ",
                f"**Label**: {a.label}  ",
            ])

            if a.minimal_support:
                lines.append(f"**Minimal Support**: {', '.join(a.minimal_support)}")
            if a.attacks_against:
                lines.append(f"**Attacked By**: {', '.join(a.attacks_against)}")
            if a.minimal_rebuttal:
                lines.append("**Rebuttal Required**:")
                for r in a.minimal_rebuttal:
                    lines.append(f"  - Defeat {r['target']} via {', '.join(r['evidence'])} (cost: {r['cost']})")
            if a.missing_evidence:
                lines.append("**Missing Evidence**:")
                for m in a.missing_evidence:
                    lines.append(f"  - [{m['type']}] {', '.join(m['evidence'])}")
            if a.certificate:
                lines.append(f"**Certificate**: {a.certificate['label']} (depth {a.certificate['proof_depth']}, verifiable: {a.certificate['verifiable']})")

            lines.append("")

        if report.impact_analysis:
            lines.extend([
                "## Rule Change Impact",
                f"- Rules added: {len(report.impact_analysis['rules_added'])}",
                f"- Rules removed: {len(report.impact_analysis['rules_removed'])}",
                f"- Claims affected: {report.impact_analysis['total_claims_affected']}",
            ])

        if report.fail_closed_boundary:
            lines.extend([
                "## Safety Boundary",
                f"- Horn truncated: {report.fail_closed_boundary['horn_truncated']}",
                f"- Grounded truncated: {report.fail_closed_boundary['grounded_truncated']}",
                f"- No uncertainty upgrade: {report.fail_closed_boundary['no_uncertainty_upgrade']}",
            ])

        return "\n".join(lines)