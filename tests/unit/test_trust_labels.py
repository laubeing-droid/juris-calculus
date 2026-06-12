from compiler_core.trust_labels import (TrustLabel, EpistemicStatus, RuleMaturity,
    DataOrigin, RED_LINE_PHRASES)

class TestTrustLabels:
    def test_default_unverified(self):
        ep = EpistemicStatus()
        assert ep.trust_label == TrustLabel.UNVERIFIED

    def test_to_dict(self):
        ep = EpistemicStatus(trust_label=TrustLabel.ENGINEERING_BASELINE,
                             data_origin=DataOrigin.SYMBOLIC_ENGINE)
        d = ep.to_dict()
        assert d['trust_label'] == 'ENGINEERING_BASELINE'
        assert d['data_origin'] == 'SYMBOLIC_ENGINE'

    def test_redline_phrases(self):
        assert 'FINAL_ALL_THEOREMS_PROVED' in RED_LINE_PHRASES
        assert 'GraphSimilarityMetric' in RED_LINE_PHRASES

    def test_data_origin_enum(self):
        assert DataOrigin.TOY_SYNTHETIC.value == 'TOY_SYNTHETIC'
        assert DataOrigin.REAL_CASE_EXTRACTED.value == 'REAL_CASE_EXTRACTED'
