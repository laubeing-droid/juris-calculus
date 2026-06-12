from compiler_core.criminal_complexity import (
    audit_criminal_claims,
    classify_criminal_complexity,
    verify_actor_charge_binding,
)
from compiler_core.config_paths import router_moe_path
from compiler_core.rule_router import RuleRouter
from compiler_core.step_verifier import StepVerifier, Verdict
from compiler_core.types import LegalClaim
from pipeline.adversarial_pipeline import AdversarialPipeline, RoleVerdict


def test_compound_charge_from_multijustice_stays_single_charge():
    row = {
        "defendant": "胡铁森",
        "accusation": "['走私、贩卖、运输、制造毒品']",
        "defendant_accusation": "['走私、贩卖、运输、制造毒品']",
        "relevant_article": "[347.0, 356.0]",
    }

    result = classify_criminal_complexity(row)

    assert result.scenario_id == "S1"
    assert result.charges == ["走私、贩卖、运输、制造毒品"]
    assert result.per_defendant_charges == {"胡铁森": ["走私、贩卖、运输、制造毒品"]}


def test_multijustice_s4_routes_to_criminal_subexpert():
    row = {
        "defendant_ls": "['胡某某', '庞某某', '房某某']",
        "accusation": "['非法拘禁', '妨害作证']",
        "fact": "公诉机关指控多名被告人共同犯罪。",
    }

    routed = RuleRouter().route([row])

    assert "刑事" in routed["selected_experts"]
    assert routed["criminal_complexity"]["scenario_id"] == "S4"
    assert routed["criminal_complexity"]["route_tag"] == "criminal_multi_defendant_multi_charge"


def test_router_uses_yaml_backed_moe_domains():
    router = RuleRouter()
    routed = router.route(["买卖合同逾期付款并主张违约责任"])

    assert router.domain_count >= 14
    assert router_moe_path("zh_CN").endswith("router_moe.yaml")
    assert "合同" in routed["selected_experts"]


def test_adversarial_auditor_flags_unbound_criminal_claim():
    case_facts = {
        "defendant_ls": "['胡某某', '庞某某']",
        "accusation": "['非法拘禁', '妨害作证']",
    }
    claims = [{"id": "c1", "description": "构成非法拘禁罪，应判处有期徒刑。", "confidence": 0.9}]

    report = audit_criminal_claims(case_facts, claims)
    adversarial = AdversarialPipeline().run_criminal_complexity_audit(case_facts, claims)

    assert not report["passed"]
    assert any("没有绑定具体被告人" in issue for issue in report["issues"])
    assert adversarial.verdict == RoleVerdict.FAIL
    assert adversarial.requires_human_review


def test_step_verifier_downgrades_missing_actor_binding():
    case_facts = {
        "defendant_ls": "['甲某', '乙某']",
        "accusation": "['盗窃', '诈骗']",
        "relevant_article": "[264.0, 266.0]",
    }
    claim = LegalClaim(id="criminal-claim", description="构成盗窃罪，适用264.0。", confidence=0.9)

    direct = verify_actor_charge_binding(claim, case_facts)
    checked = StepVerifier().verify(claim, {"criminal_case": case_facts})

    assert not direct["passed"]
    assert "缺少被告人绑定" in direct["issues"]
    assert checked.fact_law_relevance == Verdict.DOWNGRADE
    assert checked.overall == Verdict.DOWNGRADE
