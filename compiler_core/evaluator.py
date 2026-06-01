"""
juris-calculus: Fixpoint Legal Reasoning Engine
Author: Laupinco — Hokkien Computational Jurisprudence Enthusiast (Powered by Gemini & WorkBuddy & DeepSeek-V4 Pro)
License: Apache 2.0

Production-grade monotonic fixpoint iterator with:
  - Reverse-indexed rule triggering (fact→rule O(1) lookup)
  - Exception chain penetration with cycle-safe memoization
  - Concept registry scoring for cross-domain rule evaluation
  - CRITICAL_CLARITY_FAILURE: auto-halt on consecutive low-confidence streaks
  - Implicit dependency detection across exception chains
"""

from typing import List, Dict, Set, Tuple, Optional
from compiler_core.types import LegalRule, LegalFact, LegalClaim, TaintNode, IRState
from compiler_core.domain_config import DomainConfig, get_domain_config


class CriticalClarityFailure(Exception):
    """Raised when N consecutive rule applications fall below the critical_score_threshold.
    This is a feature, not a bug: the engine is honestly refusing to hallucinate."""
    def __init__(self, msg, trace):
        super().__init__(msg)
        self.trace = trace


def compute_formalizable(rule: LegalRule, k_depth: int, config: DomainConfig) -> Tuple[float, List[str]]:
    """
    Compute a rule's formalizability score (0.0–1.0) given:
      - depth: how deep in the exception chain are we? (depth penalty via k_max)
      - head_type: HORN rules score higher than NON_HORN (semantic brittleness penalty)
      - concept coverage: what fraction of this rule's concepts are in the jurisdiction registry?
      - mechanical_exception: rules that admit mechanical exceptions are more reliable
    """
    cache_key = str(config.domain.value)
    if not hasattr(rule, '_cache'):
        rule._cache = {}
    if cache_key not in rule._cache:
        concepts = rule.concepts or []
        if not concepts:
            rule._cache[cache_key] = (1.0, [])
        else:
            registered = [c for c in concepts if c in config.concept_registry]
            unregistered = [c for c in concepts if c not in config.concept_registry]
            rule._cache[cache_key] = (len(registered) / len(concepts), unregistered)
    
    coverage, unregistered = rule._cache[cache_key]
    depth_penalty = min(1.0, config.k_max / max(1, k_depth))
    horn_bonus = 1.0 if rule.head_type == "HORN" else 0.0
    mechanical_bonus = 1.0 if rule.mechanical_exception else 0.0
    
    w = config.weights  # (depth_wt, horn_wt, concept_wt, mechanical_wt)
    score = depth_penalty * w[0] + horn_bonus * w[1] + coverage * w[2] + mechanical_bonus * w[3]
    
    # Cap: non-HORN or non-mechanical rules max out at 0.4 (inherent brittleness)
    if horn_bonus == 0 or mechanical_bonus == 0:
        score = min(score, 0.4)
    
    return round(score, 2), unregistered


class FixpointEvaluator:
    """
    Deterministic legal logic core. Zero LLM hallucination.
    Runs monotonic fixed-point iteration over structured facts until convergence.

    Cross-jurisdictional compatibility:
    This engine operates on first-order predicate logic and is jurisdiction-agnostic.
    It is natively compatible with IRAC (Issue, Rule, Application, Conclusion) under
    Common Law, as well as syllogistic deduction under Civil Law systems.
    """

    # Patterns that indicate implicit legal dependencies across exception chains
    IMPLICIT_DEPENDENCY_PATTERNS = [
        "unless otherwise provided", "save as otherwise stipulated",
        "subject to", "notwithstanding", "without prejudice to"
    ]

    def __init__(self, rules: List[LegalRule], config: DomainConfig = None):
        self.rules = {r.id: r for r in rules}
        self.config = config or get_domain_config()

        # Depth cache (memoization)
        self._depth_cache: Dict[str, int] = {}
        self.rule_depths: Dict[str, int] = {}

        # Reverse index: fact_id → [rule_ids] for O(1) triggering
        self.fact_to_rules: Dict[str, List[str]] = {}
        for r in rules:
            self.rule_depths[r.id] = self._compute_depth(r.id)
            for premise in r.premise_atoms:
                self.fact_to_rules.setdefault(premise, []).append(r.id)
            for exception in r.exception_chain:
                self.fact_to_rules.setdefault(exception, []).append(r.id)

        self.implicit_dependencies = self._detect_implicit_deps()

    def _compute_depth(self, rule_id: str, visited: set = None) -> int:
        """Recursive depth in exception chain, with cycle detection."""
        if visited is None and rule_id in self._depth_cache:
            return self._depth_cache[rule_id]
        if visited is None:
            visited = set()
        if rule_id in visited:
            return 0
        visited.add(rule_id)
        rule = self.rules.get(rule_id)
        if not rule or not rule.exception_chain:
            result = 1
        else:
            result = 1 + max(
                (self._compute_depth(e, visited.copy()) for e in rule.exception_chain),
                default=0
            )
        self._depth_cache[rule_id] = result
        return result

    def _detect_implicit_deps(self) -> List[Dict]:
        """Detect implicit dependencies across exception chain boundaries."""
        deps = []
        for rule in self.rules.values():
            for exception_id in rule.exception_chain:
                exception_rule = self.rules.get(exception_id)
                if exception_rule:
                    for premise in exception_rule.premise_atoms:
                        for pattern in self.IMPLICIT_DEPENDENCY_PATTERNS:
                            if pattern.lower() in premise.lower():
                                deps.append({
                                    "rule": rule.id,
                                    "exception": exception_id,
                                    "pattern": pattern
                                })
        return deps

    def _check_premises(self, rule: LegalRule, state: IRState) -> Tuple[bool, List[str]]:
        """Check if all premises of a rule are satisfied."""
        missing = [
            atom for atom in rule.premise_atoms
            if atom not in state.facts and atom not in state.claims
        ]
        return len(missing) == 0, missing

    def _check_exceptions(self, rule: LegalRule, state: IRState) -> Optional[str]:
        """Check if any exception in the chain is triggered."""
        for exception_id in rule.exception_chain:
            exception_rule = self.rules.get(exception_id)
            if exception_rule:
                satisfied, _ = self._check_premises(exception_rule, state)
                if satisfied:
                    return exception_id
        return None

    def _apply_rule(self, rule: LegalRule, state: IRState, depth: int) -> Optional[LegalClaim]:
        """Apply a single rule: check premises → check exceptions → score → produce claim."""
        satisfied, _ = self._check_premises(rule, state)
        if not satisfied:
            return None

        # Exception chain penetration: if exception triggered, recurse into it
        triggered_exception = self._check_exceptions(rule, state)
        if triggered_exception:
            exception_rule = self.rules.get(triggered_exception)
            if exception_rule:
                return self._apply_rule(exception_rule, state, depth + 1)

        score, unregistered = compute_formalizable(rule, depth, self.config)
        taint_nodes = []

        if score < self.config.taint_threshold:
            source = ", ".join(unregistered) if unregistered else f"depth={depth}"
            taint_nodes.append(TaintNode(
                rule_id=rule.id,
                claim_id=rule.head_claim,
                taint_source=source,
                formalizable_score=score,
                depth=depth
            ))

        return LegalClaim(
            id=rule.head_claim,
            description=f"{rule.id}: {rule.head_claim}",
            confidence=score,
            taint_chain=taint_nodes,
            requires_human_review=(
                score < self.config.taint_threshold or
                score < self.config.hard_audit_threshold
            )
        )

    def evaluate(self, state: IRState) -> IRState:
        """
        Run fixpoint iteration until convergence or max_iterations.
        May raise CriticalClarityFailure if consecutive low-confidence streaks exceed threshold.

        This is the engine's self-defense mechanism: it refuses to chain together
        too many unreliable deductions, preferring honest silence over hallucination.
        """
        low_streak = 0
        streak_log = []

        if self.implicit_dependencies:
            for dep in self.implicit_dependencies[:5]:
                print(f"  [IMPLICIT] {dep['rule']} → {dep['exception']}: {dep['pattern']}")

        while state.iteration_count < state.max_iterations:
            state.iteration_count += 1
            new_claims_this_round = 0
            triggered_rule_ids = set()

            # Reverse-index lookup: which rules care about our current facts/claims?
            for fact_id in set(state.facts.keys()) | set(state.claims.keys()):
                for rule_id in self.fact_to_rules.get(fact_id, []):
                    triggered_rule_ids.add(rule_id)

            for rule_id in triggered_rule_ids:
                if rule_id in state.rules_applied or rule_id not in self.rules:
                    continue

                rule = self.rules[rule_id]
                claim = self._apply_rule(rule, state, self.rule_depths.get(rule_id, 1))
                if claim is None:
                    continue

                # CRITICAL_CLARITY_FAILURE guard
                if claim.confidence < self.config.critical_score_threshold:
                    low_streak += 1
                    streak_log.append({"rule": rule_id, "score": claim.confidence})
                    if low_streak >= self.config.critical_streak_max:
                        raise CriticalClarityFailure(
                            f"Consecutive {low_streak} rules scored below "
                            f"{self.config.critical_score_threshold}. Engine halted.",
                            streak_log
                        )
                else:
                    low_streak = 0
                    streak_log = []

                if claim.id not in state.claims:
                    state.claims[claim.id] = claim
                    state.rules_applied.add(rule_id)
                    new_claims_this_round += 1

            if new_claims_this_round == 0:
                break  # Fixpoint reached

        return state

    def validate_transition(self, from_state: str, to_state: str) -> bool:
        """Validate procedural state transition against domain config."""
        return to_state in self.config.valid_transitions.get(from_state, [])
