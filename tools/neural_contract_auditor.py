#!/usr/bin/env python3
"""Audit neural contracts, registry, and promotion policy."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.neural_yaml_sync import NeuralYAMLSyncer


def audit_neural_contracts(root: str | Path = ROOT) -> Dict[str, Any]:
    base = Path(root)
    findings: List[Dict[str, Any]] = []
    contracts = base / "neural" / "contracts"
    registry = base / "neural" / "registry" / "model_registry.yaml"
    required = [
        contracts / "feature_schema.yaml",
        contracts / "output_schema.yaml",
        contracts / "model_card_schema.yaml",
        contracts / "promotion_policy.yaml",
        registry,
    ]
    loaded: Dict[str, Any] = {}
    for path in required:
        if not path.exists():
            findings.append(_finding(str(path), "MISSING_FILE", True))
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        loaded[path.name] = data
        if not data.get("version"):
            findings.append(_finding(str(path), "VERSION_REQUIRED", True))

    output_schema = loaded.get("output_schema.yaml", {})
    if output_schema.get("requires_symbolic_verification") is not True:
        findings.append(_finding("output_schema.yaml", "SYMBOLIC_VERIFICATION_REQUIRED", True))
    for forbidden in ["legal_conclusion", "final_decision", "liability"]:
        if forbidden not in output_schema.get("forbidden_outputs", []):
            findings.append(_finding("output_schema.yaml", f"FORBIDDEN_OUTPUT_MISSING:{forbidden}", True))

    promotion = loaded.get("promotion_policy.yaml", {})
    if promotion.get("automatic_yaml_write") != "forbidden":
        findings.append(_finding("promotion_policy.yaml", "AUTOMATIC_YAML_WRITE_NOT_FORBIDDEN", True))
    syncer = NeuralYAMLSyncer(dry_run=promotion.get("automatic_yaml_write") == "forbidden")
    probe = syncer.promote("policy_probe", {"threshold": (0.1, 0.2)}, {"f1_gain": 0.0})
    if promotion.get("automatic_yaml_write") == "forbidden" and probe.recommendation not in {"PENDING_HUMAN_REVIEW", "REJECTED_BELOW_BASELINE"}:
        findings.append(_finding("promotion_policy.yaml", "PROMOTION_POLICY_SYNC_FAILED", True))

    registry_data = loaded.get("model_registry.yaml", {})
    if not isinstance(registry_data.get("models", []), list):
        findings.append(_finding("model_registry.yaml", "MODELS_NOT_LIST", True))
    else:
        seen = set()
        allowed_status = set((loaded.get("model_card_schema.yaml", {}) or {}).get("promotion_status_values", []))
        for model in registry_data.get("models", []):
            model_id = str(model.get("model_id", ""))
            if not model_id:
                findings.append(_finding("model_registry.yaml", "MODEL_ID_REQUIRED", True))
                continue
            if model_id in seen:
                findings.append(_finding("model_registry.yaml", f"DUPLICATE_MODEL_ID:{model_id}", True))
            seen.add(model_id)
            if model.get("promotion_status") not in allowed_status:
                findings.append(_finding("model_registry.yaml", f"INVALID_PROMOTION_STATUS:{model_id}", True))
            card_path = model.get("model_card")
            if card_path:
                card = base / str(card_path)
                if not card.exists():
                    findings.append(_finding("model_registry.yaml", f"MODEL_CARD_MISSING:{model_id}", True))
                else:
                    card_data = yaml.safe_load(card.read_text(encoding="utf-8")) or {}
                    for field in loaded.get("model_card_schema.yaml", {}).get("required_fields", []):
                        if field not in card_data:
                            findings.append(_finding(str(card), f"MODEL_CARD_FIELD_MISSING:{field}", True))

    blocking = [f for f in findings if f["blocking_issue"]]
    return {
        "status": "PASS" if not blocking else "FAIL",
        "finding_count": len(findings),
        "blocking_count": len(blocking),
        "findings": findings,
    }


def _finding(target: str, issue: str, blocking: bool) -> Dict[str, Any]:
    return {"target": target, "issue": issue, "blocking_issue": blocking}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit neural contracts.")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    report = audit_neural_contracts(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
