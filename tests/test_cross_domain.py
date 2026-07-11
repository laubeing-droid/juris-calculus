"""Cross-domain litigation tests: multi-domain batch + domain mapping validation."""

import json
import sys
sys.path.insert(0, "..")

from tools.batch_litigation_runner import (
    make_contract_rules,
    make_tort_rules,
    make_criminal_rules,
    make_admin_rules,
    BATCH_CASES,
)


def _load_domain_mapping():
    with open("configs/domain_mapping.json", "r") as f:
        return json.load(f)


class TestBatchTemplateExpansion:
    """Verify new domains (criminal, admin) are properly integrated."""

    def test_criminal_rules_present(self):
        rules = make_criminal_rules()
        assert len(rules) == 4
        ids = {r.id for r in rules}
        assert "rule::theft_act" in ids
        assert "rule::self_defense" in ids

    def test_criminal_rules_have_modalities(self):
        rules = make_criminal_rules()
        constitutives = [r for r in rules if r.norm_modality == "CONSTITUTIVE"]
        assert len(constitutives) >= 2

    def test_admin_rules_present(self):
        rules = make_admin_rules()
        assert len(rules) == 4
        ids = {r.id for r in rules}
        assert "rule::license_required" in ids
        assert "rule::environmental_harm" in ids

    def test_admin_rules_have_exceptions_and_priorities(self):
        rules = make_admin_rules()
        defense = [r for r in rules if "defense" in r.id]
        assert len(defense) == 1
        assert len(defense[0].priority_over) >= 1

    def test_batch_cases_cover_all_5_domains(self):
        domains = {c["domain"] for c in BATCH_CASES}
        assert "contract" in domains
        assert "license" in domains
        assert "tort" in domains
        assert "criminal" in domains
        assert "administrative" in domains

    def test_batch_cases_count_is_9(self):
        assert len(BATCH_CASES) == 9


class TestDomainMappingSchema:
    """Cross-domain mapping schema validation."""

    def test_mapping_json_loads(self):
        mapping = _load_domain_mapping()
        assert mapping["version"] == "1.0"
        assert len(mapping["domains"]) == 4

    def test_all_domains_have_overlapping_concepts(self):
        mapping = _load_domain_mapping()
        for domain in mapping["domains"]:
            concepts = mapping["domains"][domain]["overlapping_concepts"]
            assert len(concepts) >= 1, f"{domain} has no overlapping concepts"

    def test_cross_domain_cases_present(self):
        mapping = _load_domain_mapping()
        cases = mapping["cross_domain_cases"]
        assert len(cases) == 2
        assert cases[0]["case_id"] == "cross::contract_tort_overlap"
        assert cases[1]["case_id"] == "cross::criminal_admin_overlap"

    def test_cross_domain_cases_have_shared_facts(self):
        mapping = _load_domain_mapping()
        for case in mapping["cross_domain_cases"]:
            assert len(case["shared_facts"]) >= 3
            assert case["domain_a"] != case["domain_b"]


class TestMultiDomainEvaluation:
    """End-to-end litigation across multiple domains."""

    def test_contract_and_tort_joint_evaluation(self):
        from compiler_core.domain_config import DomainConfig
        from compiler_core.evaluator import FixpointEvaluator
        from compiler_core.types import IRState, LegalDomain, LegalFact
        all_rules = make_contract_rules() + make_tort_rules()
        shared_facts = ["contract_exists", "delivery_due", "duty_of_care", "breach_of_duty", "damage"]
        state = IRState(facts={fact: LegalFact(id=fact) for fact in shared_facts})
        evaluated = FixpointEvaluator(all_rules, DomainConfig(domain=LegalDomain.CIVIL)).evaluate(state)
        assert evaluated is not None

    def test_criminal_and_admin_joint_evaluation(self):
        from compiler_core.domain_config import DomainConfig
        from compiler_core.evaluator import FixpointEvaluator
        from compiler_core.types import IRState, LegalDomain, LegalFact
        all_rules = make_criminal_rules() + make_admin_rules()
        shared_facts = ["regulated_activity", "taking_property", "without_consent", "intent_to_deprive"]
        state = IRState(facts={fact: LegalFact(id=fact) for fact in shared_facts})
        evaluated = FixpointEvaluator(all_rules, DomainConfig(domain=LegalDomain.CIVIL)).evaluate(state)
        assert evaluated is not None
