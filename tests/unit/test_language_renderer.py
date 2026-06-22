"""#18: LanguageRenderer rendering tests."""
import unittest
from compiler_core.proof_tree import ProofTree, ProofNode
from compiler_core.language_renderer import ChineseRenderer, EnglishRenderer


def _make_tree():
    """Build a sample ProofTree for testing."""
    tree = ProofTree(jurisdiction="CN")
    tree.add_node(ProofNode(
        node_id="R:BLK_001", kind="blocking",
        head_claim="consideration_blocked", confidence=1.0,
        children=[], source_anchor="CivilCode_Art471", modality="PROHIBITION",
    ))
    tree.add_node(ProofNode(
        node_id="S:SPC_013", kind="spc_tendency",
        head_claim="labor_tendency", confidence=0.85,
        children=[], source_anchor="SPC_LaborInterpretation", modality="PERMISSION",
    ))
    tree.add_node(ProofNode(
        node_id="C:rule_001", kind="statute",
        head_claim="contract_breach", confidence=0.92,
        children=[], source_anchor="CivilCode_Art585", modality="OBLIGATION",
    ))
    tree.blocked_claims = ["BLK_001"]
    tree.spc_tendencies = ["S:SPC_013"]
    tree.cn_claims = ["C:rule_001"]
    return tree


class TestChineseRenderer(unittest.TestCase):

    def test_renders_proof_tree(self):
        """ChineseRenderer renders a ProofTree without errors."""
        tree = _make_tree()
        renderer = ChineseRenderer(
            claim_table={"consideration_blocked": "约因阻断", "contract_breach": "违约"},
            anchor_table={"CivilCode_Art471": "民法典第471条", "CivilCode_Art585": "民法典第585条"},
        )
        output = renderer.render_proof_tree(tree)
        self.assertIn("中华人民共和国", output)
        self.assertIn("成文法阻断", output)
        self.assertIn("最高法裁判倾向", output)

    def test_renders_blocked_claims(self):
        """Blocked claims section is rendered."""
        tree = _make_tree()
        renderer = ChineseRenderer(claim_table={"consideration_blocked": "约因阻断"})
        output = renderer.render_proof_tree(tree)
        self.assertIn("BLOCKED", output)

    def test_renders_empty_tree(self):
        """Empty tree renders without error."""
        tree = ProofTree(jurisdiction="CN")
        renderer = ChineseRenderer()
        output = renderer.render_proof_tree(tree)
        self.assertIn("中华人民共和国", output)

    def test_fallback_to_raw_id(self):
        """Missing claim_table entry falls back to raw ID."""
        tree = _make_tree()
        renderer = ChineseRenderer(claim_table={})  # empty table
        output = renderer.render_proof_tree(tree)
        # Should contain raw IDs, not crash
        self.assertIn("contract_breach", output)


class TestEnglishRenderer(unittest.TestCase):

    def test_renders_proof_tree(self):
        """EnglishRenderer renders a ProofTree without errors."""
        tree = _make_tree()
        renderer = EnglishRenderer(
            claim_table={"consideration_blocked": "Consideration blocked", "contract_breach": "Breach of contract"},
        )
        output = renderer.render_proof_tree(tree)
        self.assertIn("PRC Legal Reasoning", output)
        self.assertIn("STATUTORY BLOCKING", output)

    def test_renders_empty_tree(self):
        """Empty tree renders without error."""
        tree = ProofTree(jurisdiction="US")
        renderer = EnglishRenderer()
        output = renderer.render_proof_tree(tree)
        self.assertIn("US", output)


class TestProofTree(unittest.TestCase):

    def test_summary(self):
        """ProofTree.summary() returns correct counts."""
        tree = _make_tree()
        summary = tree.summary()
        self.assertEqual(summary["total_nodes"], 3)
        self.assertEqual(summary["blocked_count"], 1)
        self.assertEqual(summary["spc_count"], 1)
        self.assertEqual(summary["cn_count"], 1)

    def test_get_blocking_nodes(self):
        """get_blocking_nodes returns only blocking type nodes."""
        tree = _make_tree()
        blocking = tree.get_blocking_nodes()
        self.assertEqual(len(blocking), 1)
        self.assertEqual(blocking[0].kind, "blocking")

    def test_get_statute_nodes(self):
        """get_statute_nodes returns only statute type nodes."""
        tree = _make_tree()
        statutes = tree.get_statute_nodes()
        self.assertEqual(len(statutes), 1)
        self.assertEqual(statutes[0].kind, "statute")


if __name__ == "__main__":
    unittest.main()
