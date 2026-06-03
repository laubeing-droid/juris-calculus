#!/usr/bin/env python3
"""
juris-calculus 事实预检层（Fact Pre-inspection Layer）v1.0

两级架构：
  1. 纯数学阈值 → 直接注入布尔事实（LPR/DEPOSIT）
  2. 嵌套法律逻辑 → 注入"表面成立"信号，Horn引擎裁量（时效/违约金）

设计原则：
  - 预检层不替符号引擎做任何法律判断
  - 连续值 → 布尔事实的"谓词固化" (Predicate Grounding)
  - 对时效/违约金保留符号阻却通道
"""
from typing import Dict, Tuple
from datetime import datetime
from .external_context import FinancialContext, get_lpr


def inspect_lpr(ctx: FinancialContext) -> Dict[str, bool]:
    """
    阈值1：利息 > LPR×4 的纯数值比较。
    无法律逻辑陷阱，直接固化。
    依据：《民间借贷司法解释》第25条
    """
    if not ctx.lpr_4x_cap or ctx.agreed_rate <= 0:
        return {}

    lpr_exceeded = ctx.agreed_rate > ctx.lpr_4x_cap
    return {"Financial.LPR_4X_EXCEEDED": lpr_exceeded}


def inspect_deposit(ctx: FinancialContext) -> Dict[str, bool]:
    """
    阈值2：定金 > 合同价×20% 的纯数值比较。
    无法律逻辑陷阱。
    依据：《民法典》第586条
    """
    if ctx.deposit_amount <= 0 or ctx.contract_value <= 0:
        return {}

    exceeded = ctx.deposit_amount > ctx.contract_value * 0.2
    return {"Financial.DEPOSIT_EXCEED_VAL_20PCT": exceeded}


def inspect_limitation(ctx: FinancialContext) -> Dict[str, bool]:
    """
    阈值3：诉讼时效"表面届满"（Prima Facie Expired）。
    
    ⚠️ 不是直接断定"已过时效"！
    只做纯日期减法，注入"表面届满"信号。
    是否存在中断事由（催收函、承认债务、部分清偿），
    由 Horn 引擎检查 Fact.LIMITATION_INTERRUPTION_EXISTS 对抗原子决定。
    
    依据：《民法典》第188-195条
    """
    if not ctx.dispute_date:
        return {}

    try:
        dt = datetime.strptime(ctx.dispute_date[:10], "%Y-%m-%d")
        days_diff = (datetime.now() - dt).days
        prima_facie_expired = days_diff > 3 * 365
        return {"Procedural.LIMITATION_PRIMA_FACIE_EXPIRED": prima_facie_expired}
    except ValueError:
        return {}


def inspect_damages(ctx: FinancialContext) -> Dict[str, bool]:
    """
    阈值4：违约金"表面超过"损失 30%（Prima Facie）。
    
    ⚠️ 不是直接得出"违约金过高应调减"！
    双轨制：
      1. 预检层注入 DAMAGES_APPEAR_EXCEED_LOSS_30PCT（表面）
      2. 符号引擎需要 AND Fact.DEFENDANT_REQUESTS_REDUCTION（被告抗辩）
         同时成立才触发 Remedy.DAMAGES_ADJUSTED
    
    依据：《民法典》第585条、《合同法解释二》第29条
    """
    if ctx.actual_loss <= 0:
        return {}

    # 从案卷文本估算违约金
    estimated_penalty = 0.0
    if ctx.loan_amount > 0 and ctx.agreed_rate > 0:
        estimated_penalty = ctx.loan_amount * (ctx.agreed_rate / 100)
    elif ctx.loan_amount > 0 and ctx.lpr_1y > 0:
        estimated_penalty = ctx.loan_amount * ctx.lpr_1y / 100 * 2  # 默认2年

    if estimated_penalty <= 0:
        return {}

    appeared_excessive = estimated_penalty > ctx.actual_loss * 1.3
    return {"Financial.DAMAGES_APPEAR_EXCEED_LOSS_30PCT": appeared_excessive}


# ═══════════ 统一预检入口 ═══════════

def run_all_inspectors(ctx: FinancialContext) -> Dict[str, bool]:
    """
    运行全部事实预检器，返回可直接注入 IRState.facts 的布尔原子。

    在 pipeline.py 中的调用顺序：
      1. 文本事实提取（正则）→ 生成初步 facts
      2. 构建 FinancialContext（数值提取）
      3. run_all_inspectors(ctx) → 注入阈值事实
      4. FixpointEvaluator → 纯布尔不动点迭代

    Args:
        ctx: 已完成 LPR 锚定的 FinancialContext
    Returns:
        dict: {fact_id: bool}，可直接用于 state.facts
    """
    facts = {}

    # LPR 锚定
    if not ctx.lpr_1y:
        ctx.lpr_1y = get_lpr(ctx.dispute_date, "1Y") or 3.1
        ctx.lpr_4x_cap = ctx.lpr_1y * 4

    # 4 个预检器
    facts.update(inspect_lpr(ctx))            # 利息过LPR×4
    facts.update(inspect_deposit(ctx))         # 定金过20%
    facts.update(inspect_limitation(ctx))      # 时效表面届满
    facts.update(inspect_damages(ctx))         # 违约金表面超标

    return facts
