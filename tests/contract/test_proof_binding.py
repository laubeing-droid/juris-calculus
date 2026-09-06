"""Contract tests for the U01 proof binding and runtime obligation map.

The binding files are the only permitted citation of the legal-math-modeling
subject. They must stay internally consistent, must preserve the 91-module /
452-declaration inventory, and must never present component-level receipts or
pipeline stage strings as whole-chain V5 acceptance.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LMM_COMMIT = "23c5a310ae02192f2f896515b00de51895da387f"
LMM_TREE = "97275b6b691bd1757a0e2af9018c124550792a56"
COMPONENT_RECEIPT_COMMIT = "c79e03b8d0cfed85c43cc013bf8a0b50326bc858"

ALLOWED_DISPOSITIONS = {
    "RUNTIME_MAPPING",
    "RUNTIME_MAPPING_OR_BUILD_AUDIT",
    "CONTRACT_ONLY",
    "CONDITIONAL_BASIS",
    "OPTIONAL_THEORY",
    "BUILD_AUDIT",
    "RESEARCH_RETENTION",
}


def _load(relative: str) -> dict:
    return json.loads((REPO / relative).read_bytes())


def test_binding_subject_and_stage_strings_are_preserved() -> None:
    binding = _load("proofs/lmm-binding.json")
    subject = binding["legal_math_modeling_subject"]
    assert subject["commit"] == LMM_COMMIT
    assert subject["tree"] == LMM_TREE
    evidence = binding["ci_evidence"]
    assert evidence["certificate_status_exact"] == "RELEASE_PASS_PENDING_INDEPENDENT_VERIFICATION"
    assert evidence["independent_verifier_verdict_exact"] == "VERIFIED_PENDING_RELEASE_GATE"
    assert evidence["final_gate_conclusion"] == "success"


def test_inventory_carried_with_full_declaration_counts() -> None:
    inventory = _load("proofs/proof-inventory.json")
    binding = _load("proofs/lmm-binding.json")
    assert inventory["schema_version"] == "jc-upgrade-proof-source-inventory/1.0"
    assert len(inventory["sources"]) == 91
    declarations = sum(len(source["theorems"]) for source in inventory["sources"])
    assert declarations == 452
    assert binding["source_inventory_verification"]["source_count"] == 91
    assert binding["source_inventory_verification"]["theorem_declaration_count"] == 452
    assert binding["source_inventory_verification"]["hash_verified_locally"] == 91


def test_component_receipts_are_never_whole_chain_acceptance() -> None:
    binding = _load("proofs/lmm-binding.json")
    receipts = binding["runtime_refinement_receipts_bound_to"]
    assert receipts["runtime_commit"] == COMPONENT_RECEIPT_COMMIT
    assert receipts["runtime_commit"] != binding["juris_calculus_baseline"]["commit"]
    assert "not reused as V5 whole-chain" in receipts["note"]


def test_obligation_map_covers_every_module_with_allowed_dispositions() -> None:
    inventory = _load("proofs/proof-inventory.json")
    obligation_map = _load("proofs/runtime-obligation-map.json")
    dispositions = {entry["path"]: entry for entry in obligation_map["module_dispositions"]}
    inventory_paths = {source["path"] for source in inventory["sources"]}
    assert set(dispositions) == inventory_paths
    for entry in dispositions.values():
        assert entry["disposition"] in ALLOWED_DISPOSITIONS
        assert entry["sha256_verified"] is True
    summary = obligation_map["module_disposition_summary"]
    assert summary["total_modules"] == 91
    assert sum(summary["by_disposition"].values()) == 91
    assert len(obligation_map["capability_mappings"]) == 16


def test_capability_mappings_cite_existing_authority_or_declared_new_modules() -> None:
    obligation_map = _load("proofs/runtime-obligation-map.json")
    for capability in obligation_map["capability_mappings"]:
        assert capability["lean_namespace"] == "JurisLean.ULM"
        assert capability["implementation_assurance"] in {"crossCheckOnly", "tcbSpecified"}
        assert capability["acceptance_samples"], capability["capability_id"]
        for declaration in capability["key_declarations_fully_qualified"]:
            assert declaration.startswith("JurisLean.ULM.")
        for relative in capability["jc_authority_entry"]:
            path = relative.split(" ")[0]
            candidate = REPO / path
            if candidate.exists():
                continue
            assert "(new, V5)" in relative, f"unregistered authority path: {relative}"


def test_no_capability_claims_kernel_verified() -> None:
    obligation_map = _load("proofs/runtime-obligation-map.json")
    for capability in obligation_map["capability_mappings"]:
        assert capability["implementation_assurance"] != "kernelVerified"
    assert obligation_map["assurance_scale"]["default_granted"] == "crossCheckOnly"
