"""Experimental model/regex adapters must remain explicit proposal-only paths."""

import pytest

from pipeline.experimental.llm_client import (
    OpenAIProposalExtractor,
    ProposalExtractionError,
    RegexProposalExtractor,
    create_extractor,
)


def test_extractor_mode_is_explicit_and_never_silently_falls_back() -> None:
    with pytest.raises(ProposalExtractionError) as missing_mode:
        create_extractor()
    with pytest.raises(ProposalExtractionError) as missing_key:
        OpenAIProposalExtractor(api_key="")

    assert missing_mode.value.code == "EXTRACTION_MODE_REQUIRED"
    assert missing_key.value.code == "API_KEY_REQUIRED"


def test_regex_extractor_returns_candidates_not_engine_facts() -> None:
    result = RegexProposalExtractor().extract_legal_atoms("合同已经解除")

    assert result["status"] == "proposal_only"
    assert result["receipt"] == {
        "provider_kind": "regex",
        "fallback_used": False,
        "formal_admission": False,
    }
    assert "fact_candidates" in result
    assert "facts_to_engine" not in result
