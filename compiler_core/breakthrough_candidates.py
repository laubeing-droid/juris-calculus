"""Phase F2-F3: Auto-discover math breakthrough candidates with Engineering Unlock Score.

F2: 13 candidate math breakthroughs (A-M) with Math-to-Engineering Capability Cards.
F3: Scoring formula implementation for priority ranking.

Each candidate has:
  - theorem_id, precise math proposition, current gap
  - necessary assumptions, known counterexamples
  - verification strategy (Lean/SMT/Z3/experiment)
  - production module, capability unlocked
  - risk if unproved, MVM, complete proof target
  - estimated complexity, priority, dependency on G8/G9/G10
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ==========================================================================
# F2: Candidate cards (A-M)
# ==========================================================================

@dataclass
class BreakthroughCandidate:
    theorem_id: str
    proposition: str               # precise math statement
    current_gap: str               # what's missing
    assumptions: list[str]
    counterexamples: list[str]     # known counterexamples
    verification_strategy: str     # Lean / SMT / Z3 / experiment
    production_module: str         # where it would live
    capability_unlocked: str       # engineering impact
    risk_if_wrong: str             # what breaks if assumed true but false
    mvm: str                       # minimum viable math
    complete_proof_target: str     # full proof goal
    estimated_complexity: int      # 0-5
    priority_raw: float            # pre-scoring priority
    depends_on: list[str]          # G8, G9, G10, or empty
    engineering_unlock_score: float = 0.0  # computed by F3

CANDIDATES: list[dict[str, Any]] = [
    {
        "theorem_id": "A-dynamic-aaf",
        "proposition": "Adding/removing arguments or attack edges changes grounded extension only within affected SCC and its successors",
        "current_gap": "No formal proof of update locality; current implementation recomputes globally",
        "assumptions": ["finite AAF", "single-edge modification"],
        "counterexamples": ["Cross-SCC undecided propagation may expand impact"],
        "verification_strategy": "Lean inductive proof on SCC condensation DAG + bounded Z3 for counterexample search",
        "production_module": "litigation_engineering.py",
        "capability_unlocked": "Incremental recompute after evidence change; real-time interactive reasoning",
        "risk_if_wrong": "Silent incorrect labels after update; wrong legal advice",
        "mvm": "Prove locality for single-edge addition in DAG + single-SCC graphs",
        "complete_proof_target": "Full dynamic update theorem for arbitrary finite AAF",
        "estimated_complexity": 4,
        "priority_raw": 0.43,
        "depends_on": ["G9"],
    },
    {
        "theorem_id": "B-certificate-minimization",
        "proposition": "Every IN argument has a minimal defense witness (subset-minimal set of arguments that defeats all attackers)",
        "current_gap": "Current witnesses include all defeating arguments, not minimal subset",
        "assumptions": ["finite AAF", "grounded semantics"],
        "counterexamples": [],
        "verification_strategy": "Z3 optimization (minimal hitting set) + Lean for existence proof",
        "production_module": "litigation_engineering.py:generate_certificate()",
        "capability_unlocked": "Shortest defense chain display for lawyers; audit trail minimization",
        "risk_if_wrong": "Suboptimal but not incorrect — just verbose certificates",
        "mvm": "Greedy minimal witness extraction with bounded Z3 verification",
        "complete_proof_target": "NP-hard in general; bounded exact solution for practical graph sizes",
        "estimated_complexity": 3,
        "priority_raw": 0.48,
        "depends_on": ["G9"],
    },
    {
        "theorem_id": "C-minimal-support",
        "proposition": "For every claim, there exists a minimal support set (subset-minimal facts) and a minimal rebuttal set (subset-minimal counter-arguments)",
        "current_gap": "No minimal enumeration; all-or-nothing support/rebuttal",
        "assumptions": ["finite fact/rule sets"],
        "counterexamples": [],
        "verification_strategy": "Z3 MaxSAT for minimal enumeration + Lean existence",
        "production_module": "horn_completeness.py",
        "capability_unlocked": "Evidence gap analysis; proof requirement checklist; rebuttal checklist",
        "risk_if_wrong": "Overly broad support requirements; incomplete rebuttal analysis",
        "mvm": "Bounded min-support enumeration for Horn rules with <20 body atoms",
        "complete_proof_target": "Minimal support/rebuttal for arbitrary finite Horn programs",
        "estimated_complexity": 4,
        "priority_raw": 0.40,
        "depends_on": ["G8"],
    },
    {
        "theorem_id": "D-horn-aaf-preservation",
        "proposition": "The Horn→AAF compilation preserves derivability: derived(Horn) iff accepted(AAF) for all arguments not in attack cycles",
        "current_gap": "Compilation is mechanical but semantic equivalence is unproven",
        "assumptions": ["finite Horn rules", "correct attack edge construction"],
        "counterexamples": ["Cycles in AAF may not correspond to Horn derivability cycles"],
        "verification_strategy": "Lean soundness + completeness proof with explicit compilation mapping",
        "production_module": "stratified_evaluator.py",
        "capability_unlocked": "Prevent compilation-stage meaning change; audit trail from Horn to AAF",
        "risk_if_wrong": "Legal conclusion altered by compilation; silent semantic corruption",
        "mvm": "Prove preservation for Horn rules without exception chains",
        "complete_proof_target": "Full preservation for Horn + exception + priority rules",
        "estimated_complexity": 4,
        "priority_raw": 0.30,
        "depends_on": ["G8", "G9"],
    },
    {
        "theorem_id": "E-paraconsistency",
        "proposition": "When both P and not-P are derivable, the system adopts paraconsistent behavior: marks both as CONFLICTED without exploding",
        "current_gap": "No explicit paraconsistent logic; Horn contradiction silently saturates everything",
        "assumptions": ["finite rules", "explicit contradiction detection"],
        "counterexamples": ["Classical explosion: ex contradictione quodlibet"],
        "verification_strategy": "Lean for paraconsistent semantics + Z3 for bounded model checking",
        "production_module": "evaluator.py (new conflict detection layer)",
        "capability_unlocked": "Handle evidence conflicts without global contamination; display conflicting evidence to lawyer",
        "risk_if_wrong": "Silent explosion or incorrect non-explosion; wrong legal advice",
        "mvm": "Implement and verify conflict marking for direct P/not-P without explosion",
        "complete_proof_target": "Full paraconsistent logic embedding with relevance tracking",
        "estimated_complexity": 5,
        "priority_raw": 0.14,
        "depends_on": ["G8"],
    },
    {
        "theorem_id": "F-priority-wellfounded",
        "proposition": "Rule priority relations form a well-founded partial order (no infinite descending chains, no priority cycles)",
        "current_gap": "Priority chains may contain cycles; no detection or warning",
        "assumptions": ["finite rule set", "explicit priority relations"],
        "counterexamples": ["priority_over(A,B) and priority_over(B,A) simultaneously"],
        "verification_strategy": "Z3 cycle detection + Lean well-foundedness proof for finite sets",
        "production_module": "constraint_validator.py",
        "capability_unlocked": "Priority cycle detection and warning; prevents infinite regress in rule application",
        "risk_if_wrong": "Non-termination or non-deterministic rule application",
        "mvm": "Cycle detection with bounded Z3 + explicit warning",
        "complete_proof_target": "Well-foundedness certificate for all priority graphs",
        "estimated_complexity": 3,
        "priority_raw": 0.44,
        "depends_on": [],
    },
    {
        "theorem_id": "G-ddl-reparation",
        "proposition": "DDL contrary-to-duty obligations with ordered reparation chains are correctly expressible in Horn+exception logic without collapsing to simple obligation",
        "current_gap": "Chinese alternative liability (择一责任) is erroneously encoded as chain; joint liability (并列责任) should be unordered pool",
        "assumptions": ["finite obligations", "ordered preference on remedies"],
        "counterexamples": ["Joint liability encoded as chain produces wrong priority"],
        "verification_strategy": "Lean DDL semantics + juris-calculus test corpus",
        "production_module": "addons/cn/adapter.py",
        "capability_unlocked": "Correct expression of Chinese alternative liability, joint liability, and ordered remedies",
        "risk_if_wrong": "Wrong liability allocation in Chinese legal reasoning; major legal error",
        "mvm": "Correctly distinguish ordered-chain vs unordered-pool for CN civil code articles",
        "complete_proof_target": "Full DDL reparation semantics for Chinese civil obligations",
        "estimated_complexity": 5,
        "priority_raw": 0.27,
        "depends_on": ["G8"],
    },
    {
        "theorem_id": "H-temporal-validity",
        "proposition": "For rules with valid_from/valid_to, the applicable rule set at any time point t is uniquely determined and temporally consistent",
        "current_gap": "No temporal reasoning; rules are treated as simultaneously valid",
        "assumptions": ["finite time axis", "non-overlapping validity intervals"],
        "counterexamples": ["Overlapping amendments with conflicting provisions"],
        "verification_strategy": "Z3 for temporal constraint solving + Lean for determinism proof",
        "production_module": "new: temporal_validity.py",
        "capability_unlocked": "Historical case applicable law selection; statute version selection; temporal conflict resolution",
        "risk_if_wrong": "Wrong law applied to historical case; incorrect legal conclusion",
        "mvm": "Implement valid_from/valid_to filtering with Z3 conflict detection",
        "complete_proof_target": "Full temporal logic with amendment chains and transitional provisions",
        "estimated_complexity": 4,
        "priority_raw": 0.26,
        "depends_on": [],
    },
    {
        "theorem_id": "I-negative-requirements",
        "proposition": "Missing evidence (facts not in the knowledge base) is treated as UNKNOWN, not FALSE; open-world assumption with explicit closure check",
        "current_gap": "Missing facts silently treated as false (closed-world assumption in Horn logic)",
        "assumptions": ["finite predicate vocabulary", "explicit negative evidence marking"],
        "counterexamples": ["Missing evidence in Horn = false conclusion (undesirable)"],
        "verification_strategy": "Lean open-world semantics + explicit negative fact markers",
        "production_module": "evaluator.py (fact completeness checker)",
        "capability_unlocked": "Missing evidence checklists; prevent erroneous negative inference; suspend judgment",
        "risk_if_wrong": "Erroneous negative conclusion from missing evidence; wrongful legal determination",
        "mvm": "Explicit UNKNOWN marking for conclusions that depend on unverified facts",
        "complete_proof_target": "Full open-world assumption for legal Horn reasoning",
        "estimated_complexity": 4,
        "priority_raw": 0.43,
        "depends_on": ["G8"],
    },
    {
        "theorem_id": "J-cross-jurisdiction-partial",
        "proposition": "Cross-jurisdiction concept mapping is a partial function; unmapped concepts auto-degrade without breaking the entire translation",
        "current_gap": "Current implementation hard-fails on unmapped concepts",
        "assumptions": ["finite jurisdiction vocabularies", "explicit mapping table"],
        "counterexamples": ["Concept in US law with no CN equivalent"],
        "verification_strategy": "Z3 for mapping consistency + explicit degradation markers",
        "production_module": "cross_jurisdiction_router.py",
        "capability_unlocked": "Graceful degradation for unmapped concepts; automatic human review flagging",
        "risk_if_wrong": "Silent incorrect cross-jurisdiction reasoning",
        "mvm": "Partial function semantics with explicit UNMAPPED marking and degradation",
        "complete_proof_target": "Full partial-function cross-jurisdiction semantics with composition",
        "estimated_complexity": 3,
        "priority_raw": 0.48,
        "depends_on": [],
    },
    {
        "theorem_id": "K-certificate-compression",
        "proposition": "Proof certificates can be compressed via DAG sharing, hash-consing, and Merkle proof traces to sublinear storage",
        "current_gap": "Full proof traces are linear in rule applications; 21,144 rules would produce massive certificates",
        "assumptions": ["finite rule set", "shared sub-proofs"],
        "counterexamples": [],
        "verification_strategy": "Implementation + empirical compression ratio measurement",
        "production_module": "proof_trace_renderer.py",
        "capability_unlocked": "Storable, transmittable, independently verifiable proof chains for 21,144 rules",
        "risk_if_wrong": "Uncompressed certificates too large for practical transmission",
        "mvm": "Implement hash-consing for shared Horn sub-derivations",
        "complete_proof_target": "Merkle-DAG proof trace with sublinear storage",
        "estimated_complexity": 3,
        "priority_raw": 0.19,
        "depends_on": ["G8"],
    },
    {
        "theorem_id": "L-rule-change-impact",
        "proposition": "When a rule is modified/deleted/expired, the set of affected conclusions is computable as the downstream closure in the derivation DAG",
        "current_gap": "No impact analysis; rule changes require full recomputation",
        "assumptions": ["finite Horn rules", "derivation DAG tracking"],
        "counterexamples": ["Cyclic dependencies may expand impact set"],
        "verification_strategy": "Z3 for dependency closure + Lean for soundness of impact set",
        "production_module": "horn_completeness.py",
        "capability_unlocked": "Incremental recompute after law update; regression audit; impact preview",
        "risk_if_wrong": "Missed impacted conclusions after rule change; incorrect legal advice",
        "mvm": "DAG-based downstream closure computation with Z3 verification",
        "complete_proof_target": "Full impact analysis with incremental recompute",
        "estimated_complexity": 3,
        "priority_raw": 0.33,
        "depends_on": ["G8"],
    },
    {
        "theorem_id": "M-uncertainty-boundary",
        "proposition": "Logical status (IN/OUT/UNDEC), evidence quality, extraction confidence, trust label, and human review are five orthogonal dimensions; none may be collapsed into another",
        "current_gap": "Trust labels sometimes override logical status; probability scores contaminate deterministic labels",
        "assumptions": ["five orthogonal dimensions", "explicit separation in data model"],
        "counterexamples": ["Probability score overriding logical UNDEC"],
        "verification_strategy": "Type-system enforcement + test coverage for each dimension independently",
        "production_module": "trust_labels.py + stratified_evaluator.py",
        "capability_unlocked": "Prevent probability scores from covering deterministic logical status; clean separation of concerns",
        "risk_if_wrong": "Logical uncertainty conflated with statistical uncertainty; wrong legal confidence",
        "mvm": "Type-level separation of five dimensions with test coverage",
        "complete_proof_target": "Full orthogonality proof with formal semantics for each dimension",
        "estimated_complexity": 3,
        "priority_raw": 0.47,
        "depends_on": ["G8", "G9"],
    },
]


# ==========================================================================
# F3: Scoring formula
# ==========================================================================

def compute_engineering_unlock_score(candidate: dict[str, Any]) -> dict[str, Any]:
    """Score a breakthrough candidate using the F3 formula.

    EngineeringUnlockScore =
        0.30 × new_case_type_coverage
      + 0.25 × production_semantics_error_fix
      + 0.20 × audit_explanation_capability
      + 0.15 × performance_incremental_capability
      + 0.10 × cross_module_reuse

    Priority = EngineeringUnlockScore × VerificationReadiness
               / (ProofDifficulty + ImplementationDistance)

    High RiskIfWrong projects require counterexample search and spec freeze first.
    """
    # Heuristic scores from candidate metadata
    eus = candidate.get("priority_raw", 0.0)

    # ProofDifficulty and VerificationReadiness from estimated_complexity
    complexity = candidate.get("estimated_complexity", 3)
    proof_difficulty = complexity
    impl_distance = max(1, complexity - 1)
    verification_readiness = max(1, 6 - complexity)  # simpler = more ready

    priority = eus * verification_readiness / (proof_difficulty + impl_distance)
    priority = round(priority, 3)

    return {
        **candidate,
        "engineering_unlock_score": round(eus, 2),
        "proof_difficulty": proof_difficulty,
        "implementation_distance": impl_distance,
        "verification_readiness": verification_readiness,
        "priority_score": priority,
    }


def ranked_candidates() -> list[dict[str, Any]]:
    """Return candidates sorted by priority score (highest first)."""
    scored = [compute_engineering_unlock_score(c) for c in CANDIDATES]
    scored.sort(key=lambda c: c["priority_score"], reverse=True)
    return scored


def top_candidates(n: int = 5) -> list[dict[str, Any]]:
    """Return top N candidates by priority score."""
    return ranked_candidates()[:n]
