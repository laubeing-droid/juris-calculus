"""Tests for privacy-gated LLM bridge."""
from tools.llm_bridge import _sanitize, evaluate_facts_llm, align_concepts_llm, generate_nlni_llm


def test_sanitize_removes_pii_patterns():
    text = "name is ZhangSan amount 5000000 id 110101199001011234 phone 13800138000"
    clean = _sanitize(text)
    assert "110101" not in clean
    assert "13800138000" not in clean


def test_llm_bridge_returns_tainted_when_no_key():
    result = evaluate_facts_llm("contract breach unpaid")
    assert result.get("tainted") or result.get("error")


def test_evaluate_facts_llm_structured():
    result = evaluate_facts_llm("contract breach")
    assert isinstance(result, dict)


def test_align_concepts_llm_structured():
    result = align_concepts_llm("contract", "breach")
    assert isinstance(result, dict)


def test_generate_nlni_llm_structured():
    result = generate_nlni_llm("contract dispute")
    assert isinstance(result, dict)
