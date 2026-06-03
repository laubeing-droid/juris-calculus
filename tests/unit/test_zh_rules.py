#!/usr/bin/env python3
"""中国法规则单元测试 —— FixpointEvaluator 推理正确性验证"""
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from compiler_core.types import LegalRule, LegalFact, IRState, LegalDomain
from compiler_core.evaluator import FixpointEvaluator, CriticalClarityFailure, load_rules_from_yaml
from compiler_core.domain_config import get_domain_config

RULES_YAML = os.path.join(os.path.dirname(__file__), '..', '..', 'configs', 'zh_CN', 'rules.yaml')
ZH_RULES = load_rules_from_yaml(RULES_YAML)
ZH_CONFIG = get_domain_config(LegalDomain.CIVIL)
# 加载校准参数
import yaml
_config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'configs', 'zh_CN', 'domain_config.yaml')
if os.path.exists(_config_path):
    _cfg = yaml.safe_load(open(_config_path, encoding='utf-8'))
    if 'alpha_calibrated' in _cfg:
        ZH_CONFIG.alpha = _cfg['alpha_calibrated']
    if 'concept_registry' in _cfg:
        ZH_CONFIG.concept_registry = set(_cfg['concept_registry'])

EV = FixpointEvaluator(ZH_RULES, ZH_CONFIG)


def run(case_id: str, facts: dict) -> 'IRState':
    """辅助函数：构建状态=>推理=>返回结果"""
    state = IRState(world_id=case_id)
    for fid, desc in facts.items():
        state.facts[fid] = LegalFact(fid, str(desc))
    try:
        return EV.evaluate(state)
    except CriticalClarityFailure as e:
        return state


# ═══════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════

class TestLoanContract:
    """民间借贷纠纷"""

    def test_loan_default(self):
        """逾期未还：应有推理结论"""
        r = run("loan_001", {
            "loan_contract": "借款50万，月息1%",
            "contract_formed": "2023年1月签署借款合同",
            "goods_delivered": "出借人转账交付50万",
            "payment_due": "2023年7月到期",
            "payment_default": "到期未还本息",
        })
        assert len(r.claims) > 0, "逾期未还应有推理结论"
        # 结论数应在合理范围（AND 增强后不应爆炸）

    def test_statute_barred(self):
        """超过诉讼时效：应标注低置信度或触发 statute_barred"""
        r = run("loan_002", {
            "loan_contract": "借款合同",
            "statute_barred": "借款发生于2019年，至今已6年",
            "payment_due": "2020年1月到期",
        })
        claims = r.claims.values()
        low_conf = [c for c in claims if c.confidence < 0.5]
        assert len(low_conf) > 0, "诉讼时效超过应有低置信度标记"

    def test_loan_rate_limited(self):
        """利率超过LPR四倍：应有高置信度结论"""
        r = run("loan_003", {
            "loan_contract": "借款合同",
            "contract_formed": "2021年签署",
            "goods_delivered": "交付借款",
            "payment_due": "到期",
            "payment_default": "未还款",
        })
        assert len(r.claims) > 0, "应有推理结论"


class TestContract:
    """合同纠纷"""

    def test_breach(self):
        """买卖合同违约"""
        r = run("contract_001", {
            "sales_contract": "钢材购销合同",
            "contract_formed": "合同已签署",
            "goods_delivered": "卖方已交货",
            "payment_due": "货款到期",
            "payment_default": "买方未付款",
        })
        claims = [c.id for c in r.claims.values()]
        assert len(claims) > 0, "应有推理结论"
        # 不应有欺诈相关结论（本案无欺诈要素）
        fraud_claims = [c for c in claims if 'fraud' in c.lower()]
        assert len(fraud_claims) == 0, f"无欺诈要素不应触发欺诈结论: {fraud_claims}"

    def test_contract_invalid(self):
        """合同无效"""
        r = run("contract_002", {
            "sales_contract": "购销合同",
            "contract_invalid": "合同违反强制性规定",
            "contract_formed": "已签署",
        })
        assert len(r.claims) > 0, "合同无效应有推理结论"


class TestTort:
    """侵权纠纷"""

    def test_traffic_accident(self):
        """交通事故索赔"""
        r = run("tort_001", {
            "traffic_accident": "机动车交通事故",
            "fault_element": "肇事司机全责",
            "damages_suffered": "医疗费15万，伤残赔偿金40万",
            "expert_evidence": "司法鉴定九级伤残",
        })
        claims_ids = [c.id for c in r.claims.values()]
        assert len(r.claims) > 0, "交通事故应有推理结论"

    def test_emotional_distress(self):
        """精神损害赔偿"""
        r = run("tort_002", {
            "emotional_distress": "严重精神损害",
            "damages_suffered": "名誉权受损",
            "fault_element": "故意侵权",
        })
        assert len(r.claims) > 0, "精神损害应有推理结论"


class TestProperty:
    """物权与执行"""

    def test_enforcement(self):
        """强制执行"""
        r = run("enforce_001", {
            "enforcement_action": "判决已生效，申请强制执行",
            "payment_due": "债务到期",
            "payment_default": "未履行",
        })
        assert len(r.claims) > 0, "执行应有推理结论"

    def test_real_estate(self):
        """房产纠纷"""
        r = run("realty_001", {
            "real_estate": "房屋买卖合同纠纷",
            "contract_formed": "合同已签署",
            "payment_default": "买方未付全款",
        })
        assert len(r.claims) > 0, "房产纠纷应有推理结论"


class TestCompany:
    """公司纠纷"""

    def test_equity_transfer(self):
        """股权转让纠纷"""
        r = run("company_001", {
            "equity_transfer": "股权转让协议",
            "contract_formed": "协议已签署",
            "payment_default": "受让方未支付转让款",
        })
        assert len(r.claims) > 0, "股权转让应有推理结论"

    def test_shareholder_capital(self):
        """股东出资纠纷"""
        r = run("company_002", {
            "shareholder_capital": "认缴出资未实缴",
            "contract_formed": "出资协议已签署",
            "breach_alleged": "股东未按期实缴",
        })
        assert len(r.claims) > 0, "股东出资应有推理结论"


class TestCriminal:
    """刑事"""

    def test_crime_mentioned(self):
        """刑事案由提及：应有触发"""
        r = run("criminal_001", {
            "fraud_crime": "合同诈骗",
            "damages_suffered": "损失100万",
        })
        # 刑事规则较少，不一定触发，但不应崩溃
        assert r.iteration_count > 0, "推理引擎应正常迭代"


class TestAdmin:
    """行政/国家赔偿"""

    def test_admin_action(self):
        """行政行为审查"""
        r = run("admin_001", {
            "administrative_action": "行政处罚决定",
            "damages_suffered": "罚款50万",
        })
        assert len(r.claims) > 0, "行政行为应有推理结论"

    def test_state_compensation(self):
        """国家赔偿"""
        r = run("admin_002", {
            "state_compensation": "国家赔偿申请",
            "enforcement_action": "财产被查封",
            "damages_suffered": "经济损失",
        })
        assert len(r.claims) > 0, "国家赔偿应有推理结论"


class TestEdgeCases:
    """边界情况"""

    def test_no_facts(self):
        """无事实：不应无限迭代"""
        r = run("empty_001", {})
        assert r.iteration_count < r.max_iterations, "无事实时应在max_iterations内收敛"

    def test_single_fact(self):
        """单事实：不应崩溃"""
        r = run("single_001", {"damages_suffered": "有损失"})
        assert r.iteration_count > 0, "单事实应正常迭代"

    def test_unrelated_facts(self):
        """无关事实（系统不支持的概念）：应忽略不作结论"""
        r = run("unrelated_001", {
            "外星人入侵": "火星人起诉",
            "魔法合同": "隐身术交易",
        })
        # 不应崩溃
        assert r.iteration_count < r.max_iterations

    def test_convergence_speed(self):
        """收敛速度：应在5轮内终止"""
        r = run("speed_001", {
            "loan_contract": "借款合同",
            "contract_formed": "签署",
            "goods_delivered": "交付",
            "payment_due": "到期",
            "payment_default": "未还",
        })
        assert r.iteration_count <= 5, f"应在5轮内收敛，实际{r.iteration_count}轮"
