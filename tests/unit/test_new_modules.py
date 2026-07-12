"""Tests for DP policy loader, source manifest, evidence evaluation,
burden of proof, legal reasoning, criminal sentencing, IP valuation,
compliance monitoring, arbitration reasoning."""
import pytest
import sys
import os
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

CONFIGS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'configs', 'zh_CN')


def _dp_policy_fixture(tmp_path):
    path = tmp_path / "dp_policy.yaml"
    payload = {
        "policies": [
            {
                "data_class": "state_secret",
                "epsilon_range": [0.0, 0.0],
                "allowed_release_mode": "blocked",
                "approval_required": True,
                "audit_log_required": True,
                "source_id": "fixture:state_secret",
            },
            {
                "data_class": "public_record",
                "epsilon_range": [0.1, 100.0],
                "allowed_release_mode": "full",
                "approval_required": False,
                "audit_log_required": False,
                "source_id": "fixture:public_record",
            },
            {
                "data_class": "court_filing",
                "epsilon_range": [0.0, 10.0],
                "allowed_release_mode": "aggregated",
                "approval_required": False,
                "audit_log_required": True,
                "source_id": "fixture:court_filing",
            },
        ]
    }
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(path)


class TestDPPolicy:
    def test_load_policies(self, tmp_path):
        from compiler_core.dp_policy_loader import DPPolicyLoader
        loader = DPPolicyLoader()
        path = _dp_policy_fixture(tmp_path)
        assert loader.load(path)
        assert len(loader.policies) >= 3

    def test_state_secret_blocked(self, tmp_path):
        from compiler_core.dp_policy_loader import DPPolicyLoader
        loader = DPPolicyLoader()
        path = _dp_policy_fixture(tmp_path)
        loader.load(path)
        result = loader.check_release('state_secret', 0.5)
        assert not result['allowed']

    def test_public_record_allowed(self, tmp_path):
        from compiler_core.dp_policy_loader import DPPolicyLoader
        loader = DPPolicyLoader()
        path = _dp_policy_fixture(tmp_path)
        loader.load(path)
        result = loader.check_release('public_record', 50.0)
        assert result['allowed']


class TestSourceManifest:
    def test_load_manifest(self):
        from compiler_core.source_manifest import SourceManifest
        m = SourceManifest()
        path = os.path.join(CONFIGS_DIR, 'source_manifest.yaml')
        assert m.load(path)
        assert len(m.entries) >= 10

    def test_known_anchor(self):
        from compiler_core.source_manifest import SourceManifest
        m = SourceManifest()
        path = os.path.join(CONFIGS_DIR, 'source_manifest.yaml')
        m.load(path)
        r = m.validate_anchor('刑事审判实务')
        assert r['registered']
        assert r['status'] == 'REFERENCE_UNVERIFIED'

    def test_unknown_anchor(self):
        from compiler_core.source_manifest import SourceManifest
        m = SourceManifest()
        path = os.path.join(CONFIGS_DIR, 'source_manifest.yaml')
        m.load(path)
        r = m.validate_anchor('unknown_source_xyz')
        assert not r['registered']

    def test_partial_anchor_does_not_match_registered_source(self):
        from compiler_core.source_manifest import SourceManifest
        m = SourceManifest()
        path = os.path.join(CONFIGS_DIR, 'source_manifest.yaml')
        m.load(path)

        assert not m.validate_anchor('刑事审判实务/第一编')['registered']


class TestEvidenceEvaluation:
    def test_credibility_score(self):
        from compiler_core.evidence_evaluation import EvidenceItem
        e = EvidenceItem(id='e1', description='test', reliability=0.8, independence=0.9, authenticity=1.0)
        assert abs(e.credibility_score - 0.72) < 0.01

    def test_chain_completeness(self):
        from compiler_core.evidence_evaluation import compute_chain_completeness
        assert compute_chain_completeness(3, 3) == 1.0
        assert compute_chain_completeness(0, 0) == 1.0
        assert compute_chain_completeness(1, 3) < 0.5

    def test_contradiction_detection(self):
        from compiler_core.evidence_evaluation import EvidenceItem, detect_contradiction
        e1 = EvidenceItem(id='e1', description='A hit B', reliability=1.0)
        e2 = EvidenceItem(id='e2', description='A did not hit B', reliability=1.0)
        result = detect_contradiction(e1, e2, 'fact_1')
        assert result is not None
        assert result['type'] == 'CONTRADICTION'


class TestBurdenOfProof:
    def test_add_and_evaluate(self):
        from compiler_core.burden_of_proof import BurdenTracker
        t = BurdenTracker()
        t.add('plaintiff', 'breach of contract', 'burden_of_persuasion', 'preponderance')
        result = t.evaluate_completion('breach of contract')
        assert not result['burden_met']
        t.submit_evidence('breach of contract', 'contract_doc')
        result = t.evaluate_completion('breach of contract')
        assert result['burden_met']

    def test_unknown_allegation(self):
        from compiler_core.burden_of_proof import BurdenTracker
        t = BurdenTracker()
        result = t.evaluate_completion('unknown')
        assert not result['burden_met']


class TestLegalReasoning:
    def test_analogical_similarity(self):
        from compiler_core.legal_reasoning import analogical_similarity
        assert analogical_similarity(['a', 'b', 'c'], ['a', 'b', 'c']) == 1.0
        assert analogical_similarity(['a', 'b'], ['c', 'd']) == 0.0
        assert 0 < analogical_similarity(['a', 'b'], ['a', 'c']) < 1

    def test_precedent_binding_force(self):
        from compiler_core.legal_reasoning import precedent_binding_force
        assert precedent_binding_force('supreme', True) == 1.0
        assert precedent_binding_force('supreme', False) == 0.5
        assert precedent_binding_force('basic', True) < precedent_binding_force('supreme', True)

    def test_balance_interests(self):
        from compiler_core.legal_reasoning import balance_interests
        result = balance_interests({'safety': 0.7, 'freedom': 0.3})
        assert result['balanced']
        assert result['dominant_interest'] == 'safety'
        assert result['dominant_ratio'] > 0.5


class TestCriminalSentencing:
    def test_predict_range(self):
        from compiler_core.criminal_sentencing import SentencingFactors
        f = SentencingFactors(statutory_range_months=(12, 84))
        r = f.predict_range()
        assert r == (12, 84)

    def test_mitigating_factors(self):
        from compiler_core.criminal_sentencing import SentencingFactors
        f = SentencingFactors(statutory_range_months=(12, 84), mitigating_factors=['self_surrender'])
        r = f.predict_range()
        assert r[0] < 12

    def test_aggravating_factors(self):
        from compiler_core.criminal_sentencing import SentencingFactors
        f = SentencingFactors(statutory_range_months=(12, 84), aggravating_factors=['recidivist', 'cruel'])
        r = f.predict_range()
        assert r[1] > 84


class TestIPValuation:
    def test_market_value(self):
        from compiler_core.ip_valuation import IPValuation
        v = IPValuation(ip_type='patent', market_value=1000000)
        assert v.estimate_value() == 1000000

    def test_licensing_based(self):
        from compiler_core.ip_valuation import IPValuation
        v = IPValuation(ip_type='patent', licensing_revenue=50000, remaining_useful_life_years=10)
        assert v.estimate_value() == 500000

    def test_fallback_to_cost(self):
        from compiler_core.ip_valuation import IPValuation
        v = IPValuation(ip_type='copyright', development_cost=200000)
        assert v.estimate_value() == 200000


class TestComplianceAndArbitration:
    def test_compliance_check(self):
        from compiler_core.compliance_monitoring import ComplianceCheck
        c = ComplianceCheck(regulation_id='GDPR_Art6', requirement='legal basis')
        result = c.evaluate(['consent_form'])
        assert result['status'] == 'compliant'

    def test_compliance_noncompliant(self):
        from compiler_core.compliance_monitoring import ComplianceCheck
        c = ComplianceCheck(regulation_id='GDPR_Art6', requirement='legal basis')
        result = c.evaluate([])
        assert result['status'] == 'non_compliant'

    def test_arbitration_enforceable(self):
        from compiler_core.arbitration_reasoning import ArbitrationAnalysis
        a = ArbitrationAnalysis(arbitration_clause_valid=True, arbitral_institution='CIETAC')
        result = a.evaluate_enforceability()
        assert result['enforceable']

    def test_arbitration_not_enforceable(self):
        from compiler_core.arbitration_reasoning import ArbitrationAnalysis
        a = ArbitrationAnalysis(arbitration_clause_valid=False)
        result = a.evaluate_enforceability()
        assert not result['enforceable']
