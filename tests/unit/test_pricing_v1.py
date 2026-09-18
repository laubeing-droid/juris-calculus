"""生产定价核心与校准估计器（03 卡步骤 2-3，母本 §3.3.2/§3.3.3）。

冻结样例与八条 PRICE 具名断言全部在此；无测试或 skip 不算 PASS
（00 卡 §五：真实运行报告禁混 mock，本文件为纯函数级独立单测）。
"""
from __future__ import annotations

import copy
from decimal import Decimal

import pytest

from compiler_core.pricing import (
    ALPHA_CLAMP_HIGH,
    ALPHA_CLAMP_LOW,
    BillingTier,
    CalibrationSample,
    FEATURE_DEFINITION_LEGACY_DTH,
    FEATURE_DEFINITION_RAW_COUNT,
    canonical_decimal_text,
    decimal_text,
    estimate_default,
    estimate_legacy_baseline,
    fit_alpha,
)

FROZEN_EXAMPLE = dict(
    effective_nodes=10,
    alpha="1.25",
    location_factor="1.3",
    stage_factor="1.25",
    overhead_hours="8",
    rate_minor=3300,
    alpha_status="fitted",
)


# ---------------------------------------------------------------------------
# 冻结样例（母本 §3.3.2 精确匹配）
# ---------------------------------------------------------------------------


def test_frozen_pricing_example():
    result = estimate_default(**FROZEN_EXAMPLE, batch_position=1)
    assert result["variable_hours_unrounded"] == "20.3125"
    assert result["variable_amount_minor"] == 67031
    assert result["overhead_amount_minor"] == 26400
    assert result["amount_minor"] == 93431
    assert result["display_hours"] == "28.3"
    assert result["delta"] is None
    assert result["guarantee_level"] is None
    assert result["model_version"] == "Z-v1-default"
    assert result["h_policy"] == "unwired-v1"


def test_batch_decay_keeps_factors_and_overhead():
    values = [
        estimate_default(**FROZEN_EXAMPLE, batch_position=n)
        for n in range(1, 6)
    ]
    total = sum(Decimal(row["total_hours_unrounded"]) for row in values)
    assert abs(total - Decimal("98.59")) < Decimal("0.01")
    assert all(row["overhead_hours_unrounded"] == "8" for row in values)
    # 衰减只作用变动部分：每件 overhead 金额恒为 8h×3300=26400 分
    assert all(row["overhead_amount_minor"] == 26400 for row in values)


def test_decay_is_strictly_decreasing():
    totals = [
        Decimal(estimate_default(**FROZEN_EXAMPLE, batch_position=n)["total_hours_unrounded"])
        for n in range(1, 8)
    ]
    assert all(a > b for a, b in zip(totals, totals[1:]))


def test_input_validation_rejects_out_of_range():
    with pytest.raises(ValueError):
        estimate_default(**{**FROZEN_EXAMPLE, "effective_nodes": -1}, batch_position=1)
    with pytest.raises(ValueError):
        estimate_default(**{**FROZEN_EXAMPLE, "alpha": "0"}, batch_position=1)
    with pytest.raises(ValueError):
        estimate_default(**{**FROZEN_EXAMPLE}, batch_position=0)


def test_versions_do_not_mix_baseline_vs_production():
    production = estimate_default(**FROZEN_EXAMPLE, batch_position=1)
    baseline = estimate_legacy_baseline(
        effective_nodes=10,
        alpha="1.25",
        location_factor="1.3",
        stage_factor="1.25",
        overhead_hours="8",
        rate_minor=3300,
    )
    assert production["model_version"] == "Z-v1-default"
    assert baseline["model_version"] == "v1.0.3-baseline"
    # 历史 v1.0.3 单件无衰减；生产首件含 decay(1)=1，两者单件数值一致
    assert baseline["variable_hours_unrounded"] == production["variable_hours_unrounded"]


def test_billing_tier_constants_restored():
    tier = BillingTier()
    assert tier.partner == Decimal("1.8")
    assert tier.senior_associate == Decimal("1.3")
    assert tier.associate == Decimal("1.0")
    assert tier.paralegal == Decimal("0.5")


# ---------------------------------------------------------------------------
# DecimalText 映射（规范十进制字符串）
# ---------------------------------------------------------------------------


def test_decimal_text_canonical_roundtrip():
    assert canonical_decimal_text(Decimal("20.3125")) == "20.3125"
    assert canonical_decimal_text(Decimal("1.0")) == "1"
    assert canonical_decimal_text(Decimal("0.500")) == "0.5"
    assert canonical_decimal_text(Decimal("0")) == "0"
    assert canonical_decimal_text(Decimal("-0")) == "0"
    assert canonical_decimal_text(Decimal("1E+2")) == "100"
    assert decimal_text("20.3125") == Decimal("20.3125")
    with pytest.raises(ValueError):
        decimal_text("1.50")
    with pytest.raises(ValueError):
        decimal_text("1E+2")
    with pytest.raises(ValueError):
        decimal_text("abc")


# ---------------------------------------------------------------------------
# 八条 PRICE 具名断言（母本 §3.3.3）
# ---------------------------------------------------------------------------


def _samples(nodes_hours, version=FEATURE_DEFINITION_RAW_COUNT, resolution=1):
    return [
        CalibrationSample(
            entry_ref=f"entry-{index}",
            feature_definition_version=version,
            duration_seconds=int(round(hours * 3600)),
            effective_nodes=nodes,
            source_resolution_seconds=resolution,
        )
        for index, (nodes, hours) in enumerate(nodes_hours)
    ]


def test_price_ten_points_fit_1_25():
    data = [(10 * n, 1.25 * 10 * n) for n in range(1, 11)]
    fit = fit_alpha(_samples(data), feature_definition_version=FEATURE_DEFINITION_RAW_COUNT)
    assert fit["status"] == "fitted"
    assert fit["alpha"] == "1.25"
    assert fit["samples_used"] == 10
    assert fit["guarantee_level"] is None and fit["delta"] is None
    assert fit["estimator_version"] == "theilsen-legacy-branches/1"
    assert fit["feature_definition_version"] == FEATURE_DEFINITION_RAW_COUNT


def test_price_input_order_does_not_change_fit():
    data = [(10 * n, 1.25 * 10 * n) for n in range(1, 11)]
    shuffled = list(reversed(data))
    one = fit_alpha(_samples(data), feature_definition_version=FEATURE_DEFINITION_RAW_COUNT)
    two = fit_alpha(_samples(shuffled), feature_definition_version=FEATURE_DEFINITION_RAW_COUNT)
    assert one["alpha"] == two["alpha"]
    assert one["status"] == two["status"] == "fitted"


def test_price_insufficient_samples_keep_candidate_but_use_1():
    data = [(10, 1.4 * 10), (20, 1.4 * 20)]
    fit = fit_alpha(_samples(data), feature_definition_version=FEATURE_DEFINITION_RAW_COUNT)
    assert fit["status"] == "insufficient_data"
    assert fit["candidate_alpha"] == "1.4"
    assert fit["alpha"] == "1"
    assert fit["guarantee_level"] is None and fit["delta"] is None


def test_price_legacy_negative_slope_branch_preserved():
    # 节点越多工时越少 → 成对斜率全为 -1 → abs 门后 α=1（历史分支保留）
    data = [(10 * n, (200 - 10 * n)) for n in range(1, 11)]
    fit = fit_alpha(_samples(data), feature_definition_version=FEATURE_DEFINITION_RAW_COUNT)
    assert fit["status"] == "fitted"
    assert fit["alpha"] == "1"


def test_price_feature_versions_cannot_mix():
    raw = _samples([(10, 12.5), (20, 25.0)], version=FEATURE_DEFINITION_RAW_COUNT)
    dth = _samples([(10, 12.5)], version=FEATURE_DEFINITION_LEGACY_DTH)
    with pytest.raises(ValueError):
        fit_alpha(raw + dth, feature_definition_version=FEATURE_DEFINITION_RAW_COUNT)
    # 各自版本内可拟合，α 不跨定义复用
    fit_raw = fit_alpha(raw, feature_definition_version=FEATURE_DEFINITION_RAW_COUNT)
    fit_dth = fit_alpha(dth, feature_definition_version=FEATURE_DEFINITION_LEGACY_DTH)
    assert fit_raw["feature_definition_version"] != fit_dth["feature_definition_version"]


def test_price_old_bill_survives_new_alpha():
    old = estimate_default(**{**FROZEN_EXAMPLE, "alpha": "1.0",
                              "alpha_status": "insufficient_data"}, batch_position=1)
    frozen_old = copy.deepcopy(old)
    # 新数据拟合出新 α，不影响已出的旧账（纯函数 + 旧账自存输入）
    fit = fit_alpha(
        _samples([(10 * n, 1.25 * 10 * n) for n in range(1, 11)]),
        feature_definition_version=FEATURE_DEFINITION_RAW_COUNT,
    )
    assert fit["alpha"] == "1.25"
    assert old == frozen_old
    rederived = estimate_default(**{**FROZEN_EXAMPLE, "alpha": "1.0",
                                    "alpha_status": "insufficient_data"}, batch_position=1)
    assert rederived == old
    new = estimate_default(**FROZEN_EXAMPLE, batch_position=1)
    assert new["variable_amount_minor"] != old["variable_amount_minor"]


def test_price_unattributed_seconds_excluded_with_reason():
    samples = _samples([(10, 12.5), (20, 25.0), (30, 37.5)])
    unattributed = CalibrationSample(
        entry_ref="entry-noise",
        feature_definition_version=FEATURE_DEFINITION_RAW_COUNT,
        duration_seconds=999999,
        effective_nodes=500,
        attributed=False,
    )
    fit = fit_alpha(
        samples + [unattributed],
        feature_definition_version=FEATURE_DEFINITION_RAW_COUNT,
    )
    assert fit["status"] == "fitted"
    assert fit["alpha"] == "1.25"
    reasons = {row["entryRef"]: row["reason"] for row in fit["excluded"]}
    assert reasons == {"entry-noise": "unattributed_seconds"}


def test_price_batch_no_early_rounding():
    from decimal import localcontext

    positions = range(1, 6)
    rows = [estimate_default(**FROZEN_EXAMPLE, batch_position=n) for n in positions]
    # 未舍入工时总和与独立 40 位精度重算精确相等（无中途舍入）
    with localcontext() as context:
        context.prec = 40
        expected = sum(
            Decimal(10) * Decimal("1.25") * Decimal("1.3") * Decimal("1.25")
            * (Decimal(n) ** Decimal("-0.65")) + Decimal(8)
            for n in positions
        )
        unrounded_total = sum(
            (Decimal(r["total_hours_unrounded"]) for r in rows), Decimal(0)
        )
    assert unrounded_total == expected
    total_minor = int(
        (unrounded_total * Decimal(3300)).quantize(Decimal(1), rounding="ROUND_HALF_UP")
    )
    sum_of_amounts = sum(r["amount_minor"] for r in rows)
    # 逐件 half-up 后求和 ≥ 先加总再舍入（单调），且不得用 0.1h 展示值算钱
    assert sum_of_amounts >= total_minor
    display_sum = sum(Decimal(r["display_hours"]) for r in rows) * 3300
    assert sum_of_amounts != int(display_sum)
    # alpha 夹紧边界
    assert ALPHA_CLAMP_LOW == Decimal("0.05") and ALPHA_CLAMP_HIGH == Decimal("2.0")
