#!/usr/bin/env python3
"""Dry-run migrate legacy LegalRule YAML into Typed Legal IR v3 sidecars."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.legal_ir_v3 import LegalIRRule
from compiler_core.plugin_registry import registry
from compiler_core.type_checker import check_legal_ir_rule
from compiler_core.types import LegalRule


def migrate_rule_file(
    source: str | Path,
    out: str | Path | None = None,
    jurisdiction: str = "",
    limit: int | None = None,
    repair_requests_out: str | Path | None = None,
) -> Dict[str, Any]:
    source_path = _resolve(source)
    data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        return _report(source_path, out, 0, [], [{"index": -1, "rule_id": "<file>", "issue": "RULES_NOT_LIST"}])

    migrated: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    findings: List[Dict[str, Any]] = []
    repair_requests: List[Dict[str, Any]] = []
    known_rule_ids = [str(rule.get("id", "")) for rule in raw_rules if isinstance(rule, dict)]

    for index, raw in enumerate(_take(raw_rules, limit)):
        if not isinstance(raw, dict):
            skipped.append({"index": index, "reason": "RULE_NOT_MAPPING"})
            findings.append({"index": index, "rule_id": "<non-mapping>", "issue": "RULE_NOT_MAPPING"})
            continue
        try:
            legal_rule = _legal_rule_from_dict(raw, default_jurisdiction=jurisdiction or _infer_jurisdiction(source_path))
            ir_rule = LegalIRRule.from_legal_rule(legal_rule, jurisdiction=legal_rule.jurisdiction)
            textual_exceptions = _normalize_exception_refs(ir_rule, known_rule_ids)
            for exception_index, text in enumerate(textual_exceptions, start=1):
                repair_requests.append(_exception_repair_request(source_path, legal_rule, text, index, exception_index))
            check_report = check_legal_ir_rule(ir_rule, known_rule_ids=known_rule_ids)
            for issue in check_report.issues:
                findings.append({"index": index, "rule_id": legal_rule.id, "issue": issue})
            migrated.append(_ir_rule_to_dict(ir_rule))
        except Exception as exc:
            skipped.append({"index": index, "rule_id": str(raw.get("id", "")), "reason": f"MIGRATION_ERROR:{exc}"})
            findings.append({"index": index, "rule_id": str(raw.get("id", "<unknown>")), "issue": f"MIGRATION_ERROR:{exc}"})

    if out is not None:
        out_path = _resolve(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "legal_ir_v3",
            "source": str(source_path),
            "jurisdiction": jurisdiction or _infer_jurisdiction(source_path),
            "rules": migrated,
        }
        out_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    if repair_requests_out is not None:
        repair_path = _resolve(repair_requests_out)
        repair_path.parent.mkdir(parents=True, exist_ok=True)
        repair_path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in repair_requests),
            encoding="utf-8",
        )

    return _report(
        source_path,
        out,
        len(raw_rules),
        skipped,
        findings,
        migrated_count=len(migrated),
        repair_request_count=len(repair_requests),
        repair_requests_out=repair_requests_out,
    )


def discover_rule_sources() -> List[Dict[str, str]]:
    """Discover first-class and addon rule YAML sources."""
    sources: Dict[str, Dict[str, str]] = {}
    for jurisdiction, rel in {
        "zh_CN": "configs/zh_CN/rules.yaml",
        "hk": "configs/hk/rules.yaml",
        "hk_expanded": "configs/hk/rules_expanded.yaml",
        "en_US": "configs/en_US/rules.yaml",
        "us_adapter": "configs/en_US/US_Adapter.yaml",
    }.items():
        path = ROOT / rel
        if path.exists():
            sources[rel] = {"jurisdiction": jurisdiction, "path": rel, "source": "config"}
    registry.discover()
    for code in registry.list_installed():
        rel = registry.get_rules_path(code)
        if rel and (ROOT / rel).exists():
            sources[rel] = {"jurisdiction": code, "path": rel, "source": "addon"}
    return sorted(sources.values(), key=lambda item: (item["jurisdiction"], item["path"]))


def _legal_rule_from_dict(data: Dict[str, Any], default_jurisdiction: str) -> LegalRule:
    return LegalRule(
        id=str(data.get("id", "")),
        premise_atoms=[str(item) for item in data.get("premise_atoms", []) or []],
        head_claim=str(data.get("head_claim", "")),
        exception_chain=[str(item) for item in data.get("exception_chain", []) or []],
        concepts=[str(item) for item in data.get("concepts", []) or []],
        mechanical_exception=bool(data.get("mechanical_exception", True)),
        head_type=str(data.get("head_type", "HORN")),
        attacks=[str(item) for item in data.get("attacks", []) or []],
        priority_over=[str(item) for item in data.get("priority_over", []) or []],
        source_anchor=str(data.get("source_anchor", "")),
        valid_from=str(data.get("valid_from", "")),
        valid_to=str(data.get("valid_to", "")),
        jurisdiction=str(data.get("jurisdiction", default_jurisdiction)),
        authority_rank=str(data.get("authority_rank", "")),
    )


def _normalize_exception_refs(rule: LegalIRRule, known_rule_ids: List[str]) -> List[str]:
    known = set(known_rule_ids)
    refs: List[str] = []
    textual: List[str] = []
    for item in rule.exceptions:
        if item in known:
            refs.append(item)
        else:
            textual.append(item)
    rule.exceptions = refs
    if textual:
        rule.priority["textual_exceptions"] = textual
    return textual


def _exception_repair_request(
    source_path: Path,
    rule: LegalRule,
    textual_exception: str,
    index: int,
    exception_index: int,
) -> Dict[str, Any]:
    digest = hashlib.sha256(textual_exception.encode("utf-8")).hexdigest()[:8]
    request_id = f"MIGRATE-{source_path.stem}-{rule.id}-{index}-EX{exception_index}-{digest}"
    payload = {
        "source": str(source_path),
        "rule_id": rule.id,
        "head_claim": rule.head_claim,
        "premise_atoms": rule.premise_atoms,
        "textual_exception": textual_exception,
        "jurisdiction": rule.jurisdiction,
    }
    return {
        "request_id": request_id,
        "batch_id": "TO_BE_ASSIGNED",
        "task": "ir_migration_repair",
        "input": payload,
        "constraints": {
            "repo_write_allowed": False,
            "must_return_jsonl": True,
            "allowed_statuses": ["candidate", "needs_context", "unsupported", "abstain"],
            "required_repair_type": "textual_exception_to_rule_ref_or_new_rule_candidate",
        },
        "input_hash": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
    }


def _ir_rule_to_dict(rule: LegalIRRule) -> Dict[str, Any]:
    data = asdict(rule)
    data["rule_type"] = rule.rule_type.value
    for variable in data.get("variables", []):
        variable["type"] = str(variable["type"].value if hasattr(variable["type"], "value") else variable["type"])
    return data


def _report(
    source_path: Path,
    out: str | Path | None,
    source_rule_count: int,
    skipped: List[Dict[str, Any]],
    findings: List[Dict[str, Any]],
    migrated_count: int = 0,
    repair_request_count: int = 0,
    repair_requests_out: str | Path | None = None,
) -> Dict[str, Any]:
    blocking = [item for item in findings if not str(item.get("issue", "")).startswith("SOURCE_ANCHOR")]
    return {
        "source": str(source_path),
        "out": str(_resolve(out)) if out is not None else None,
        "source_rule_count": source_rule_count,
        "migrated_count": migrated_count,
        "skipped_count": len(skipped),
        "finding_count": len(findings),
        "repair_request_count": repair_request_count,
        "repair_requests_out": str(_resolve(repair_requests_out)) if repair_requests_out is not None else None,
        "blocking_count": len(blocking),
        "status": "PASS" if not blocking and not skipped else "FAIL",
        "skipped": skipped,
        "findings": findings,
    }


def _infer_jurisdiction(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    if "zh_cn" in parts:
        return "zh_CN"
    if "hk" in parts:
        return "hk"
    if "en_us" in parts or "us" in parts:
        return "en_US"
    return "UNKNOWN"


def _take(items: List[Any], limit: int | None) -> Iterable[Any]:
    if limit is None:
        return items
    return items[:limit]


def _resolve(path: str | Path | None) -> Path:
    if path is None:
        raise ValueError("path is required")
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run migrate rule YAML to Typed Legal IR v3.")
    parser.add_argument("source", nargs="?")
    parser.add_argument("--discover", action="store_true", help="List discoverable config/addon rule sources.")
    parser.add_argument("--out")
    parser.add_argument("--jurisdiction", default="")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repair-requests-out", help="Write third-party LLM repair requests for textual exceptions.")
    parser.add_argument("--allow-findings", action="store_true", help="Return success even when non-blocking findings exist.")
    args = parser.parse_args()
    if args.discover:
        report = {"status": "PASS", "sources": discover_rule_sources(), "source_count": len(discover_rule_sources())}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if not args.source:
        parser.error("source is required unless --discover is used")
    report = migrate_rule_file(
        args.source,
        out=args.out,
        jurisdiction=args.jurisdiction,
        limit=args.limit,
        repair_requests_out=args.repair_requests_out,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.allow_findings and report["migrated_count"] > 0:
        return 0
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
