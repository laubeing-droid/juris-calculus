#!/usr/bin/env python3
"""
juris-calculus 动态精算上下文 v1.0
二级解耦：定性推理（Symbolic Layer）→ 定量精算（Actuarial Layer）

设计原则：
1. 符号引擎不碰数值，只输出 Claim.XXX_SUPPORTED 原子
2. 外部管道根据原子+Context计算具体金额
3. LPR 按纠纷发生日做时间戳锚定（Temporal Anchoring）
4. 懒加载：只有符号引擎激活金融概念时才获取外部数据
"""
import json, os, time
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

# ═══════════ 一、LPR 历史数据（本地缓存，定期更新即可）═══════════
# 数据源：中国人民银行 LPR 报价
# 最后更新：2026-06-04
LPR_HISTORY = {
    # 格式：YYYY-MM-DD → (1Y_LPR, 5Y_LPR)
    # ⚠️ 2025年数据根据趋势估算，请以央行公告为准
    "2026-06-04": (3.00, 3.60),
    "2026-04-20": (3.00, 3.60),
    "2026-03-20": (3.00, 3.60),
    "2026-02-20": (3.00, 3.60),
    "2026-01-20": (3.05, 3.60),
    "2025-12-20": (3.05, 3.60),
    "2025-10-21": (3.05, 3.60),
    "2025-08-20": (3.10, 3.60),
    "2025-06-20": (3.10, 3.60),
    "2025-04-21": (3.10, 3.60),
    "2025-02-20": (3.10, 3.60),
    "2024-11-20": (3.10, 3.60),
    "2024-10-21": (3.10, 3.60),
    "2024-09-20": (3.35, 3.85),
    "2024-08-20": (3.35, 3.85),
    "2024-07-22": (3.35, 3.85),
    "2024-06-20": (3.45, 3.95),
    "2024-05-20": (3.45, 3.95),
    "2024-04-22": (3.45, 3.95),
    "2024-03-20": (3.45, 3.95),
    "2024-02-20": (3.45, 3.95),
}

@dataclass
class FinancialContext:
    """精算上下文 —— 运行时由 pipeline 构建，传入 legalos_pricing"""
    dispute_date: str = ""          # 纠纷发生日 YYYY-MM-DD
    contract_date: str = ""         # 合同成立日 YYYY-MM-DD
    lpr_1y: float = 0.0             # 一年期 LPR
    lpr_5y: float = 0.0             # 五年期 LPR
    lpr_4x_cap: float = 0.0         # LPR×4 上限
    agreed_rate: float = 0.0        # 约定年利率 %
    loan_amount: float = 0.0        # 本金
    actual_loss: float = 0.0        # 实际损失
    contract_value: float = 0.0     # 合同价款
    deposit_amount: float = 0.0     # 定金
    # 布尔标志（由符号引擎输出后填入）
    interest_supported: bool = False    # 利息主张获得支持
    excess_interest_barred: bool = False  # 超额利息被排除
    penalty_adjusted: bool = False     # 违约金需调减
    deposit_invalid: bool = False      # 定金超额无效
    statute_barred: bool = False       # 诉讼时效已过

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# ═══════════ 二、LPR 获取（时间戳锚定）═══════════

def get_lpr(dispute_date: str, period: str = "1Y") -> Optional[float]:
    """
    根据纠纷发生日获取历史 LPR。

    时间戳锚定（Temporal Anchoring）：
    使用纠纷当日或最近一次 LPR 报价，而非当前实时 LPR。
    确保同案卷在不同时间评测得到一致结果。

    Args:
        dispute_date: YYYY-MM-DD
        period: "1Y" 或 "5Y"
    Returns:
        float LPR 或 None（无匹配数据）
    """
    if not dispute_date:
        return None

    # 找不晚于 dispute_date 的最新 LPR 报价
    target = datetime.strptime(dispute_date[:10], "%Y-%m-%d")
    best_date = None
    best_lpr = None

    for date_str, (lpr_1y, lpr_5y) in sorted(LPR_HISTORY.items()):
        d = datetime.strptime(date_str, "%Y-%m-%d")
        if d <= target:
            best_date = date_str
            best_lpr = (lpr_1y, lpr_5y)

    if best_lpr is None:
        # 纠纷日早于所有数据 → 取最早一条作为下限锚定
        first_date = next(iter(sorted(LPR_HISTORY.keys())))
        return LPR_HISTORY[first_date][0] if period == "1Y" else LPR_HISTORY[first_date][1]

    idx = 0 if period == "1Y" else 1
    return best_lpr[idx]


# ═══════════ 三、事实预检层（数值 → 布尔事实）═══════════

def precheck_thresholds(ctx: FinancialContext) -> Dict[str, bool]:
    """
    数值比较 → 布尔事实 转换。
    在推理前调用，产出 Horn 引擎可用的谓词。

    四个标准阈值：
    - LPR×4：民间借贷利率保护上限
    - 损失×30%：违约金过高调减标准
    - 合同价×20%：定金标准
    - 已过诉讼时效：3年民事/1年刑事

    Returns:
        dict[fact_id] = True/False，可直接注入 IRState.facts
    """
    facts = {}

    # 阈值1：利息 > LPR×4
    if ctx.agreed_rate > 0 and ctx.lpr_4x_cap > 0:
        facts["Financial.LPR_4X_EXCEEDED"] = ctx.agreed_rate > ctx.lpr_4x_cap

    # 阈值2：违约金 > 实际损失×30%
    if ctx.actual_loss > 0:
        # 案卷文本提取的"违约金"与"实际损失"比例
        estimated_penalty = ctx.loan_amount * (ctx.agreed_rate / 100) if ctx.loan_amount > 0 else 0
        if estimated_penalty > 0:
            excess = estimated_penalty > ctx.actual_loss * 1.3
            facts["Financial.PENALTY_EXCESSIVE"] = excess

    # 阈值3：定金 > 合同价×20%
    if ctx.deposit_amount > 0 and ctx.contract_value > 0:
        facts["Financial.DEPOSIT_EXCEEDS_20PCT"] = ctx.deposit_amount > ctx.contract_value * 0.2

    # 阈值4：已过诉讼时效（3年普通/2年特殊）
    if ctx.dispute_date:
        try:
            dt = datetime.strptime(ctx.dispute_date[:10], "%Y-%m-%d")
            now = datetime.now()
            years_passed = (now - dt).days / 365.25
            facts["Procedural.STATUTE_BARRED"] = years_passed > 3.0
        except ValueError:
            pass

    return facts


# ═══════════ 四、精算计算（定量层）═══════════

def compute_financials(ctx: FinancialContext) -> Dict[str, float]:
    """
    基于符号引擎输出的布尔原子 + Context 数值，计算最终赔偿。

    仅在 claim.interest_supported 等标志为 True 时才计算。
    """
    result = {}

    # 利息计算（本金 × 年利率 × 年数）
    if ctx.interest_supported and ctx.loan_amount > 0:
        rate = min(ctx.agreed_rate, ctx.lpr_4x_cap) if ctx.lpr_4x_cap > 0 else ctx.agreed_rate
        if ctx.lpr_1y > 0 and rate == 0:
            rate = ctx.lpr_1y  # 没有约定利率，按 LPR 算
        result["interest_amount"] = round(ctx.loan_amount * (rate / 100), 2)

    # 违约金（最高为实际损失的 30%）
    if ctx.penalty_adjusted and ctx.actual_loss > 0:
        result["penalty_amount"] = round(ctx.actual_loss * 0.3, 2)
    elif ctx.actual_loss > 0:
        result["penalty_amount"] = round(ctx.actual_loss * 0.3, 2)

    # 定金返还/双倍
    if ctx.deposit_invalid:
        result["deposit_return"] = 0.0
    elif ctx.deposit_amount > 0:
        result["deposit_return"] = ctx.deposit_amount

    # 诉讼时效已过 → 不支持
    if ctx.statute_barred:
        for k in list(result.keys()):
            result[k] = 0.0
        result["statute_barred_dismissed"] = True

    return result
