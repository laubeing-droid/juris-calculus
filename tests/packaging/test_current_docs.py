"""Current V4 documentation must not restore historical authority or release claims."""

from __future__ import annotations

from pathlib import Path

from compiler_core.version import __version__


ROOT = Path(__file__).resolve().parents[2]
CURRENT = (
    ROOT / "README.md",
    ROOT / "CHANGELOG.md",
    ROOT / "HANDOFF.md",
    ROOT / "AGENTS.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "operations" / "RELEASE_V4.md",
)


def test_current_entrypoint_docs_are_v4_and_reference_live_paths() -> None:
    joined = "\n".join(path.read_text(encoding="utf-8") for path in CURRENT)
    assert __version__ == "4.0.0"
    assert "4.0.0" in joined
    for relative in (
        "compiler_core/version.py", "schemas/jc-v4.schema.json", "mcp_manifest.json",
        "tools/build_provenance.py", ".github/workflows/ci.yml",
        ".github/workflows/auto-release.yml",
    ):
        assert (ROOT / relative).is_file(), relative
        assert relative in joined
    assert "tests\\unit\\test_v3_entrypoint_boundary.py" not in joined


def test_historical_guides_are_not_current_authority() -> None:
    joined = "\n".join(path.read_text(encoding="utf-8") for path in CURRENT)
    assert "MIGRATION_V2_TO_V3.md" not in joined
    assert "Legacy corpora are available" not in joined
    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "Historical task definitions (not current authority)" in docs_index
    assert "V3_HISTORICAL_REPLAY.md" not in docs_index
    assert not (ROOT / "docs/operations/V3_HISTORICAL_REPLAY.md").exists()


def test_release_docs_do_not_claim_external_promotion_is_complete() -> None:
    release = (ROOT / "docs" / "operations" / "RELEASE_V4.md").read_text(encoding="utf-8")
    handoff = (ROOT / "HANDOFF.md").read_text(encoding="utf-8")
    assert "TEST_ONLY_NOT_PROMOTABLE" in release
    assert "生产发布" in release
    assert "not completed" in handoff
    assert "branch protection" in handoff
    assert "生产 Ed25519" in handoff


def test_current_docs_make_no_unverifiable_external_completion_claim() -> None:
    joined = "\n".join(path.read_text(encoding="utf-8") for path in (*CURRENT, ROOT / "memory.md", ROOT / "remediation/v4/STATUS.md"))
    assert "LOCAL_PRODUCTION_ACTIVE" not in joined
    assert "92 tasks" not in joined
    assert "JC_REMEDIATION_STATE_ROOT" not in joined
