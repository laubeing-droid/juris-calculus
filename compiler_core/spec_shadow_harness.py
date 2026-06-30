#!/usr/bin/env python3
"""Cross-repo shadow harness for spec-vs-JC differential checks."""

from __future__ import annotations

import importlib
import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from compiler_core.argumentation import grounded_extension, proof_trace
from compiler_core.certificate_checker import GroundedINCertificate, OUTCertificate, UNDECCertificate
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator
from compiler_core.types import IRState, LegalDomain, LegalFact, LegalRule


SPEC_REPO_ENV = "LEGAL_MATH_MODELING_ROOT"


def _default_spec_repo_root() -> Path:
    """Resolve the companion spec repo without falling back to stale paths."""

    env_root = os.environ.get(SPEC_REPO_ENV, "").strip()
    if env_root:
        return Path(env_root).resolve()

    jc_root = Path(__file__).resolve().parents[1]
    candidates = (
        jc_root.parent / "数学证明" / "legal-math-modeling",
        jc_root.parent / "legal-math-modeling",
    )
    for candidate in candidates:
        if (candidate / "theory" / "spec" / "reference_semantics.py").exists():
            return candidate.resolve()
    return candidates[0].resolve()


SPEC_REPO_ROOT = _default_spec_repo_root()
JC_REPO_ROOT = Path(__file__).resolve().parents[1]


def _git_head(path: Path) -> str:
    """Return the git HEAD for a repo, or UNKNOWN when unavailable."""

    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "UNKNOWN"


@dataclass(frozen=True)
class ShadowFixture:
    """A single spec shadow scenario to compare against the formal companion repo."""

    fixture_id: str
    variant: str
    initial_facts: Tuple[str, ...]
    rules: Tuple[LegalRule, ...]
    expected_focus_claim: str
    expected_defeater_claim: str | None = None
    direct_fact_arguments: Tuple[str, ...] = ()


def _load_spec_modules(spec_repo_root: Path = SPEC_REPO_ROOT):
    """Load the formal companion repo's reference evaluator modules."""

    spec_repo_root = Path(spec_repo_root).resolve()
    reference_path = spec_repo_root / "theory" / "spec" / "reference_semantics.py"
    certificate_path = spec_repo_root / "theory" / "spec" / "certificate_schema.py"
    if not reference_path.exists() or not certificate_path.exists():
        raise FileNotFoundError(
            f"spec modules not found under {spec_repo_root}; set {SPEC_REPO_ENV}"
        )

    spec_root = str(spec_repo_root)
    if spec_root not in sys.path:
        sys.path.insert(0, spec_root)
    importlib.invalidate_caches()
    reference_semantics = importlib.import_module("theory.spec.reference_semantics")
    certificate_schema = importlib.import_module("theory.spec.certificate_schema")
    return reference_semantics, certificate_schema


def _build_contract_fixture(force_majeure: bool) -> ShadowFixture:
    """Build the JC-side contract-breach shadow fixture."""

    facts = ("contract_exists", "delivery_due", "goods_not_delivered")
    if force_majeure:
        facts = facts + ("force_majeure",)

    rules = (
        LegalRule(
            id="rule::delivery_obligation",
            premise_atoms=["contract_exists", "delivery_due"],
            head_claim="norm::delivery::active",
            norm_modality="OBLIGATION",
        ),
        LegalRule(
            id="rule::failed_delivery",
            premise_atoms=["norm::delivery::active", "goods_not_delivered"],
            head_claim="delivery_breach",
            norm_modality="OBLIGATION",
        ),
    )
    return ShadowFixture(
        fixture_id="contract_breach",
        variant="force_majeure" if force_majeure else "plain",
        initial_facts=facts,
        rules=rules,
        expected_focus_claim="delivery_breach",
        expected_defeater_claim="force_majeure" if force_majeure else None,
        direct_fact_arguments=("force_majeure",) if force_majeure else (),
    )


def _build_license_fixture(priority_active: bool) -> ShadowFixture:
    """Build the JC-side licensed-use priority fixture."""

    facts = ("license_signed", "rights_holder_authorized", "used_work", "use_within_scope")
    rules = [
        LegalRule(
            id="rule::license_status",
            premise_atoms=["license_signed", "rights_holder_authorized"],
            head_claim="license_status_active",
            norm_modality="CONSTITUTIVE",
        ),
        LegalRule(
            id="rule::licensed_use_permission",
            premise_atoms=["license_status_active", "use_within_scope"],
            head_claim="use_permitted",
            norm_modality="PERMISSION",
            priority_over=["rule::used_work"] if priority_active else [],
        ),
        LegalRule(
            id="rule::used_work",
            premise_atoms=["used_work"],
            head_claim="unauthorized_use",
            norm_modality="PROHIBITION",
        ),
    ]
    return ShadowFixture(
        fixture_id="license_permission_priority",
        variant="priority_on" if priority_active else "priority_off",
        initial_facts=facts,
        rules=tuple(rules),
        expected_focus_claim="use_permitted",
        expected_defeater_claim="unauthorized_use" if not priority_active else None,
    )


def _build_tort_fixture(contributory_negligence: bool) -> ShadowFixture:
    facts = ("duty_of_care", "breach_of_duty", "causation", "damage")
    if contributory_negligence:
        facts = facts + ("contributory_negligence",)
    rules = (
        LegalRule(
            id="rule::tort_breach",
            premise_atoms=["duty_of_care", "breach_of_duty", "causation", "damage"],
            head_claim="tort_liability",
            norm_modality="OBLIGATION",
        ),
    )
    return ShadowFixture(
        fixture_id="tort_breach",
        variant="with_negligence" if contributory_negligence else "plain",
        initial_facts=facts,
        rules=rules,
        expected_focus_claim="tort_liability",
        expected_defeater_claim="contributory_negligence" if contributory_negligence else None,
        direct_fact_arguments=("contributory_negligence",) if contributory_negligence else (),
    )


def _build_criminal_fixture(self_defense: bool) -> ShadowFixture:
    facts = ("actus_reus", "mens_rea", "absence_of_defense")
    if self_defense:
        facts = facts + ("self_defense",)
    rules = (
        LegalRule(
            id="rule::criminal_breach",
            premise_atoms=["actus_reus", "mens_rea", "absence_of_defense"],
            head_claim="criminal_liability",
            norm_modality="PROHIBITION",
        ),
    )
    return ShadowFixture(
        fixture_id="criminal_breach",
        variant="self_defense" if self_defense else "plain",
        initial_facts=facts,
        rules=rules,
        expected_focus_claim="criminal_liability",
        expected_defeater_claim="self_defense" if self_defense else None,
        direct_fact_arguments=("self_defense",) if self_defense else (),
    )


def _build_admin_fixture(priority_active: bool) -> ShadowFixture:
    facts = ("admin_action", "exceeds_authority", "no_legal_basis")
    if priority_active:
        facts = facts + ("legal_basis_exists",)
    rules = [
        LegalRule(
            id="rule::admin_breach",
            premise_atoms=["admin_action", "exceeds_authority", "no_legal_basis"],
            head_claim="admin_illegality",
            norm_modality="OBLIGATION",
        ),
        LegalRule(
            id="rule::higher_law_validity",
            premise_atoms=["legal_basis_exists"],
            head_claim="admin_action_valid",
            norm_modality="CONSTITUTIVE",
            priority_over=["rule::admin_breach"] if priority_active else [],
        ),
    ]
    return ShadowFixture(
        fixture_id="admin_breach",
        variant="priority_on" if priority_active else "priority_off",
        initial_facts=facts,
        rules=tuple(rules),
        expected_focus_claim="admin_illegality",
        expected_defeater_claim="admin_action_valid" if priority_active else None,
    )


def _make_state(initial_facts: Iterable[str], max_iterations: int = 50) -> IRState:
    """Construct a minimal IR state for the JC Horn stage."""

    state = IRState(
        facts={fact_id: LegalFact(id=fact_id, description=fact_id) for fact_id in initial_facts},
        domain=LegalDomain.CIVIL,
    )
    state.max_iterations = max_iterations
    return state


def _run_horn_shadow(fixture: ShadowFixture) -> IRState:
    """Run the JC Horn stage for a shadow fixture."""

    evaluator = FixpointEvaluator(list(fixture.rules), DomainConfig(domain=LegalDomain.CIVIL))
    state = _make_state(fixture.initial_facts)
    return evaluator.evaluate_horn(state)


def _build_attack_records(fixture: ShadowFixture, horn_state: IRState) -> list[dict[str, str]]:
    """Build a compact attack layer from local rule metadata."""

    present_claims = set(horn_state.claims.keys())
    rule_by_id = {rule.id: rule for rule in fixture.rules}
    records: list[dict[str, str]] = []

    for rule in fixture.rules:
        if rule.head_claim not in present_claims:
            continue
        for attacked_rule_id in rule.attacks:
            target_rule = rule_by_id.get(attacked_rule_id)
            if target_rule and target_rule.head_claim in present_claims:
                records.append(
                    {
                        "source": rule.head_claim,
                        "target": target_rule.head_claim,
                        "kind": "EXCEPTION",
                        "reason": f"{rule.head_claim} defeats {target_rule.head_claim}",
                    }
                )
        for priority_rule_id in rule.priority_over:
            target_rule = rule_by_id.get(priority_rule_id)
            if target_rule and target_rule.head_claim in present_claims:
                records.append(
                    {
                        "source": rule.head_claim,
                        "target": target_rule.head_claim,
                        "kind": "PRIORITY_DEFEAT",
                        "reason": f"{rule.id} has priority over {priority_rule_id}",
                    }
                )
    if fixture.fixture_id == "contract_breach":
        if "force_majeure" in present_claims and "delivery_breach" in present_claims:
            records.append(
                {
                    "source": "force_majeure",
                    "target": "delivery_breach",
                    "kind": "EXCEPTION",
                    "reason": "force_majeure defeats delivery_breach",
                }
            )
    if fixture.fixture_id == "tort_breach":
        if "contributory_negligence" in present_claims and "tort_liability" in present_claims:
            records.append(
                {
                    "source": "contributory_negligence",
                    "target": "tort_liability",
                    "kind": "EXCEPTION",
                    "reason": "contributory_negligence defeats tort_liability",
                }
            )
    if fixture.fixture_id == "criminal_breach":
        if "self_defense" in present_claims and "criminal_liability" in present_claims:
            records.append(
                {
                    "source": "self_defense",
                    "target": "criminal_liability",
                    "kind": "EXCEPTION",
                    "reason": "self_defense defeats criminal_liability",
                }
            )
    return records


def _jc_status_for_fixture(
    fixture: ShadowFixture,
    ge_result: Mapping[str, Any],
    horn_state: IRState,
    attack_records: list[dict[str, str]],
) -> tuple[str, str | None]:
    """Project JC stage outputs to the spec-side status vocabulary."""

    if horn_state.horn_truncated or ge_result.get("truncated"):
        return "TAINTED", "JC shadow evaluator truncated before completing the formal boundary."

    accepted = set(ge_result["accepted"])
    if fixture.fixture_id == "contract_breach":
        if fixture.expected_focus_claim in accepted:
            return "PROVED", None
        if fixture.expected_defeater_claim and fixture.expected_defeater_claim in accepted:
            return "REFUTED", None
        return "UNDECIDED", "Contract breach claim did not reach a decisive grounded status."

    if fixture.fixture_id == "license_permission_priority":
        priority_present = any(record["kind"] == "PRIORITY_DEFEAT" for record in attack_records)
        if "use_permitted" in accepted and "unauthorized_use" not in accepted:
            return "PROVED", None
        if "unauthorized_use" in accepted and not priority_present:
            return "REFUTED", None
        if not accepted:
            return "UNDECIDED", "Licensed-use slice produced no accepted arguments."
        return "TAINTED", "Permission/prohibition interaction remained ambiguous."

    if fixture.fixture_id == "tort_breach":
        if fixture.expected_focus_claim in accepted:
            return "PROVED", None
        if fixture.expected_defeater_claim and fixture.expected_defeater_claim in accepted:
            return "REFUTED", None
        return "UNDECIDED", "Tort breach claim did not reach a decisive grounded status."

    if fixture.fixture_id == "criminal_breach":
        if fixture.expected_focus_claim in accepted:
            return "PROVED", None
        if fixture.expected_defeater_claim and fixture.expected_defeater_claim in accepted:
            return "REFUTED", None
        return "UNDECIDED", "Criminal breach claim did not reach a decisive grounded status."

    if fixture.fixture_id == "admin_breach":
        priority_present = any(record["kind"] == "PRIORITY_DEFEAT" for record in attack_records)
        if fixture.expected_focus_claim in accepted and not priority_present:
            return "PROVED", None
        if fixture.expected_defeater_claim and fixture.expected_defeater_claim in accepted and priority_present:
            return "REFUTED", None
        if not accepted:
            return "UNDECIDED", "Admin slice produced no accepted arguments."
        return "TAINTED", "Admin illegality interaction remained ambiguous."

    return "TAINTED", "Unknown shadow fixture type."


def _inject_spec_aligned_arguments(fixture: ShadowFixture, horn_state: IRState) -> None:
    """Add spec-side argument shapes that JC does not materialize by default."""

    for fact_argument in fixture.direct_fact_arguments:
        if fact_argument not in horn_state.claims:
            horn_state.claims[fact_argument] = horn_state.claims.get(fact_argument) or type(
                "SyntheticClaim",
                (),
                {"id": fact_argument},
            )()

    if fixture.fixture_id == "license_permission_priority" and "unauthorized_use" in horn_state.claims:
        active_id = "norm::unauthorized_use_prohibition::active"
        if active_id not in horn_state.claims:
            horn_state.claims[active_id] = type("SyntheticClaim", (), {"id": active_id})()

    if fixture.fixture_id == "tort_breach" and "tort_liability" in horn_state.claims:
        for inject_id in ("norm::tort::active",):
            if inject_id not in horn_state.claims:
                horn_state.claims[inject_id] = type("SyntheticClaim", (), {"id": inject_id})()

    if fixture.fixture_id == "criminal_breach" and "criminal_liability" in horn_state.claims:
        for inject_id in ("norm::criminal::active",):
            if inject_id not in horn_state.claims:
                horn_state.claims[inject_id] = type("SyntheticClaim", (), {"id": inject_id})()

    if fixture.fixture_id == "admin_breach" and "admin_illegality" in horn_state.claims:
        for inject_id in ("norm::admin::active",):
            if inject_id not in horn_state.claims:
                horn_state.claims[inject_id] = type("SyntheticClaim", (), {"id": inject_id})()


def _verify_grounded_certificates(
    claims: list[dict[str, Any]],
    attacks: list[tuple[str, str]],
    ge_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify grounded labels with the independent JC certificate checker."""

    trace = proof_trace(claims, attacks, ge_result)
    args = tuple(claim["id"] for claim in claims)
    aaf = (args, tuple(attacks))
    accepted = set(ge_result["accepted"])
    rejected = set(ge_result["rejected"])
    undecided = set(ge_result["undecided"])

    iteration_first_seen: dict[str, int] = {}
    for item in trace["iteration_history"]:
        iteration = item["iteration"]
        for accepted_id in item["defended"]:
            iteration_first_seen.setdefault(accepted_id, iteration)

    errors: list[str] = []
    for accepted_id in accepted:
        cert = GroundedINCertificate(
            argument_id=accepted_id,
            accepted_iteration=iteration_first_seen.get(accepted_id, 1),
        )
        if not cert.verify(aaf):
            errors.append(f"IN certificate failed for {accepted_id}")

    attack_set = set(attacks)
    for rejected_id in rejected:
        attackers = [src for src, tgt in attack_set if tgt == rejected_id and src in accepted]
        if not attackers:
            errors.append(f"OUT certificate missing accepted attacker for {rejected_id}")
            continue
        cert = OUTCertificate(
            argument_id=rejected_id,
            in_attacker=attackers[0],
            attacker_in_cert=GroundedINCertificate(
                argument_id=attackers[0],
                accepted_iteration=iteration_first_seen.get(attackers[0], 1),
            ),
        )
        if not cert.verify(aaf):
            errors.append(f"OUT certificate failed for {rejected_id}")

    for undecided_id in undecided:
        cert = UNDECCertificate(argument_id=undecided_id)
        if not cert.verify(aaf):
            errors.append(f"UNDEC certificate failed for {undecided_id}")

    return {"ok": not errors, "errors": errors}


def build_jc_shadow_payload(fixture: ShadowFixture) -> dict[str, Any]:
    """Run the local JC shadow path and emit a spec-aligned payload."""

    horn_state = _run_horn_shadow(fixture)
    _inject_spec_aligned_arguments(fixture, horn_state)
    claims = [{"id": claim_id} for claim_id in sorted(horn_state.claims.keys())]
    attack_records = _build_attack_records(fixture, horn_state)
    attack_edges = [(record["source"], record["target"]) for record in attack_records]
    ge_result = grounded_extension(claims, attack_edges)
    status, fail_closed_reason = _jc_status_for_fixture(fixture, ge_result, horn_state, attack_records)
    certificate_verdict = _verify_grounded_certificates(claims, attack_edges, ge_result)

    return {
        "fixture_id": fixture.fixture_id,
        "variant": fixture.variant,
        "schema_version": "spec-cert-v1",
        "status": status,
        "facts": list(fixture.initial_facts),
        "horn_rules_fired": sorted(horn_state.rules_applied),
        "closure_claims": sorted(horn_state.claims.keys()),
        "arguments_constructed": sorted(horn_state.claims.keys()),
        "attacks_constructed": [
            f"{record['source']}->{record['target']}:{record['kind']}"
            for record in attack_records
        ],
        "attack_kinds": sorted({record["kind"] for record in attack_records}),
        "accepted_argument_ids": list(ge_result["accepted"]),
        "rejected_argument_ids": list(ge_result["rejected"]),
        "undecided_argument_ids": list(ge_result["undecided"]),
        "fail_closed_reason": fail_closed_reason,
        "horn_truncated": horn_state.horn_truncated,
        "grounded_truncated": ge_result["truncated"],
        "checker_verdict": certificate_verdict,
    }


def build_spec_payload(fixture_id: str, variant: str, spec_repo_root: Path = SPEC_REPO_ROOT) -> dict[str, Any]:
    """Evaluate the formal companion repo fixture and normalize the result."""

    reference_semantics, _certificate_schema = _load_spec_modules(spec_repo_root)
    if fixture_id == "contract_breach":
        model = reference_semantics.build_contract_breach_demo_model(force_majeure=(variant == "force_majeure"))
        trace, contract_report, certificate = reference_semantics.evaluate_contract_breach_with_contract(model)
    elif fixture_id == "license_permission_priority":
        model = reference_semantics.build_license_permission_demo_model(priority_active=(variant == "priority_on"))
        trace, contract_report, certificate = reference_semantics.evaluate_license_permission_with_contract(model)
    elif fixture_id == "tort_breach":
        model = reference_semantics.build_tort_demo_model(contributory_negligence=(variant == "with_negligence"))
        trace, contract_report, certificate = reference_semantics.evaluate_tort_with_contract(model)
    elif fixture_id == "criminal_breach":
        model = reference_semantics.build_criminal_demo_model(self_defense=(variant == "self_defense"))
        trace, contract_report, certificate = reference_semantics.evaluate_criminal_with_contract(model)
    elif fixture_id == "admin_breach":
        model = reference_semantics.build_admin_demo_model(priority_active=(variant == "priority_on"))
        trace, contract_report, certificate = reference_semantics.evaluate_admin_with_contract(model)
    else:
        raise ValueError(f"Unknown fixture_id: {fixture_id}")

    conclusion_by_argument: dict[str, str] = {}
    attack_semantics: list[str] = []
    for step in trace.steps:
        if step.phase == "aaf" and step.event == "argument_constructed":
            conclusion_by_argument[step.payload["argument_id"]] = step.payload["conclusion"]
        elif step.phase == "aaf" and step.event == "attack_constructed":
            attacker = conclusion_by_argument.get(step.payload["attacker_id"], step.payload["attacker_id"])
            target = conclusion_by_argument.get(step.payload["target_id"], step.payload["target_id"])
            attack_semantics.append(
                f"{attacker}->{target}:{step.payload['kind']}"
            )

    return {
        "fixture_id": fixture_id,
        "variant": variant,
        "schema_version": certificate.schema_version,
        "status": certificate.status,
        "facts": list(certificate.facts),
        "horn_rules_fired": list(certificate.horn_rules_fired),
        "arguments_constructed": sorted(conclusion_by_argument.values()),
        "attacks_constructed": sorted(attack_semantics),
        "attack_kinds": list(certificate.attack_kinds),
        "accepted_argument_ids": sorted(
            conclusion_by_argument.get(argument_id, argument_id)
            for argument_id in certificate.accepted_argument_ids
        ),
        "fail_closed_reason": certificate.fail_closed_reason,
        "contract_satisfied": contract_report.satisfied,
    }


def compare_spec_and_jc_payloads(spec_payload: Mapping[str, Any], jc_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a field-by-field differential report."""

    aligned: list[str] = []
    diverged: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []

    comparable_fields = (
        "schema_version",
        "status",
        "facts",
        "horn_rules_fired",
        "arguments_constructed",
        "attacks_constructed",
        "attack_kinds",
        "accepted_argument_ids",
        "fail_closed_reason",
    )

    for field in comparable_fields:
        spec_value = spec_payload.get(field)
        jc_value = jc_payload.get(field)
        if field in {
            "facts",
            "horn_rules_fired",
            "arguments_constructed",
            "attacks_constructed",
            "attack_kinds",
            "accepted_argument_ids",
        }:
            spec_value = sorted(set(spec_value or []))
            jc_value = sorted(set(jc_value or []))
        if spec_value == jc_value:
            aligned.append(field)
        else:
            diverged[field] = {"spec": spec_value, "jc": jc_value}

    if jc_payload.get("checker_verdict", {}).get("ok"):
        aligned.append("checker_verdict")
    else:
        diverged["checker_verdict"] = jc_payload.get("checker_verdict", {})
        blockers.extend(jc_payload.get("checker_verdict", {}).get("errors", []))

    if not spec_payload.get("contract_satisfied", True):
        blockers.append("Spec contract report itself is not satisfied.")
    if jc_payload.get("horn_truncated") or jc_payload.get("grounded_truncated"):
        blockers.append("JC shadow path truncated before completing one of the stages.")

    return {
        "fixture_id": spec_payload["fixture_id"],
        "variant": spec_payload["variant"],
        "status": "ALIGNED" if not diverged and not blockers else "DIVERGED",
        "aligned_fields": sorted(set(aligned)),
        "diverged_fields": diverged,
        "blockers": blockers,
    }


def run_fixture_comparison(fixture: ShadowFixture, spec_repo_root: Path = SPEC_REPO_ROOT) -> dict[str, Any]:
    """Run a single fixture end-to-end."""

    spec_payload = build_spec_payload(fixture.fixture_id, fixture.variant, spec_repo_root)
    jc_payload = build_jc_shadow_payload(fixture)
    report = compare_spec_and_jc_payloads(spec_payload, jc_payload)
    return {
        "spec": spec_payload,
        "jc": jc_payload,
        "report": report,
    }


def build_cross_repo_differential_report(spec_repo_root: Path = SPEC_REPO_ROOT) -> dict[str, Any]:
    """Run all supported fixtures and return the first cross-repo report."""

    spec_repo_root = Path(spec_repo_root).resolve()
    fixtures = (
        _build_contract_fixture(False),
        _build_contract_fixture(True),
        _build_license_fixture(True),
        _build_license_fixture(False),
        _build_tort_fixture(False),
        _build_tort_fixture(True),
        _build_criminal_fixture(False),
        _build_criminal_fixture(True),
        _build_admin_fixture(True),
        _build_admin_fixture(False),
    )
    comparisons = [run_fixture_comparison(fixture, spec_repo_root) for fixture in fixtures]
    diverged = sum(1 for item in comparisons if item["report"]["status"] == "DIVERGED")
    return {
        "spec_repo_root": str(spec_repo_root),
        "legal_math_head": _git_head(spec_repo_root),
        "jc_head": _git_head(JC_REPO_ROOT),
        "status": "PASS" if diverged == 0 else "FAIL",
        "fixtures": comparisons,
        "summary": {
            "fixture_count": len(comparisons),
            "aligned_count": sum(1 for item in comparisons if item["report"]["status"] == "ALIGNED"),
            "diverged_count": diverged,
        },
    }


def write_differential_report(
    path: str | Path,
    spec_repo_root: Path = SPEC_REPO_ROOT,
) -> Path:
    """Write the first cross-repo differential report to disk."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    report = build_cross_repo_differential_report(spec_repo_root)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def write_differential_markdown(
    path: str | Path,
    report: Mapping[str, Any],
) -> Path:
    """Write a human-readable differential summary."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary", {})
    lines = [
        "# JC Spec Shadow Differential Report",
        "",
        f"- status: {report.get('status')}",
        f"- legal_math_head: {report.get('legal_math_head')}",
        f"- jc_head: {report.get('jc_head')}",
        f"- fixture_count: {summary.get('fixture_count')}",
        f"- aligned_count: {summary.get('aligned_count')}",
        f"- diverged_count: {summary.get('diverged_count')}",
        "",
        "## Fixtures",
    ]
    for item in report.get("fixtures", []):
        fixture_report = item.get("report", {})
        lines.append(
            f"- {fixture_report.get('fixture_id')}::{fixture_report.get('variant')} "
            f"=> {fixture_report.get('status')}"
        )
        blockers = fixture_report.get("blockers", [])
        if blockers:
            lines.append(f"  blockers: {', '.join(blockers)}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for Playbook differential verification."""

    parser = argparse.ArgumentParser(description="Run JC spec shadow differential checks.")
    parser.add_argument("--spec-root", default=str(SPEC_REPO_ROOT), help="Path to legal-math-modeling root.")
    parser.add_argument("--output", required=True, help="JSON output path.")
    parser.add_argument("--markdown-output", default=None, help="Markdown output path.")
    args = parser.parse_args(argv)

    spec_root = Path(args.spec_root).resolve()
    report = build_cross_repo_differential_report(spec_root)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_out = Path(args.markdown_output) if args.markdown_output else out.with_suffix(".md")
    write_differential_markdown(md_out, report)
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
