#!/usr/bin/env python3
"""Rule quality audit for legal rule YAML files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml


ROOT = Path(__file__).resolve().parent.parent
REQUIRED_FIELDS = {"id", "premise_atoms", "head_claim", "head_type"}


def audit_rules(path: str | Path, strict_source_anchor: bool = False, tests_root: str | Path | None = None) -> Dict[str, Any]:
    rule_path = _resolve(path)
    data = yaml.safe_load(rule_path.read_text(encoding="utf-8")) or {}
    rules = data.get("rules", [])
    findings: List[Dict[str, Any]] = []

    if not isinstance(rules, list):
        return {
            "path": str(rule_path),
            "rule_count": 0,
            "status": "FAIL",
            "findings": [{"rule_id": "<file>", "blocking_issue": True, "issue": "RULES_NOT_LIST"}],
        }

    ids = {str(rule.get("id", "")) for rule in rules if isinstance(rule, dict)}
    claims = {str(rule.get("head_claim", "")) for rule in rules if isinstance(rule, dict)}
    id_counts: Dict[str, int] = {}
    head_counts: Dict[str, int] = {}
    for rule in rules:
        if isinstance(rule, dict):
            id_counts[str(rule.get("id", ""))] = id_counts.get(str(rule.get("id", "")), 0) + 1
            head_counts[str(rule.get("head_claim", ""))] = head_counts.get(str(rule.get("head_claim", "")), 0) + 1
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            findings.append(_finding(index, "<non-mapping>", "RULE_NOT_MAPPING", True))
            continue
        rid = str(rule.get("id", f"rule[{index}]"))
        if id_counts.get(rid, 0) > 1:
            findings.append(_finding(index, rid, "DUPLICATE_RULE_ID", True))
        if rule.get("head_claim") and head_counts.get(str(rule.get("head_claim", "")), 0) > 1:
            findings.append(_finding(index, rid, "DUPLICATE_HEAD_CLAIM", False))
        for field in sorted(REQUIRED_FIELDS - set(rule.keys())):
            findings.append(_finding(index, rid, f"MISSING_FIELD:{field}", True))
        if not isinstance(rule.get("premise_atoms", []), list):
            findings.append(_finding(index, rid, "PREMISE_ATOMS_NOT_LIST", True))
        if not str(rule.get("head_claim", "")).strip():
            findings.append(_finding(index, rid, "EMPTY_HEAD_CLAIM", True))
        for ref in rule.get("exception_chain", []) or []:
            if ref not in ids:
                findings.append(_finding(index, rid, f"UNKNOWN_EXCEPTION:{ref}", True))
        for ref in rule.get("attacks", []) or []:
            if ref not in ids and ref not in claims:
                findings.append(_finding(index, rid, f"UNKNOWN_ATTACK_TARGET:{ref}", True))
        if rule.get("source_anchor") is None:
            findings.append(_finding(index, rid, "SOURCE_ANCHOR_MISSING", strict_source_anchor))
        elif not str(rule.get("source_anchor", "")).strip():
            findings.append(_finding(index, rid, "SOURCE_ANCHOR_EMPTY", strict_source_anchor))
        if rule.get("valid_from") and rule.get("valid_to") and str(rule["valid_from"]) > str(rule["valid_to"]):
            findings.append(_finding(index, rid, "INVALID_VALIDITY_INTERVAL", True))
        if tests_root and not _rule_id_mentioned(rid, tests_root):
            findings.append(_finding(index, rid, "RULE_ID_NOT_MENTIONED_IN_TESTS", False))

    # DDL audit
    _audit_ddl_dimensions(rule, findings, index, rid)

    graph = {
        str(rule.get("id", "")): list(rule.get("exception_chain", []) or []) + list(rule.get("attacks", []) or [])
        for rule in rules
        if isinstance(rule, dict)
    }
    for cycle in _cycles(graph):
        findings.append(_finding(-1, " -> ".join(cycle), "RULE_GRAPH_CYCLE", True))
    referenced = {ref for refs in graph.values() for ref in refs if ref in ids}
    for index, rule in enumerate(rules):
        if isinstance(rule, dict):
            rid = str(rule.get("id", ""))
            if rid and rid not in referenced and not rule.get("premise_atoms"):
                findings.append(_finding(index, rid, "DEAD_RULE_NO_PREMISES_OR_REFERENCES", False))

    blocking = [f for f in findings if f["blocking_issue"]]
    return {
        "path": str(rule_path),
        "rule_count": len(rules),
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "status": "PASS" if not blocking else "FAIL",
        "findings": findings,
    }


def _finding(index: int, rule_id: str, issue: str, blocking: bool) -> Dict[str, Any]:
    return {
        "index": index,
        "rule_id": rule_id,
        "issue": issue,
        "score": 0.0 if blocking else 0.5,
        "evidence": [],
        "blocking_issue": blocking,
        "repair_instruction": _repair(issue),
    }

def _audit_ddl_dimensions(rule: dict, findings: list, index: int, rid: str) -> None:
    norm = str(rule.get("norm_modality", "UNKNOWN") or "UNKNOWN")
    if norm == "UNKNOWN":
        findings.append(_finding(index, rid, "DDL_NORM_MODALITY_UNASSIGNED", False))
    rcp = rule.get("reparation_chain_pool") or []
    if rcp:
        for item in rcp:
            if isinstance(item, dict):
                alts = item.get("alternatives", []) or []
                for alt in alts:
                    if isinstance(alt, dict) and not alt.get("selector"):
                        findings.append(_finding(index, rid, "DDL_REMEDY_POOL_WITHOUT_SELECTOR", False))
    head = str(rule.get("head_claim", ""))
    for sig in [chr(25110)+chr(32773), chr(20219)+chr(36873)+chr(20854)+chr(19968), chr(31561)+chr(36829)+chr(32422)+chr(36131)+chr(20219)]:
        if sig in head and norm == "OBLIGATION":
            findings.append(_finding(index, rid, "DDL_OBLIGATION_WITH_OR_CHAIN", False))


def _repair(issue: str) -> str:
    if issue.startswith("MISSING_FIELD"):
        return "Add the required field and a focused regression test."
    if issue.startswith("UNKNOWN_"):
        return "Reference an existing rule id or claim id, or add the missing rule."
    if issue == "SOURCE_ANCHOR_EMPTY":
        return "Add source_anchor before promoting this rule beyond draft maturity."
    if issue.startswith("DDL_"):
        return "Assign norm_modality via ddl_preclassifier or LLM candidate pipeline."
    return "Inspect and repair the rule metadata."


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p


def _rule_id_mentioned(rule_id: str, tests_root: str | Path) -> bool:
    root = _resolve(tests_root)
    if not root.exists():
        return False
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".py", ".yaml", ".yml", ".json", ".txt"}:
            try:
                if rule_id in path.read_text(encoding="utf-8", errors="ignore"):
                    return True
            except OSError:
                continue
    return False


def _cycles(graph: Dict[str, List[str]]) -> List[List[str]]:
    found: List[List[str]] = []
    visiting: List[str] = []
    visited = set()

    def dfs(node: str) -> None:
        if node in visiting:
            found.append(visiting[visiting.index(node):] + [node])
            return
        if node in visited:
            return
        visiting.append(node)
        for nxt in graph.get(node, []):
            if nxt in graph:
                dfs(nxt)
        visiting.pop()
        visited.add(node)

    for node in graph:
        dfs(node)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit legal rule YAML quality.")
    parser.add_argument("path")
    parser.add_argument("--strict-source-anchor", action="store_true")
    parser.add_argument("--tests-root")
    args = parser.parse_args()
    report = audit_rules(args.path, strict_source_anchor=args.strict_source_anchor, tests_root=args.tests_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
