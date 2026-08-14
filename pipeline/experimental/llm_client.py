"""Explicit proposal-only extractors with no provider-to-regex fallback."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ONTOLOGY_PATH = Path(__file__).resolve().parents[2] / "configs" / "zh_CN" / "ontology_map.yaml"


class ProposalExtractionError(RuntimeError):
    """Stable failure for unavailable or invalid proposal providers."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


def load_ontology_whitelist() -> tuple[str, ...]:
    import yaml

    whitelist: set[str] = set()
    if ONTOLOGY_PATH.exists():
        document = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8")) or {}
        for domain_config in document.values():
            if isinstance(domain_config, dict) and isinstance(domain_config.get("fact_atoms"), dict):
                whitelist.update(str(atom) for atom in domain_config["fact_atoms"].values())
    whitelist.update({
        "Fact.SEMANTIC_WEAK_ALIGNMENT",
        "Fact.DEFENDANT_REQUESTS_REDUCTION",
        "Fact.LIMITATION_INTERRUPTION_EXISTS",
        "Defense.BLOCKED_NO_EQUIVALENT",
    })
    return tuple(sorted(whitelist))


class RegexProposalExtractor:
    """Explicit deterministic baseline; output is never an admitted fact."""

    def extract_legal_atoms(self, case_text: str, rag_context: str | None = None) -> dict[str, Any]:
        from pipeline.pipeline import fact_predicates_from_text

        candidates = fact_predicates_from_text(case_text)
        return {
            "status": "proposal_only",
            "fact_candidates": dict(sorted(candidates.items())),
            "risk_dashboard": [],
            "receipt": {
                "provider_kind": "regex",
                "fallback_used": False,
                "formal_admission": False,
            },
        }


class OpenAIProposalExtractor:
    """Real OpenAI-compatible provider; missing capability fails explicitly."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str = "gpt-4o",
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("LLM_API_KEY", "")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model_name = model_name
        self.whitelist = frozenset(load_ontology_whitelist())
        if not self.api_key:
            raise ProposalExtractionError("API_KEY_REQUIRED", "real provider requires LLM_API_KEY")

    def extract_legal_atoms(self, case_text: str, rag_context: str | None = None) -> dict[str, Any]:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProposalExtractionError("PROVIDER_UNAVAILABLE", "openai package is not installed") from exc

        prompt = (
            "Return JSON with a facts array. Each item must contain atom and source_quote. "
            "These are proposals only and are not verified facts.\n\n"
            + (rag_context or "")
        )
        try:
            response = OpenAI(api_key=self.api_key, base_url=self.base_url).chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": case_text[:4000]},
                ],
                temperature=0.0,
            )
            raw = response.choices[0].message.content or "{}"
            payload = json.loads(raw)
        except Exception as exc:
            raise ProposalExtractionError("PROVIDER_CALL_FAILED", type(exc).__name__) from exc

        candidates = []
        for item in payload.get("facts", []):
            if not isinstance(item, dict) or str(item.get("atom", "")) not in self.whitelist:
                continue
            candidates.append({
                "atom": str(item["atom"]),
                "source_quote": str(item.get("source_quote", ""))[:100],
            })
        return {
            "status": "proposal_only",
            "fact_candidates": candidates,
            "risk_dashboard": [],
            "receipt": {
                "provider_kind": "openai_compatible",
                "model": self.model_name,
                "fallback_used": False,
                "formal_admission": False,
            },
        }


def create_extractor(*, mode: str | None = None, **kwargs):
    """Require an explicit real or regex mode; never infer fallback behavior."""

    if mode == "regex":
        return RegexProposalExtractor()
    if mode == "real":
        return OpenAIProposalExtractor(**kwargs)
    raise ProposalExtractionError("EXTRACTION_MODE_REQUIRED", "mode must be 'real' or 'regex'")
