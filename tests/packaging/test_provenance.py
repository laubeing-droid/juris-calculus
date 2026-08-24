"""Signed release provenance, exact SBOM, and checksum mutation gates."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any
import zipfile

import pytest

from tools.build_provenance import (
    MATERIAL_PATHS,
    EvidenceError,
    create_release_evidence,
    verify_release_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
KEY_PATH = "tests/fixtures/keys/v4-test-ed25519.json"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout.strip()


def _record_hash(payload: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode("ascii")
    return "sha256=" + encoded.rstrip("=")


def _write_wheel(
    path: Path,
    *,
    module_payload: bytes = b'__version__ = "4.0.0"\n',
    recorded_module_payload: bytes | None = None,
) -> None:
    dist_info = "juris_calculus-4.0.0.dist-info"
    files = {
        "compiler_core/__init__.py": module_payload,
        f"{dist_info}/METADATA": (
            b"Metadata-Version: 2.4\nName: juris-calculus\nVersion: 4.0.0\n\n"
        ),
        f"{dist_info}/WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: jc-test\nRoot-Is-Purelib: true\n"
            b"Tag: py3-none-any\n\n"
        ),
    }
    recorded = dict(files)
    if recorded_module_payload is not None:
        recorded["compiler_core/__init__.py"] = recorded_module_payload
    record_path = f"{dist_info}/RECORD"
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    for name in sorted(recorded):
        payload = recorded[name]
        writer.writerow((name, _record_hash(payload), str(len(payload))))
    writer.writerow((record_path, "", ""))
    files[record_path] = stream.getvalue().encode("utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, files[name])


def _case(tmp_path: Path) -> dict[str, Any]:
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative in (*MATERIAL_PATHS, KEY_PATH, "tools/build_provenance.py"):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    _git(repo, "init")
    _git(repo, "config", "core.autocrlf", "false")
    _git(repo, "config", "user.email", "w6-06@example.invalid")
    _git(repo, "config", "user.name", "W6-06 Test")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "fixture")
    commit = _git(repo, "rev-parse", "HEAD")
    wheel = tmp_path / "juris_calculus-4.0.0-py3-none-any.whl"
    rebuild = tmp_path / "rebuild.whl"
    _write_wheel(wheel)
    shutil.copyfile(wheel, rebuild)
    sbom = tmp_path / "release-sbom.json"
    provenance = tmp_path / "build-provenance.json"
    checksums = tmp_path / "SHA256SUMS"
    create_release_evidence(
        root=repo,
        wheel=wheel,
        rebuild_wheel=rebuild,
        source_commit=commit,
        tag="v4.0.0",
        key_path=repo / KEY_PATH,
        sbom_output=sbom,
        provenance_output=provenance,
        checksums_output=checksums,
        release_candidate=True,
    )
    return {
        "repo": repo,
        "commit": commit,
        "wheel": wheel,
        "rebuild": rebuild,
        "sbom": sbom,
        "provenance": provenance,
        "checksums": checksums,
        "key": repo / KEY_PATH,
    }


def _verify(case: dict[str, Any], *, allow_test_key: bool = True) -> dict[str, Any]:
    return verify_release_evidence(
        root=case["repo"],
        wheel=case["wheel"],
        sbom_path=case["sbom"],
        provenance_path=case["provenance"],
        checksums_path=case["checksums"],
        key_path=case["key"],
        allow_test_key=allow_test_key,
    )


def _write_canonical(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n",
    )


def test_release_identity_binds_commit_tag_version_and_artifacts(tmp_path: Path) -> None:
    case = _case(tmp_path)
    evidence = _verify(case)
    statement = evidence["statement"]
    assert statement["source"]["commit"] == case["commit"]
    assert statement["release_identity"] == {
        "project": "juris-calculus", "version": "4.0.0", "tag": "v4.0.0",
    }
    assert statement["subject"]["sha256"].startswith("sha256:")
    assert statement["build_evidence"]["kind"] == "BYTE_IDENTICAL_REBUILD"


def test_signed_scope_is_distinct_and_unsigned_fails(tmp_path: Path) -> None:
    case = _case(tmp_path)
    evidence = _verify(case)
    assert evidence["signature"]["scope"] == "release-build-provenance"
    assert evidence["signature"]["scope"] not in {"build-attestation", "pack-release"}
    del evidence["signature"]
    _write_canonical(case["provenance"], evidence)
    with pytest.raises(EvidenceError):
        _verify(case)


def test_sbom_exactly_covers_wheel_record_and_runtime_dependencies(tmp_path: Path) -> None:
    case = _case(tmp_path)
    _verify(case)
    sbom = json.loads(case["sbom"].read_text(encoding="utf-8"))
    assert len(sbom["wheel_files"]) == sbom["artifact"]["record_entries"] == 4
    assert {item["name"] for item in sbom["runtime_dependencies"]} == {
        "pyyaml", "cryptography", "cffi", "pycparser",
    }
    sbom["wheel_files"].pop()
    _write_canonical(case["sbom"], sbom)
    with pytest.raises(EvidenceError):
        _verify(case)


def test_checksums_exactly_cover_release_artifacts(tmp_path: Path) -> None:
    case = _case(tmp_path)
    _verify(case)
    names = {line.split("  ", 1)[1] for line in case["checksums"].read_text().splitlines()}
    assert names == {case["wheel"].name, case["sbom"].name, case["provenance"].name}
    case["checksums"].write_text(case["checksums"].read_text() + "0" * 64 + "  extra\n")
    with pytest.raises(EvidenceError, match="checksums"):
        _verify(case)


def test_material_and_spec_mutations_fail_closed(tmp_path: Path) -> None:
    case = _case(tmp_path)
    baseline = json.loads(case["provenance"].read_text(encoding="utf-8"))
    mutations = []
    for path in (
        "requirements/core.lock",
        "schemas/jc-v4.schema.json",
        "mcp_manifest.json",
        "docs/architecture/module-authority.json",
    ):
        changed = json.loads(json.dumps(baseline))
        changed["statement"]["release_materials"][path] = "sha256:" + "0" * 64
        mutations.append(changed)
    changed = json.loads(json.dumps(baseline))
    changed["statement"]["companion_spec_commit"] = "0" * 40
    mutations.append(changed)
    for mutation in mutations:
        _write_canonical(case["provenance"], mutation)
        with pytest.raises(EvidenceError):
            _verify(case)


def test_wheel_and_record_mutations_fail_closed(tmp_path: Path) -> None:
    case = _case(tmp_path)
    case["wheel"].write_bytes(case["wheel"].read_bytes() + b"tampered")
    with pytest.raises(EvidenceError):
        _verify(case)
    broken = tmp_path / "broken.whl"
    _write_wheel(
        broken,
        module_payload=b"tampered\n",
        recorded_module_payload=b'__version__ = "4.0.0"\n',
    )
    case["wheel"] = broken
    with pytest.raises(EvidenceError, match="RECORD"):
        _verify(case)


def test_test_key_is_non_promotable_without_explicit_allowance(tmp_path: Path) -> None:
    case = _case(tmp_path)
    evidence = _verify(case)
    assert evidence["statement"]["promotion_status"] == "TEST_ONLY_NOT_PROMOTABLE"
    assert evidence["statement"]["production_release_claimed"] is False
    with pytest.raises(EvidenceError, match="production promotion"):
        _verify(case, allow_test_key=False)


def test_dirty_tracked_attestor_tree_fails_closed(tmp_path: Path) -> None:
    case = _case(tmp_path)
    material = case["repo"] / "schemas/jc-v4.schema.json"
    material.write_bytes(material.read_bytes() + b"\n")
    with pytest.raises(EvidenceError, match="tracked or staged"):
        _verify(case)


def test_ab_rebuild_mismatch_fails_closed(tmp_path: Path) -> None:
    case = _case(tmp_path)
    case["rebuild"].write_bytes(case["rebuild"].read_bytes() + b"different")
    with pytest.raises(EvidenceError, match="byte-identical"):
        create_release_evidence(
            root=case["repo"], wheel=case["wheel"], rebuild_wheel=case["rebuild"],
            source_commit=case["commit"], tag="v4.0.0", key_path=case["key"],
            sbom_output=tmp_path / "other-sbom.json",
            provenance_output=tmp_path / "other-provenance.json",
            checksums_output=tmp_path / "other-checksums.txt", release_candidate=True,
        )


def test_missing_build_evidence_and_wrong_tag_fail_closed(tmp_path: Path) -> None:
    case = _case(tmp_path)
    common = {
        "root": case["repo"], "wheel": case["wheel"],
        "source_commit": case["commit"], "key_path": case["key"],
        "sbom_output": tmp_path / "other-sbom.json",
        "provenance_output": tmp_path / "other-provenance.json",
        "checksums_output": tmp_path / "other-checksums.txt", "release_candidate": True,
    }
    with pytest.raises(EvidenceError, match="intended tag"):
        create_release_evidence(tag="v4.0.1", rebuild_wheel=case["rebuild"], **common)
    with pytest.raises(EvidenceError, match="exactly one"):
        create_release_evidence(tag="v4.0.0", **common)
