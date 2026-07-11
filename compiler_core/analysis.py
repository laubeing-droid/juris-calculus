"""只读审计run的ADVISORY策略与结构化类案分析。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

from compiler_core.audit_bundle import default_state_root, verify_audit_bundle
from compiler_core.canonical_serialization import semantic_digest


ANALYSIS_SCHEMA_VERSION = "1.0"
CASE_INDEX_SCHEMA_VERSION = "1.0"


class AnalysisError(RuntimeError):
    """策略、类案index或artifact写入错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def analyze_strategy(run_id: str, *, state_root: Path | None = None) -> dict[str, Any]:
    """从完整审计run生成不改变结论的机器ADVISORY。"""

    root = Path(state_root or default_state_root()).resolve()
    verified = verify_audit_bundle(root, run_id)
    result = verified.semantic_result
    before = result.to_dict()
    paths: list[dict[str, Any]] = []
    for item in result.missing_fact_review:
        paths.append({
            "path_type": "EVIDENCE_COMPLETION",
            "basis_ids": [item.fact_id, *item.impacted_rule_ids, *item.impacted_claim_ids],
            "assumptions": [],
            "required_review": item.source_requirement,
        })
    attack_edges = [edge for edge in verified.graph_payload.get("edges", ()) if edge.get("type") in {"attack", "exception", "priority"}]
    if attack_edges:
        paths.append({
            "path_type": "CONFLICT_REVIEW",
            "basis_ids": sorted({str(edge.get("source", "")) for edge in attack_edges} | {str(edge.get("target", "")) for edge in attack_edges}),
            "assumptions": [],
            "required_review": "review explicit attack, exception, and priority edges",
        })
    if result.branches or result.taint:
        paths.append({
            "path_type": "ASSUMPTION_STRESS_TEST",
            "basis_ids": [branch.branch_id for branch in result.branches],
            "assumptions": list(result.taint),
            "required_review": "compare branch consequences without promoting assumptions",
        })
    if result.claims:
        paths.append({
            "path_type": "PRESERVE_FORMAL_BASIS",
            "basis_ids": [*result.claims, *result.used_rule_ids, *result.source_ids],
            "assumptions": [],
            "required_review": "verify source currency and certificate before external use",
        })
    if not paths:
        paths.append({
            "path_type": "NO_ACTIONABLE_FORMAL_BASIS",
            "basis_ids": [],
            "assumptions": [],
            "required_review": "supply verified facts or resolve engine/admission errors",
        })
    report = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis_kind": "LITIGATION_STRATEGY",
        "analysis_status": "ADVISORY",
        "run_id": result.run_id,
        "result_digest": result.result_digest,
        "result_status": result.result_status.value,
        "review_required": True,
        "formal_certificate_generated": False,
        "basis": {
            "claim_ids": list(result.claims),
            "rule_ids": list(result.used_rule_ids),
            "source_ids": list(result.source_ids),
            "risk_labels": list(result.risk_labels),
            "missing_fact_ids": list(result.missing_fact_ids),
        },
        "paths": paths,
        "limitations": [
            "advisory only",
            "no new facts or legal authorities inferred",
            "does not modify or replace the CanonicalResult",
        ],
    }
    if before != result.to_dict():
        raise AnalysisError("CANONICAL_RESULT_DRIFT", "strategy analysis changed the semantic result")
    return _write_analysis(root, result.run_id, result.result_digest, "strategy", report)


def analyze_similar_cases(
    run_id: str,
    index_path: Path,
    *,
    state_root: Path | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """用结构化集合特征做确定性类案排序，不使用向量库或远程embedding。"""

    if limit < 1 or limit > 100:
        raise AnalysisError("INVALID_LIMIT", "limit must be between 1 and 100")
    root = Path(state_root or default_state_root()).resolve()
    verified = verify_audit_bundle(root, run_id)
    index = load_case_index(index_path)
    result = verified.semantic_result
    current = {
        "fact_ids": set(result.used_fact_ids),
        "rule_ids": set(result.used_rule_ids),
        "claim_ids": set(result.claims),
        "edge_types": {str(edge.get("type", "")) for edge in verified.graph_payload.get("edges", ())},
    }
    matches = []
    for case in index["cases"]:
        features = {name: set(case.get(name, ())) for name in current}
        components = {
            "facts": _jaccard(current["fact_ids"], features["fact_ids"]),
            "rules": _jaccard(current["rule_ids"], features["rule_ids"]),
            "claims": _jaccard(current["claim_ids"], features["claim_ids"]),
            "edges": _jaccard(current["edge_types"], features["edge_types"]),
        }
        score = round(0.4 * components["facts"] + 0.3 * components["rules"] + 0.2 * components["claims"] + 0.1 * components["edges"], 6)
        matches.append({
            "case_id": case["case_id"],
            "score": score,
            "components": components,
            "similar_factors": {
                name: sorted(current[name] & features[name]) for name in current
            },
            "different_factors": {
                name: sorted(current[name] ^ features[name]) for name in current
            },
            "jurisdiction": case["jurisdiction"],
            "decision_date": case["decision_date"],
            "source_ref": case["source_ref"],
            "source_hash": case["source_hash"],
        })
    matches.sort(key=lambda item: (-item["score"], item["case_id"]))
    fixture = bool(index["fixture"])
    report = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis_kind": "SIMILAR_CASES",
        "analysis_status": "ADVISORY",
        "quality_status": "FIXTURE_ONLY" if fixture else "OPERATOR_DECLARED_INDEX",
        "run_id": result.run_id,
        "result_digest": result.result_digest,
        "review_required": True,
        "formal_certificate_generated": False,
        "index": {
            "index_id": index["index_id"],
            "version": index["version"],
            "index_digest": index["index_digest"],
            "jurisdiction": index["jurisdiction"],
            "source_id": index["source_id"],
            "fixture": fixture,
        },
        "matches": matches[:limit],
        "limitations": [
            "structural similarity does not predict a court outcome",
            "differences and source currency require lawyer review",
            "fixture indexes cannot establish real-world case quality",
        ],
    }
    return _write_analysis(root, result.run_id, result.result_digest, "similar-cases", report)


def load_case_index(path: Path) -> dict[str, Any]:
    """验证类案index schema、内容digest和逐案source hash。"""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisError("CASE_INDEX_UNAVAILABLE", type(exc).__name__) from exc
    required = {
        "schema_version", "index_id", "version", "index_digest", "jurisdiction",
        "source_id", "fixture", "cases",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise AnalysisError("INVALID_CASE_INDEX", "index fields mismatch")
    if payload["schema_version"] != CASE_INDEX_SCHEMA_VERSION or not isinstance(payload["cases"], list):
        raise AnalysisError("INVALID_CASE_INDEX", "unsupported schema or cases")
    calculated = semantic_digest({key: value for key, value in payload.items() if key != "index_digest"})
    if payload["index_digest"] != calculated:
        raise AnalysisError("CASE_INDEX_DIGEST_MISMATCH", "index content digest mismatch")
    case_required = {
        "case_id", "jurisdiction", "decision_date", "source_ref", "source_hash",
        "fact_ids", "rule_ids", "claim_ids", "edge_types",
    }
    case_ids: set[str] = set()
    for case in payload["cases"]:
        if not isinstance(case, dict) or set(case) != case_required:
            raise AnalysisError("INVALID_CASE_INDEX", "case fields mismatch")
        case_id = str(case["case_id"])
        if not case_id or case_id in case_ids:
            raise AnalysisError("INVALID_CASE_INDEX", "duplicate or empty case_id")
        case_ids.add(case_id)
        if not _is_sha256(str(case["source_hash"])):
            raise AnalysisError("INVALID_CASE_INDEX", "source_hash must be SHA-256")
        for field in ("fact_ids", "rule_ids", "claim_ids", "edge_types"):
            if not isinstance(case[field], list) or len(case[field]) != len(set(map(str, case[field]))):
                raise AnalysisError("INVALID_CASE_INDEX", f"{field} must be a unique array")
    return payload


def analysis_schema_document() -> dict[str, Any]:
    """返回ADVISORY输出和类案index的公共schema。"""

    strings = {"type": "array", "items": {"type": "string"}, "uniqueItems": True}
    digest = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    return {
        "$defs": {
            "StrategyAdvisory": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema_version", "analysis_kind", "analysis_status", "run_id", "result_digest", "result_status",
                    "review_required", "formal_certificate_generated", "basis", "paths", "limitations",
                ],
                "properties": {
                    "schema_version": {"const": ANALYSIS_SCHEMA_VERSION},
                    "analysis_kind": {"const": "LITIGATION_STRATEGY"},
                    "analysis_status": {"const": "ADVISORY"},
                    "run_id": {"type": "string"},
                    "result_digest": digest,
                    "result_status": {"type": "string"},
                    "review_required": {"const": True},
                    "formal_certificate_generated": {"const": False},
                    "basis": {"type": "object"},
                    "paths": {"type": "array", "items": {"type": "object"}},
                    "limitations": strings,
                },
            },
            "SimilarCasesAdvisory": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema_version", "analysis_kind", "analysis_status", "quality_status", "run_id",
                    "result_digest", "review_required", "formal_certificate_generated", "index", "matches", "limitations",
                ],
                "properties": {
                    "schema_version": {"const": ANALYSIS_SCHEMA_VERSION},
                    "analysis_kind": {"const": "SIMILAR_CASES"},
                    "analysis_status": {"const": "ADVISORY"},
                    "quality_status": {"type": "string", "enum": ["FIXTURE_ONLY", "OPERATOR_DECLARED_INDEX"]},
                    "run_id": {"type": "string"},
                    "result_digest": digest,
                    "review_required": {"const": True},
                    "formal_certificate_generated": {"const": False},
                    "index": {"type": "object"},
                    "matches": {"type": "array", "items": {"type": "object"}},
                    "limitations": strings,
                },
            },
            "CaseIndex": {
                "type": "object",
                "additionalProperties": False,
                "required": sorted([
                    "schema_version", "index_id", "version", "index_digest", "jurisdiction",
                    "source_id", "fixture", "cases",
                ]),
                "properties": {
                    "schema_version": {"const": CASE_INDEX_SCHEMA_VERSION},
                    "index_id": {"type": "string", "minLength": 1},
                    "version": {"type": "string", "minLength": 1},
                    "index_digest": digest,
                    "jurisdiction": {"type": "string", "minLength": 1},
                    "source_id": {"type": "string", "minLength": 1},
                    "fixture": {"type": "boolean"},
                    "cases": {"type": "array", "items": {"type": "object"}},
                },
            },
        }
    }


def _write_analysis(root: Path, run_id: str, result_digest: str, name: str, report: Mapping[str, Any]) -> dict[str, Any]:
    """写入独立ADVISORY artifact并返回紧凑引用。"""

    relative = Path("analysis") / run_id.replace("::", "--") / result_digest / f"{name}.json"
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    _atomic_write(root / relative, payload.encode("utf-8"))
    return {
        **dict(report),
        "artifact_ref": relative.as_posix(),
        "artifact_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    """任一侧无特征时记0，避免以共同缺失制造虚高相似度。"""

    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _is_sha256(value: str) -> bool:
    """验证小写或大写十六进制SHA-256。"""

    return len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)


def _atomic_write(path: Path, payload: bytes) -> None:
    """原子写ADVISORY artifact。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
