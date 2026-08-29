"""Official YAML rule admission verified in source state.

Five cases from the V4 plan: a verified CLEAN rule is reasoning-ready;
CANDIDATE_ONLY quality, an unverified or badly hashed source, and an
out-of-whitelist modality are all kept out of the formal rule set.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from compiler_core.rule_packs import manifest_content_digest, sha256_file, verify_pack_manifest


def _write_yaml(path: Path, document) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return sha256_file(path)


def _build_pack(
    config_root: Path,
    *,
    rule: dict,
    source: dict,
) -> Path:
    rule_hash = _write_yaml(
        config_root / "packs" / "official-yaml-it" / "rules.yaml",
        {"_meta": {"total": 1}, "rules": [rule]},
    )
    source_hash = _write_yaml(
        config_root / "packs" / "official-yaml-it" / "sources.yaml",
        {"sources": [source]},
    )
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
        "rule_files": [{"path": "packs/official-yaml-it/rules.yaml", "sha256": rule_hash}],
        "source_files": [{"path": "packs/official-yaml-it/sources.yaml", "sha256": source_hash}],
        "config_files": [],
        "build_attestation": "a" * 64,
        "build_commit": "b" * 40,
        "inventory": {
            "corpus_total": 1,
            "reasoning_eligible_total": 1,
            "candidate_only_total": 0,
        },
    }

    def finalize(expected: dict) -> dict:
        document = {**manifest, "inventory": expected}
        document["content_digest"] = manifest_content_digest(document)
        return document

    manifest = finalize({
        "corpus_total": 1,
        "reasoning_eligible_total": 1,
        "candidate_only_total": 0,
    })
    manifest_path = config_root / "packs" / "official-yaml-it" / "manifest.yaml"
    _write_yaml(manifest_path, manifest)
    verification = verify_pack_manifest(manifest_path, config_root)
    if verification.candidate_rule_ids:
        manifest = finalize({
            "corpus_total": 1,
            "reasoning_eligible_total": 0,
            "candidate_only_total": 1,
        })
        _write_yaml(manifest_path, manifest)
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
    return {
        "source_id": "pipl-test-source",
        "verified": True,
        "content_hash": "c" * 64,
    }


def test_verified_clean_rule_is_reasoning_ready(tmp_path: Path) -> None:
    verification = _build_pack(
        tmp_path, rule=_base_rule(), source=_verified_source(),
    )
    assert verification.integrity_valid is True
    assert verification.reasoning_ready is True
    assert verification.verified_rule_ids == ("PIPL-TEST-001",)
    assert verification.inventory == {
        "corpus_total": 1, "reasoning_eligible_total": 1, "candidate_only_total": 0,
    }


def test_candidate_only_quality_stays_out_of_reasoning(tmp_path: Path) -> None:
    rule = {**_base_rule(), "data_quality": "CANDIDATE_ONLY"}
    verification = _build_pack(tmp_path, rule=rule, source=_verified_source())
    assert verification.reasoning_ready is False
    assert verification.candidate_rule_ids == ("PIPL-TEST-001",)
    assert verification.verified_rule_ids == ()


def test_unverified_source_stays_out_of_reasoning(tmp_path: Path) -> None:
    verification = _build_pack(
        tmp_path, rule=_base_rule(),
        source={**_verified_source(), "verified": False},
    )
    assert verification.reasoning_ready is False
    assert verification.candidate_rule_ids == ("PIPL-TEST-001",)


def test_illegal_source_hash_stays_out_of_reasoning(tmp_path: Path) -> None:
    verification = _build_pack(
        tmp_path, rule=_base_rule(),
        source={**_verified_source(), "content_hash": "nothex"},
    )
    assert verification.reasoning_ready is False
    assert verification.candidate_rule_ids == ("PIPL-TEST-001",)


def test_non_whitelisted_modality_reports_an_issue(tmp_path: Path) -> None:
    rule = {**_base_rule(), "norm_modality": "MAYBE"}
    verification = _build_pack(tmp_path, rule=rule, source=_verified_source())
    assert verification.reasoning_ready is False
    assert any(
        issue["code"] == "INVALID_RULE_MODALITY" and issue["detail"] == "PIPL-TEST-001"
        for issue in verification.issues
    )


def test_missing_source_anchor_demotes_rule_to_candidate(tmp_path: Path) -> None:
    rule = {**_base_rule(), "source_anchor": ""}
    verification = _build_pack(tmp_path, rule=rule, source=_verified_source())
    assert verification.reasoning_ready is False
    assert verification.candidate_rule_ids == ("PIPL-TEST-001",)


def test_invalid_rule_date_is_reported(tmp_path: Path) -> None:
    rule = {**_base_rule(), "valid_from": "31-12-2020"}
    verification = _build_pack(tmp_path, rule=rule, source=_verified_source())
    assert verification.reasoning_ready is False
    assert any(
        issue["code"] == "INVALID_RULE_DATE" for issue in verification.issues
    )
