"""Official YAML rule admission verified against the installed wheel.

This file runs OUTSIDE the source tree: a conftest in the harness directory
asserts that compiler_core resolves to the installed wheel. It repeats the
source-state positive and negative admission cases, and pins the retired
module set as absent from the installation.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import yaml

from compiler_core.rule_packs import manifest_content_digest, sha256_file, verify_pack_manifest

ENV_ROOT = Path(os.environ["JC_INSTALLED_ENV_ROOT"]).resolve()


def test_installed_wheel_origin_and_retired_modules() -> None:
    import compiler_core

    assert Path(compiler_core.__file__).resolve().is_relative_to(ENV_ROOT)
    assert importlib.util.find_spec("compiler_core.rule_admission") is not None
    assert importlib.util.find_spec("compiler_core.trust_labels") is not None
    # Literal find_spec probes keep the authority graph free of unresolved
    # dynamic imports while pinning every retired module as absent.
    assert importlib.util.find_spec("compiler_core.types") is None
    assert importlib.util.find_spec("compiler_core.analysis") is None
    assert importlib.util.find_spec("compiler_core.compat_v3_v4") is None
    assert importlib.util.find_spec("compiler_core.adapter_base") is None
    assert importlib.util.find_spec("compiler_core.classifier") is None
    assert importlib.util.find_spec("compiler_core.invariance_metrics") is None
    assert importlib.util.find_spec("compiler_core.kg_recall") is None
    assert importlib.util.find_spec("compiler_core.legal_memory") is None
    assert importlib.util.find_spec("compiler_core.result_diff") is None
    assert importlib.util.find_spec("compiler_core.result_exporter") is None
    assert importlib.util.find_spec("compiler_core.proof_trace_visualizer") is None
    assert importlib.util.find_spec("compiler_core.banach_verifier") is None
    assert importlib.util.find_spec("compiler_core.breakthrough_verification") is None
    assert importlib.util.find_spec("compiler_core.cross_jurisdiction_compare") is None
    assert importlib.util.find_spec("compiler_core.incremental_grounded") is None
    assert importlib.util.find_spec("compiler_core.defeasible_priority") is None
    assert importlib.util.find_spec("compiler_core.g8_evaluator_patch") is None
    assert importlib.util.find_spec("compiler_core.grounded_smt_verifier") is None
    assert importlib.util.find_spec("compiler_core.universal_grounded_smt") is None
    assert importlib.util.find_spec("compiler_core.output_firewall") is None
    assert importlib.util.find_spec("compiler_core.review_packet") is None
    assert importlib.util.find_spec("compiler_core.validity_state_machine") is None
    assert importlib.util.find_spec("compiler_core.smt_sidecar") is None
    assert importlib.util.find_spec("compiler_core.breakthrough_candidates") is None
    assert importlib.util.find_spec("compiler_core.horn_completeness") is None
    assert importlib.util.find_spec("compiler_core.stratified_evaluator") is None
    assert importlib.util.find_spec("compiler_core.cross_jurisdiction_router") is None
    assert importlib.util.find_spec("pipeline") is None
    assert importlib.util.find_spec("addons") is None
    assert importlib.util.find_spec("tests") is None
    assert importlib.util.find_spec("tools") is None


def _write_yaml(path: Path, document) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return sha256_file(path)


def _verify(config_root: Path, rule: dict, source: dict):
    rule_hash = _write_yaml(
        config_root / "packs" / "official-yaml-it" / "rules.yaml",
        {"_meta": {"total": 1}, "rules": [rule]},
    )
    source_hash = _write_yaml(
        config_root / "packs" / "official-yaml-it" / "sources.yaml",
        {"sources": [source]},
    )
    manifest_path = config_root / "packs" / "official-yaml-it" / "manifest.yaml"

    def write(inventory: dict):
        manifest = {
            "schema_version": "1.0",
            "pack_id": "official-yaml-it",
            "version": "1.0.0",
            "kind": "official",
            "status": "active",
            "jurisdiction": "CN",
            "governing_law": "中华人民共和国个人信息保护法",
            "effective_from": "2021-11-01",
            "effective_to": "",
            "rule_files": [
                {"path": "packs/official-yaml-it/rules.yaml", "sha256": rule_hash},
            ],
            "source_files": [
                {"path": "packs/official-yaml-it/sources.yaml", "sha256": source_hash},
            ],
            "config_files": [],
            "build_attestation": "a" * 64,
            "build_commit": "b" * 40,
            "inventory": inventory,
        }
        manifest["content_digest"] = manifest_content_digest(manifest)
        _write_yaml(manifest_path, manifest)

    write({"corpus_total": 1, "reasoning_eligible_total": 1, "candidate_only_total": 0})
    verification = verify_pack_manifest(manifest_path, config_root)
    if verification.candidate_rule_ids:
        write({"corpus_total": 1, "reasoning_eligible_total": 0, "candidate_only_total": 1})
        verification = verify_pack_manifest(manifest_path, config_root)
    return verification


def _base_rule() -> dict:
    return {
        "id": "PIPL-TEST-001",
        "head_claim": "claim::pipl.test.lawful",
        "premise_atoms": ["fact::pipl.test.basis_present"],
        "exception_chain": [],
        "priority_over": [],
        "norm_modality": "OBLIGATION",
        "source_anchor": "pipl-test-source",
        "data_quality": "CLEAN",
        "valid_from": "2021-11-01",
        "valid_to": "",
    }


def _verified_source() -> dict:
    return {"source_id": "pipl-test-source", "verified": True, "content_hash": "c" * 64}


def test_official_yaml_positive_case_is_reasoning_ready(tmp_path: Path) -> None:
    verification = _verify(tmp_path, _base_rule(), _verified_source())
    assert verification.integrity_valid is True
    assert verification.reasoning_ready is True
    assert verification.verified_rule_ids == ("PIPL-TEST-001",)


def test_official_yaml_candidate_quality_is_rejected(tmp_path: Path) -> None:
    verification = _verify(
        tmp_path, {**_base_rule(), "data_quality": "CANDIDATE_ONLY"},
        _verified_source(),
    )
    assert verification.reasoning_ready is False
    assert verification.candidate_rule_ids == ("PIPL-TEST-001",)


def test_official_yaml_unverified_source_is_rejected(tmp_path: Path) -> None:
    verification = _verify(
        tmp_path, _base_rule(), {**_verified_source(), "verified": False},
    )
    assert verification.reasoning_ready is False
    assert verification.candidate_rule_ids == ("PIPL-TEST-001",)


def test_official_yaml_bad_source_hash_is_rejected(tmp_path: Path) -> None:
    verification = _verify(
        tmp_path, _base_rule(), {**_verified_source(), "content_hash": "nothex"},
    )
    assert verification.reasoning_ready is False
    assert verification.candidate_rule_ids == ("PIPL-TEST-001",)


def test_official_yaml_unknown_modality_reports_issue(tmp_path: Path) -> None:
    verification = _verify(
        tmp_path, {**_base_rule(), "norm_modality": "MAYBE"}, _verified_source(),
    )
    assert verification.reasoning_ready is False
    assert any(
        issue["code"] == "INVALID_RULE_MODALITY" for issue in verification.issues
    )
