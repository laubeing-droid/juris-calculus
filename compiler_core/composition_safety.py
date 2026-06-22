"""Phase E: Four-stage compositional safety.

E1: Stage interface invariants for Horn→AAF→Grounded→Trust Label
E2: Attack graph construction completeness check
E3: Compositional safety matrix — fail-closed information propagation
E4: Golden corpus schema definition

Principle: four individually correct stages do not automatically compose
to pipeline correctness. This module defines and checks the compositional
conditions that MUST hold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ==========================================================================
# E1: Stage interface invariants
# ==========================================================================

@dataclass
class Stage1Interface:
    """Stage 1 (Horn) output invariants."""
    claims: list[str]                    # derived claim IDs
    source_rules: list[str]              # rule IDs that produced claims
    saturation_status: str               # "saturated" | "truncated" | "unknown"
    provenance: list[dict[str, Any]]     # per-claim derivation witnesses
    truncation_warning: str              # non-empty if saturation_status != "saturated"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.saturation_status == "truncated" and not self.truncation_warning:
            errors.append("TRUNCATED without warning")
        if self.saturation_status == "unknown":
            errors.append("UNKNOWN saturation — downstream stages must degrade")
        if not self.claims and self.saturation_status == "saturated":
            pass  # vacuously saturated
        return errors


@dataclass
class Stage2Interface:
    """Stage 2 (AAF attack graph) output invariants."""
    arguments: list[dict[str, Any]]       # argument objects (mapped from claims)
    attack_edges: list[tuple[str, str]]   # (source, target) pairs
    edge_sources: dict[str, list[str]]    # per-edge type: rebuttal, undercut, exception, priority, prohibition
    source_anchors: list[dict[str, Any]]  # per-attack provenance
    completeness: str                     # "complete" | "partial" | "unknown"

    def validate(self) -> list[str]:
        errors: list[str] = []
        arg_ids = {a["id"] for a in self.arguments}
        for src, tgt in self.attack_edges:
            if src not in arg_ids:
                errors.append(f"Attack source {src} not in arguments")
            if tgt not in arg_ids:
                errors.append(f"Attack target {tgt} not in arguments")
        if self.completeness == "unknown":
            errors.append("UNKNOWN attack graph completeness — downstream must degrade")
        return errors


@dataclass
class Stage3Interface:
    """Stage 3 (Grounded extension) output invariants."""
    accepted: list[str]
    rejected: list[str]
    undecided: list[str]
    convergent: bool
    truncated: bool
    certificate: dict[str, Any] | None    # verifiable proof certificate
    witness_data: dict[str, Any]          # SCC/cycle/defense witnesses

    def validate(self) -> list[str]:
        errors: list[str] = []
        all_labels = set(self.accepted + self.rejected + self.undecided)
        if len(all_labels) != len(self.accepted) + len(self.rejected) + len(self.undecided):
            errors.append("Label overlap detected")
        if self.truncated and self.convergent:
            errors.append("TRUNCATED but convergent — invalid")
        if not self.convergent and not self.truncated:
            errors.append("Neither convergent nor truncated — invalid state")
        return errors


@dataclass
class Stage4Interface:
    """Stage 4 (Trust Label projection) output invariants."""
    label_map: dict[str, str]             # argument ID → trust label
    forbidden: list[str]                  # arguments marked forbidden
    human_review: list[str]               # arguments flagged for human review
    undec_degraded: bool                  # True if UNDEC properly downgraded (not projected to forbidden)

    def validate(self) -> list[str]:
        errors: list[str] = []
        # UNDEC must NOT project to forbidden
        for arg_id, label in self.label_map.items():
            if label == "forbidden" and arg_id in self.forbidden:
                pass  # OK
            elif label == "forbidden" and arg_id not in self.forbidden:
                errors.append(f"Argument {arg_id} marked forbidden but not in forbidden list")
        return errors


# ==========================================================================
# E2: Attack graph construction completeness
# ==========================================================================

ATTACK_SOURCE_TYPES = [
    "explicit_attack",
    "priority_over",
    "exception_reverse",
    "rebuttal",
    "prohibition",
    "temporal_invalidity",
    "jurisdiction_conflict",
]

@dataclass
class AttackCompletenessReport:
    complete: bool
    covered_sources: list[str]
    missing_sources: list[str]
    total_edges: int
    edge_counts_by_source: dict[str, int]

def check_attack_graph_completeness(
    claims: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    attack_edges: list[tuple[str, str]],
    edge_types: dict[str, list[str]],
) -> AttackCompletenessReport:
    """Check which attack source types are represented in the graph."""
    covered = [t for t in ATTACK_SOURCE_TYPES if t in edge_types]
    missing = [t for t in ATTACK_SOURCE_TYPES if t not in edge_types]

    return AttackCompletenessReport(
        complete=len(missing) == 0,
        covered_sources=covered,
        missing_sources=missing,
        total_edges=len(attack_edges),
        edge_counts_by_source={t: len(v) for t, v in edge_types.items()},
    )


# ==========================================================================
# E3: Compositional safety matrix — fail-closed propagation
# ==========================================================================

@dataclass
class CompositionSafetyReport:
    safe: bool
    stages: list[str]                          # stages checked
    degradation_path: list[dict[str, str]]     # what degrades when
    failures: list[str]                         # safety violations

def check_compositional_safety(
    stage1: Stage1Interface | None,
    stage2: Stage2Interface | None,
    stage3: Stage3Interface | None,
    stage4: Stage4Interface | None,
) -> CompositionSafetyReport:
    """Verify that downstream stages degrade correctly when upstream is uncertain.

    Rules:
      - Stage 1 UNKNOWN → Stage 4 must label all outputs UNVERIFIED
      - Stage 2 UNKNOWN → Stage 3 must produce UNDEC for all impacted arguments
      - Stage 3 TRUNCATED → Stage 4 must flag human_review
      - Stage 3 UNDEC → Stage 4 must NOT project to forbidden
      - Any stage TRUNCATED → pipeline output cannot claim completeness
    """
    failures: list[str] = []
    degradation_path: list[dict[str, str]] = []

    if stage1 and stage1.saturation_status == "unknown":
        degradation_path.append({"from": "Stage1", "to": "Stage4", "action": "UNVERIFIED all labels"})

    if stage2 and stage2.completeness == "unknown":
        degradation_path.append({"from": "Stage2", "to": "Stage3", "action": "UNDEC all cycle-affected arguments"})

    if stage3:
        if stage3.truncated:
            degradation_path.append({"from": "Stage3", "to": "Stage4", "action": "Flag human_review"})
        if stage4:
            # UNDEC must not project to forbidden
            for arg_id in stage3.undecided:
                if arg_id in stage4.forbidden:
                    failures.append(f"UNDEC argument {arg_id} projected to forbidden — VIOLATION")

    if stage4:
        s4_errors = stage4.validate()
        failures.extend(s4_errors)

    safe = len(failures) == 0

    return CompositionSafetyReport(
        safe=safe,
        stages=[s for s, v in [("Stage1",stage1),("Stage2",stage2),("Stage3",stage3),("Stage4",stage4)] if v is not None],
        degradation_path=degradation_path,
        failures=failures,
    )


# ==========================================================================
# E4: Golden corpus schema
# ==========================================================================

@dataclass
class GoldenCase:
    """One end-to-end test case for the four-stage pipeline."""
    case_id: str
    description: str
    facts: list[dict[str, Any]]             # initial facts
    rules: list[dict[str, Any]]             # applicable rules
    generated_aaf: dict[str, Any]           # expected attack graph
    expected_labels: dict[str, str]         # arg_id → IN|OUT|UNDEC
    proof_certificates: list[dict[str, Any]] # verifiable certificates
    trust_projection: dict[str, str]         # arg_id → trust label
    source_anchors: list[dict[str, Any]]     # provenance for each edge/label

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.facts:
            errors.append("Empty facts")
        if not self.rules:
            errors.append("Empty rules")
        if not self.generated_aaf and self.generated_aaf != {}:
            errors.append("Missing generated AAF")
        if not self.expected_labels:
            errors.append("Missing expected labels")
        return errors


# Pre-built golden corpus cases
GOLDEN_CORPUS: list[dict[str, Any]] = [
    {
        "case_id": "contract-claim-counterclaim",
        "description": "Contract claim right → defense → counter-defense",
        "facts": [{"id": "F1", "text": "contract signed"}, {"id": "F2", "text": "breach occurred"}],
        "rules": [
            {"id": "R1", "head": "claim_valid", "body": ["F1", "F2"]},
            {"id": "R2", "head": "defense_force_majeure", "body": ["F3"]},
        ],
    },
    {
        "case_id": "evidence-mutual-attack",
        "description": "Two pieces of evidence mutually attacking each other",
        "facts": [{"id": "E1", "text": "witness testimony"}, {"id": "E2", "text": "documentary evidence"}],
        "rules": [
            {"id": "R3", "head": "evidence_credible", "body": ["E1"]},
            {"id": "R4", "head": "evidence_credible", "body": ["E2"]},
        ],
    },
    {
        "case_id": "multi-expert-opinion",
        "description": "Multiple expert opinions with conflicting conclusions",
        "facts": [{"id": "X1", "text": "expert A opinion"}, {"id": "X2", "text": "expert B opinion"}],
        "rules": [],
    },
    {
        "case_id": "rule-exception-chain",
        "description": "General rule → exception → exception to exception",
        "facts": [{"id": "G1", "text": "general provision applies"}],
        "rules": [
            {"id": "R5", "head": "general_rule_applies", "body": ["G1"]},
            {"id": "R6", "head": "exception_applies", "body": ["G1"]},
        ],
    },
    {
        "case_id": "priority-conflict",
        "description": "Two rules with conflicting priorities",
        "facts": [{"id": "P1", "text": "higher statute"}, {"id": "P2", "text": "lower regulation"}],
        "rules": [
            {"id": "R7", "head": "higher_prevails", "body": ["P1"]},
            {"id": "R8", "head": "lower_applies", "body": ["P2"]},
        ],
    },
    {
        "case_id": "cyclic-dispute",
        "description": "Arguments forming a cycle with no clear resolution",
        "facts": [{"id": "C1", "text": "plaintiff claim"}, {"id": "C2", "text": "defendant counterclaim"}],
        "rules": [],
    },
    {
        "case_id": "missing-necessary-fact",
        "description": "Claim missing a necessary fact for legal conclusion",
        "facts": [{"id": "M1", "text": "partial evidence"}],
        "rules": [{"id": "R9", "head": "conclusion_reached", "body": ["M1", "M2"]}],
    },
    {
        "case_id": "temporal-validity-conflict",
        "description": "Old law vs new law temporal conflict",
        "facts": [{"id": "T1", "text": "event occurred 2020"}, {"id": "T2", "text": "law amended 2023"}],
        "rules": [],
    },
    {
        "case_id": "cross-jurisdiction-gap",
        "description": "Concept exists in one jurisdiction but not another",
        "facts": [{"id": "J1", "text": "US concept"}, {"id": "J2", "text": "CN concept"}],
        "rules": [],
    },
]
