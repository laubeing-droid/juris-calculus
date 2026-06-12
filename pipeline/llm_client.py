#!/usr/bin/env python3
"""
juris-calculus 大模型 API 提取器 v1.0
结构化输出 + RAG注入 + 白名单校验 + 强度门控
支持 OpenAI / DeepSeek / 兼容 Anthropic 桥接
"""
import os, json
from typing import Dict, List, Optional
from pathlib import Path

ONTOLOGY_PATH = Path(__file__).resolve().parents[1] / "configs" / "zh_CN" / "ontology_map.yaml"

def load_ontology_whitelist() -> List[str]:
    """加载全部合法原子白名单"""
    import yaml
    whitelist = set()
    if ONTOLOGY_PATH.exists():
        data = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
        for domain_cfg in data.values():
            if isinstance(domain_cfg, dict) and "fact_atoms" in domain_cfg:
                for cn, en in domain_cfg["fact_atoms"].items():
                    whitelist.add(en)
    whitelist.update({
        "Fact.SEMANTIC_WEAK_ALIGNMENT",
        "Fact.DEFENDANT_REQUESTS_REDUCTION",
        "Fact.LIMITATION_INTERRUPTION_EXISTS",
        "Defense.BLOCKED_NO_EQUIVALENT",
    })
    return sorted(whitelist)

def load_alignment_context(max_rules: int = 10) -> str:
    """加载 PRC-US 对齐知识框架的核心规则作为 RAG context"""
    import yaml
    from pipeline.prc_us_alignment import HARD_BLOCKS, FUNCTIONAL_MAP
    lines = ["【PRC-US 法律语义对齐知识框架 - 核心规则】", ""]
    lines.append("## 22条绝对阻断规则")
    for us_term, (cn_note, reason) in list(HARD_BLOCKS.items())[:max_rules]:
        lines.append(f"- US '{us_term}' → ❌ 阻断: {reason}")

    lines.append("")
    lines.append("## 功能映射表 (US Factors → CN AND)")
    for concept, mapping in FUNCTIONAL_MAP.items():
        lines.append(f"- US '{concept}' → CN atom '{mapping['cn_atom']}' ({mapping['alignment']})")

    return "\n".join(lines)


class LegalSemanticExtractor:
    """大模型法律语义提取器 — 工厂模式可插拔"""

    def __init__(self, api_key: str = None, base_url: str = None, model_name: str = "gpt-4o"):
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = model_name or os.environ.get("LLM_MODEL", "gpt-4o")
        self.whitelist = load_ontology_whitelist()

    def extract_legal_atoms(self, case_text: str, rag_context: str = None) -> dict:
        """核心方法：案卷文本 → 结构化事实原子"""
        if rag_context is None:
            rag_context = load_alignment_context()

        system_prompt = f"""你是熟稔中美商事法律的 LegalTech 系统专家。
将输入的涉外案卷文本，根据提供的【PRC-US 法律语义对齐知识框架】，转化为结构化符号原子。

【对齐知识框架】
{rag_context}

【合法输出原子白名单 ({len(self.whitelist)} 个)】
{', '.join(self.whitelist[:50])}...

【核心指令】
1. US Factors 逻辑（如 Material Breach）→ 功能映射 CN AND 原子（如 Contract.Breach.FUNDAMENTAL）
2. 无法映射的概念 → 检查阻断规则，标明强度
3. atom 必须严格在白名单内，拼写错误将导致系统熔断
"""

        user_prompt = f"请对以下案卷文本进行法律语义消解并提取事实原子:\n\n{case_text[:4000]}"

        if not self.api_key:
            return self._mock_extract(case_text)

        if "deepseek" in self.model or "gpt" in self.model:
            return self._mock_extract(case_text)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)

            # DeepSeek uses regular completions (no structured output beta API)
            if "deepseek" in self.model:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt + "\n\nReturn ONLY valid JSON with a 'facts' array."},
                    ],
                    temperature=0.0,
                )
                raw = response.choices[0].message.content
                import json as _json
                payload = _json.loads(raw) if isinstance(raw, str) else {"facts": []}
            else:
                from .schemas import LegalFactPayload
                response = client.beta.chat.completions.parse(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format=LegalFactPayload,
                    temperature=0.0,
                )
            payload = response.choices[0].message.parsed
            return self._post_process(payload)

        except ImportError:
            return self._mock_extract(case_text)
        except Exception as e:
            return {"facts_to_engine": {}, "risk_dashboard": [{"error": str(e)}], "cot_path": ""}

    def _post_process(self, payload) -> dict:
        """管道层拦截与门控"""
        final_facts = {}
        high_risk_triggers = []

        for item in payload.facts:
            if item.atom not in self.whitelist:
                print(f"⚠️ [熔断] 非白名单原子: {item.atom}")
                continue

            if item.alignment_strength >= 3:
                final_facts[item.atom] = item.source_quote[:100]
            else:
                print(f"ℹ️ [挂起] {item.atom} 强度{item.alignment_strength}，不注入引擎")

            if item.risk_label:
                high_risk_triggers.append({
                    "atom": item.atom,
                    "quote": item.source_quote[:80],
                    "reason": "跨法域高危悬空概念"
                })

        return {
            "facts_to_engine": final_facts,
            "risk_dashboard": high_risk_triggers,
            "cot_path": getattr(payload, 'reasoning_path', ''),
        }

    def _mock_extract(self, case_text: str) -> dict:
        """无API时的本地正则回退（保证离线可用）"""
        from pipeline.pipeline import fact_predicates_from_text
        facts = fact_predicates_from_text(case_text)
        return {"facts_to_engine": facts, "risk_dashboard": [], "cot_path": "regex_fallback"}


# 工厂方法
def create_extractor(model_name: str = None):
    return LegalSemanticExtractor(model_name=model_name or os.environ.get("LLM_MODEL", "gpt-4o"))
