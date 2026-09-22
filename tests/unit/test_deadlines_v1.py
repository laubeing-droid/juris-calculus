"""期限算法与日历（03 卡步骤 5，母本 §3.3.5；DEADLINE.no_2027_guess 等）。

冻结样例：未覆盖年份（含 2027 公布前）dueDate=null + calendar_coverage_missing；
刑拘链分阶段无固定 37 日；保全上限核对 + 法院届满日倒计时；年/月期限
月末与闰年按冻结规则；举证/上诉/仲裁锚定独立。
"""
from __future__ import annotations

from datetime import date, datetime, timezone as dt_timezone
from pathlib import Path

import pytest

from compiler_core.deadlines import (
    BRANCH_TABLE,
    CalendarSnapshot,
    DeadlineError,
    add_business_days,
    calendar_shift,
    compute_deadline,
    load_deadline_rules,
    roll_forward,
)

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
NOW = datetime(2026, 9, 19, tzinfo=dt_timezone.utc)


def _calendar(year: int, released: bool = True, overrides: dict[str, bool] | None = None,
              end_year: int | None = None):
    end = end_year or year
    return CalendarSnapshot(
        version=f"cn-test-{year}",
        coverage_start=date(year, 1, 1),
        coverage_end=date(end, 12, 31),
        released=released,
        overrides=overrides or {},
    )


def _event(anchor: str, value: str):
    return {
        anchor: {"value": value, "precision": "date", "timezone": "Asia/Shanghai", "sourceRefs": []},
    }


def _rule(registry, rule_id):
    return registry[(rule_id, "1")]


@pytest.fixture(scope="module")
def registry():
    return load_deadline_rules(CONFIGS)


# ---------------------------------------------------------------------------
# 日历原语
# ---------------------------------------------------------------------------


def test_calendar_shift_month_end_clamp():
    assert calendar_shift(date(2025, 1, 31), 1, "months") == date(2025, 2, 28)
    assert calendar_shift(date(2024, 2, 29), 1, "years") == date(2025, 2, 28)
    assert calendar_shift(date(2024, 1, 29), 1, "months") == date(2024, 2, 29)  # 闰年
    assert calendar_shift(date(2025, 11, 30), 3, "months") == date(2026, 2, 28)
    with pytest.raises(DeadlineError):
        calendar_shift(date(2025, 1, 1), 1, "weeks")


def test_uncovered_calendar_is_fail_closed():
    calendar = _calendar(2026, released=False)
    with pytest.raises(DeadlineError) as error:
        calendar.is_business_day(date(2026, 5, 4))
    assert error.value.code == "calendar_coverage_missing"
    with pytest.raises(DeadlineError):
        _calendar(2026).is_business_day(date(2027, 1, 5))


def test_add_business_days_and_roll_forward():
    # 2026-05-01(五) 劳动节假期 override；周末顺延
    calendar = _calendar(2026, overrides={"2026-05-01": False, "2026-05-04": False})
    assert add_business_days(date(2026, 4, 30), 1, calendar) == date(2026, 5, 5)
    assert roll_forward(date(2026, 5, 2), calendar) == date(2026, 5, 5)


# ---------------------------------------------------------------------------
# 期限计算：普通分支
# ---------------------------------------------------------------------------


def test_limitation_three_years_month_end(registry):
    result = compute_deadline(
        rule=_rule(registry, "civil.limitation.general"),
        event=_event("awareAt", "2023-06-30"),
        calendar=_calendar(2026),
        matter_id="m-1", event_id="e-1", event_revision=1, now=NOW,
    )
    assert result["dueDate"] == "2026-06-30"
    assert result["dateOrigin"] == "calculated"
    assert result["current"] is True
    steps = "\n".join(result["calculationSteps"])
    assert "calendar_period:3years" in steps
    assert result["calculationReceiptRef"]["kind"] == "calculation-receipt"


def test_evidence_and_appeal_anchor_served_at(registry):
    appeal = compute_deadline(
        rule=_rule(registry, "civil.appeal.judgment"),
        event=_event("servedAt", "2026-03-02"),
        calendar=_calendar(2026),
        matter_id="m-1", event_id="e-2", event_revision=1, now=NOW,
    )
    assert appeal["dueDate"] == "2026-03-17"  # 送达日不计入，15 日
    evidence = compute_deadline(
        rule=_rule(registry, "civil.evidence.first_instance"),
        event=_event("servedAt", "2026-03-02"),
        calendar=_calendar(2026),
        matter_id="m-1", event_id="e-2", event_revision=1, now=NOW,
    )
    assert evidence["dueDate"] == "2026-04-01"


def test_due_date_rolls_forward_on_rest_day(registry):
    # 2026-05-17(日) → 顺延至 05-18(一)
    appeal = compute_deadline(
        rule=_rule(registry, "civil.appeal.judgment"),
        event=_event("servedAt", "2026-05-02"),
        calendar=_calendar(2026),
        matter_id="m-1", event_id="e-3", event_revision=1, now=NOW,
    )
    assert appeal["dueDate"] == "2026-05-18"
    steps = "\n".join(appeal["calculationSteps"])
    assert "roll_forward:2026-05-17->2026-05-18" in steps


def test_deadline_no_2027_guess(registry):
    # 2026-12-28 送达 +15 日 → 2027-01-12，超出 2026 覆盖：缺口如实返回
    result = compute_deadline(
        rule=_rule(registry, "civil.appeal.judgment"),
        event=_event("servedAt", "2026-12-28"),
        calendar=_calendar(2026),
        matter_id="m-1", event_id="e-4", event_revision=1, now=NOW,
    )
    assert result["dueDate"] is None
    assert result["dueAt"] is None
    assert "calendar_coverage_missing:true" in result["calculationSteps"]
    assert result["calculationReceiptRef"] is not None
    with pytest.raises(DeadlineError) as error:
        _calendar(2026).is_business_day(date(2027, 1, 12))
    assert error.value.code == "calendar_coverage_missing"


def test_unknown_precision_and_missing_anchor(registry):
    rule = _rule(registry, "civil.appeal.judgment")
    with pytest.raises(DeadlineError) as error:
        compute_deadline(
            rule=rule,
            event={"servedAt": {"value": None, "precision": "unknown", "timezone": None, "sourceRefs": []}},
            calendar=_calendar(2026),
            matter_id="m-1", event_id="e-5", event_revision=1, now=NOW,
        )
    assert error.value.code == "deadline_trigger_event_time_unknown"
    with pytest.raises(DeadlineError):
        compute_deadline(
            rule=rule,
            event=_event("hearingAt", "2026-03-02"),
            calendar=_calendar(2026),
            matter_id="m-1", event_id="e-5", event_revision=1, now=NOW,
        )


# ---------------------------------------------------------------------------
# 刑拘链：分阶段，无固定 37 日
# ---------------------------------------------------------------------------


def test_criminal_custody_chain_is_staged_no_fixed_37(registry):
    detention = compute_deadline(
        rule=_rule(registry, "criminal.custody.detention"),
        event=dict(_event("occurredAt", "2026-03-01"), legalContext={"authorityEvidence": True}),
        calendar=_calendar(2026),
        matter_id="m-2", event_id="e-c1", event_revision=1, now=NOW,
    )
    assert detention["dueDate"] == "2026-03-04"  # 刑诉法105条：拘留当日不计入
    extended = compute_deadline(
        rule=_rule(registry, "criminal.custody.detention.extended"),
        event=dict(_event("occurredAt", "2026-03-01"), legalContext={"approvedExtensionDays": 4, "extensionApproved": True, "authorityEvidence": True}),
        calendar=_calendar(2026),
        matter_id="m-2", event_id="e-c1", event_revision=1, now=NOW,
    )
    assert extended["dueDate"] == "2026-03-08"  # 原三日加获准四日，末日休假不顺延
    major = compute_deadline(
        rule=_rule(registry, "criminal.custody.detention.major"),
        event=dict(_event("occurredAt", "2026-03-01"), legalContext={"authorityEvidence": True}),
        calendar=_calendar(2026),
        matter_id="m-2", event_id="e-c1", event_revision=1, now=NOW,
    )
    assert major["dueDate"] == "2026-03-31"
    decision = compute_deadline(
        rule=_rule(registry, "criminal.custody.procuratorate.decision"),
        event=dict(_event("servedAt", "2026-03-03"), legalContext={"authorityEvidence": True}),  # 检察院实际收到提请批准逮捕书之日
        calendar=_calendar(2026),
        matter_id="m-2", event_id="e-c2", event_revision=1, now=NOW,
    )
    assert decision["dueDate"] == "2026-03-10"  # 收到当日不计入，七日内
    # 任何规则/分支/源码不含固定 37 日常数
    assert not any(rule.get("durationDays") == 37 for rule in registry.values())


# ---------------------------------------------------------------------------
# 保全：上限核对 + 法院届满日 + 续保不自动延长
# ---------------------------------------------------------------------------


def _preservation_event(preserved_on, court_expiry):
    return {
        "occurredAt": {"value": preserved_on, "precision": "date", "timezone": "Asia/Shanghai", "sourceRefs": []},
        "hearingAt": {"value": court_expiry, "precision": "date", "timezone": "Asia/Shanghai", "sourceRefs": []},
    }


def test_preservation_cap_ok_and_countdown_by_court(registry):
    rule = _rule(registry, "preservation.bank_deposit.court")
    result = compute_deadline(
        rule=rule,
        event=_preservation_event("2026-01-10", "2026-12-31"),
        calendar=_calendar(2026),
        matter_id="m-3", event_id="e-p1", event_revision=1, now=NOW,
    )
    assert result["dueDate"] == "2026-12-31"
    steps = "\n".join(result["calculationSteps"])
    assert "cap_check:propertyType=bank_deposit" in steps
    assert "court_expiry:2026-12-31" in steps


def test_preservation_cap_exceeded_fails_closed(registry):
    rule = _rule(registry, "preservation.bank_deposit.court")  # 存款上限 365 日
    with pytest.raises(DeadlineError) as error:
        compute_deadline(
            rule=rule,
            event=_preservation_event("2026-01-10", "2027-06-30"),
            calendar=_calendar(2026),
            matter_id="m-3", event_id="e-p2", event_revision=1, now=NOW,
        )
    assert error.value.code == "preservation_cap_exceeded"


def test_renewal_application_does_not_extend(registry):
    rule = dict(_rule(registry, "preservation.renewal.application"),
                courtSpecifiedDate="2026-12-31")
    result = compute_deadline(
        rule=rule,
        event=_event("occurredAt", "2026-01-10"),
        calendar=_calendar(2026),
        matter_id="m-3", event_id="e-p3", event_revision=1, now=NOW,
    )
    assert result["dueDate"] == "2026-12-24"  # 届满七日前申请（保全规定第十八条）
    steps = "\n".join(result["calculationSteps"])
    assert "no_auto_extension:true" in steps


def test_renewal_window_days_is_seven_per_judicial_interpretation(registry):
    rule = registry[("preservation.renewal.application", "1")]
    assert int(rule["windowDays"]) == 7
    authority = rule.get("authority") or {}
    assert authority.get("article", "").startswith("第十八条")
    assert "七日前" in authority.get("article", "")
    assert str(authority.get("verifyReceipt", "")).startswith("lcver-")


# ---------------------------------------------------------------------------
# 法院指定日与时效中止/中断
# ---------------------------------------------------------------------------


def test_court_specified_date_registered_as_is(registry):
    rule = dict(_rule(registry, "preservation.bank_deposit.court"),
                branch="court_specified", courtSpecifiedDate="2026-07-07")
    # 法院指定日即便落在休息日也不顺延、不调用法定天数
    result = compute_deadline(
        rule=rule,
        event=_preservation_event("2026-01-10", "2026-07-07"),
        calendar=_calendar(2026),
        matter_id="m-4", event_id="e-7", event_revision=1, now=NOW,
    )
    assert result["dueDate"] == "2026-07-07"
    assert result["dateOrigin"] == "calculated"
    steps = "\n".join(result["calculationSteps"])
    assert "court_specified:2026-07-07" in steps


def test_limitation_interruption_restarts_period(registry):
    base = dict(_rule(registry, "civil.limitation.general"),
                adjustments=[{"kind": "interruption", "at": "2025-03-01", "eventRef": "ev-int", "legalGroundConfirmed": True}])
    result = compute_deadline(
        rule=base,
        event=_event("awareAt", "2024-02-29"),
        calendar=_calendar(2024, end_year=2028),
        matter_id="m-5", event_id="e-8", event_revision=1, now=NOW,
    )
    # 中断后自中断日重新起算 3 年（2025-03-01 → 2028-03-01，日历年移动）
    assert result["dueDate"] == "2028-03-01"
    assert "ev-int" in result["adjustmentEventRefs"]


def test_limitation_obstacle_ending_before_last_six_months_does_not_suspend(registry):
    base = dict(_rule(registry, "civil.limitation.general"),
                adjustments=[{"kind": "suspension", "from": "2024-06-01", "to": "2024-08-31",
                              "eventRef": "ev-sus", "legalGroundConfirmed": True,
                              "cannotExercise": True, "ground": "force_majeure"}])
    result = compute_deadline(
        rule=base,
        event=_event("awareAt", "2023-06-30"),
        calendar=_calendar(2026),
        matter_id="m-5", event_id="e-9", event_revision=1, now=NOW,
    )
    # 障碍于最后六个月窗口前消除，不改变2026-06-30期限。
    assert result["dueDate"] == "2026-06-30"
    assert "suspension:not_in_effective_window" in result["calculationSteps"]


def test_registry_branches_are_declared(registry):
    for (rule_id, version), rule in registry.items():
        assert rule["branch"] in BRANCH_TABLE, rule_id
        assert version == "1" or version.isdigit()


# ---------------------------------------------------------------------------
# U02 规则数据修正：仲裁撤销三个月（2025 修订第七十二条）+ 旧版保留
# ---------------------------------------------------------------------------


def test_arbitration_set_aside_current_is_three_months(registry):
    rule = registry[("arbitration.set_aside.award", "2")]
    assert int(rule["durationDays"]) == 3
    assert rule["durationUnit"] == "months"
    assert rule["anchor"] == "servedAt"  # 自收到裁决书之日起
    result = compute_deadline(
        rule=rule,
        event=_event("servedAt", "2026-04-10"),
        calendar=_calendar(2026),
        matter_id="m-6", event_id="e-a1", event_revision=1, now=NOW,
    )
    # 2026-04-10 + 3 个月 = 2026-07-10（起算日不计入）
    assert result["dueDate"] == "2026-07-10"
    steps = "\n".join(result["calculationSteps"])
    assert "calendar_period:3months" in steps
    authority = rule.get("authority") or {}
    assert "三个月" in authority.get("article", "")
    assert authority.get("verifyReceipt") == "lcver-8701db6a8153daaf"
    assert authority.get("verification") == "verified"
    assert rule["effectiveFrom"] == "2026-03-01"  # 2025 修订施行日


def test_arbitration_set_aside_legacy_six_months_kept_as_historical(registry):
    rule = registry[("arbitration.set_aside.award", "1")]
    assert rule.get("status") == "historical"
    assert rule.get("supersededBy") == "2"
    assert int(rule["durationDays"]) == 6
    result = compute_deadline(
        rule=rule,
        event=_event("servedAt", "2026-04-10"),
        calendar=_calendar(2026),
        matter_id="m-6", event_id="e-a2", event_revision=1, now=NOW,
    )
    # 历史版本可读回：六个月口径 2026-04-10 → 2026-10-10（周六顺延至 10-12）
    assert result["dueDate"] == "2026-10-12"
    assert rule["effectiveTo"] == "2026-02-28"


def test_arbitration_versions_do_not_share_default(registry):
    # 两版本并存且口径不同；新计算必须显式选择 version "2"
    assert registry[("arbitration.set_aside.award", "2")]["durationDays"] != \
        registry[("arbitration.set_aside.award", "1")]["durationDays"]
