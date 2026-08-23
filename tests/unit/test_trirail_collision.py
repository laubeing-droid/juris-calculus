"""The retained PRC experiment is bounded to CBL and SPC inputs."""

from pathlib import Path

from compiler_core.prc_collision_engine import PRCCollisionEngine
from compiler_core.types import LegalFact


ROOT = Path(__file__).resolve().parents[2]


def test_experiment_has_no_formal_or_legacy_consumer() -> None:
    """No full-corpus track, path construction, or silent zero-count fallback remains."""

    source = (ROOT / "compiler_core" / "prc_collision_engine.py").read_text(encoding="utf-8")
    for marker in ("cn_rules", "_run_cn_track", "cn_rule_count", "cn_zero_streak"):
        assert marker not in source

    engine = PRCCollisionEngine()
    assert set(engine.rule_inventory["tracks"]) == {"blocking", "spc"}
    tree = engine.run({"Cross_Border_Context": LegalFact(id="Cross_Border_Context")})
    assert all(node_id.startswith(("R:", "S:")) for node_id in tree.nodes)
    assert tree.cn_claims == []
