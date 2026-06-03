#!/usr/bin/env python3
"""
中国法域 — 民商事合同核心 Provider v1.0.0
覆盖：借贷 / 买卖 / 租赁 / 建设工程 / 委托 / 担保
"""
import yaml, os
from pathlib import Path
from src.juris_calculus.core.base import BaseDomainProvider

CONFIG_DIR = Path(__file__).resolve().parents[5] / "configs" / "zh_CN"

class CNContractProvider(BaseDomainProvider):
    """中国合同纠纷领域"""

    @property
    def domain_id(self) -> str: return "contract"

    @property
    def jurisdiction(self) -> str: return "cn"

    @property
    def atom_registry(self) -> dict:
        return {
            "合同成立": "Contract.Status.FORMED",
            "合同有效": "Contract.Status.VALID",
            "合同无效": "Contract.Status.INVALID",
            "合同解除": "Contract.Status.TERMINATED",
            "逾期付款": "Contract.Performance.PAYMENT_OVERDUE",
            "未交付": "Contract.Performance.NON_DELIVERY",
            "已履行": "Contract.Performance.FULFILLED",
            "根本违约": "Contract.Breach.FUNDAMENTAL",
            "违约": "Contract.Breach.OCCURRED",
            "约定利息": "Contract.Finance.AGREED_INTEREST",
            "违约金": "Contract.Relief.LIQUIDATED_DAMAGES",
            "实际损失": "Contract.Finance.ACTUAL_LOSS",
            "定金": "Contract.Finance.DEPOSIT",
            "LPR": "Contract.Finance.LPR_REFERENCE",
            "建设工程优先受偿权": "Contract.Security.CONSTRUCTION_LIEN",
            "抵押": "Contract.Security.MORTGAGE",
            "连带责任": "Contract.Liability.JOINT_SEVERAL",
            "不可抗力": "Contract.Defense.FORCE_MAJEURE",
            "情势变更": "Contract.Defense.CHANGED_CIRCUMSTANCES",
        }

    @property
    def rules(self) -> list:
        from compiler_core.evaluator import load_rules_from_yaml
        rules_path = CONFIG_DIR / "rules.yaml"
        if rules_path.exists():
            return load_rules_from_yaml(str(rules_path))
        return []

    @property
    def concepts(self) -> list:
        return [
            "合同成立", "合同效力", "违约责任", "违约金调整",
            "损害赔偿计算", "民间借贷利率", "买卖合同风险转移",
            "租赁优先购买权", "建设工程优先受偿权", "定金罚则",
            "格式条款规制", "免责条款效力", "减损规则",
        ]

    @property
    def alpha(self) -> float: return 1.0
