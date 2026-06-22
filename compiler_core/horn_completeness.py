"""G8 Horn completeness wrapper — D1-D6 formalization layer.

Provides derived iteration bounds, saturation/convergence signaling,
and provenance witness generation on top of the existing FixpointEvaluator.

Per D-phase requirements:
  - D1: Formal Horn immediate consequence operator T_H
  - D2: Lean theorems for monotonicity, termination, least fixed point
  - D3: Eliminate external hbound dependency — derive bound from state space
  - D4: Juris-calculus semantics purification — explicit TRUNCATED status
  - D5: Provenance capabilities — canonical proof witness per conclusion
  - D6: Engineering unlocks — coverage, rule chain tracing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# D1: Formal Horn operator T_H — immediate consequence
# ---------------------------------------------------------------------------

def horn_immediate_consequence(
    facts: dict[str, Any], rules: list[dict[str, Any]]
) -> set[str]:
    """T_H(I) = {head | body ⊆ I for some rule}.
    
    This is the Horn immediate consequence operator. For a set of ground
    facts I and Horn rules (head :- body), T_H(I) returns all heads whose
    bodies are satisfied by I.
    """
    derived: set[str] = set()
    for rule in rules:
        head = rule.get("head", "")
        body = rule.get("body", [])
        if not head:
            continue
        if all(atom in facts for atom in body):
            derived.add(head)
    return derived


# ---------------------------------------------------------------------------
# D1: Derived iteration bound from Horn state space
# ---------------------------------------------------------------------------

def horn_derived_bound(facts: dict[str, Any], rules: list[dict[str, Any]]) -> int:
    """Compute the derived iteration upper bound for Horn fixpoint.
    
    Derivation: the T_H operator can produce at most N new ground atoms
    where N is the number of distinct heads in the rule set. The iteration
    from the initial facts saturates in at most N steps.
    
    This removes the hardcoded k_max / hbound external dependency.
    """
    heads = {rule.get("head", "") for rule in rules}
    heads.discard("")
    return len(heads)


# ---------------------------------------------------------------------------
# D3/D4: Horn fixpoint with completeness signaling
# ---------------------------------------------------------------------------

@dataclass
class HornCompletenessResult:
    saturated: bool         # True if fixpoint reached within derived_bound
    truncated: bool         # True if max_iter insufficient to reach fixpoint
    derived_bound: int      # Bound derived from rule head count
    iterations: int         # Actual iterations executed
    derived_count: int      # Number of new atoms derived
    proof_witnesses: list[dict[str, Any]] = field(default_factory=list)


def horn_fixpoint_with_completeness(
    initial_facts: dict[str, Any],
    rules: list[dict[str, Any]],
    max_iter: int | None = None,
) -> tuple[set[str], HornCompletenessResult]:
    """Compute Horn least fixed point with D-style completeness tracking.
    
    Args:
        initial_facts: Starting set of ground facts (dict keys = fact IDs)
        rules: Horn rules with 'head' and 'body' (list of fact IDs)
        max_iter: Optional explicit bound. If None, derived from rule heads.
    
    Returns:
        (saturated_facts, completeness_result)
        - saturated_facts: set of all derived fact IDs
        - completeness_result: convergence/truncation status, bound, witnesses
    """
    derived_bound = horn_derived_bound(initial_facts, rules)
    if max_iter is None:
        max_iter = derived_bound + 1  # +1 for convergence check
    elif max_iter < 1:
        max_iter = 1

    facts: set[str] = set(initial_facts.keys())
    saturated = False
    iteration = 0
    witnesses: list[dict[str, Any]] = []

    while iteration < max_iter:
        iteration += 1
        new_facts = horn_immediate_consequence(
            {f: True for f in facts}, rules
        )
        newly_derived = new_facts - facts

        if not newly_derived:
            saturated = True
            break

        # Record proof witness for each newly derived fact
        for fact_id in sorted(newly_derived):
            activating_rules = [
                r for r in rules
                if r.get("head") == fact_id
                and all(a in facts for a in r.get("body", []))
            ]
            witnesses.append({
                "fact": fact_id,
                "iteration": iteration,
                "activating_rule": activating_rules[0].get("head", "") if activating_rules else "unknown",
                "body_atoms": activating_rules[0].get("body", []) if activating_rules else [],
                "supporting_facts": sorted(facts & set(activating_rules[0].get("body", []))) if activating_rules else [],
            })

        facts |= newly_derived

    return facts, HornCompletenessResult(
        saturated=saturated,
        truncated=not saturated and iteration >= max_iter,
        derived_bound=derived_bound,
        iterations=iteration,
        derived_count=len(facts) - len(initial_facts),
        proof_witnesses=witnesses,
    )


# ---------------------------------------------------------------------------
# D5: Provenance — distinguishing completeness vs witness vs support
# ---------------------------------------------------------------------------

@dataclass
class ConclusionProvenance:
    conclusion: str
    complete: bool              # 1. conclusion completeness
    canonical_witness: dict[str, Any] | None  # 2. at least one proof witness
    minimal_support_set: list[str]  # 3. all minimal supporting facts
    rule_chain: list[str]       # 4. full syntactic proof path (rule IDs)

    @staticmethod
    def from_horn_result(
        conclusion: str,
        facts: set[str],
        completeness: HornCompletenessResult,
        rules: list[dict[str, Any]],
    ) -> "ConclusionProvenance":
        """Build provenance from Horn fixpoint result."""
        # Find witness
        witness = None
        for w in completeness.proof_witnesses:
            if w["fact"] == conclusion:
                witness = w
                break

        # Minimal support set: body atoms from the first applicable rule
        minimal_support: list[str] = []
        if witness:
            minimal_support = witness.get("body_atoms", [])

        # Rule chain: collect rule IDs for each witness
        rule_chain: list[str] = []
        for w in completeness.proof_witnesses:
            if w["fact"] == conclusion or w["fact"] in minimal_support:
                rule_chain.append(w.get("activating_rule", ""))

        return ConclusionProvenance(
            conclusion=conclusion,
            complete=completeness.saturated,
            canonical_witness=witness,
            minimal_support_set=minimal_support,
            rule_chain=rule_chain,
        )
