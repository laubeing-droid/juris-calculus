"""Tests for privacy-gated LLM bridge."""
from tools.llm_bridge import _sanitize, evaluate_facts_llm, align_concepts_llm, generate_nlni_llm


def test_sanitize_strips_pii():
    text = "??????500??????110101199001011234???13800138000"
    clean = _sanitize(text)
    assert "??" not in clean
    assert "110101" not in clean
    assert "13800138000" not in clean


def test_llm_bridge_returns_tainted_when_no_key():
    result = evaluate_facts_llm("???????")
    assert result.get("tainted") or result.get("error")


def test_evaluate_facts_llm_structured():
    result = evaluate_facts_llm("????")
    assert isinstance(result, dict)


def test_align_concepts_llm_structured():
    result = align_concepts_llm("??", "contract")
    assert isinstance(result, dict)


def test_generate_nlni_llm_structured():
    result = generate_nlni_llm("??????")
    assert isinstance(result, dict)
