"""Executable contract for the exact current CI and release lanes."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.supply_chain_gate import parse_lock


ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github/workflows/ci.yml"
ACTION_PIN = re.compile(r"^[^@]+@[0-9a-f]{40}$")
EXPECTED_LANES = [
    {"os": "ubuntu-latest", "python": "3.11"},
    {"os": "ubuntu-latest", "python": "3.12"},
    {"os": "windows-latest", "python": "3.11"},
    {"os": "windows-latest", "python": "3.12"},
]


def _document(text: str | None = None) -> dict[str, Any]:
    return yaml.load(CI.read_text(encoding="utf-8") if text is None else text, Loader=yaml.BaseLoader)


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return job.get("steps", [])


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(step.get("run", "") for step in _steps(job))


def _ci_problems(text: str) -> list[str]:
    document = _document(text)
    jobs = document.get("jobs", {})
    problems: list[str] = []
    required = jobs.get("required", {})
    lanes = required.get("strategy", {}).get("matrix", {}).get("include", [])
    if lanes != EXPECTED_LANES:
        problems.append("matrix")
    if "legal-math-modeling" in text or "requirements/dev.lock" in text:
        problems.append("external-or-retired")
    uses = [step["uses"] for job in jobs.values() for step in _steps(job) if "uses" in step]
    if not uses or any(ACTION_PIN.fullmatch(value) is None for value in uses):
        problems.append("action-pin")
    required_runs = _runs(required)
    package_runs = _runs(jobs.get("package", {}))
    if "run --through V4-03-OFFICIAL-YAML" not in required_runs:
        problems.append("required")
    if "--installed-wheel" not in package_runs or "cmp work/dist-a/*.whl" not in package_runs:
        problems.append("package")
    provenance_markers = (
        "build_provenance.py create", "build_provenance.py verify", "--rebuild-wheel",
        "--source-commit", "--sbom-output", "--checksums-output",
        "--release-candidate", "--allow-test-key",
    )
    if any(marker not in package_runs for marker in provenance_markers):
        problems.append("release-provenance")
    return problems


def test_required_matrix_is_exact_four_lanes_and_self_contained() -> None:
    text = CI.read_text(encoding="utf-8")
    document = _document(text)
    assert _ci_problems(text) == []
    assert document["jobs"]["required"]["strategy"]["fail-fast"] == "false"
    assert "LEGAL_MATH_MODELING_ROOT" not in text
    assert "Checkout pinned specification" not in text


def test_ci_uses_only_pinned_actions_and_hash_locked_installs() -> None:
    document = _document()
    steps = [step for job in document["jobs"].values() for step in _steps(job)]
    uses = [step["uses"] for step in steps if "uses" in step]
    installs = [line.strip() for step in steps for line in step.get("run", "").splitlines() if "pip install" in line]
    required_runs = _runs(document["jobs"]["required"])

    assert uses and all(ACTION_PIN.fullmatch(value) for value in uses)
    assert installs and all("--require-hashes" in line and "requirements/" in line for line in installs)
    assert "requirements/build.lock" in required_runs
    assert "requirements/test.lock" in required_runs
    assert "requirements/dev.lock" not in CI.read_text(encoding="utf-8")


def test_ci_covers_required_suites_and_platform_subsets() -> None:
    required = _document()["jobs"]["required"]
    names = {step["name"] for step in _steps(required)}
    runs = _runs(required)
    assert "Required current suites" in names
    assert "Ubuntu storage and chaos subset" in names
    assert "Windows DACL and reparse subset" in names
    assert "run --through V4-03-OFFICIAL-YAML" in runs
    assert "tests/storage_chaos" in runs and "tests/windows_security" in runs
    assert "tests/contract tests/differential tests/dsh_formal" not in runs


def test_ci_static_lane_covers_generated_authority_purity_secrets_lint_type_unit() -> None:
    static = _document()["jobs"]["static"]
    names = {step["name"] for step in _steps(static)}
    runs = _runs(static)
    assert {
        "Generated publications are current",
        "Git and AST authority",
        "Current authority and docs",
        "Purity and committed-secret policy",
        "Ruff fatal-error gate on current paths",
        "Mypy release and CI surfaces",
        "Current unit gates",
        "Lock hash license and vulnerability audit",
    } <= names
    assert "python -m ruff check" in runs and "python -m mypy" in runs
    assert "--all-profiles" in runs
    assert "checks.py generated" in runs and "build_file_disposition.py --check" in runs
    assert "observed_graph.py" in runs and "checks.py cleanup" in runs
    assert "verify-wave" not in runs and "file-map" not in runs


def test_ci_release_lane_covers_ab_build_installed_sbom_provenance_perf_docs() -> None:
    package = _document()["jobs"]["package"]
    names = {step["name"] for step in _steps(package)}
    runs = _runs(package)
    assert {
        "Two clean source archives and byte-identical wheels",
        "Repository-outside installed production suites",
        "Installed official YAML admission",
        "CycloneDX SBOM",
        "Build provenance",
        "Performance gate",
        "Current documentation paths",
    } <= names
    assert runs.count("git archive --format=tar HEAD") == 2
    assert "cmp work/dist-a/*.whl work/dist-b/*.whl" in runs
    assert "--installed-wheel" in runs and "--format cyclonedx-json" in runs
    assert "build_provenance.py create" in runs and "build_provenance.py verify" in runs
    assert "--rebuild-wheel" in runs and "--release-candidate" in runs
    assert "--sbom-output" in runs and "--checksums-output" in runs
    assert "--allow-test-key" in runs
    assert "test_resource_limits.py" in runs
    assert "checks.py wheel --out-dir work/official-wheel" in runs


def test_release_lock_contains_hash_pinned_ruff_mypy_graph() -> None:
    parsed = parse_lock(ROOT / "requirements/release.lock")
    packages = parsed["packages"]
    assert parsed["profile"] == "release"
    assert {"ruff", "mypy", "mypy-extensions", "pathspec"} <= set(packages)
    assert {name for name, row in packages.items() if row["role"] == "direct"} == {
        "build", "setuptools", "wheel", "pip-audit", "ruff", "mypy",
    }
    assert all(row["hashes"] for row in packages.values())


def test_committed_private_key_is_test_only_and_unique() -> None:
    path = ROOT / "tests/fixtures/keys/v4-test-ed25519.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    private_bytes = base64.b64decode(fixture["private_key_base64"], validate=True)
    public_bytes = base64.b64decode(fixture["public_key_base64"], validate=True)
    key = Ed25519PrivateKey.from_private_bytes(private_bytes)

    assert fixture["scope"] == "test-only" and fixture["production_allowed"] is False
    assert fixture["private_key_sha256"] == "sha256:" + hashlib.sha256(private_bytes).hexdigest()
    assert key.public_key().public_bytes_raw() == public_bytes
    payload = b"juris-calculus-v4-test-only"
    key.public_key().verify(key.sign(payload), payload)

    tracked = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    for encoded in tracked:
        if not encoded or encoded.decode("utf-8") == path.relative_to(ROOT).as_posix():
            continue
        raw = (ROOT / encoded.decode("utf-8")).read_bytes()
        assert private_bytes not in raw
        assert fixture["private_key_base64"].encode("ascii") not in raw


def test_ci_contract_mutations_fail_closed() -> None:
    baseline = CI.read_text(encoding="utf-8")
    mutations = (
        baseline.replace('          - os: windows-latest\n            python: "3.11"\n', "", 1),
        baseline.replace("Checkout exact source", "Checkout legal-math-modeling", 1),
        baseline.replace("actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5", "actions/checkout@v4", 1),
        baseline.replace("requirements/test.lock", "requirements/dev.lock", 1),
        baseline.replace("--installed-wheel", "--source-wheel", 1),
    )
    assert all(_ci_problems(mutated) for mutated in mutations)
