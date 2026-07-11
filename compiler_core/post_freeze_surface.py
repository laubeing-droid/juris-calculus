#!/usr/bin/env python3
"""Post-freeze public kernel surface for Playbook F1-F14.

This module intentionally stays at the engineering wrapper layer. It exposes
auditable toy-kernel capabilities, report shapes, and fail-closed gates without
changing DecisionStatus, the certificate checker, or attack/priority semantics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping

from compiler_core.argumentation import grounded_extension, proof_trace
from compiler_core.cross_jurisdiction_router import CrossJurisdictionRouter
from compiler_core.horn_completeness import analyze_rule_impact, compute_missing_evidence
from compiler_core.output_firewall import renderer_firewall_metadata
from compiler_core.types import LegalRule


PUBLIC_KERNEL = "PUBLIC_KERNEL"
ENGINEERING_ONLY = "ENGINEERING_ONLY"
ENGINEERING_BASELINE = "ENGINEERING_BASELINE"


def envelope(
    payload: Mapping[str, Any] | None = None,
    *,
    status: str = "ok",
    decision_status: str | None = None,
    trace: Mapping[str, Any] | None = None,
    certificate: Mapping[str, Any] | None = None,
    risk_labels: Iterable[str] = (),
    semantic_boundary: str = ENGINEERING_ONLY,
    public_private_classification: str = PUBLIC_KERNEL,
    evidence: Iterable[Any] = (),
) -> dict[str, Any]:
    """Return the uniform MCP/API envelope required by the Playbook."""

    return {
        "status": status,
        "decision_status": decision_status,
        "trace": dict(trace or {}),
        "certificate": dict(certificate or {}),
        "risk_labels": list(risk_labels),
        "semantic_boundary": semantic_boundary,
        "public_private_classification": public_private_classification,
        "evidence": list(evidence),
        "payload": dict(payload or {}),
    }


def toy_contract_rules() -> list[LegalRule]:
    """Return a public toy contract fixture with exception and priority shapes."""

    return [
        LegalRule(
            id="rule::delivery_obligation",
            premise_atoms=["contract_exists", "delivery_due"],
            head_claim="norm::delivery::active",
            norm_modality="OBLIGATION",
            source_anchor="toy://contract/rule::delivery_obligation",
        ),
        LegalRule(
            id="rule::failed_delivery",
            premise_atoms=["norm::delivery::active", "goods_not_delivered"],
            head_claim="delivery_breach",
            norm_modality="OBLIGATION",
            source_anchor="toy://contract/rule::failed_delivery",
        ),
        LegalRule(
            id="rule::force_majeure_exception",
            premise_atoms=["force_majeure"],
            head_claim="force_majeure_defense",
            norm_modality="CONSTITUTIVE",
            attacks=["rule::failed_delivery"],
            source_anchor="toy://contract/rule::force_majeure_exception",
        ),
        LegalRule(
            id="rule::priority_defense",
            premise_atoms=["verified_priority"],
            head_claim="priority_defense",
            norm_modality="CONSTITUTIVE",
            priority_over=["rule::failed_delivery"],
            source_anchor="toy://contract/rule::priority_defense",
        ),
    ]


def certified_litigation_report(args: Mapping[str, Any]) -> dict[str, Any]:
    """拒绝旧toy evaluate；正式报告只能消费已完成的审计run。"""

    payload = {
        "error": "toy report evaluation was removed; use jc evaluate and then jc render",
        "code": "AUDITED_RUN_REQUIRED",
        "run_id": args.get("run_id", ""),
        "checker_verdict": {"accepted": False, "reason": "no audited run supplied"},
        "renderer_firewall": renderer_firewall_metadata("review_only_result"),
    }
    return envelope(
        payload,
        status="blocked",
        decision_status="UNDECIDED",
        risk_labels=["AUDITED_RUN_REQUIRED"],
        evidence=["compiler_core.application", "compiler_core.audit_bundle"],
    )


def minimum_evidence_checklist(args: Mapping[str, Any]) -> dict[str, Any]:
    """Build F2 missing-evidence suggestions without asserting missing facts."""

    facts = set(args.get("facts") or ["contract_exists"])
    target = str(args.get("target") or "delivery_breach")
    rules = [
        {"id": rule.id, "head": rule.head_claim, "body": list(rule.premise_atoms)}
        for rule in toy_contract_rules()
    ]
    checklist = compute_missing_evidence(target, facts, rules)
    payload = {
        "target": target,
        "suggestions_only": True,
        "evidence_type_suggestions": [
            {"fact": fact, "suggested_evidence_type": "source-bounded proof or verified record"}
            for fact in checklist.get("missing_facts", [])
        ],
        "checklist": checklist,
    }
    return envelope(payload, decision_status="UNDECIDED", risk_labels=["MISSING_EVIDENCE"], evidence=["compute_missing_evidence"])


def attack_graph_explanation(args: Mapping[str, Any]) -> dict[str, Any]:
    """Build F3 attack graph explanation with cycle and priority witnesses."""

    graph_kind = str(args.get("graph_kind") or "cycle")
    if graph_kind == "priority":
        claims = [{"id": "permission"}, {"id": "prohibition"}]
        attacks = [("permission", "prohibition")]
        kinds = [{"source": "permission", "target": "prohibition", "kind": "PRIORITY_DEFEAT"}]
    elif graph_kind == "self_attack":
        claims = [{"id": "self"}]
        attacks = [("self", "self")]
        kinds = [{"source": "self", "target": "self", "kind": "SELF_ATTACK"}]
    else:
        claims = [{"id": "a"}, {"id": "b"}]
        attacks = [("a", "b"), ("b", "a")]
        kinds = [
            {"source": "a", "target": "b", "kind": "REBUTTAL"},
            {"source": "b", "target": "a", "kind": "REBUTTAL"},
        ]
    ge = grounded_extension(claims, attacks)
    payload = {
        "graph_kind": graph_kind,
        "arguments": claims,
        "attacks": kinds,
        "grounded_result": ge,
        "trace": proof_trace(claims, attacks, ge),
        "visualization_payload": {"nodes": claims, "edges": kinds},
    }
    return envelope(payload, decision_status="UNDECIDED" if ge["undecided"] else None, evidence=["grounded_extension", "proof_trace"])


def cross_repo_diff(args: Mapping[str, Any]) -> dict[str, Any]:
    """Build F4 differential summary using the spec shadow harness."""

    from compiler_core.spec_shadow_harness import build_cross_repo_differential_report

    spec_root = args.get("spec_root")
    report = (
        build_cross_repo_differential_report(Path(spec_root))
        if spec_root
        else build_cross_repo_differential_report()
    )
    summary = report.get("summary", {})
    status = "ok" if summary.get("diverged_count") == 0 else "blocked"
    return envelope(report, status=status, decision_status=None, risk_labels=[] if status == "ok" else ["SPEC_SHADOW_MISMATCH"], evidence=["spec_shadow_harness"])


def batch_case_audit(args: Mapping[str, Any]) -> dict[str, Any]:
    """Build F5 batch audit output where single-case errors stay local."""

    cases = args.get("cases") or [
        {"case_id": f"toy-{idx}", "facts": ["contract_exists", "delivery_due", "goods_not_delivered"]}
        for idx in range(int(args.get("count", 10)))
    ]
    results = []
    for case in cases:
        try:
            result = certified_litigation_report({"facts": case.get("facts", [])})
            results.append({
                "case_id": case.get("case_id", "unknown"),
                "decision_status": result["decision_status"],
                "missing_evidence": result["payload"].get("risk_labels", []),
                "rule_hit_distribution": result["payload"].get("triggered_rules", []),
                "tainted_ratio": 1.0 if "TAINTED" in result["risk_labels"] else 0.0,
                "manual_review_queue": result["risk_labels"],
                "status": result["status"],
            })
        except Exception as exc:  # pragma: no cover - defensive fail-closed path
            results.append({"case_id": case.get("case_id", "unknown"), "status": "blocked", "error": str(exc)})
    payload = {"formats": ["json", "csv", "markdown"], "results": results, "case_count": len(results)}
    return envelope(payload, status="ok", evidence=["batch_case_audit"])


def ingest_candidate(args: Mapping[str, Any]) -> dict[str, Any]:
    """Build F6 candidate ingestion gate that never promotes LLM output directly."""

    candidate = {
        "raw_text": str(args.get("raw_text") or ""),
        "normalized_candidate": str(args.get("normalized_candidate") or args.get("raw_text") or ""),
        "source_span": args.get("source_span"),
        "provenance": args.get("provenance", "candidate://unverified"),
        "verification_state": "CANDIDATE_ONLY",
        "enters_kernel": False,
        "lsc_boundary": {
            "result_status": "review_only_result",
            "used_fact_keys": [],
            "used_rule_ids": [],
            "source_snapshot_ids": [],
            "provenance": {"summary_only": True, "source": "candidate ingestion"},
            "taint": ["candidate_only"],
            "review_required": True,
            "formal_kernel_used": False,
            "renderer_output_kind": "review_packet",
        },
    }
    return envelope(candidate, status="blocked", decision_status="TAINTED", risk_labels=["CANDIDATE_ONLY"], evidence=["LLM_INGESTION_CONTRACT.md"])


def governance_report(args: Mapping[str, Any]) -> dict[str, Any]:
    """Build F7 public rule-governance report for toy or supplied rules."""

    rules = args.get("rules") or [
        {"id": r.id, "head": r.head_claim, "body": r.premise_atoms, "source_anchor": r.source_anchor}
        for r in toy_contract_rules()
    ]
    missing = [rule.get("id") for rule in rules if not rule.get("source_anchor")]
    duplicate_ids = sorted({rule.get("id") for rule in rules if [r.get("id") for r in rules].count(rule.get("id")) > 1})
    payload = {
        "source_anchor_coverage": (len(rules) - len(missing)) / len(rules) if rules else 1.0,
        "duplicate_rules": duplicate_ids,
        "stale_rules": [],
        "conflicting_rules": [],
        "missing_provenance": missing,
        "public_private_rule_classification": PUBLIC_KERNEL,
        "risk_queue": missing,
    }
    return envelope(payload, risk_labels=["MISSING_PROVENANCE"] if missing else [], evidence=["governance_report"])


def impact_report(args: Mapping[str, Any]) -> dict[str, Any]:
    """Build F8 rule-change impact report without changing decisions."""

    rules = [
        {"id": rule.id, "head": rule.head_claim, "body": list(rule.premise_atoms)}
        for rule in toy_contract_rules()
    ]
    facts = set(args.get("facts") or ["contract_exists", "delivery_due", "goods_not_delivered"])
    rule_id = str(args.get("rule_id") or "rule::delivery_obligation")
    payload = analyze_rule_impact(rule_id, rules, facts)
    payload["decision_changed"] = False
    payload["required_recheck_fixtures"] = ["toy_contract_breach"]
    payload["affected_certificates"] = payload.get("downstream_affected", [])
    payload["affected_cases"] = ["toy-0"] if payload.get("total_affected", 0) else []
    return envelope(payload, evidence=["analyze_rule_impact"])


def jurisdiction_route_guard(args: Mapping[str, Any]) -> dict[str, Any]:
    """Build F9 route-guard output that blocks unmapped/collision states."""

    router = CrossJurisdictionRouter()
    config_path = args.get("registry_path")
    if not config_path:
        from compiler_core.config_paths import config_dir

        config_path = str(Path(config_dir()) / "obstruction_registry.yaml")
    router.load(str(config_path))
    result = router.route(
        str(args.get("concept") or "unknown"),
        str(args.get("source") or "CN"),
        str(args.get("target") or "HK"),
    )
    blocked = result.get("status") != "MATCH"
    return envelope(result, status="blocked" if blocked else "ok", decision_status="UNDECIDED" if blocked else None, risk_labels=[result.get("status", "UNMAPPED")] if blocked else [], evidence=["CrossJurisdictionRouter"])


def damages_baseline(args: Mapping[str, Any]) -> dict[str, Any]:
    """Build F11 engineering-baseline damages estimate."""

    principal = float(args.get("principal", 100000))
    lpr_rate = float(args.get("lpr_rate", 3.45))
    days = int(args.get("interest_days", 365))
    interest = round(principal * ((lpr_rate * 4) / 100) * (days / 365), 2)
    payload = {
        "amount_range": [round(principal, 2), round(principal + interest, 2)],
        "sample_basis": "toy statutory-interest baseline",
        "uncertainty": "high",
        "excluded_factors": ["court discretion", "case-specific mitigation", "private evidence"],
        "risk_label": ENGINEERING_BASELINE,
    }
    return envelope(payload, decision_status=None, risk_labels=[ENGINEERING_BASELINE], evidence=["damages_baseline"])


def case_deviation_detection(args: Mapping[str, Any]) -> dict[str, Any]:
    """Build F12 sample-deviation report without claiming legal necessity."""

    samples = list(args.get("samples") or [])
    if len(samples) < 3:
        payload = {
            "similar_case_cluster": [],
            "deviation_score": None,
            "feature_explanation": [],
            "sample_limitation": "insufficient public toy samples",
            "review_recommendation": "blocked_low_evidence",
        }
        return envelope(payload, status="blocked", decision_status=None, risk_labels=["LOW_EVIDENCE"], evidence=["case_deviation_detection"])
    payload = {
        "similar_case_cluster": samples[:5],
        "deviation_score": 0.0,
        "feature_explanation": ["toy cluster only"],
        "sample_limitation": "public toy sample, not legal necessity",
        "review_recommendation": "manual_review",
    }
    return envelope(payload, risk_labels=[ENGINEERING_BASELINE], evidence=["case_deviation_detection"])


def stress_fixtures(args: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build F13 red/green stress fixtures for the differential harness."""

    fixtures = [
        {"id": "cycle_attack_red", "type": "cycle attack", "expected": "UNDECIDED"},
        {"id": "self_attack_red", "type": "self-attack", "expected": "UNDECIDED"},
        {"id": "exception_chain_green", "type": "exception chain", "expected": "REFUTED"},
        {"id": "priority_conflict_red", "type": "priority conflict", "expected": "UNDECIDED"},
        {"id": "missing_evidence_red", "type": "missing evidence", "expected": "UNDECIDED"},
        {"id": "tainted_fact_red", "type": "tainted fact", "expected": "TAINTED"},
        {"id": "malformed_certificate_red", "type": "malformed certificate", "expected": "TAINTED"},
        {"id": "jurisdiction_collision_red", "type": "jurisdiction collision", "expected": "UNDECIDED"},
    ]
    return envelope({"fixtures": fixtures, "differential_ready": True}, evidence=["stress_fixtures"])


def private_layer_contract(args: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build F14 public/private boundary contract for lawyer workflow layers."""

    payload = {
        "public_repo_allows": ["interface contract", "privacy boundary doc", "toy report sample", "no-client-data tests"],
        "private_layer_only": ["fact organization", "evidence checklist", "litigation strategy draft", "client report", "manual review workflow", "firm-specific templates"],
        "kernel_semantics_changed": False,
        "public_scan_terms": ["client evidence", "litigation strategy", "private benchmark", "firm template"],
    }
    return envelope(payload, evidence=["public_private_boundary"])


SURFACE_TOOLS: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
    "evaluate": certified_litigation_report,
    "render": certified_litigation_report,
    "check": lambda args: certified_litigation_report({**dict(args), "malformed_certificate": bool(args.get("malformed_certificate", False))}),
    "trace": attack_graph_explanation,
    "route": jurisdiction_route_guard,
    "batch": batch_case_audit,
    "diff": cross_repo_diff,
    "governance": governance_report,
    "impact": impact_report,
    "ingest_candidate": ingest_candidate,
    "minimum_evidence": minimum_evidence_checklist,
    "damages_baseline": damages_baseline,
    "case_deviation": case_deviation_detection,
    "stress_fixtures": lambda args: stress_fixtures(args),
    "private_layer_contract": lambda args: private_layer_contract(args),
}
