"""W7：中国官方规则工程平台与首个完整规则域（民事诉讼期间计算）。

依据：20260815 施工方案 §13。状态原则：

- `cn-official` 在第一方来源与正式规则未就绪前继续 blocked；
  本模块建设完整 staging/build/release 分层，不原地解锁空包。
- 规则晋级由外部人工授权；manifest 状态不能由生成器自动修改。
- 法律解释、工程编码和测试预期由不同字段、不同收据承载。
- 真实 pilot 使用去标识化合成边界事实，不写入私人案件。
- 首域未完成时对外状态只能是 BLOCKED 或 PARTIAL。

平台流水线：

    first-party source snapshot
      -> structure extraction
      -> candidate RuleV4
      -> source/interpretation/legal review
      -> mutation and boundary fixtures
      -> LMM semantic conformance
      -> human promotion receipt
      -> signed pack build
      -> JC load/replay
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from compiler_core.jcs import jcs_digest


PACK_ID = "cn-official"
FIRST_RULE_DOMAIN = "civil_procedure_time_computation"
PACK_STATUSES = ("blocked", "partial", "active")

_CANONICAL_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

# 首域类型化词汇表：文书类型、期间类型、起算、届满、顺延、中止/中断、例外、程序阶段。
# 词汇表本身是工程脚手架；条文绑定值只能来自第一方快照，不得在此发明。
DOMAIN_VOCABULARY = {
    "document_types": (
        "judgment",
        "ruling",
        "mediation_statement",
        "decision",
        "notice",
    ),
    "period_types": (
        "appeal_period",
        "filing_period",
        "evidence_period",
        "performance_period",
        "objection_period",
    ),
    "computation_aspects": (
        "start_point",
        "expiry_point",
        "extension_on_holiday",
        "suspension",
        "interruption",
        "in_transit_exclusion",
    ),
    "procedure_stages": (
        "first_instance",
        "second_instance",
        "retrial",
        "execution",
    ),
    "version_points": (
        "publication_time",
        "effective_time",
        "revision_time",
    ),
}

REVIEW_ROLES = ("source_reviewer", "interpretation_reviewer", "legal_reviewer")


class RulePlatformError(ValueError):
    """平台门禁错误；code 稳定可机读。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _require_nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RulePlatformError("MISSING_REQUIRED_FIELD", name)
    return value


def _require_canonical_time(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _CANONICAL_TIME_RE.match(value):
        raise RulePlatformError("NONCANONICAL_TIME", f"{name}={value!r}")
    return value


@dataclass(frozen=True)
class CandidateRuleV4:
    """候选规则：必须绑定精确官方文本快照、条款 locator、公布/施行/修订状态。"""

    rule_id: str
    domain: str
    snapshot_ref: str
    snapshot_raw_hash: str
    locator: str
    publication_time: str
    effective_time: str
    revision_status: str
    vocabulary_terms: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _require_nonempty(self.rule_id, "rule_id"))
        if self.domain != FIRST_RULE_DOMAIN:
            raise RulePlatformError("UNKNOWN_RULE_DOMAIN", self.domain)
        object.__setattr__(self, "snapshot_ref", _require_nonempty(self.snapshot_ref, "snapshot_ref"))
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.snapshot_raw_hash):
            raise RulePlatformError("INVALID_DIGEST", "snapshot_raw_hash")
        object.__setattr__(self, "locator", _require_nonempty(self.locator, "locator"))
        object.__setattr__(self, "publication_time", _require_canonical_time(self.publication_time, "publication_time"))
        object.__setattr__(self, "effective_time", _require_canonical_time(self.effective_time, "effective_time"))
        if self.revision_status not in ("original", "revised", "pending_revision"):
            raise RulePlatformError("INVALID_ENUM", f"revision_status={self.revision_status!r}")
        flat_terms = {term for group in DOMAIN_VOCABULARY.values() for term in group}
        unknown = sorted(set(self.vocabulary_terms) - flat_terms)
        if unknown:
            raise RulePlatformError("UNKNOWN_VOCABULARY_TERM", ", ".join(unknown))
        object.__setattr__(self, "vocabulary_terms", tuple(sorted(set(self.vocabulary_terms))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "domain": self.domain,
            "snapshot_ref": self.snapshot_ref,
            "snapshot_raw_hash": self.snapshot_raw_hash,
            "locator": self.locator,
            "publication_time": self.publication_time,
            "effective_time": self.effective_time,
            "revision_status": self.revision_status,
            "vocabulary_terms": list(self.vocabulary_terms),
        }


@dataclass(frozen=True)
class DomainReviewReceiptV1:
    """三类审核分离收据：来源、解释、法律审核各自独立。"""

    role: str
    rule_id: str
    verdict: str
    notes_digest: str
    issued_at: str

    def __post_init__(self) -> None:
        if self.role not in REVIEW_ROLES:
            raise RulePlatformError("INVALID_ENUM", f"role={self.role!r}")
        object.__setattr__(self, "rule_id", _require_nonempty(self.rule_id, "rule_id"))
        if self.verdict not in ("approved", "rejected", "blocked"):
            raise RulePlatformError("INVALID_ENUM", f"verdict={self.verdict!r}")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.notes_digest):
            raise RulePlatformError("INVALID_DIGEST", "notes_digest")
        object.__setattr__(self, "issued_at", _require_canonical_time(self.issued_at, "issued_at"))


@dataclass(frozen=True)
class HumanPromotionReceiptV1:
    """人工晋级收据：manifest 状态变更的唯一授权来源。"""

    receipt_id: str
    pack_id: str
    rule_domain: str
    approver_role: str
    approval_ref: str
    issued_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "receipt_id", _require_nonempty(self.receipt_id, "receipt_id"))
        if self.pack_id != PACK_ID:
            raise RulePlatformError("UNKNOWN_PACK", self.pack_id)
        if self.rule_domain != FIRST_RULE_DOMAIN:
            raise RulePlatformError("UNKNOWN_RULE_DOMAIN", self.rule_domain)
        if self.approver_role not in ("rule_maintainer", "legal_harness_approver"):
            raise RulePlatformError("INVALID_ENUM", f"approver_role={self.approver_role!r}")
        object.__setattr__(self, "approval_ref", _require_nonempty(self.approval_ref, "approval_ref"))
        object.__setattr__(self, "issued_at", _require_canonical_time(self.issued_at, "issued_at"))

    @property
    def receipt_digest(self) -> str:
        return jcs_digest({
            "receipt_id": self.receipt_id,
            "pack_id": self.pack_id,
            "rule_domain": self.rule_domain,
            "approver_role": self.approver_role,
            "approval_ref": self.approval_ref,
            "issued_at": self.issued_at,
        })


class RulePlatformCN:
    """staging/build/release 分层与晋级门禁。

    生成器在任何情况下都不得自动把 manifest 状态提升为 active；
    只有携带有效 HumanPromotionReceiptV1 的显式调用才允许变更，
    且第一方来源缺失时保持 blocked。
    """

    def __init__(self) -> None:
        self._candidates: dict[str, CandidateRuleV4] = {}
        self._reviews: dict[str, list[DomainReviewReceiptV1]] = {}
        self._first_party_snapshot_available = False
        self._promotion_receipt: HumanPromotionReceiptV1 | None = None

    def declare_first_party_snapshot(self, *, available: bool) -> None:
        """第一方来源可得性只能由外部取证流程声明，不得由生成器伪造。"""

        self._first_party_snapshot_available = bool(available)

    def stage_candidate(self, candidate: CandidateRuleV4) -> None:
        if not self._first_party_snapshot_available:
            raise RulePlatformError("FIRST_PARTY_SOURCE_UNAVAILABLE", candidate.snapshot_ref)
        self._candidates[candidate.rule_id] = candidate

    def record_review(self, receipt: DomainReviewReceiptV1) -> None:
        if receipt.rule_id not in self._candidates:
            raise RulePlatformError("UNKNOWN_RULE", receipt.rule_id)
        self._reviews.setdefault(receipt.rule_id, []).append(receipt)

    def review_state(self, rule_id: str) -> dict[str, str]:
        return {receipt.role: receipt.verdict for receipt in self._reviews.get(rule_id, ())}

    def domain_ready(self) -> bool:
        """首域完成判据：每条候选规则三类审核全部 approved。"""

        if not self._candidates:
            return False
        for rule_id in self._candidates:
            verdicts = self.review_state(rule_id)
            if any(verdicts.get(role) != "approved" for role in REVIEW_ROLES):
                return False
        return True

    def build_status(self) -> str:
        """对外状态只能是 blocked/partial/active；状态由事实派生，不可写入。

        基础设施 PASS 不升级法律内容：没有有效人工晋级收据时，
        最多只能是 partial（已有候选）或 blocked（无候选）。
        """

        if self._promotion_receipt is not None:
            return "active"
        return "partial" if self._candidates else "blocked"

    def promote(self, receipt: HumanPromotionReceiptV1) -> str:
        """人工晋级：缺第一方来源、首域未就绪或收据无效时一律拒绝。"""

        if not self._first_party_snapshot_available:
            raise RulePlatformError("FIRST_PARTY_SOURCE_UNAVAILABLE", receipt.pack_id)
        if not self.domain_ready():
            raise RulePlatformError("DOMAIN_NOT_READY", receipt.rule_domain)
        self._promotion_receipt = receipt
        return self.build_status()

    def generator_may_not_promote(self) -> None:
        """显式护栏：生成器路径永远不能触达 active。

        生成器不携带晋级收据；任何时刻它看到的派生状态都不是 active。
        """

        assert self._promotion_receipt is None or self.build_status() == "active"
        if self._promotion_receipt is None:
            assert self.build_status() in ("blocked", "partial")
