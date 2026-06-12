#!/usr/bin/env python3
"""Criminal multi-party/multi-charge reasoning helpers.

This module distills the MultiJustice-MPMCP scenario model into symbolic
checks.  It does not embed the dataset; it uses the four scenario topology as
L3 routing metadata, L4 audit policy, and L5 binding verification.
"""
from __future__ import annotations

import re
import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

import yaml

from compiler_core.config_paths import criminal_complexity_path


DEFAULT_CONFIG = {
    "scenarios": {
        "S1": {"label": "单人单罪", "min_defendants": 1, "max_defendants": 1, "min_charges": 1, "max_charges": 1, "route_tag": "criminal_single_defendant_single_charge"},
        "S2": {"label": "单人多罪", "min_defendants": 1, "max_defendants": 1, "min_charges": 2, "max_charges": None, "route_tag": "criminal_single_defendant_multi_charge"},
        "S3": {"label": "多人单罪", "min_defendants": 2, "max_defendants": None, "min_charges": 1, "max_charges": 1, "route_tag": "criminal_multi_defendant_single_charge"},
        "S4": {"label": "多人多罪", "min_defendants": 2, "max_defendants": None, "min_charges": 2, "max_charges": None, "route_tag": "criminal_multi_defendant_multi_charge"},
    },
    "route_keywords": {"criminal": ["刑事", "犯罪", "罪名", "被告人", "公诉机关", "判处", "有期徒刑", "共同犯罪"]},
    "audit_policy": {
        "require_defendant_charge_binding_for": ["S2", "S3", "S4"],
        "warn_if_claim_mentions_charge_without_defendant": True,
        "warn_if_claim_mentions_penalty_without_defendant": True,
    },
    "binding_fields": {
        "defendants": ["defendant", "defendants", "defendant_ls", "被告人"],
        "charges": ["accusation", "charge", "charges", "罪名"],
        "per_defendant_charges": ["defendant_accusation", "defendant_charge", "被告人罪名"],
        "per_defendant_judgment": ["defendant_judgement", "defendant_judgment", "被告人判决"],
        "relevant_law": ["relevant_law", "relevant_article", "article_content", "法律依据", "适用法条"],
    },
}


@dataclass
class CriminalComplexityResult:
    scenario_id: str = "UNKNOWN"
    scenario_label: str = "未识别"
    route_tag: str = ""
    defendant_count: int = 0
    charge_count: int = 0
    defendants: List[str] = field(default_factory=list)
    charges: List[str] = field(default_factory=list)
    per_defendant_charges: Dict[str, List[str]] = field(default_factory=dict)
    relevant_law: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def requires_binding_verification(self) -> bool:
        return self.scenario_id in {"S2", "S3", "S4"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_label": self.scenario_label,
            "route_tag": self.route_tag,
            "defendant_count": self.defendant_count,
            "charge_count": self.charge_count,
            "defendants": self.defendants,
            "charges": self.charges,
            "per_defendant_charges": self.per_defendant_charges,
            "relevant_law": self.relevant_law,
            "warnings": self.warnings,
            "requires_binding_verification": self.requires_binding_verification,
        }


def load_criminal_complexity_config(path: Optional[str] = None) -> Dict[str, Any]:
    cfg_path = Path(path or criminal_complexity_path("zh_CN"))
    if not cfg_path.exists():
        return DEFAULT_CONFIG
    loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    merged = dict(DEFAULT_CONFIG)
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def classify_criminal_complexity(items: Any, config: Optional[Dict[str, Any]] = None) -> CriminalComplexityResult:
    cfg = config or load_criminal_complexity_config()
    records = _normalize_records(items)
    defendants = _unique(_collect_values(records, cfg["binding_fields"]["defendants"]))
    charges = _unique(_collect_values(records, cfg["binding_fields"]["charges"]))
    per_defendant = _collect_binding_map(records, cfg["binding_fields"]["per_defendant_charges"], defendants, charges)
    relevant_law = _unique(_collect_values(records, cfg["binding_fields"]["relevant_law"]))

    text_blob = "\n".join(_record_text(record) for record in records)
    if not defendants:
        defendants = _extract_defendants_from_text(text_blob)
    if not charges:
        charges = _extract_charges_from_text(text_blob)
    if not per_defendant:
        per_defendant = _infer_simple_bindings(defendants, charges)

    scenario_id = _match_scenario(len(defendants), len(charges), cfg["scenarios"])
    scenario = cfg["scenarios"].get(scenario_id, {})
    result = CriminalComplexityResult(
        scenario_id=scenario_id,
        scenario_label=scenario.get("label", "未识别"),
        route_tag=scenario.get("route_tag", ""),
        defendant_count=len(defendants),
        charge_count=len(charges),
        defendants=defendants,
        charges=charges,
        per_defendant_charges=per_defendant,
        relevant_law=relevant_law,
    )
    result.warnings = _binding_warnings(result, cfg)
    return result


def is_criminal_case(items: Any, config: Optional[Dict[str, Any]] = None) -> bool:
    cfg = config or load_criminal_complexity_config()
    text_blob = "\n".join(_record_text(record) for record in _normalize_records(items))
    if any(keyword in text_blob for keyword in cfg.get("route_keywords", {}).get("criminal", [])):
        return True
    result = classify_criminal_complexity(items, cfg)
    return bool(result.defendants and result.charges)


def audit_criminal_claims(case_items: Any, claims: Optional[Sequence[Any]] = None,
                          config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = config or load_criminal_complexity_config()
    result = classify_criminal_complexity(case_items, cfg)
    issues = list(result.warnings)
    policy = cfg.get("audit_policy", {})
    claim_texts = [_record_text(c) for c in (claims or [])]

    if policy.get("warn_if_claim_mentions_charge_without_defendant", True):
        for text in claim_texts:
            if _mentions_any(text, result.charges) and not _mentions_any(text, result.defendants):
                issues.append("刑事结论提到罪名但没有绑定具体被告人")
    if policy.get("warn_if_claim_mentions_penalty_without_defendant", True):
        for text in claim_texts:
            if re.search(r"(有期徒刑|拘役|管制|罚金|缓刑|无期徒刑|死刑)", text) and not _mentions_any(text, result.defendants):
                issues.append("刑罚结论没有绑定具体被告人")

    return {"complexity": result.to_dict(), "issues": _unique(issues), "passed": not issues}


def verify_actor_charge_binding(claim: Any, case_items: Any,
                                config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    result = classify_criminal_complexity(case_items, config)
    text = _record_text(claim)
    issues: List[str] = []
    if result.requires_binding_verification:
        if not _mentions_any(text, result.defendants):
            issues.append("缺少被告人绑定")
        if not _mentions_any(text, result.charges):
            issues.append("缺少罪名绑定")
        if result.relevant_law and not _mentions_any(text, result.relevant_law):
            issues.append("缺少法条绑定")
    return {"passed": not issues, "issues": issues, "complexity": result.to_dict()}


def _normalize_records(items: Any) -> List[Any]:
    if items is None:
        return []
    if isinstance(items, (str, bytes, Mapping)):
        return [items]
    if isinstance(items, Iterable):
        return list(items)
    return [items]


def _record_text(record: Any) -> str:
    if record is None:
        return ""
    if isinstance(record, bytes):
        return record.decode("utf-8", errors="ignore")
    if isinstance(record, str):
        return record
    if isinstance(record, Mapping):
        return " ".join(_stringify(v) for v in record.values())
    parts = []
    for attr in ("id", "description", "source", "raw_text", "head_claim"):
        if hasattr(record, attr):
            parts.append(_stringify(getattr(record, attr)))
    return " ".join(parts)


def _collect_values(records: Sequence[Any], field_names: Sequence[str]) -> List[str]:
    values: List[str] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        normalized = {str(k).strip(): v for k, v in record.items()}
        for name in field_names:
            if name in normalized:
                values.extend(_split_values(normalized[name]))
    return values


def _collect_binding_map(records: Sequence[Any], field_names: Sequence[str],
                         defendants: Sequence[str], charges: Sequence[str]) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        normalized = {str(k).strip(): v for k, v in record.items()}
        for name in field_names:
            if name not in normalized:
                continue
            raw = normalized[name]
            parsed = _literal_or_raw(raw)
            raw = parsed
            if isinstance(raw, Mapping):
                for defendant, charge_values in raw.items():
                    mapping[str(defendant)] = _unique(_split_values(charge_values))
            elif isinstance(raw, list):
                for item in raw:
                    if isinstance(item, Mapping):
                        defendant = item.get("defendant") or item.get("被告人")
                        charge = item.get("charge") or item.get("accusation") or item.get("罪名")
                        if defendant and charge:
                            mapping.setdefault(str(defendant), [])
                            mapping[str(defendant)].extend(_split_values(charge))
            elif isinstance(raw, str):
                for defendant in defendants:
                    if defendant in raw:
                        linked = [charge for charge in charges if charge in raw]
                        if linked:
                            mapping.setdefault(defendant, [])
                            mapping[defendant].extend(linked)
    return {k: _unique(v) for k, v in mapping.items()}


def _split_values(value: Any) -> List[str]:
    if value is None:
        return []
    value = _literal_or_raw(value)
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for item in value:
            if isinstance(item, str):
                clean = item.strip()
                if clean:
                    out.append(clean)
            else:
                out.extend(_split_values(item))
        return out
    if isinstance(value, Mapping):
        out: List[str] = []
        for item in value.values():
            out.extend(_split_values(item))
        return out
    text = str(value).strip()
    if not text:
        return []
    parts = re.split(r"[、,，;；/|]+", text)
    return [p.strip() for p in parts if p.strip()]


def _literal_or_raw(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{(":
        return value
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return value


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_stringify(v) for v in value)
    if isinstance(value, Mapping):
        return " ".join(f"{k}:{_stringify(v)}" for k, v in value.items())
    return str(value)


def _unique(values: Sequence[str]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _extract_defendants_from_text(text: str) -> List[str]:
    names = re.findall(r"被告人([\u4e00-\u9fa5A-Za-z0-9]{1,8})", text)
    return _unique([n for n in names if n not in {"因", "犯", "被", "系"}])


def _extract_charges_from_text(text: str) -> List[str]:
    charges = re.findall(r"犯([\u4e00-\u9fa5]{2,20}?罪)", text)
    charges.extend(re.findall(r"以([\u4e00-\u9fa5]{2,20}?罪)", text))
    return _unique(charges)


def _match_scenario(defendant_count: int, charge_count: int, scenarios: Mapping[str, Mapping[str, Any]]) -> str:
    if defendant_count <= 0 or charge_count <= 0:
        return "UNKNOWN"
    for scenario_id, spec in scenarios.items():
        if _within(defendant_count, spec.get("min_defendants"), spec.get("max_defendants")) and _within(charge_count, spec.get("min_charges"), spec.get("max_charges")):
            return scenario_id
    return "UNKNOWN"


def _within(value: int, minimum: Optional[int], maximum: Optional[int]) -> bool:
    if minimum is not None and value < minimum:
        return False
    if maximum is not None and value > maximum:
        return False
    return True


def _binding_warnings(result: CriminalComplexityResult, config: Dict[str, Any]) -> List[str]:
    required = set(config.get("audit_policy", {}).get("require_defendant_charge_binding_for", []))
    warnings: List[str] = []
    if result.scenario_id in required and not result.per_defendant_charges:
        warnings.append(f"{result.scenario_label}案件缺少被告人-罪名逐人绑定")
    if result.scenario_id in required and result.per_defendant_charges:
        missing = [d for d in result.defendants if d not in result.per_defendant_charges]
        if missing:
            warnings.append("部分被告人缺少罪名绑定: " + ", ".join(missing))
    return warnings


def _infer_simple_bindings(defendants: Sequence[str], charges: Sequence[str]) -> Dict[str, List[str]]:
    if len(defendants) == 1 and charges:
        return {defendants[0]: list(charges)}
    if len(charges) == 1 and defendants:
        return {defendant: [charges[0]] for defendant in defendants}
    return {}


def _mentions_any(text: str, values: Sequence[str]) -> bool:
    return any(value and value in text for value in values)
