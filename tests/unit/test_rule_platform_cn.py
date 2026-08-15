"""W7：cn-official 规则工程平台与首域晋级门禁测试。

覆盖方案 §13 与 Gate：
- 第一方来源缺失时 staging/晋级全部拒绝，manifest 保持 blocked；
- 每条规则必须绑定 snapshot hash 与 locator；
- 三类审核分离，缺任一类不得 domain_ready；
- manifest 状态只能由有效 HumanPromotionReceiptV1 显式晋级。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from compiler_core.rule_platform_cn import (
    CandidateRuleV4,
    DomainReviewReceiptV1,
    FIRST_RULE_DOMAIN,
    HumanPromotionReceiptV1,
    RulePlatformCN,
    RulePlatformError,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def h(prefix: str) -> str:
    return "sha256:" + (prefix * 32)[:64]


def _candidate(**overrides) -> CandidateRuleV4:
    payload = dict(
        rule_id="R-CPL-ART85-APPEAL",
        domain=FIRST_RULE_DOMAIN,
        snapshot_ref="src-cpl-2021",
        snapshot_raw_hash=h("aa"),
        locator="art_85",
        publication_time="2021-12-24T00:00:00Z",
        effective_time="2022-01-01T00:00:00Z",
        revision_status="revised",
        vocabulary_terms=("appeal_period", "judgment", "start_point", "expiry_point", "second_instance"),
    )
    payload.update(overrides)
    return CandidateRuleV4(**payload)


def _review(role: str, rule_id: str = "R-CPL-ART85-APPEAL") -> DomainReviewReceiptV1:
    return DomainReviewReceiptV1(
        role=role,
        rule_id=rule_id,
        verdict="approved",
        notes_digest=h("99"),
        issued_at="2026-08-15T00:00:00Z",
    )


def _promotion() -> HumanPromotionReceiptV1:
    return HumanPromotionReceiptV1(
        receipt_id="promo-0001",
        pack_id="cn-official",
        rule_domain=FIRST_RULE_DOMAIN,
        approver_role="rule_maintainer",
        approval_ref="approval-0001",
        issued_at="2026-08-16T00:00:00Z",
    )


class TestCandidateValidation:
    def test_candidate_requires_snapshot_hash_and_locator(self):
        with pytest.raises(RulePlatformError) as exc:
            _candidate(snapshot_raw_hash="no-hash")
        assert exc.value.code == "INVALID_DIGEST"
        with pytest.raises(RulePlatformError) as exc:
            _candidate(locator="")
        assert exc.value.code == "MISSING_REQUIRED_FIELD"

    def test_unknown_domain_or_vocabulary_rejected(self):
        with pytest.raises(RulePlatformError) as exc:
            _candidate(domain="criminal_sentencing")
        assert exc.value.code == "UNKNOWN_RULE_DOMAIN"
        with pytest.raises(RulePlatformError) as exc:
            _candidate(vocabulary_terms=("appeal_period", "invented_term"))
        assert exc.value.code == "UNKNOWN_VOCABULARY_TERM"


class TestFirstPartyGate:
    def test_staging_blocked_without_first_party_snapshot(self):
        platform = RulePlatformCN()
        with pytest.raises(RulePlatformError) as exc:
            platform.stage_candidate(_candidate())
        assert exc.value.code == "FIRST_PARTY_SOURCE_UNAVAILABLE"
        assert platform.build_status() == "blocked"

    def test_promotion_blocked_without_first_party_snapshot(self):
        platform = RulePlatformCN()
        with pytest.raises(RulePlatformError) as exc:
            platform.promote(_promotion())
        assert exc.value.code == "FIRST_PARTY_SOURCE_UNAVAILABLE"


class TestReviewSeparation:
    def _staged_platform(self) -> RulePlatformCN:
        platform = RulePlatformCN()
        platform.declare_first_party_snapshot(available=True)
        platform.stage_candidate(_candidate())
        return platform

    def test_domain_not_ready_until_all_three_reviews_approved(self):
        platform = self._staged_platform()
        platform.record_review(_review("source_reviewer"))
        platform.record_review(_review("interpretation_reviewer"))
        assert platform.domain_ready() is False
        platform.record_review(_review("legal_reviewer"))
        assert platform.domain_ready() is True

    def test_rejected_review_blocks_domain(self):
        platform = self._staged_platform()
        platform.record_review(_review("source_reviewer"))
        platform.record_review(_review("interpretation_reviewer"))
        rejected = DomainReviewReceiptV1(
            role="legal_reviewer",
            rule_id="R-CPL-ART85-APPEAL",
            verdict="rejected",
            notes_digest=h("88"),
            issued_at="2026-08-15T00:00:00Z",
        )
        platform.record_review(rejected)
        assert platform.domain_ready() is False

    def test_review_roles_separated_from_runtime_receipts(self):
        with pytest.raises(RulePlatformError) as exc:
            _review("runtime_test_runner")
        assert exc.value.code == "INVALID_ENUM"


class TestPromotionGate:
    def test_generator_never_promotes(self):
        platform = RulePlatformCN()
        platform.declare_first_party_snapshot(available=True)
        platform.stage_candidate(_candidate())
        for role in ("source_reviewer", "interpretation_reviewer", "legal_reviewer"):
            platform.record_review(_review(role))
        assert platform.build_status() == "partial"
        platform.generator_may_not_promote()
        assert platform.build_status() == "partial"

    def test_full_promotion_requires_receipt_and_ready_domain(self):
        platform = RulePlatformCN()
        platform.declare_first_party_snapshot(available=True)
        platform.stage_candidate(_candidate())
        with pytest.raises(RulePlatformError) as exc:
            platform.promote(_promotion())
        assert exc.value.code == "DOMAIN_NOT_READY"
        for role in ("source_reviewer", "interpretation_reviewer", "legal_reviewer"):
            platform.record_review(_review(role))
        assert platform.promote(_promotion()) == "active"

    def test_invalid_promotion_receipt_rejected(self):
        with pytest.raises(RulePlatformError) as exc:
            HumanPromotionReceiptV1(
                receipt_id="promo-x",
                pack_id="other-pack",
                rule_domain=FIRST_RULE_DOMAIN,
                approver_role="rule_maintainer",
                approval_ref="approval-x",
                issued_at="2026-08-16T00:00:00Z",
            )
        assert exc.value.code == "UNKNOWN_PACK"


class TestTrackedManifestStaysBlocked:
    def test_cn_official_manifest_remains_blocked(self):
        """施工不得借基础设施 PASS 宣称法律内容 ready；manifest 保持 blocked。"""

        manifest_path = REPO_ROOT / "configs" / "packs" / "cn-official" / "manifest.yaml"
        document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert document["status"] == "blocked"
        assert document["rule_files"] == []
        assert document["config_files"] == []

    def test_layering_directories_exist(self):
        pack_root = REPO_ROOT / "configs" / "packs" / "cn-official"
        for layer in ("staging", "build", "release"):
            assert (pack_root / layer / "README.md").is_file()
