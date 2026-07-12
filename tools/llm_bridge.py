#!/usr/bin/env python3
"""Privacy-gated LLM bridge for JC. Zero API key = zero network calls."""
import os, json, re, hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
ROOT = Path(__file__).resolve().parent.parent
TAINT_TAG = "TAINTED_LLM_SUGGESTION"
DATA_ORIGIN = "NEURAL_LEAF_SUGGESTION"

def _key(): return os.environ.get("LLM_API_KEY", "")

def _log_call(mode, sanitized_input, result):
    out = ROOT / "过程文件" / "llm_audit"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log = {"timestamp": datetime.now(timezone.utc).isoformat(), "mode": mode, "input_hash": hashlib.sha256(sanitized_input.encode()).hexdigest()[:16], "result_summary": str(result)[:500]}
    (out / "call_{}_{}.json".format(stamp, mode)).write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

def _sanitize(text):
    """Privacy gate: strip PII before sending to external LLM."""
    t = text
    t = re.sub(r"[?????????????\d]+[???]", "[?????]", t)
    t = re.sub(r"[?][\u4e00-\u9fa5]{1,3}", "[?????]", t)
    t = re.sub(r"(\d{17}[\dXx]|\d{15})", "[???????]", t)
    t = re.sub(r"1[3-9]\d{9}", "[??????]", t)
    return t

def _call_llm(mode, sp, user_content):
    """Internal: privacy-gated LLM call."""
    if not _key(): return {"error": "no LLM_API_KEY", "tainted": True, "data_origin": DATA_ORIGIN}
    sanitized = _sanitize(user_content)
    try:
        from pipeline.llm_client import LegalSemanticExtractor
        ext = LegalSemanticExtractor()
        result = ext.extract_legal_atoms(sanitized)
        _log_call(mode, sanitized, result)
        if isinstance(result, dict):
            result["tainted"] = True
            result["data_origin"] = DATA_ORIGIN
            return result
        return {"raw": str(result), "tainted": True, "data_origin": DATA_ORIGIN}
    except Exception as e:
        return {"error": str(e), "tainted": True, "data_origin": DATA_ORIGIN}

def evaluate_facts_llm(fact_text):
    return _call_llm("evaluate_facts", "Extract structured legal facts as JSON array.", fact_text)

def align_concepts_llm(cn_concept, us_concept):
    return _call_llm("align_concepts", "Align Chinese and US legal concepts. Return JSON with aligned, confidence, note.", "CN: " + cn_concept + " US: " + us_concept)

def generate_nlni_llm(case_description):
    return _call_llm("generate_nlni", "Generate NLNI training pairs from description. Return JSON with pairs array.", case_description)
