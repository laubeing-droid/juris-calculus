"""规则语料治理报告；复用pack完整性、准入inventory和人工promotion边界。"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

import yaml

from compiler_core.rule_packs import LoadedCorpusPack, RulePackRegistry
from compiler_core.types import build_rule_inventory, normalize_rule_admission, resolve_rule_source_anchor


REQUIRED_RULE_FIELDS = frozenset({"id", "premise_atoms", "head_claim"})
ALLOWED_MODALITIES = frozenset({"OBLIGATION", "PROHIBITION", "PERMISSION", "CONSTITUTIVE", "UNKNOWN", ""})


def audit_rule_file(path: str | Path, *, test_rule_ids: set[str] | None = None) -> dict[str, Any]:
    """审计单个规则YAML，并把缺来源保留为candidate问题而非自动修复。"""

    selected = Path(path)
    document = yaml.safe_load(selected.read_text(encoding="utf-8")) or {}
    rules = document.get("rules", []) if isinstance(document, dict) else []
    if not isinstance(rules, list):
        return {
            "resource": selected.name,
            "status": "FAIL",
            "inventory": {"corpus_total": 0, "reasoning_eligible_total": 0, "candidate_only_total": 0},
            "candidate_rule_ids": [],
            "findings": [_finding("<file>", "RULES_NOT_LIST", True)],
        }
    material = [dict(rule) for rule in rules if isinstance(rule, Mapping)]
    ids = [str(rule.get("id", "")) for rule in material]
    id_counts = Counter(ids)
    id_set = set(ids)
    claims = {str(rule.get("head_claim", "")) for rule in material}
    findings: list[dict[str, Any]] = []
    candidate_ids: list[str] = []
    for index, raw in enumerate(material):
        rule = normalize_rule_admission(raw)
        rule_id = str(rule.get("id", f"rule[{index}]"))
        if id_counts[rule_id] > 1:
            findings.append(_finding(rule_id, "DUPLICATE_RULE_ID", True))
        for field in sorted(REQUIRED_RULE_FIELDS - set(raw)):
            findings.append(_finding(rule_id, f"MISSING_FIELD:{field}", True))
        if not isinstance(raw.get("premise_atoms", []), list):
            findings.append(_finding(rule_id, "PREMISE_ATOMS_NOT_LIST", True))
        for reference in raw.get("exception_chain", ()) or ():
            if reference not in id_set:
                findings.append(_finding(rule_id, f"UNKNOWN_EXCEPTION:{reference}", True))
        for reference in raw.get("attacks", ()) or ():
            if reference not in id_set and reference not in claims:
                findings.append(_finding(rule_id, f"UNKNOWN_ATTACK_TARGET:{reference}", True))
        for reference in raw.get("priority_over", ()) or ():
            if reference not in id_set and reference not in claims:
                findings.append(_finding(rule_id, f"UNKNOWN_PRIORITY_TARGET:{reference}", True))
        source_anchor = resolve_rule_source_anchor(raw)
        if not source_anchor or str(rule.get("data_quality", "")) == "CANDIDATE_ONLY":
            candidate_ids.append(rule_id)
        if not source_anchor:
            findings.append(_finding(rule_id, "SOURCE_ANCHOR_MISSING", False))
        if raw.get("valid_from") and raw.get("valid_to") and str(raw["valid_from"]) > str(raw["valid_to"]):
            findings.append(_finding(rule_id, "INVALID_VALIDITY_INTERVAL", True))
        modality = str(raw.get("norm_modality", "UNKNOWN") or "UNKNOWN")
        if modality not in ALLOWED_MODALITIES:
            findings.append(_finding(rule_id, "INVALID_MODALITY", True))
        elif modality in {"UNKNOWN", ""}:
            findings.append(_finding(rule_id, "MODALITY_UNASSIGNED", False))
        for item in raw.get("reparation_chain_pool", ()) or ():
            if isinstance(item, Mapping):
                for alternative in item.get("alternatives", ()) or ():
                    if isinstance(alternative, Mapping) and not alternative.get("selector"):
                        findings.append(_finding(rule_id, "REMEDY_POOL_WITHOUT_SELECTOR", False))
        if test_rule_ids is not None and rule_id not in test_rule_ids:
            findings.append(_finding(rule_id, "RULE_ID_NOT_MENTIONED_IN_TESTS", False))
    for index, raw in enumerate(rules):
        if not isinstance(raw, Mapping):
            findings.append(_finding(f"rule[{index}]", "RULE_NOT_MAPPING", True))
    graph = {
        str(rule.get("id", "")): tuple(rule.get("exception_chain", ()) or ()) + tuple(rule.get("attacks", ()) or ())
        for rule in material
    }
    for cycle in _cycles(graph):
        findings.append(_finding(" -> ".join(cycle), "RULE_GRAPH_CYCLE", True))
    inventory = build_rule_inventory(material)
    blocking = sum(1 for finding in findings if finding["blocking"])
    return {
        "resource": selected.name,
        "status": "PASS" if blocking == 0 else "FAIL",
        "inventory": inventory,
        "candidate_rule_ids": sorted(set(candidate_ids)),
        "finding_count": len(findings),
        "blocking_count": blocking,
        "findings": sorted(findings, key=lambda item: (item["rule_id"], item["code"])),
    }


def audit_pack(
    registry: RulePackRegistry,
    pack_id: str,
    *,
    tests_root: Path | None = None,
) -> dict[str, Any]:
    """生成完整pack治理artifact；报告只能建议人工晋升。"""

    pack = registry.load_corpus_pack(pack_id)
    test_ids = _test_rule_ids(tests_root) if tests_root is not None else None
    files = [audit_rule_file(path, test_rule_ids=test_ids) for path in pack.rule_paths]
    source_snapshots = _source_inventory(pack)
    findings = [finding for report in files for finding in report["findings"]]
    candidate_ids = set(pack.verification.candidate_rule_ids)
    promotion_blocking = sum(
        1
        for finding in findings
        if finding["blocking"] or finding["code"] in {"SOURCE_ANCHOR_MISSING", "SOURCE_ANCHOR_EMPTY"}
    )
    blocking = sum(
        1
        for finding in findings
        if finding["blocking"] and finding["rule_id"] not in candidate_ids
    )
    unmentioned = sum(1 for item in findings if item["code"] == "RULE_ID_NOT_MENTIONED_IN_TESTS")
    verification = pack.verification
    return {
        "schema_version": "1.0",
        "report_kind": "RULE_GOVERNANCE",
        "pack_id": verification.pack_id,
        "pack_version": verification.version,
        "pack_digest": verification.content_digest,
        "jurisdiction": verification.jurisdiction,
        "integrity_valid": verification.integrity_valid,
        "reasoning_ready": verification.reasoning_ready,
        "inventory": dict(verification.inventory),
        "candidate_rule_ids": list(verification.candidate_rule_ids),
        "duplicate_rule_ids": sorted({item["rule_id"] for item in findings if item["code"] == "DUPLICATE_RULE_ID"}),
        "validity": {
            "effective_from": str(pack.manifest.get("effective_from", "")),
            "effective_to": str(pack.manifest.get("effective_to", "")),
        },
        "source_snapshots": source_snapshots,
        "test_coverage": {
            "status": "PASS" if tests_root is not None and unmentioned == 0 else "WARN" if tests_root is not None else "BLOCKED",
            "reason": "" if tests_root is not None else "tests_root_not_supplied",
            "unmentioned_rule_count": unmentioned,
        },
        "finding_count": len(findings),
        "blocking_count": blocking,
        "promotion_blocking_count": promotion_blocking,
        "status": "PASS" if verification.integrity_valid and blocking == 0 else "FAIL",
        "promotion": {
            "automatic": False,
            "suggestion_only": True,
            "required_action": "obtain external human approval, add verified source material, and re-verify the pack before changing pack status",
        },
        "file_reports": files,
    }


def write_governance_report(report: Mapping[str, Any], output_path: Path) -> str:
    """写入确定性JSON并返回内容SHA-256。"""

    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, output_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def governance_schema_document() -> dict[str, Any]:
    """返回治理artifact顶层严格schema。"""

    return {
        "$defs": {
            "RuleGovernanceReport": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema_version", "report_kind", "pack_id", "pack_version", "pack_digest",
                    "jurisdiction", "integrity_valid", "reasoning_ready", "inventory",
                    "candidate_rule_ids", "duplicate_rule_ids", "validity", "source_snapshots",
                    "test_coverage", "finding_count", "blocking_count", "promotion_blocking_count",
                    "status", "promotion", "file_reports",
                ],
                "properties": {
                    "schema_version": {"const": "1.0"},
                    "report_kind": {"const": "RULE_GOVERNANCE"},
                    "pack_id": {"type": "string"},
                    "pack_version": {"type": "string"},
                    "pack_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "jurisdiction": {"type": "string"},
                    "integrity_valid": {"type": "boolean"},
                    "reasoning_ready": {"type": "boolean"},
                    "inventory": {"type": "object"},
                    "candidate_rule_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "duplicate_rule_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "validity": {"type": "object"},
                    "source_snapshots": {"type": "array", "items": {"type": "object"}},
                    "test_coverage": {"type": "object"},
                    "finding_count": {"type": "integer", "minimum": 0},
                    "blocking_count": {"type": "integer", "minimum": 0},
                    "promotion_blocking_count": {"type": "integer", "minimum": 0},
                    "status": {"type": "string", "enum": ["PASS", "FAIL"]},
                    "promotion": {"type": "object"},
                    "file_reports": {"type": "array", "items": {"type": "object"}},
                },
            }
        }
    }


def _finding(rule_id: str, code: str, blocking: bool) -> dict[str, Any]:
    """构造稳定治理finding。"""

    return {"rule_id": rule_id, "code": code, "blocking": blocking}


def _source_inventory(pack: LoadedCorpusPack) -> list[dict[str, Any]]:
    """读取pack已hash验证的source manifest摘要。"""

    snapshots: list[dict[str, Any]] = []
    for path in pack.source_paths:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for source in document.get("sources", ()) if isinstance(document, Mapping) else ():
            if isinstance(source, Mapping):
                snapshots.append({
                    "source_id": str(source.get("source_id", "")),
                    "verified": source.get("verified") is True,
                    "content_hash": str(source.get("content_hash", "")),
                    "jurisdiction": str(source.get("jurisdiction", "")),
                    "effective_from": str(source.get("effective_from", "")),
                    "effective_to": str(source.get("effective_to", "")),
                })
    return sorted(snapshots, key=lambda item: item["source_id"])


def _test_rule_ids(root: Path) -> set[str]:
    """从显式测试目录提取可比较标识符；目录缺失即治理错误。"""

    selected = Path(root)
    if not selected.is_dir():
        raise ValueError("tests_root must be an existing directory")
    identifiers: set[str] = set()
    for path in sorted(selected.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".py", ".yaml", ".yml", ".json", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            identifiers.update(text.replace('"', " ").replace("'", " ").split())
    return identifiers


def _cycles(graph: Mapping[str, Iterable[str]]) -> list[list[str]]:
    """返回确定性规则引用环。"""

    found: list[list[str]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            found.append(visiting[visiting.index(node):] + [node])
            return
        if node in visited:
            return
        visiting.append(node)
        for target in sorted(str(item) for item in graph.get(node, ()) if str(item) in graph):
            visit(target)
        visiting.pop()
        visited.add(node)

    for node in sorted(graph):
        visit(node)
    return found
