#!/usr/bin/env python3
"""Create and verify signed release evidence for one exact tested wheel."""

from __future__ import annotations

import argparse
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
import zipfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


ROOT = Path(__file__).resolve().parent.parent
SPEC_COMMIT = "a3a015941f75091c87d57aa956e712f1546dd7d4"
SIGNING_DOMAIN = b"juris-calculus\0release-build-provenance\0"
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
VERSION_RE = re.compile(r'(?m)^__version__ = "([^"]+)"$')
REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")
HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})(?=\s|$)")
MATERIAL_PATHS = (
    "compiler_core/version.py",
    "docs/architecture/module-authority.json",
    "mcp_manifest.json",
    "requirements/build.lock",
    "requirements/core.lock",
    "requirements/release.lock",
    "requirements/source-tool.lock",
    "requirements/test.lock",
    "schemas/jc-v4.schema.json",
    "tests/fixtures/golden/v4-test-trust-policy.json",
    "tests/fixtures/keys/v4-synthetic-trust.json",
    "tests/required-v4-tests.json",
)
SOURCE_BUILD_LOCKS = (
    "requirements/build.lock",
    "requirements/core.lock",
    "requirements/test.lock",
)


class EvidenceError(ValueError):
    """Stable fail-closed error for malformed or mismatched release evidence."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_identity(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {"filename": path.name, "sha256": _sha256(payload), "bytes": len(payload)}


def _git(root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if check and completed.returncode != 0:
        detail = " ".join((completed.stderr or completed.stdout).split())[-800:]
        raise EvidenceError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _git_bytes(root: Path, commit: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=root, capture_output=True, check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[-800:]
        raise EvidenceError(f"committed material is unavailable: {path}: {detail}")
    return completed.stdout


def _commit_tree(root: Path, commit: str) -> str:
    if COMMIT_RE.fullmatch(commit) is None:
        raise EvidenceError("source commit must be 40 lowercase hexadecimal characters")
    resolved = _git(root, "rev-parse", "--verify", f"{commit}^{{commit}}")
    if resolved != commit:
        raise EvidenceError("source commit is not the exact resolved commit")
    tree = _git(root, "rev-parse", f"{commit}^{{tree}}")
    if COMMIT_RE.fullmatch(tree) is None:
        raise EvidenceError("source tree is malformed")
    return tree


def _ensure_clean_attestor(root: Path) -> tuple[str, str]:
    commit = _git(root, "rev-parse", "HEAD")
    tree = _commit_tree(root, commit)
    for args in (
        ("diff", "--quiet", "HEAD", "--"),
        ("diff", "--cached", "--quiet", "HEAD", "--"),
    ):
        if subprocess.run(["git", *args], cwd=root, check=False).returncode != 0:
            raise EvidenceError("attestor has tracked or staged worktree changes")
    return commit, tree


def _material_identities(root: Path, commit: str) -> dict[str, str]:
    return {path: _sha256(_git_bytes(root, commit, path)) for path in MATERIAL_PATHS}


def _source_lock_identities(root: Path, commit: str) -> dict[str, dict[str, str]]:
    identities: dict[str, dict[str, str]] = {}
    for path in SOURCE_BUILD_LOCKS:
        payload = _git_bytes(root, commit, path)
        identities[path] = {
            "git_blob_sha256": _sha256(payload),
            "crlf_execution_sha256": _sha256(payload.replace(b"\n", b"\r\n")),
        }
    return identities


def _parse_lock(payload: bytes) -> list[dict[str, Any]]:
    lines = payload.decode("utf-8").splitlines()
    annotations: dict[str, str] = {}
    packages: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("# "):
            key, separator, value = line[2:].partition(": ")
            if separator and key in {"package", "role", "license"}:
                annotations[key] = value
            index += 1
            continue
        block = [line]
        while block[-1].endswith("\\"):
            index += 1
            if index >= len(lines):
                raise EvidenceError("core lock has an unterminated requirement")
            block.append(lines[index].strip())
        joined = " ".join(
            part[:-1].strip() if part.endswith("\\") else part for part in block
        )
        match = REQUIREMENT_RE.match(joined)
        hashes = HASH_RE.findall(joined)
        if match is None or set(annotations) != {"package", "role", "license"} or not hashes:
            raise EvidenceError("core lock contains an unbound requirement")
        name, version = match.groups()
        canonical_name = re.sub(r"[-_.]+", "-", name).lower()
        if re.sub(r"[-_.]+", "-", annotations["package"]).lower() != canonical_name:
            raise EvidenceError("core lock package annotation drifted")
        packages.append({
            "name": canonical_name,
            "version": version,
            "role": annotations["role"],
            "license": annotations["license"],
            "hashes": sorted(hashes),
        })
        annotations = {}
        index += 1
    if annotations or not packages:
        raise EvidenceError("core lock is incomplete")
    return sorted(packages, key=lambda item: str(item["name"]))


def _record_hash(payload: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode("ascii")
    return "sha256=" + encoded.rstrip("=")


def _wheel_inventory(wheel: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or any(name.endswith("/") for name in names):
                raise EvidenceError("wheel has duplicate names or directory records")
            record_paths = [name for name in names if name.endswith(".dist-info/RECORD")]
            metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
            wheel_paths = [name for name in names if name.endswith(".dist-info/WHEEL")]
            if len(record_paths) != 1 or len(metadata_paths) != 1 or len(wheel_paths) != 1:
                raise EvidenceError("wheel must contain exactly one METADATA, WHEEL, and RECORD")
            contents = {name: archive.read(name) for name in names}
    except (OSError, zipfile.BadZipFile) as exc:
        raise EvidenceError(f"wheel is unreadable: {exc}") from exc
    record_path = record_paths[0]
    try:
        rows = list(csv.reader(io.StringIO(contents[record_path].decode("utf-8"))))
    except (UnicodeError, csv.Error) as exc:
        raise EvidenceError(f"wheel RECORD is unreadable: {exc}") from exc
    if any(len(row) != 3 for row in rows):
        raise EvidenceError("wheel RECORD rows must contain exactly three fields")
    by_name = {row[0]: row[1:] for row in rows}
    if len(by_name) != len(rows) or set(by_name) != set(names):
        raise EvidenceError("wheel RECORD does not exactly cover archive files")
    files: list[dict[str, Any]] = []
    for name in sorted(names):
        payload = contents[name]
        digest, size = by_name[name]
        if name == record_path:
            if digest or size:
                raise EvidenceError("wheel RECORD self-row must omit digest and size")
        elif digest != _record_hash(payload) or size != str(len(payload)):
            raise EvidenceError(f"wheel RECORD mismatch: {name}")
        files.append({"path": name, "sha256": _sha256(payload), "bytes": len(payload)})
    metadata = BytesParser().parsebytes(contents[metadata_paths[0]])
    project = metadata.get("Name")
    version = metadata.get("Version")
    if not project or not version:
        raise EvidenceError("wheel METADATA lacks Name or Version")
    wheel_metadata = BytesParser().parsebytes(contents[wheel_paths[0]])
    tags = wheel_metadata.get_all("Tag", [])
    if len(tags) != 1 or re.fullmatch(r"[A-Za-z0-9_.]+-[A-Za-z0-9_.]+-[A-Za-z0-9_.]+", tags[0]) is None:
        raise EvidenceError("wheel must declare exactly one valid compatibility tag")
    logical_filename = (
        f"{re.sub(r'[-_.]+', '_', project)}-{version}-{tags[0]}.whl"
    )
    identity = _file_identity(wheel)
    identity.update({
        "filename": logical_filename,
        "project": project,
        "version": version,
        "record_path": record_path,
        "record_sha256": _sha256(contents[record_path]),
        "record_entries": len(rows),
    })
    return identity, files


def _tool_spec_digest(manifest_bytes: bytes) -> str:
    try:
        tools = json.loads(manifest_bytes)["tools"]
        specs = [{
            "name": tool["name"],
            "description": tool["description"],
            "input_type": tool["inputSchema"]["$ref"].rsplit("/", 1)[-1],
            "output_type": tool["outputSchema"]["$ref"].rsplit("/", 1)[-1],
            "error_type": tool["x-jc-errorSchema"]["$ref"].rsplit("/", 1)[-1],
        } for tool in tools]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"MCP ToolSpec publication is malformed: {exc}") from exc
    return _sha256(_canonical_bytes(specs))


def _version_at(root: Path, commit: str) -> str:
    source = _git_bytes(root, commit, "compiler_core/version.py").decode("utf-8")
    match = VERSION_RE.search(source)
    if match is None:
        raise EvidenceError("source version authority is malformed")
    return match.group(1)


def _build_evidence(
    root: Path,
    wheel_identity: dict[str, Any],
    source_commit: str,
    source_tree: str,
    attestor_commit: str,
    rebuild_wheel: Path | None,
    build_report: Path | None,
    build_receipt_digest: str | None,
) -> dict[str, Any]:
    if (rebuild_wheel is None) == (build_report is None):
        raise EvidenceError("provide exactly one of rebuild wheel or build report")
    if rebuild_wheel is not None:
        rebuilt = _file_identity(rebuild_wheel)
        if rebuilt["sha256"] != wheel_identity["sha256"] or rebuilt["bytes"] != wheel_identity["bytes"]:
            raise EvidenceError("A/B rebuild wheels are not byte-identical")
        if source_commit != attestor_commit:
            raise EvidenceError("direct A/B evidence must be built from the attestor commit")
        return {
            "kind": "BYTE_IDENTICAL_REBUILD",
            "wheel_a": wheel_identity,
            "wheel_b": rebuilt,
        }
    if build_report is None or build_receipt_digest is None:
        raise EvidenceError("formal build report requires its completed receipt digest")
    if DIGEST_RE.fullmatch(build_receipt_digest) is None:
        raise EvidenceError("build receipt digest is malformed")
    try:
        report_bytes = build_report.read_bytes()
        report = json.loads(report_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"formal build report is unreadable: {exc}") from exc
    formal = report.get("formal_wheel", {})
    builds = report.get("builds", [])
    if (
        report.get("schema_version") != "jc/w6-dual-build-installed-e2e/1.0"
        or report.get("status") != "PASS"
        or report.get("commit") != source_commit
        or report.get("tree") != source_tree
        or formal.get("sha256") != wheel_identity["sha256"]
        or formal.get("bytes") != wheel_identity["bytes"]
        or formal.get("filename") != wheel_identity["filename"]
        or formal.get("byte_identical_rebuilds") is not True
        or len(builds) != 2
        or any(
            not isinstance(row, dict)
            or row.get("fresh_build_environment") is not True
            or row.get("network_disabled") is not True
            or row.get("gate_report", {}).get("sha256") != wheel_identity["sha256"]
            for row in builds
        )
    ):
        raise EvidenceError("formal build report does not bind the exact dual-built wheel")
    source_locks = _source_lock_identities(root, source_commit)
    expected_report_locks = {
        "build": source_locks["requirements/build.lock"]["crlf_execution_sha256"],
        "core": source_locks["requirements/core.lock"]["crlf_execution_sha256"],
        "test": source_locks["requirements/test.lock"]["crlf_execution_sha256"],
    }
    if report.get("lock_digests") != expected_report_locks:
        raise EvidenceError("formal build report lock binding drifted")
    return {
        "kind": "W6_04_LOCKED_DUAL_BUILD",
        "report": {
            "filename": build_report.name,
            "sha256": _sha256(report_bytes),
            "bytes": len(report_bytes),
        },
        "receipt_digest": build_receipt_digest,
        "source_archive": report.get("source_archive"),
        "build_lanes": [row.get("lane") for row in builds],
    }


def _load_key(path: Path, *, private: bool) -> tuple[dict[str, Any], bytes, bytes | None]:
    try:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        public_bytes = base64.b64decode(fixture["public_key_base64"], validate=True)
        private_bytes = (
            base64.b64decode(fixture["private_key_base64"], validate=True) if private else None
        )
    except (KeyError, OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"signing key is unreadable: {exc}") from exc
    if (
        fixture.get("algorithm") != "Ed25519"
        or len(public_bytes) != 32
        or fixture.get("public_key_sha256") != _sha256(public_bytes)
        or not isinstance(fixture.get("key_id"), str)
    ):
        raise EvidenceError("signing key public identity is malformed")
    if private_bytes is not None:
        if len(private_bytes) != 32 or fixture.get("private_key_sha256") != _sha256(private_bytes):
            raise EvidenceError("signing key private identity is malformed")
        derived = Ed25519PrivateKey.from_private_bytes(private_bytes).public_key().public_bytes_raw()
        if derived != public_bytes:
            raise EvidenceError("signing key public/private bytes disagree")
    return fixture, public_bytes, private_bytes


def _sbom_document(
    wheel_identity: dict[str, Any],
    wheel_files: list[dict[str, Any]],
    core_lock_bytes: bytes,
) -> dict[str, Any]:
    return {
        "schema_version": "jc/release-wheel-sbom/1.0",
        "artifact": wheel_identity,
        "wheel_files": wheel_files,
        "runtime_dependencies": _parse_lock(core_lock_bytes),
        "runtime_lock": {
            "path": "requirements/core.lock",
            "sha256": _sha256(core_lock_bytes),
        },
    }


def create_release_evidence(
    *,
    root: Path,
    wheel: Path,
    source_commit: str,
    tag: str,
    key_path: Path,
    sbom_output: Path,
    provenance_output: Path,
    checksums_output: Path,
    rebuild_wheel: Path | None = None,
    build_report: Path | None = None,
    build_receipt_digest: str | None = None,
    release_candidate: bool = False,
) -> dict[str, Any]:
    """Create deterministic signed evidence for one wheel."""

    attestor_commit, attestor_tree = _ensure_clean_attestor(root)
    source_tree = _commit_tree(root, source_commit)
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_commit, attestor_commit],
        cwd=root, check=False,
    )
    if ancestor.returncode != 0:
        raise EvidenceError("wheel source commit is not an ancestor of the attestor commit")
    wheel_identity, wheel_files = _wheel_inventory(wheel)
    version = _version_at(root, source_commit)
    if wheel_identity["project"] != "juris-calculus" or wheel_identity["version"] != version:
        raise EvidenceError("wheel name/version does not match source version authority")
    if tag != f"v{version}":
        raise EvidenceError("intended tag does not exactly match wheel version")
    key, public_bytes, private_bytes = _load_key(key_path, private=True)
    if private_bytes is None:
        raise EvidenceError("signing key lacks private bytes")
    test_only = key.get("scope") == "test-only" or key.get("production_allowed") is False
    if test_only and not release_candidate:
        raise EvidenceError("test-only key requires explicit release-candidate mode")
    if not test_only and release_candidate:
        raise EvidenceError("release-candidate mode is reserved for the test-only key")
    materials = _material_identities(root, attestor_commit)
    source_locks = _source_lock_identities(root, source_commit)
    build_evidence = _build_evidence(
        root, wheel_identity, source_commit, source_tree, attestor_commit,
        rebuild_wheel, build_report, build_receipt_digest,
    )
    sbom = _sbom_document(
        wheel_identity, wheel_files, _git_bytes(root, source_commit, "requirements/core.lock"),
    )
    sbom_output.parent.mkdir(parents=True, exist_ok=True)
    sbom_bytes = _canonical_bytes(sbom) + b"\n"
    sbom_output.write_bytes(sbom_bytes)
    statement = {
        "schema_version": "jc/release-build-provenance-statement/1.0",
        "subject": wheel_identity,
        "release_identity": {"project": "juris-calculus", "version": version, "tag": tag},
        "source": {"commit": source_commit, "tree": source_tree},
        "attestor": {
            "commit": attestor_commit,
            "tree": attestor_tree,
            "builder_sha256": _sha256(
                _git_bytes(root, attestor_commit, "tools/build_provenance.py")
            ),
        },
        "companion_spec_commit": SPEC_COMMIT,
        "release_materials": materials,
        "source_build_locks": source_locks,
        "tool_spec_digest": _tool_spec_digest(
            _git_bytes(root, attestor_commit, "mcp_manifest.json")
        ),
        "provenance_filename": provenance_output.name,
        "sbom": {
            "filename": sbom_output.name,
            "sha256": _sha256(sbom_bytes),
            "bytes": len(sbom_bytes),
        },
        "build_evidence": build_evidence,
        "release_candidate": release_candidate,
        "production_release_claimed": False,
        "promotion_status": (
            "TEST_ONLY_NOT_PROMOTABLE" if test_only else "PENDING_TAG_VERIFICATION"
        ),
    }
    signature = Ed25519PrivateKey.from_private_bytes(private_bytes).sign(
        SIGNING_DOMAIN + _canonical_bytes(statement)
    )
    provenance = {
        "schema_version": "jc/signed-release-build-provenance/1.0",
        "statement": statement,
        "signature": {
            "algorithm": "Ed25519",
            "key_id": key["key_id"],
            "role": "release_attestor",
            "scope": "release-build-provenance",
            "artifact_kind": "release-provenance",
            "public_key_base64": base64.b64encode(public_bytes).decode("ascii"),
            "signature_base64": base64.b64encode(signature).decode("ascii"),
            "test_only": test_only,
            "production_allowed": bool(key.get("production_allowed")),
        },
    }
    provenance_output.parent.mkdir(parents=True, exist_ok=True)
    provenance_bytes = _canonical_bytes(provenance) + b"\n"
    provenance_output.write_bytes(provenance_bytes)
    checksum_rows = sorted((
        (str(wheel_identity["filename"]), str(wheel_identity["sha256"])),
        (sbom_output.name, _sha256(sbom_bytes)),
        (provenance_output.name, _sha256(provenance_bytes)),
    ))
    checksums_output.parent.mkdir(parents=True, exist_ok=True)
    checksums_output.write_text(
        "".join(
            f"{digest.removeprefix('sha256:')}  {name}\n"
            for name, digest in checksum_rows
        ),
        encoding="utf-8", newline="\n",
    )
    return provenance


def _checksum_document(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            digest, separator, name = line.partition("  ")
            if not separator or re.fullmatch(r"[0-9a-f]{64}", digest) is None or not name:
                raise EvidenceError("checksums file contains a malformed row")
            if name in rows:
                raise EvidenceError("checksums file contains a duplicate filename")
            rows[name] = "sha256:" + digest
    except (OSError, UnicodeError) as exc:
        raise EvidenceError(f"checksums file is unreadable: {exc}") from exc
    return rows


def verify_release_evidence(
    *,
    root: Path,
    wheel: Path,
    sbom_path: Path,
    provenance_path: Path,
    checksums_path: Path,
    key_path: Path,
    allow_test_key: bool = False,
    require_tag_ref: bool = False,
    expected_attestor_commit: str | None = None,
) -> dict[str, Any]:
    """Verify signature, identity, build, SBOM, materials, and checksums."""

    if expected_attestor_commit is None:
        attestor_commit, attestor_tree = _ensure_clean_attestor(root)
    else:
        attestor_commit = expected_attestor_commit
        attestor_tree = _commit_tree(root, attestor_commit)
    try:
        provenance_bytes = provenance_path.read_bytes()
        provenance = json.loads(provenance_bytes)
        sbom_bytes = sbom_path.read_bytes()
        sbom = json.loads(sbom_bytes)
        statement = provenance["statement"]
        signature = provenance["signature"]
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"release evidence is unreadable: {exc}") from exc
    if provenance_bytes != _canonical_bytes(provenance) + b"\n":
        raise EvidenceError("provenance bytes are not canonical")
    if sbom_bytes != _canonical_bytes(sbom) + b"\n":
        raise EvidenceError("SBOM bytes are not canonical")
    if provenance.get("schema_version") != "jc/signed-release-build-provenance/1.0":
        raise EvidenceError("provenance schema version drifted")
    expected_signature = {
        "algorithm": "Ed25519",
        "role": "release_attestor",
        "scope": "release-build-provenance",
        "artifact_kind": "release-provenance",
    }
    if any(signature.get(key) != value for key, value in expected_signature.items()):
        raise EvidenceError("signature algorithm, role, scope, or artifact kind drifted")
    key, public_bytes, _ = _load_key(key_path, private=False)
    if (
        signature.get("key_id") != key["key_id"]
        or signature.get("public_key_base64")
        != base64.b64encode(public_bytes).decode("ascii")
    ):
        raise EvidenceError("provenance signing key identity drifted")
    test_only = key.get("scope") == "test-only" or key.get("production_allowed") is False
    if (
        signature.get("test_only") is not test_only
        or signature.get("production_allowed") is not bool(key.get("production_allowed"))
    ):
        raise EvidenceError("provenance key policy flags drifted")
    if test_only and not allow_test_key:
        raise EvidenceError("test-only provenance is not accepted for production promotion")
    try:
        signed = base64.b64decode(signature["signature_base64"], validate=True)
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(
            signed, SIGNING_DOMAIN + _canonical_bytes(statement),
        )
    except (KeyError, ValueError, InvalidSignature) as exc:
        raise EvidenceError("provenance signature verification failed") from exc
    if statement.get("production_release_claimed") is not False:
        raise EvidenceError("W6-06 evidence must not claim a production release")
    if test_only and (
        statement.get("release_candidate") is not True
        or statement.get("promotion_status") != "TEST_ONLY_NOT_PROMOTABLE"
    ):
        raise EvidenceError("test-only provenance must remain explicitly non-promotable")
    source = statement.get("source", {})
    attestor = statement.get("attestor", {})
    source_commit = source.get("commit")
    if not isinstance(source_commit, str):
        raise EvidenceError("source commit is missing")
    source_tree = _commit_tree(root, source_commit)
    if source.get("tree") != source_tree:
        raise EvidenceError("source tree binding drifted")
    if attestor != {
        "commit": attestor_commit,
        "tree": attestor_tree,
        "builder_sha256": _sha256(
            _git_bytes(root, attestor_commit, "tools/build_provenance.py")
        ),
    }:
        raise EvidenceError("attestor commit, tree, or builder binding drifted")
    if statement.get("companion_spec_commit") != SPEC_COMMIT:
        raise EvidenceError("companion specification commit drifted")
    if statement.get("release_materials") != _material_identities(root, attestor_commit):
        raise EvidenceError("release material binding drifted")
    if statement.get("source_build_locks") != _source_lock_identities(root, source_commit):
        raise EvidenceError("source build lock binding drifted")
    if statement.get("tool_spec_digest") != _tool_spec_digest(
        _git_bytes(root, attestor_commit, "mcp_manifest.json")
    ):
        raise EvidenceError("ToolSpec semantic digest drifted")
    wheel_identity, wheel_files = _wheel_inventory(wheel)
    if statement.get("subject") != wheel_identity:
        raise EvidenceError("provenance subject does not bind the exact wheel")
    version = _version_at(root, source_commit)
    tag = f"v{version}"
    if statement.get("release_identity") != {
        "project": "juris-calculus", "version": version, "tag": tag,
    }:
        raise EvidenceError("release commit/tag/version identity drifted")
    if require_tag_ref:
        tagged = _git(root, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
        if tagged != source_commit:
            raise EvidenceError("release tag does not resolve to the wheel source commit")
    build_evidence = statement.get("build_evidence", {})
    if build_evidence.get("kind") == "BYTE_IDENTICAL_REBUILD":
        wheel_b = build_evidence.get("wheel_b", {})
        if (
            build_evidence.get("wheel_a") != wheel_identity
            or wheel_b.get("sha256") != wheel_identity["sha256"]
            or wheel_b.get("bytes") != wheel_identity["bytes"]
            or source_commit != attestor_commit
        ):
            raise EvidenceError("A/B rebuild evidence drifted")
    elif build_evidence.get("kind") == "W6_04_LOCKED_DUAL_BUILD":
        report = build_evidence.get("report", {})
        if (
            not isinstance(report, dict)
            or DIGEST_RE.fullmatch(str(report.get("sha256"))) is None
            or DIGEST_RE.fullmatch(str(build_evidence.get("receipt_digest"))) is None
            or build_evidence.get("build_lanes") != ["A", "B"]
        ):
            raise EvidenceError("formal dual-build evidence is malformed")
    else:
        raise EvidenceError("build evidence kind is missing or unsupported")
    expected_sbom = _sbom_document(
        wheel_identity, wheel_files,
        _git_bytes(root, source_commit, "requirements/core.lock"),
    )
    if sbom != expected_sbom:
        raise EvidenceError("SBOM does not exactly cover wheel RECORD and runtime dependencies")
    sbom_identity = statement.get("sbom", {})
    provenance_filename = statement.get("provenance_filename")
    if (
        not isinstance(sbom_identity, dict)
        or not isinstance(sbom_identity.get("filename"), str)
        or Path(str(sbom_identity["filename"])).name != sbom_identity["filename"]
        or not isinstance(provenance_filename, str)
        or Path(provenance_filename).name != provenance_filename
    ):
        raise EvidenceError("release evidence logical filenames are malformed")
    if sbom_identity != {
        "filename": sbom_identity["filename"],
        "sha256": _sha256(sbom_bytes),
        "bytes": len(sbom_bytes),
    }:
        raise EvidenceError("provenance SBOM binding drifted")
    checksums = _checksum_document(checksums_path)
    expected_checksums = {
        str(wheel_identity["filename"]): str(wheel_identity["sha256"]),
        str(sbom_identity["filename"]): _sha256(sbom_bytes),
        provenance_filename: _sha256(provenance_bytes),
    }
    if checksums != expected_checksums:
        raise EvidenceError("checksums do not exactly cover wheel, SBOM, and provenance")
    return provenance


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--wheel", type=Path, required=True)
    create.add_argument("--rebuild-wheel", type=Path)
    create.add_argument("--build-report", type=Path)
    create.add_argument("--build-receipt-digest")
    create.add_argument("--source-commit", required=True)
    create.add_argument("--tag", required=True)
    create.add_argument("--key", type=Path, required=True)
    create.add_argument("--sbom-output", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--checksums-output", type=Path, required=True)
    create.add_argument("--release-candidate", action="store_true")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--wheel", type=Path, required=True)
    verify.add_argument("--sbom", type=Path, required=True)
    verify.add_argument("--provenance", type=Path, required=True)
    verify.add_argument("--checksums", type=Path, required=True)
    verify.add_argument("--key", type=Path, required=True)
    verify.add_argument("--allow-test-key", action="store_true")
    verify.add_argument("--require-tag-ref", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            result = create_release_evidence(
                root=ROOT, wheel=args.wheel, source_commit=args.source_commit,
                tag=args.tag, key_path=args.key, sbom_output=args.sbom_output,
                provenance_output=args.output, checksums_output=args.checksums_output,
                rebuild_wheel=args.rebuild_wheel, build_report=args.build_report,
                build_receipt_digest=args.build_receipt_digest,
                release_candidate=args.release_candidate,
            )
        else:
            result = verify_release_evidence(
                root=ROOT, wheel=args.wheel, sbom_path=args.sbom,
                provenance_path=args.provenance, checksums_path=args.checksums,
                key_path=args.key, allow_test_key=args.allow_test_key,
                require_tag_ref=args.require_tag_ref,
            )
    except (EvidenceError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"release provenance FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": "PASS", "command": args.command,
        "wheel_sha256": result["statement"]["subject"]["sha256"],
        "promotion_status": result["statement"]["promotion_status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
