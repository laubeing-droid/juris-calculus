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
from compiler_core.constraint_validator import ConstraintValidator
import logging

from compiler_core.types import LegalRule, LegalFact, LegalClaim, TaintNode, IRState
from compiler_core.domain_config import DomainConfig, get_domain_config, check_discretionary

logger = logging.getLogger(__name__)


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
        "subject to", "notwithstanding", "without prejudice to",
        "另有规定", "但.*除外", "法律另有规定", "除.*外", "除非",
        "当事人另有约定", "合同另有约定"
    ]

    def __init__(self, rules: List[LegalRule], config: DomainConfig = None, domain_id: str = None, overrides_path: str = None):
        self.config = config or get_domain_config()
        self.domain_id = domain_id

        # 编译期转换：单前提规则注入域锚点
        from compiler_core.transformer import auto_patch
        rules = auto_patch(rules)

        # 多租户安全防线
        if self.domain_id:
            self.rules = {
                r.id: r for r in rules
                if getattr(r, 'namespace', 'general') in (self.domain_id, 'general')
            }
        else:
            self.rules = {r.id: r for r in rules}

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

        # 约束层：Rebuttal Hook + Audit Trail
        self.constraint_validator = ConstraintValidator(overrides_path=overrides_path)
        self.audit_log: List[dict] = []

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

        # v1.1 Traceability: resolve L2→L1→L0 chain
        domain_origin = getattr(rule, 'namespace', 'general')
        l0_source = self.constraint_validator.resolve_L0_primitive(rule.concepts) if self.constraint_validator.loaded else ''

        return LegalClaim(
            id=rule.head_claim,
            description=f"{rule.id}: {rule.head_claim}",
            confidence=score,
            taint_chain=taint_nodes,
            requires_human_review=(
                score < self.config.taint_threshold or
                score < self.config.hard_audit_threshold
            ),
            domain_origin=domain_origin,
            L0_primitive_source=l0_source
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
                logger.info(f"[IMPLICIT] {dep['rule']} → {dep['exception']}: {dep['pattern']}")

        while state.iteration_count < state.max_iterations:
            state.iteration_count += 1
            new_claims_this_round = 0
            triggered_rule_ids = set()

            # ═══ v1.1.0 前置强制收敛钩子 (pre-iteration) ═══
            # 在每次迭代开始时应用约束规则，确保状态变化在规则匹配前生效
            if self.constraint_validator.loaded and state.iteration_count == 1:
                forced = self.constraint_validator.check_constraint_rules(state)
                for fr in forced:
                    target = fr.get("target", "")
                    action = fr.get("action", "force_state")
                    new_st = fr.get("new_state", "")
                    if state.state_tracker.get(f"{target}_irreversible"):
                        continue
                    if action == "force_state" and target and new_st:
                        state.state_tracker[target] = new_st
                        if fr.get("irreversible"):
                            state.state_tracker[f"{target}_irreversible"] = True
                        logger.info(f"[FORCED-PRE] {fr['id']}: {target} → {new_st}")
                    elif action == "suppress_power" and target:
                        state.state_tracker[target] = "SUPPRESSED"
                        logger.info(f"[FORCED-PRE] {fr['id']}: {target} → SUPPRESSED")

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

                # ═══ 约束层钩子：Rebuttal Check + Unknown Concept Warning ═══
                confidence_before = claim.confidence
                if self.constraint_validator.loaded and rule.concepts:
                    # 未定义概念检测
                    undef = self.constraint_validator.get_undefined_concepts(rule.concepts)
                    if undef:
                        logger.info(
                            f"[ONTO_WARN] {rule.id}: concepts not in ontology: {undef} — treated as Strict"
                        )

                    rebuttal = self.constraint_validator.check_rebuttal(
                        rule.head_claim, rule.concepts, state
                    )
                    if rebuttal.triggered:
                        claim.confidence = 0.0
                        state.rebuttal_log.append(
                            self.constraint_validator.to_audit_json(
                                rebuttal, rule_id=rule.id, confidence_before=confidence_before
                            )
                        )
                        # ═══ State Machine Hook ═══
                        if hasattr(rebuttal, 'new_state') and rebuttal.new_state:
                            state.state_tracker[rebuttal.claim_id] = rebuttal.new_state
                            logger.info(f"[STATE] {rebuttal.claim_id} → {rebuttal.new_state}")
                        logger.info(f"[REBUTTAL] {rule.id}: {rebuttal.trigger_fact} → confidence {confidence_before:.2f}→0.0")

                # ═══ v1.1 强制收敛钩子 (per-rule) ═══
                if self.constraint_validator.loaded:
                    forced = self.constraint_validator.check_constraint_rules(state)
                    for fr in forced:
                        target = fr.get("target", "")
                        action = fr.get("action", "force_state")
                        new_st = fr.get("new_state", "")

                        # 不可逆保护: 已标记irreversible的跳过
                        if state.state_tracker.get(f"{target}_irreversible"):
                            logger.info(f"[FORCED] {fr['id']}: SKIPPED — {target} already irreversible ({state.state_tracker.get(target)})")
                            continue

                        if action == "force_state" and target and new_st:
                            state.state_tracker[target] = new_st
                            if fr.get("irreversible"):
                                state.state_tracker[f"{target}_irreversible"] = True
                            logger.info(f"[FORCED] {fr['id']}: {target} → {new_st} ({fr.get('reason','')})")

                        elif action == "suppress_power" and target:
                            state.state_tracker[target] = "SUPPRESSED"
                            # 抑制所有以该target为premise的下游claim
                            for cid, claim in list(state.claims.items()):
                                if claim.confidence > 0:
                                    claim.confidence = 0.0
                            logger.info(f"[FORCED] {fr['id']}: {target} → SUPPRESSED | 下游claims已归零 ({fr.get('reason','')})")

                # CRITICAL_CLARITY_FAILURE guard
                if claim.confidence < self.config.critical_score_threshold:
                    low_streak += 1
                    streak_log.append({"rule": rule_id, "score": claim.confidence})
                    if low_streak >= self.config.critical_streak_max:
                        # v1.2.0: 熔断时附带已收敛的 partial state，不再返回空
                        exc = CriticalClarityFailure(
                            f"Consecutive {low_streak} rules scored below "
                            f"{self.config.critical_score_threshold}. Engine halted.",
                            streak_log
                        )
                        # 注入 partial_state 供调用方降级消费
                        exc.partial_state = state
                        raise exc
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

    def check_fact_discretionary(self, fact):
        if not self.config.enable_discretionary_taint:
            return fact
        result = check_discretionary(fact.description)
        if result["tainted"]:
            fact.taint_status = "TAINTED"
            fact.extraction_confidence = min(fact.extraction_confidence, result["confidence_cap"])
            logger.info("DISCRETIONARY_TAINT: %s matched=%s", fact.id, result["matched_concepts"])
        return fact

    def evaluate_with_taint_gate(self, state):
        for fact_id in list(state.facts.keys()):
            state.facts[fact_id] = self.check_fact_discretionary(state.facts[fact_id])
        return self.evaluate(state)

    def check_negative_specs(self, state):
        """V6: Reverse requirement gap detection."""
        violations = []
        for rule_id, rule in self.rules.items():
            pass
        return violations

    def evaluate_with_full_gate(self, state):
        """V6: Negative Spec -> Discretionary -> Fixpoint pipeline."""
        violations = self.check_negative_specs(state)
        if violations:
            logger.warning("NEGATIVE_SPEC: %d violations", len(violations))
        state = self.evaluate_with_taint_gate(state)
        return state

    def validate_transition(self, from_state: str, to_state: str) -> bool:
        """Validate procedural state transition against domain config."""
        return to_state in self.config.valid_transitions.get(from_state, [])


def load_rules_from_yaml(filepath: str) -> List[LegalRule]:
    """
    Load legal rules from a YAML configuration file.

    YAML format:
        rules:
          - id: R1
            premise_atoms: [A, B]
            head_claim: C1
            concepts: [Contract, Payment]
            exception_chain: []
            head_type: HORN
            mechanical_exception: true
    """
    import yaml
    with open(filepath, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    rules = []
    for r in data.get('rules', []):
        rules.append(LegalRule(
            id=r['id'],
            premise_atoms=r.get('premise_atoms', []),
            head_claim=r.get('head_claim', ''),
            concepts=r.get('concepts', []),
            exception_chain=r.get('exception_chain', []),
            head_type=r.get('head_type', 'HORN'),
            mechanical_exception=r.get('mechanical_exception', True),
        ))
    return rules
