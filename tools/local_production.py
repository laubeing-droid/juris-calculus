#!/usr/bin/env python3
"""Local V4 production lifecycle commands."""

from __future__ import annotations

import argparse
from base64 import b64decode, b64encode
from binascii import Error as Base64Error
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.canonical_serialization import DigestV4, canonical_bytes, digest_value, parse_json_document
from compiler_core.contracts import ContentRefV4


ROOT_FIELDS = {
    "schema_version", "scope", "signing_mode", "independent_human_review",
    "activated_at", "expires_at", "private_seed_base64",
}
TRUST_FIELDS = {
    "schema_version", "scope", "production_allowed", "signing_mode",
    "independent_human_review", "verification_time", "runtime_identity",
    "trust_policy", "trust_keys",
}
PROFILE_PIN_FIELDS = (
    "schema_version", "engine_version", "engine_source_tree", "engine_build_digest",
    "wheel_digest", "package_digest", "lock_digest", "schema_digest",
    "tool_spec_digest", "active_pack_ref", "trust_policy_ref",
    "storage_capability_ref", "kernel_ready", "legal_production_ready",
)


def _derive(master: bytes, name: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=b"jc-v4-local-production-v1",
        info=f"juris-calculus/local-production/{name}".encode("ascii"),
    ).derive(master)


def _harden_key_acl(path: Path) -> None:
    if os.name != "nt":
        return
    domain = os.environ.get("USERDOMAIN")
    account = f"{domain}\\{getpass.getuser()}" if domain else getpass.getuser()
    subprocess.run(
        [
            "icacls", str(path), "/inheritance:r", "/grant:r",
            f"{account}:(F)", "*S-1-5-18:(F)", "*S-1-5-32-544:(F)",
        ],
        check=True, capture_output=True,
    )


def initialize_service_key(root_path: Path, output_path: Path, trust_path: Path) -> None:
    """Derive the runtime-only service key; this is the sole root-seed reader."""

    root = parse_json_document(root_path.read_bytes())
    trust = parse_json_document(trust_path.read_bytes())
    if type(root) is not dict or set(root) != ROOT_FIELDS:
        raise ValueError("local production root fields are not exact")
    if type(trust) is not dict or set(trust) != TRUST_FIELDS:
        raise ValueError("local production trust fields are not exact")
    if root["schema_version"] != "jc/local-production-root/1.0":
        raise ValueError("local production root schema is unsupported")
    try:
        seed = _derive(b64decode(root["private_seed_base64"], validate=True), "service")
    except (Base64Error, TypeError, ValueError) as exc:
        raise ValueError("local production root seed is invalid") from exc
    private_key = Ed25519PrivateKey.from_private_bytes(seed)
    public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    service = next((row for row in trust["trust_keys"]
                    if row.get("key_id") == "local-production-service-key"), None)
    if service is None or b64decode(service["public_key_base64"], validate=True) != public:
        raise ValueError("derived service key does not match production trust")
    document = {
        "schema_version": "jc/local-production-service-key/1.0",
        "key_id": service["key_id"], "issuer": service["issuer"],
        "principal_id": service["principal_id"],
        "private_seed_base64": b64encode(seed).decode("ascii"),
        "public_key_base64": b64encode(public).decode("ascii"),
    }
    encoded = canonical_bytes(document)
    if output_path.is_file():
        if output_path.read_bytes() != encoded:
            raise ValueError("existing service runtime key differs from derived identity")
        _harden_key_acl(output_path)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encoded)
    _harden_key_acl(output_path)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None,
         timeout: int = 900, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command, cwd=cwd, env=env, input=input_text, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False, timeout=timeout,
    )
    if completed.returncode != 0:
        detail = " ".join((completed.stderr or completed.stdout).split())[-1600:]
        raise ValueError(f"command failed ({completed.returncode}): {detail}")
    return completed


def _git(*args: str) -> str:
    return _run(["git", *args], cwd=ROOT, timeout=120).stdout.strip()


def _venv_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _clean_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
    return env


def _efs_evidence(path: Path) -> dict[str, object]:
    if os.name != "nt":
        return {"encrypted": False, "algorithm": "platform-not-windows"}
    completed = _run(["cipher", "/c", str(path)], cwd=path.parent, timeout=120)
    output = completed.stdout
    if "AES" not in output or "256" not in output:
        raise ValueError("production state is not EFS AES-256")
    return {
        "encrypted": True, "algorithm": "EFS-AES-256",
        "cipher_output_digest": str(DigestV4.from_bytes(output.encode("utf-8"))),
    }


def _pointer_bytes(state_root: Path) -> dict[str, bytes | None]:
    deployment = state_root / "deployment"
    return {
        name: (deployment / name).read_bytes() if (deployment / name).is_file() else None
        for name in ("current.json", "previous.json", "profile-registry.json")
    }


def _installed_probe(python: Path, cwd: Path, environment: dict[str, str]) -> dict[str, object]:
    code = (
        "import json,pathlib,sys;import compiler_core,mcp_server;"
        "from compiler_core.version import __version__;"
        "root=pathlib.Path(sys.prefix).resolve();"
        "origins=[pathlib.Path(compiler_core.__file__).resolve(),"
        "pathlib.Path(mcp_server.__file__).resolve()];"
        "assert all(p.is_relative_to(root) for p in origins);"
        "print(json.dumps({'version':__version__,'prefix':str(root),"
        "'origins_in_venv':True},sort_keys=True))"
    )
    return json.loads(_run(
        [str(python), "-I", "-B", "-c", code], cwd=cwd,
        env=environment, timeout=120,
    ).stdout)


def _reuse_prepared(state_root: Path, source_commit: str) -> dict[str, object] | None:
    pointer_path = state_root / "deployment/prepared.json"
    if not pointer_path.is_file():
        return None
    try:
        pointer = parse_json_document(pointer_path.read_bytes())
        manifest_path = Path(pointer["manifest_path"])
        manifest = parse_json_document(manifest_path.read_bytes())
        wheel = Path(manifest["wheel_path"])
        python = Path(manifest["venv_python"])
        if (
            pointer_path.read_bytes() != canonical_bytes(pointer)
            or manifest_path.read_bytes() != canonical_bytes(manifest)
            or pointer["manifest_digest"] != _sha256(manifest_path)
            or manifest["source_commit"] != source_commit
            or manifest["wheel_digest"] != _sha256(wheel)
            or manifest["status"] != "PREPARED"
            or manifest["reproducible_build"] is not True
        ):
            return None
        probe = _installed_probe(python, manifest_path.parent / "runtime", _clean_environment())
        if probe["version"] != "4.0.0":
            return None
        return manifest
    except (KeyError, OSError, TypeError, ValueError):
        return None


def prepare_release(state_root: Path) -> dict[str, object]:
    """Build twice, install once, and publish an inactive immutable release pointer."""

    state_root = state_root.resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    efs = _efs_evidence(state_root)
    if _git("status", "--porcelain"):
        raise ValueError("prepare requires a clean committed worktree")
    source_commit = _git("rev-parse", "HEAD")
    reused = _reuse_prepared(state_root, source_commit)
    if reused is not None:
        return reused
    before = _pointer_bytes(state_root)
    source_tree = _git("rev-parse", "HEAD^{tree}")
    source_epoch = int(_git("show", "-s", "--format=%ct", "HEAD"))
    deployment = state_root / "deployment"
    deployment.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jc-v4-prepare-") as raw:
        temporary = Path(raw)
        archive = temporary / "source.tar"
        _run(["git", "archive", "--format=tar", "HEAD", "-o", str(archive)], cwd=ROOT)
        source = temporary / "source"
        source.mkdir()
        with tarfile.open(archive) as stream:
            stream.extractall(source, filter="data")
        build_env = temporary / "build-venv"
        _run([sys.executable, "-B", "-m", "venv", str(build_env)], cwd=temporary)
        build_python = _venv_python(build_env)
        env = _clean_environment()
        _run([
            str(build_python), "-B", "-m", "pip", "install",
            "--disable-pip-version-check", "--require-hashes", "-r",
            str(source / "requirements/build.lock"),
        ], cwd=temporary, env=env)
        reports: list[dict[str, object]] = []
        wheels: list[Path] = []
        for serial in (1, 2):
            out = temporary / f"dist-{serial}"
            report_path = temporary / f"build-{serial}.json"
            completed = _run([
                str(build_python), "-B", str(source / "tools/wheel_gate.py"),
                "--source", str(source), "--out-dir", str(out),
                "--source-date-epoch", str(source_epoch), "--no-isolation",
                "--output", str(report_path),
            ], cwd=temporary, env=env, timeout=1200)
            report = json.loads(completed.stdout)
            if report.get("status") != "PASS":
                raise ValueError("wheel gate did not pass")
            reports.append(report)
            wheels.append(next(out.glob("*.whl")))
        if wheels[0].read_bytes() != wheels[1].read_bytes():
            raise ValueError("independent wheel builds are not byte-identical")
        wheel_digest = _sha256(wheels[0])
        release_id = f"4.0.0-{source_commit[:12]}-{wheel_digest[7:19]}"
        release = deployment / "releases" / release_id
        if release.exists():
            raise ValueError("existing release identity is inconsistent with prepared pointer")
        artifacts = release / "artifacts"
        config_dir = release / "config"
        runtime_dir = release / "runtime"
        for path in (artifacts, config_dir, runtime_dir):
            path.mkdir(parents=True, exist_ok=False)
        wheel = artifacts / wheels[0].name
        shutil.copyfile(wheels[0], wheel)
        lock = ROOT / "requirements/core.lock"
        lock_digest = _sha256(lock)
        wheelhouse = deployment / "wheelhouse" / lock_digest.removeprefix("sha256:")
        wheelhouse.mkdir(parents=True, exist_ok=True)
        if not any(wheelhouse.iterdir()):
            _run([
                sys.executable, "-B", "-m", "pip", "download",
                "--disable-pip-version-check", "--require-hashes", "--dest",
                str(wheelhouse), "-r", str(lock),
            ], cwd=deployment, env=env)
        venv = release / "venv"
        _run([sys.executable, "-B", "-m", "venv", str(venv)], cwd=release)
        python = _venv_python(venv)
        _run([
            str(python), "-B", "-m", "pip", "install", "--no-index",
            "--find-links", str(wheelhouse), "--require-hashes", "-r", str(lock),
        ], cwd=runtime_dir, env=env)
        _run([
            str(python), "-B", "-m", "pip", "install", "--no-index", "--no-deps",
            str(wheel),
        ], cwd=runtime_dir, env=env)
        _run([str(python), "-B", "-m", "pip", "check"], cwd=runtime_dir, env=env)
        probe = _installed_probe(python, runtime_dir, env)
        if probe != {
            "version": "4.0.0", "prefix": str(venv.resolve()), "origins_in_venv": True,
        }:
            raise ValueError("installed wheel origin or version drifted")
        packages = json.loads(_run(
            [str(python), "-I", "-B", "-m", "pip", "list", "--format=json"],
            cwd=runtime_dir, env=env,
        ).stdout)
        package_digest = str(digest_value(sorted(
            [row["name"].lower(), row["version"]] for row in packages
        )))
        identity_code = (
            "import json;from compiler_core.backend_router import backend_profile_digest_v4;"
            "from compiler_core.mcp import tool_spec_digest;"
            "from compiler_core.production_runtime import _algorithm_profile_digest;"
            "print(json.dumps({'tool_spec_digest':str(tool_spec_digest()),"
            "'algorithm_profile_digest':str(_algorithm_profile_digest()),"
            "'backend_profile_digest':str(backend_profile_digest_v4(solver_deadline_ms=2500))},"
            "sort_keys=True))"
        )
        installed_identity = json.loads(_run(
            [str(python), "-I", "-B", "-c", identity_code], cwd=runtime_dir, env=env,
        ).stdout)
        storage = {
            "schema_version": "jc/local-storage-capability/1.0",
            "scope": "local-windows-efs-pipl-articles-13-18",
            "encrypted": True,
            "quota_bytes": 268435456,
        }
        storage_path = config_dir / "storage-capability.json"
        storage_path.write_bytes(canonical_bytes(storage))
        storage_ref = ContentRefV4(
            "storage-capability", DigestV4.from_bytes(storage_path.read_bytes())
        )
        runtime_config = {
            "schema_version": "jc/production-runtime/1.0",
            "pack_path": str((state_root / "packs/cn-official-local-4.0.0.json").resolve()),
            "trust_path": str((state_root / "trust/cn-official-local.json").resolve()),
            "service_key_path": str((state_root / "identity/service-runtime.json").resolve()),
            "state_root": str((state_root / "runtime-state").resolve()),
            "quota_bytes": 268435456,
            "engine_source_commit": source_commit,
            "wheel_digest": wheel_digest,
            "package_digest": package_digest,
            "lock_digest": lock_digest,
            "tool_spec_digest": installed_identity["tool_spec_digest"],
            "algorithm_profile_digest": installed_identity["algorithm_profile_digest"],
            "backend_profile_digest": installed_identity["backend_profile_digest"],
            "storage_capability_ref": storage_ref.to_dict(),
        }
        runtime_config_path = config_dir / "runtime-config.json"
        runtime_config_path.write_bytes(canonical_bytes(runtime_config))
        runtime_env = {
            **env,
            "JC_RUNTIME_FACTORY": "compiler_core.production_runtime",
            "JC_PRODUCTION_CONFIG": str(runtime_config_path.resolve()),
        }
        capability_code = (
            "import json;from compiler_core.client import runtime_client;"
            "from compiler_core.canonical_serialization import canonical_bytes;"
            "from compiler_core.mcp import runtime_tools_list;"
            "print(canonical_bytes({'capabilities':runtime_client().capabilities().to_dict(),"
            "'tools':runtime_tools_list()}).decode())"
        )
        publication = json.loads(_run(
            [str(python), "-I", "-B", "-c", capability_code], cwd=runtime_dir,
            env=runtime_env, timeout=180,
        ).stdout)
        pins = {field: publication["capabilities"][field] for field in PROFILE_PIN_FIELDS}
        profile = {
            "schema_version": "jc/formal-profile/1.0", "profile_id": release_id,
            "production": True, "loaded_by_default": False,
            "python": str(python.resolve()), "module": "mcp_server",
            "cwd": str(runtime_dir.resolve()),
            "environment": {
                "JC_RUNTIME_FACTORY": "compiler_core.production_runtime",
                "JC_PRODUCTION_CONFIG": str(runtime_config_path.resolve()),
            },
            "allowed_tools": [
                "jc_capabilities", "jc_evaluate", "jc_verify_run", "jc_read_artifact",
            ],
            "tools_list_digest": str(DigestV4.from_bytes(canonical_bytes(publication["tools"]))),
            "capability_pins": pins, "page_bytes": 65536,
            "startup_timeout_seconds": 30, "tool_timeout_seconds": 120,
        }
        profile_path = config_dir / "formal-profile.json"
        profile_path.write_bytes(canonical_bytes(profile))
        sbom = {
            "schema_version": "jc/local-production-sbom/1.0",
            "release_id": release_id,
            "packages": sorted(packages, key=lambda row: row["name"].casefold()),
        }
        sbom_path = artifacts / "sbom.json"
        sbom_path.write_bytes(canonical_bytes(sbom))
        provenance = {
            "schema_version": "jc/local-production-provenance/1.0",
            "release_id": release_id, "source_commit": source_commit,
            "source_tree": source_tree, "source_date_epoch": source_epoch,
            "wheel_digest": wheel_digest, "reproducible_build": True,
            "build_report_digests": [
                str(DigestV4.from_bytes(canonical_bytes(report))) for report in reports
            ],
            "scope": "local-windows-efs-pipl-articles-13-18",
            "remote_release_claimed": False,
        }
        provenance_path = artifacts / "provenance.json"
        provenance_path.write_bytes(canonical_bytes(provenance))
        efs_path = artifacts / "efs.json"
        efs_path.write_bytes(canonical_bytes(efs))
        checksum_targets = (wheel, sbom_path, provenance_path, efs_path,
                            runtime_config_path, profile_path, storage_path)
        checksums = {
            "schema_version": "jc/local-production-checksums/1.0",
            "files": {path.name: _sha256(path) for path in checksum_targets},
        }
        checksums_path = artifacts / "checksums.json"
        checksums_path.write_bytes(canonical_bytes(checksums))
        manifest = {
            "schema_version": "jc/local-production-release/1.0",
            "release_id": release_id, "status": "PREPARED",
            "scope": "local-windows-efs-pipl-articles-13-18",
            "source_commit": source_commit, "source_tree": source_tree,
            "wheel_path": str(wheel.resolve()), "wheel_digest": wheel_digest,
            "lock_digest": lock_digest, "package_digest": package_digest,
            "runtime_config_path": str(runtime_config_path.resolve()),
            "runtime_config_digest": _sha256(runtime_config_path),
            "profile_path": str(profile_path.resolve()),
            "profile_digest": _sha256(profile_path),
            "checksums_path": str(checksums_path.resolve()),
            "checksums_digest": _sha256(checksums_path),
            "venv_python": str(python.resolve()),
            "reproducible_build": True, "installed_origin_verified": True,
            "efs": efs, "activated": False,
        }
        manifest_path = release / "release.json"
        manifest_path.write_bytes(canonical_bytes(manifest))
        pointer = {
            "schema_version": "jc/local-production-prepared/1.0",
            "release_id": release_id, "manifest_path": str(manifest_path.resolve()),
            "manifest_digest": _sha256(manifest_path),
        }
        pointer_path = deployment / "prepared.json"
        pointer_path.write_bytes(canonical_bytes(pointer))
    after = _pointer_bytes(state_root)
    for name in ("current.json", "previous.json", "profile-registry.json"):
        if before[name] != after[name]:
            raise ValueError(f"prepare changed inactive pointer {name}")
    return manifest


_INSTALLED_CASE_CODE = r"""
import base64
import json
import pathlib
import sys
from compiler_core.canonical_serialization import DigestV4, canonical_bytes
from compiler_core.client import runtime_client
from compiler_core.contracts import CaseInputBundleV4, DecisionStatusV4, MCPEvaluateInputV4

try:
    bundle = CaseInputBundleV4.from_json_bytes(pathlib.Path(sys.argv[1]).read_bytes())
    client = runtime_client()
    evaluated = client.evaluate_for_mcp(MCPEvaluateInputV4(bundle))
    row = {
        "decision_status": evaluated.result.decision_status.value,
        "execution_status": evaluated.result.execution_status.value,
        "certificate_kind": evaluated.result.certificate_kind.value,
        "run_identity_ref": evaluated.result.run_identity_ref.to_dict(),
        "result_digest": str(evaluated.result.result_digest),
    }
    if evaluated.result.decision_status is DecisionStatusV4.ACCEPTED_FORMAL_RESULT:
        verified = client.verify_for_mcp(evaluated.run_handle, offline_replay=True)
        if (
            verified.verification.status != "VERIFIED"
            or verified.replay is None
            or verified.replay.status != "MATCH"
            or verified.replay.semantic_equal is not True
        ):
            raise RuntimeError("installed verification or replay failed")
        read_rows = []
        for handle in (evaluated.certificate_handle, evaluated.run_handle, *evaluated.artifact_handles):
            content = bytearray()
            offset = 0
            while offset < handle.size_bytes:
                page = client.read_artifact(
                    handle, offset=offset, length=min(65536, handle.size_bytes - offset)
                )
                chunk = base64.b64decode(page.content_base64, validate=True)
                if page.offset != offset or page.chunk_digest != DigestV4.from_bytes(chunk):
                    raise RuntimeError("installed artifact page binding failed")
                content.extend(chunk)
                offset += len(chunk)
            if DigestV4.from_bytes(content) != handle.content_ref.digest:
                raise RuntimeError("installed artifact digest failed")
            read_rows.append({
                "handle": handle.to_dict(),
                "bytes_digest": str(DigestV4.from_bytes(content)),
                "bytes_read": len(content),
            })
        row.update({
            "certificate_handle": evaluated.certificate_handle.to_dict(),
            "run_handle": evaluated.run_handle.to_dict(),
            "artifact_handles": [item.to_dict() for item in evaluated.artifact_handles],
            "verification": verified.verification.to_dict(),
            "replay": verified.replay.to_dict(),
            "reads": read_rows,
        })
except Exception as exc:
    row = {
        "error_code": getattr(exc, "code", type(exc).__name__),
        "error_stage": getattr(exc, "stage", "runtime"),
    }
print(canonical_bytes(row).decode("utf-8"))
"""


def _release_from_pointer(release_file: Path) -> tuple[dict[str, object], Path]:
    pointer = parse_json_document(release_file.read_bytes())
    if type(pointer) is not dict or release_file.read_bytes() != canonical_bytes(pointer):
        raise ValueError("release pointer is not canonical")
    manifest_path = Path(str(pointer["manifest_path"])).resolve()
    manifest = parse_json_document(manifest_path.read_bytes())
    if (
        type(manifest) is not dict
        or manifest_path.read_bytes() != canonical_bytes(manifest)
        or pointer["manifest_digest"] != _sha256(manifest_path)
        or pointer["release_id"] != manifest["release_id"]
    ):
        raise ValueError("release pointer does not bind its manifest")
    return manifest, manifest_path


def _atomic_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    with temporary.open("wb") as stream:
        stream.write(canonical_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _installed_case(
    manifest: dict[str, object], bundle_path: Path,
) -> dict[str, object]:
    python = Path(str(manifest["venv_python"]))
    runtime = Path(str(manifest["runtime_config_path"])).parent.parent / "runtime"
    environment = {
        **_clean_environment(),
        "JC_RUNTIME_FACTORY": "compiler_core.production_runtime",
        "JC_PRODUCTION_CONFIG": str(manifest["runtime_config_path"]),
    }
    completed = _run(
        [str(python), "-I", "-B", "-c", _INSTALLED_CASE_CODE, str(bundle_path)],
        cwd=runtime, env=environment, timeout=300,
    )
    return json.loads(completed.stdout)


def verify_release(state_root: Path, release_file: Path) -> dict[str, object]:
    """Run real smoke bundles in the installed release without activating it."""

    prepared = prepare_release(state_root)
    manifest, manifest_path = _release_from_pointer(release_file)
    if prepared["release_id"] != manifest["release_id"]:
        raise ValueError("prepared release changed during verification")
    evidence = manifest_path.parent / "evidence"
    smoke = evidence / "smoke-bundles"
    smoke.mkdir(parents=True, exist_ok=True)

    # The fixture builder owns only no-personal-information test material; evaluation
    # remains entirely inside the installed wheel and its production composition root.
    from tests.formal_e2e.test_local_production_chain import production_bundle

    positives: list[dict[str, object]] = []
    for article in range(13, 19):
        path = smoke / f"article-{article}-positive.json"
        path.write_bytes(production_bundle(article).canonical_bytes())
        row = _installed_case(manifest, path)
        if (
            row.get("decision_status") != "accepted_formal_result"
            or row.get("certificate_kind") != "formal_verified"
            or row.get("verification", {}).get("status") != "VERIFIED"
            or row.get("replay", {}).get("status") != "MATCH"
        ):
            raise ValueError(f"PIPL article {article} installed chain failed")
        positives.append({"article": article, **row})

    matrix_inputs = {
        "missing": production_bundle(15, fact_key="pipl.unrelated.fact"),
        "review": production_bundle(15, dispute_state="DISPUTED"),
        "hypothetical": production_bundle(15, assumption_state="USER_ASSUMED"),
    }
    expected = {
        "missing": "missing_required_fact",
        "review": "review_only_result",
        "hypothetical": "hypothetical_result",
    }
    matrix: dict[str, dict[str, object]] = {}
    for name, bundle in matrix_inputs.items():
        path = smoke / f"{name}.json"
        path.write_bytes(bundle.canonical_bytes())
        row = _installed_case(manifest, path)
        if row.get("decision_status") != expected[name]:
            raise ValueError(f"installed {name} state differs")
        matrix[name] = row

    tampered = production_bundle(15).to_dict()
    artifact = next(
        item for item in tampered["artifacts"] if item["artifact_kind"] == "fact-attestation"
    )
    encoded = bytearray(b64decode(artifact["content_base64"], validate=True))
    encoded[-1] ^= 1
    artifact["content_base64"] = b64encode(encoded).decode("ascii")
    body = {key: value for key, value in tampered.items() if key != "bundle_digest"}
    tampered["bundle_digest"] = str(digest_value(body))
    tamper_path = smoke / "wrong-fact-signature.json"
    tamper_path.write_bytes(canonical_bytes(tampered))
    tamper_result = _installed_case(manifest, tamper_path)
    if "error_code" not in tamper_result and tamper_result.get("decision_status") not in {
        "blocked", "engine_error",
    }:
        raise ValueError("wrong fact signature did not fail closed")
    matrix["wrong_fact_signature"] = tamper_result

    profile = parse_json_document(Path(str(manifest["profile_path"])).read_bytes())
    registry = {
        "schema_version": "jc/formal-profile-registry/1.0",
        "active_profile": manifest["release_id"],
        "profiles": {manifest["release_id"]: profile},
    }
    registry_path = evidence / "preactivation-profile-registry.json"
    registry_path.write_bytes(canonical_bytes(registry))
    bridge = Path(str(manifest["venv_python"])).with_name(
        "jc-formal.exe" if os.name == "nt" else "jc-formal"
    )
    bridge_output = json.loads(_run(
        [str(bridge), "--registry", str(registry_path), "--input",
         str(smoke / "article-15-positive.json")],
        cwd=manifest_path.parent / "runtime", env=_clean_environment(), timeout=300,
    ).stdout)
    if bridge_output.get("marker") != "JC_FORMAL_VERIFIED":
        raise ValueError("installed formal bridge did not deliver verified bytes")

    report = {
        "schema_version": "jc/local-production-positive-chain/1.0",
        "release_id": manifest["release_id"],
        "source_commit": manifest["source_commit"],
        "scope": manifest["scope"],
        "installed_origin_verified": True,
        "positive_runs": positives,
        "state_matrix": matrix,
        "formal_bridge": bridge_output,
    }
    report["report_digest"] = str(digest_value(report))
    report_path = evidence / "positive-chain.json"
    report_path.write_bytes(canonical_bytes(report))
    return report


def activate_release(state_root: Path, release_file: Path) -> dict[str, object]:
    """Atomically publish a verified release and its sole formal profile."""

    manifest, manifest_path = _release_from_pointer(release_file)
    evidence_path = manifest_path.parent / "evidence/positive-chain.json"
    evidence = parse_json_document(evidence_path.read_bytes())
    if (
        type(evidence) is not dict
        or evidence_path.read_bytes() != canonical_bytes(evidence)
        or evidence.get("release_id") != manifest["release_id"]
        or len(evidence.get("positive_runs", [])) != 6
    ):
        raise ValueError("release lacks exact positive verification evidence")
    profile = parse_json_document(Path(str(manifest["profile_path"])).read_bytes())
    deployment = state_root.resolve() / "deployment"
    current_path = deployment / "current.json"
    previous_path = deployment / "previous.json"
    registry_path = deployment / "profile-registry.json"
    existing = _pointer_bytes(state_root.resolve())
    if existing["current.json"] is not None:
        old = parse_json_document(existing["current.json"])
        if old.get("release_id") == manifest["release_id"]:
            return old
        previous = {
            "schema_version": "jc/local-production-previous/1.0",
            "production_rollback_allowed": True,
            "current": old,
        }
    else:
        previous = {
            "schema_version": "jc/local-production-previous/1.0",
            "production_rollback_allowed": False,
            "reason": "legacy_shell_only_deployment_has_no_runtime_verification",
        }
    activated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    current = {
        "schema_version": "jc/local-production-current/1.0",
        "status": "LOCAL_PRODUCTION_ACTIVE",
        "scope": manifest["scope"],
        "release_id": manifest["release_id"],
        "manifest_path": str(manifest_path),
        "manifest_digest": _sha256(manifest_path),
        "verification_path": str(evidence_path),
        "verification_digest": _sha256(evidence_path),
        "activated_at": activated_at,
    }
    registry = {
        "schema_version": "jc/formal-profile-registry/1.0",
        "active_profile": manifest["release_id"],
        "profiles": {manifest["release_id"]: profile},
    }
    try:
        _atomic_write(previous_path, previous)
        _atomic_write(current_path, current)
        _atomic_write(registry_path, registry)
        from compiler_core.formal_bridge import load_active_profile
        if load_active_profile(registry_path).profile_id != manifest["release_id"]:
            raise ValueError("activated profile identity differs")
    except Exception:
        for name, path in (
            ("current.json", current_path), ("previous.json", previous_path),
            ("profile-registry.json", registry_path),
        ):
            raw = existing[name]
            if raw is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_bytes(raw)
        raise
    return current


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init_key = commands.add_parser("init-service-key")
    init_key.add_argument("--root", type=Path, required=True)
    init_key.add_argument("--output", type=Path, required=True)
    init_key.add_argument("--trust", type=Path, required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--state-root", type=Path, required=True)
    for name in ("verify", "activate"):
        command = commands.add_parser(name)
        command.add_argument("--state-root", type=Path, required=True)
        command.add_argument("--release-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init-service-key":
            initialize_service_key(args.root, args.output, args.trust)
        elif args.command == "prepare":
            result = prepare_release(args.state_root)
            print(json.dumps({
                "release_id": result["release_id"], "status": result["status"],
                "wheel_digest": result["wheel_digest"],
            }, sort_keys=True))
        elif args.command == "verify":
            result = verify_release(args.state_root, args.release_file)
            print(json.dumps({
                "release_id": result["release_id"], "status": "POSITIVE_VERIFIED",
                "positive_runs": len(result["positive_runs"]),
            }, sort_keys=True))
        elif args.command == "activate":
            result = activate_release(args.state_root, args.release_file)
            print(json.dumps({
                "release_id": result["release_id"], "status": result["status"],
            }, sort_keys=True))
    except (OSError, TypeError, ValueError) as exc:
        print(f"local production failed: {exc}", file=sys.stderr)
        return 1
    print(f"local production {args.command} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
