"""U10 acceptance samples JT46/JT47: V4->V5 offline migration boundaries and
the renderer's no-embellishment guard."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from tools.migrate_v4_bundle import MigrationError, migrate_document

REPO = Path(__file__).resolve().parents[2]


def _v4_bundle() -> dict:
    return {
        "schema_version": "jc/case-input-bundle/1.0",
        "bundle_id": "bundle-1",
        "request": {
            "schema_version": "jc/4.0",
            "request_id": "req-1",
            "legal_context": {"jurisdiction": "CN", "governing_law": "CN-civil"},
            "decision_time": "2026-09-06T00:00:00Z",
            "source_bundle_ref": {"kind": "source-bundle", "digest": "sha256:" + "ab" * 32},
            "evidence_manifest_ref": {"kind": "evidence-manifest", "digest": "sha256:" + "cd" * 32},
            "fact_attestation_refs": [],
            "rule_pack_ref": {"kind": "pack-manifest", "digest": "sha256:" + "ef" * 32},
            "requested_outputs": [],
            "proposal_refs": [],
        },
        "artifacts": [],
        "bundle_digest": "sha256:" + "11" * 32,
        "sealed_certificate": {"kind": "formal-certificate", "digest": "sha256:" + "22" * 32},
    }


def test_jt46_migration_rewrites_wire_and_flags_every_signature() -> None:
    bundle = _v4_bundle()
    migrated, report = migrate_document(deepcopy(bundle))
    assert migrated["request"]["schema_version"] == "jc/5.0"
    assert any(
        change["path"] == "/request/schema_version" for change in report["changed_fields"]
    )
    # the sealed old certificate is carried as a reference and flagged, never revived
    assert report["stale_signatures"] == ["/sealed_certificate"]
    assert any("re-admission" in obligation for obligation in report["obligations"])
    assert report["not_claims"]


def test_jt46_old_certificate_reuse_is_refused_by_the_v5_contract() -> None:
    from compiler_core.contracts import CaseInputBundleV4, ContractV4Error

    migrated, _ = migrate_document(_v4_bundle())
    # the migrated bundle still carries the old self digest and old certificate
    # reference: the V5 contract authority rejects it (digest/signature binding)
    with pytest.raises(ContractV4Error):
        CaseInputBundleV4.from_dict(migrated)


def test_jt46_migration_refuses_non_object_input() -> None:
    with pytest.raises(MigrationError):
        migrate_document([1, 2, 3])


def test_jt47_neutral_profile_forbids_probability_embellishment() -> None:
    profile = yaml.safe_load(
        (REPO / "configs/render_profiles/neutral.yaml").read_text(encoding="utf-8")
    )
    phrases = [str(phrase).casefold() for phrase in profile["forbidden_phrases"]]
    assert "胜诉概率" in phrases
    assert "大概率胜诉" in phrases
    assert "guaranteed win" in phrases


def test_jt47_renderer_content_is_mechanical_and_verbatim() -> None:
    import inspect

    from compiler_core import rendering

    source = inspect.getsource(rendering._lines)
    # the renderer prints the raw enum value; unknown and hypothetical flow
    # through verbatim with no probability or certainty language anywhere
    assert "decision_status.value" in source
    for forbidden in ("大概率", "胜诉率", "probability", "guarantee"):
        assert forbidden not in source
    assert rendering.__all__ == ("RenderOutputV4", "RendererV4Error", "render_verified_bundle")
