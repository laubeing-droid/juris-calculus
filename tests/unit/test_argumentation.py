from compiler_core.argumentation import grounded_extension

class TestArgumentation:
    def test_single_claim_no_attacks(self):
        claims = [{'id': 'c1', 'confidence': 0.8}]
        result = grounded_extension(claims, [])
        assert result['accepted'] == ['c1']
        assert result['rejected'] == []

    def test_two_claims_mutual_attack(self):
        claims = [{'id': 'c1', 'confidence': 0.8}, {'id': 'c2', 'confidence': 0.7}]
        attacks = [('c1', 'c2'), ('c2', 'c1')]
        result = grounded_extension(claims, attacks)
        assert result['accepted'] == []

    def test_linear_attack_chain(self):
        claims = [{'id': 'c1', 'confidence': 0.9}, {'id': 'c2', 'confidence': 0.5}]
        attacks = [('c1', 'c2')]
        result = grounded_extension(claims, attacks)
        assert 'c1' in result['accepted']
        assert 'c2' in result['rejected']
