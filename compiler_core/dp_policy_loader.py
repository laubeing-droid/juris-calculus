"""DP policy loader — epsilon from YAML config, never derived from legal privilege.

Mathematical basis: dp_legal_privilege.py — epsilon is policy config.
Counterexample: epsilon_CN(5)=1.0, epsilon_US(5)=2.5 proves
privilege->epsilon is not a function.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import yaml
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class DPPolicy:
    data_class: str
    epsilon_range: Tuple[float, float]
    allowed_release_mode: str  # blocked / anonymized / aggregated / full
    approval_required: bool
    audit_log_required: bool
    source_id: str  # REQUIRED: no source_id -> reject

    def validate(self) -> List[str]:
        errors = []
        if not self.source_id:
            errors.append(f"DPPolicy[{self.data_class}]: source_id is REQUIRED")
        if self.epsilon_range[0] < 0:
            errors.append(f"DPPolicy[{self.data_class}]: epsilon_min must be >= 0")
        if self.epsilon_range[0] > self.epsilon_range[1]:
            errors.append(f"DPPolicy[{self.data_class}]: epsilon_min > epsilon_max")
        if self.allowed_release_mode == "full" and self.epsilon_range[0] == 0.0:
            errors.append(f"DPPolicy[{self.data_class}]: full release with epsilon=0 is contradictory")
        return errors


@dataclass
class DPPolicyLoader:
    policies: List[DPPolicy] = field(default_factory=list)
    loaded: bool = False

    def load(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            logger.warning("DP_POLICY_NOT_FOUND: %s", filepath)
            return False
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        self.policies = []
        for p in data.get('policies', []):
            eps = p.get('epsilon_range', [0.0, 1.0])
            policy = DPPolicy(
                data_class=p['data_class'],
                epsilon_range=(float(eps[0]), float(eps[1])),
                allowed_release_mode=p.get('allowed_release_mode', 'blocked'),
                approval_required=p.get('approval_required', True),
                audit_log_required=p.get('audit_log_required', True),
                source_id=p.get('source_id', ''),
            )
            errors = policy.validate()
            if errors:
                for e in errors:
                    logger.error("DP_POLICY_INVALID: %s", e)
                continue
            self.policies.append(policy)
        self.loaded = True
        logger.info("DP_POLICY_LOADED: %d policies", len(self.policies))
        return True

    def get_policy(self, data_class: str) -> Optional[DPPolicy]:
        for p in self.policies:
            if p.data_class == data_class:
                return p
        return None

    def check_release(self, data_class: str, proposed_epsilon: float) -> dict:
        policy = self.get_policy(data_class)
        if policy is None:
            return {"allowed": False, "reason": f"No policy for data_class={data_class}"}
        if not policy.source_id:
            return {"allowed": False, "reason": "source_id missing"}
        if proposed_epsilon < policy.epsilon_range[0] or proposed_epsilon > policy.epsilon_range[1]:
            return {
                "allowed": False,
                "reason": f"epsilon={proposed_epsilon} outside range {policy.epsilon_range}",
            }
        return {
            "allowed": True,
            "mode": policy.allowed_release_mode,
            "approval_required": policy.approval_required,
        }
