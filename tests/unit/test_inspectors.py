#!/usr/bin/env python3
"""inspectors.py 四组黄金边界测试"""
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from legalos_services.external_context import FinancialContext, get_lpr
from legalos_services.inspectors import run_all_inspectors


# ═════════════╗
# 测试1: 利息超标
# ═════════════╝
def test_lpr_exceeded():
    """约定利率24%，LPR 3.45% → LPR_4X_EXCEEDED=True"""
    ctx = FinancialContext(
        dispute_date='2024-06-15',
        agreed_rate=24.0,
        loan_amount=500000,
    )
    facts = run_all_inspectors(ctx)
    assert ctx.lpr_1y == 3.45, f"LPR应为3.45%，实际{ctx.lpr_1y}"
    assert ctx.lpr_4x_cap == 13.8, f"4x上限应为13.8%，实际{ctx.lpr_4x_cap}"
    assert facts.get("Financial.LPR_4X_EXCEEDED") == True, "24% > 13.8% 应触发超标"


def test_lpr_not_exceeded():
    """约定利率10%，LPR 3.45% → LPR_4X_EXCEEDED=False"""
    ctx = FinancialContext(
        dispute_date='2024-06-15',
        agreed_rate=10.0,
    )
    facts = run_all_inspectors(ctx)
    assert facts.get("Financial.LPR_4X_EXCEEDED") == False, "10% < 13.8% 不应触发"


# ═════════════╗
# 测试2: 诉讼时效表面届满
# ═════════════╝
def test_limitation_prima_facie_expired():
    """借款到期2021年 → LIMITATION_PRIMA_FACIE_EXPIRED=True"""
    ctx = FinancialContext(dispute_date='2021-06-01')
    facts = run_all_inspectors(ctx)
    assert facts.get("Procedural.LIMITATION_PRIMA_FACIE_EXPIRED") == True, "2021至今已过3年"


def test_limitation_not_expired():
    """借款到期2025年 → 不应触发"""
    ctx = FinancialContext(dispute_date='2025-06-01')
    facts = run_all_inspectors(ctx)
    assert facts.get("Procedural.LIMITATION_PRIMA_FACIE_EXPIRED") == False, "2025至今不足3年"


# ═════════════╗
# 测试3: 时效中断（需要事实中已有催收函原子）
# ═════════════╝
def test_limitation_interrupted_horn_logic():
    """
    日期上表面届满，但存在中断事实 → Horn引警应能阻断驳回。
    
    此测试验证逻辑而非实际数据：
    - Procedural.LIMITATION_PRIMA_FACIE_EXPIRED = True（日期层面）
    - Fact.LIMITATION_INTERRUPTION_EXISTS 由正则在 pipeline 中注入
    - rules.yaml 中的 exception_chain 应有 Fact.LIMITATION_INTERRUPTION_EXISTS
    """
    ctx = FinancialContext(dispute_date='2021-06-01')
    facts = run_all_inspectors(ctx)
    assert facts["Procedural.LIMITATION_PRIMA_FACIE_EXPIRED"] == True
    # 此测试仅验证预检层能正确注入表面届满
    # Horn 阻却逻辑由 rules.yaml 的 exception_chain 验证


def test_damages_full_pipeline():
    """违约金+实际损失的完整精算链路"""
    ctx = FinancialContext(
        dispute_date='2024-06-01',
        agreed_rate=15,      # 超出 LPR 3.45%×4=13.8%
        loan_amount=200000,  # 本金20万
        actual_loss=50000,   # 实际损失5万
    )
    facts = run_all_inspectors(ctx)
    assert facts["Financial.LPR_4X_EXCEEDED"] == True
    # 违约金表面超标 = 预估利息(200000×15%/100=30000) vs 实际损失×1.3(65000)
    # 30000 < 65000 → 不超标
    assert facts.get("Financial.DAMAGES_APPEAR_EXCEED_LOSS_30PCT", False) == False


# ═════════════╗
# 测试4: 定金超标
# ═════════════╝
def test_deposit_exceeded():
    """合同价100万，定金30万 → DEPOSIT_EXCEED_VAL_20PCT=True"""
    ctx = FinancialContext(
        deposit_amount=300000,
        contract_value=1000000,
    )
    facts = run_all_inspectors(ctx)
    assert facts.get("Financial.DEPOSIT_EXCEED_VAL_20PCT") == True, "30万 > 100万×20%"


def test_deposit_not_exceeded():
    """合同价100万，定金15万 → 不触发"""
    ctx = FinancialContext(
        deposit_amount=150000,
        contract_value=1000000,
    )
    facts = run_all_inspectors(ctx)
    assert facts.get("Financial.DEPOSIT_EXCEED_VAL_20PCT") == False, "15万 < 100万×20%"


# ═════════════╗
# 综合测试: 空输入不崩溃
# ═════════════╝
def test_empty_context():
    """空 FinancialContext → 不应崩溃"""
    ctx = FinancialContext()
    facts = run_all_inspectors(ctx)
    assert isinstance(facts, dict)
    assert len(facts) == 0 or all(v in (True, False) for v in facts.values())
