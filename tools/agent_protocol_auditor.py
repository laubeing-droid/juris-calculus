#!/usr/bin/env python3
"""Audit physically isolated agent collaboration protocol."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml


ROOT = Path(__file__).resolve().parent.parent


def audit_protocol(protocol_path: str = "configs/agent_collaboration_protocol.yaml") -> Dict[str, Any]:
    path = Path(protocol_path)
    if not path.is_absolute():
        path = ROOT / path
    issues: List[str] = []
    if not path.exists():
        return {"status": "FAIL", "issues": ["protocol file missing"], "protocol": str(path)}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    roles = data.get("roles", {})
    required_roles = {"implementer", "spec_compliance_reviewer", "code_quality_reviewer", "verification"}
    missing_roles = required_roles - set(roles)
    if missing_roles:
        issues.append("missing roles: " + ", ".join(sorted(missing_roles)))

    implementer = roles.get("implementer", {})
    status_enum = set(implementer.get("status_enum", []))
    required_status = {"DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"}
    if required_status - status_enum:
        issues.append("implementer.status_enum incomplete")
    if "declare_pass" not in set(implementer.get("forbidden_actions", [])):
        issues.append("implementer must be forbidden to declare_pass")

    spec = roles.get("spec_compliance_reviewer", {})
    quality = roles.get("code_quality_reviewer", {})
    verification = roles.get("verification", {})
    if spec.get("sequence") != 1:
        issues.append("spec_compliance_reviewer must have sequence=1")
    if quality.get("sequence") != 2:
        issues.append("code_quality_reviewer must have sequence=2")
    if verification.get("sequence") != 3:
        issues.append("verification must have sequence=3")
    if "spec_compliance_reviewer_PASS" not in set(quality.get("precondition", [])):
        issues.append("code_quality_reviewer requires spec_compliance_reviewer_PASS precondition")
    if "implementer_report" not in set(spec.get("must_not_trust", [])):
        issues.append("spec reviewer must not trust implementer_report")

    controller_rules = data.get("controller_rules", {})
    required_true_rules = [
        "provide_full_task_text_to_subagents",
        "subagents_must_not_be_forced_to_read_plan_file",
        "spec_review_before_quality_review",
        "reviewer_issue_requires_implementer_fix_and_rereview",
        "human_review_evidence_required_before_public_release",
    ]
    for rule in required_true_rules:
        if controller_rules.get(rule) is not True:
            issues.append(f"controller_rules.{rule} must be true")

    release_fields = set((data.get("release_evidence", {}) or {}).get("required_fields", []))
    for field in {"human_reviewer", "model_or_harness_disclosure", "verification_report"}:
        if field not in release_fields:
            issues.append(f"release_evidence missing {field}")

    return {"status": "PASS" if not issues else "FAIL", "issues": issues, "protocol": str(path)}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit agent collaboration protocol.")
    parser.add_argument("--protocol", default="configs/agent_collaboration_protocol.yaml")
    args = parser.parse_args(argv)
    report = audit_protocol(args.protocol)
    print(f"status={report['status']} issues={len(report['issues'])}")
    for issue in report["issues"]:
        print(f"ISSUE: {issue}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
