"""Fail-closed hash-lock, license, wheel-metadata, and vulnerability gate."""

from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import json
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any, Callable


EXIT_CODES = {"PASS": 0, "FAIL": 1, "BLOCKED": 2}
PROFILE_FILES = {
    "production": "core.lock",
    "build": "build.lock",
    "test": "test.lock",
    "source-tool": "source-tool.lock",
    "release": "release.lock",
}
PROFILE_COUNTS = {"production": 4, "build": 6, "test": 18, "source-tool": 16, "release": 38}
PROFILE_DIRECT = {
    "production": {"pyyaml", "cryptography"},
    "build": {"build", "setuptools", "wheel"},
    "test": {"pyyaml", "cryptography", "hypothesis", "jsonschema", "pytest"},
    "source-tool": {"pyyaml", "cryptography", "pydantic", "python-docx", "pdfplumber"},
    "release": {"build", "setuptools", "wheel", "pip-audit", "ruff", "mypy"},
}
# Bound to the independently resolved CPython 3.11/3.12 Windows/Linux wheel inventory.
PROFILE_DIGESTS = {
    "production": "sha256:38c31bd070b4e9b5cfe0ace8723bb3fc08c25deb724d18a9ac7b2d3b1d8b0ba1",
    "build": "sha256:58a1991e555e12cbb69b178f70c6e8b4dddefb58ec4430777330f7c08d2c54ba",
    "test": "sha256:edfc366bf7559b20a80eb05d30e442a4a1aeaf7ca2b66a117eaae9591cf1a60b",
    "source-tool": "sha256:bade5d3e8b6f5df6c24b56ee54d9fb290d0e55e4838cfc76b674bf93a5a5df48",
    "release": "sha256:d4123c89c77e1b73e17206177ab69345f47e5620cc737bab5fcd69c64a568304",
}
ALLOWED_LICENSES = {
    "Apache-2.0", "Apache-2.0 OR BSD-2-Clause", "Apache-2.0 OR BSD-3-Clause",
    "BSD-2-Clause", "BSD-3-Clause", "BSD-3-Clause OR Apache-2.0", "MIT",
    "MIT-0", "MIT-CMU", "MPL-2.0", "PSF-2.0",
}
LICENSE_ALIASES = {
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Apache 2.0": "Apache-2.0",
    "PSFL": "PSF-2.0",
    "BSD-3-Clause, Apache-2.0, dependency licenses": "BSD-3-Clause OR Apache-2.0",
}
TARGETS = {
    "win311": {"python_version": "3.11", "python_full_version": "3.11.0", "sys_platform": "win32", "platform_system": "Windows", "os_name": "nt", "platform_machine": "AMD64"},
    "win312": {"python_version": "3.12", "python_full_version": "3.12.0", "sys_platform": "win32", "platform_system": "Windows", "os_name": "nt", "platform_machine": "AMD64"},
    "linux311": {"python_version": "3.11", "python_full_version": "3.11.0", "sys_platform": "linux", "platform_system": "Linux", "os_name": "posix", "platform_machine": "x86_64"},
    "linux312": {"python_version": "3.12", "python_full_version": "3.12.0", "sys_platform": "linux", "platform_system": "Linux", "os_name": "posix", "platform_machine": "x86_64"},
}
HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})(?=\s|$)")
REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")


def canonicalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def parse_lock(path: str | Path) -> dict[str, Any]:
    """Parse the strict annotated lock grammar; reject every unbound token."""

    lines = Path(path).read_text(encoding="utf-8").splitlines()
    profile: str | None = None
    annotations: dict[str, str] = {}
    packages: dict[str, dict[str, Any]] = {}
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("# "):
            key, separator, value = line[2:].partition(": ")
            if separator and key in {"profile", "package", "role", "license"}:
                if key == "profile":
                    if profile is not None:
                        raise ValueError(f"{path}: duplicate profile header")
                    profile = value
                else:
                    annotations[key] = value
            index += 1
            continue
        block = [lines[index].strip()]
        while block[-1].endswith("\\"):
            index += 1
            if index >= len(lines):
                raise ValueError(f"{path}: unterminated requirement continuation")
            block.append(lines[index].strip())
        joined = " ".join(part[:-1].strip() if part.endswith("\\") else part for part in block)
        match = REQUIREMENT_RE.match(joined)
        if match is None:
            raise ValueError(f"{path}: invalid requirement: {joined}")
        raw_name, version = match.groups()
        name = canonicalize_name(raw_name)
        hashes = HASH_RE.findall(joined)
        remainder = HASH_RE.sub("", joined[match.end():]).strip()
        if remainder or not hashes or len(hashes) != len(set(hashes)):
            raise ValueError(f"{path}: {name} must contain only unique sha256 hashes")
        if set(annotations) != {"package", "role", "license"}:
            raise ValueError(f"{path}: {name} lacks package/role/license annotations")
        if canonicalize_name(annotations["package"]) != name:
            raise ValueError(f"{path}: package annotation does not bind {name}")
        if annotations["role"] not in {"direct", "transitive"}:
            raise ValueError(f"{path}: invalid role for {name}")
        if name in packages:
            raise ValueError(f"{path}: duplicate package {name}")
        packages[name] = {
            "name": name,
            "version": version,
            "role": annotations["role"],
            "license": annotations["license"],
            "hashes": sorted(hashes),
        }
        annotations = {}
        index += 1
    if profile is None or annotations:
        raise ValueError(f"{path}: incomplete profile or dangling annotation")
    return {"profile": profile, "packages": packages}


def profile_digest(parsed: dict[str, Any]) -> str:
    return _canonical_digest([parsed["packages"][name] for name in sorted(parsed["packages"])])


def verify_lock_profiles(
    lock_root: str | Path = "requirements", pyproject_path: str | Path = "pyproject.toml"
) -> dict[str, Any]:
    """Verify the five exact profiles, every pin/hash/license, and distribution split."""

    root = Path(lock_root)
    problems: list[str] = []
    observed_files = {path.name for path in root.glob("*.lock")}
    expected_files = set(PROFILE_FILES.values())
    if observed_files != expected_files:
        problems.append(f"lock file set drifted: {sorted(observed_files)} != {sorted(expected_files)}")
    profiles: dict[str, Any] = {}
    for profile, filename in PROFILE_FILES.items():
        try:
            parsed = parse_lock(root / filename)
        except (OSError, UnicodeError, ValueError) as exc:
            problems.append(str(exc))
            continue
        profiles[profile] = parsed
        packages = parsed["packages"]
        direct = {name for name, row in packages.items() if row["role"] == "direct"}
        if parsed["profile"] != profile:
            problems.append(f"{filename}: profile header drifted")
        if len(packages) != PROFILE_COUNTS[profile]:
            problems.append(f"{profile}: package count drifted")
        if direct != PROFILE_DIRECT[profile]:
            problems.append(f"{profile}: direct dependency set drifted")
        digest = profile_digest(parsed)
        if digest != PROFILE_DIGESTS[profile]:
            problems.append(f"{profile}: full pin/hash/license manifest digest drifted")
        denied = sorted({row["license"] for row in packages.values()} - ALLOWED_LICENSES)
        if denied:
            problems.append(f"{profile}: denied or unknown licenses: {denied}")
    if len(profiles) == len(PROFILE_FILES):
        names = {profile: set(parsed["packages"]) for profile, parsed in profiles.items()}
        if names["production"] != {"pyyaml", "cryptography", "cffi", "pycparser"}:
            problems.append("production: runtime graph is not the exact four-package core")
        if not {"pydantic", "python-docx", "pdfplumber"} <= names["source-tool"]:
            problems.append("source-tool: pipeline dependency ownership drifted")
        if "hypothesis" not in names["test"]:
            problems.append("test: Hypothesis ownership drifted")
        if any({"jinja2", "markupsafe"} & package_names for package_names in names.values()):
            problems.append("Jinja2/render graph must be absent from every profile")
        if names["production"] & {"pydantic", "python-docx", "pdfplumber", "hypothesis"}:
            problems.append("production: source-tool/test dependency leaked into runtime")
    try:
        project = tomllib.loads(Path(pyproject_path).read_text(encoding="utf-8"))
        if project.get("project", {}).get("dependencies") != ["PyYAML>=6.0", "cryptography==50.0.0"]:
            problems.append("pyproject: production dependency metadata drifted")
        if "optional-dependencies" in project.get("project", {}):
            problems.append("pyproject: released optional dependency profiles must be absent")
        if project.get("build-system", {}).get("requires") != ["setuptools==83.0.0", "wheel==0.47.0"]:
            problems.append("pyproject: build backend pins drifted")
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        problems.append(f"pyproject is unreadable: {exc}")
    summary = {
        profile: {
            "file": PROFILE_FILES[profile],
            "package_count": len(parsed["packages"]),
            "manifest_digest": profile_digest(parsed),
        }
        for profile, parsed in sorted(profiles.items())
    }
    return {"schema_version": "jc/supply-chain-static/1.0", "status": "PASS" if not problems else "FAIL", "profiles": summary, "problems": problems}


def _metadata_license(metadata: Any) -> str:
    raw = metadata.get("License-Expression") or metadata.get("License")
    if not raw:
        raw = ";".join(value for value in metadata.get_all("Classifier", []) if value.startswith("License ::"))
    return LICENSE_ALIASES.get(raw, raw)


def _root_metadata_names(names: list[str]) -> list[str]:
    """Select the wheel's own METADATA, excluding vendored dist-info trees."""

    return [name for name in names if name.count("/") == 1 and name.endswith(".dist-info/METADATA")]


def profile_reachability_problems(
    reports: list[dict[str, Any]], expected_packages: set[str],
) -> list[str]:
    reached = {
        name for report in reports for name in report.get("reachable_packages", [])
    }
    return [] if reached == expected_packages else [
        f"target reachability union drifted: {sorted(reached)} != {sorted(expected_packages)}"
    ]


def inspect_wheelhouse(lock: str | Path, wheelhouse: str | Path, target: str) -> dict[str, Any]:
    """Reconcile selected wheel hashes, METADATA dependency graph, and lock rows."""

    from packaging.markers import default_environment
    from packaging.requirements import Requirement

    parsed = parse_lock(lock)
    expected = parsed["packages"]
    components: dict[str, dict[str, Any]] = {}
    raw_dependencies: dict[str, list[str]] = {}
    problems: list[str] = []
    for wheel in sorted(Path(wheelhouse).glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            metadata_names = _root_metadata_names(archive.namelist())
            if len(metadata_names) != 1:
                problems.append(f"{wheel.name}: METADATA cardinality drifted")
                continue
            metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        name = canonicalize_name(metadata["Name"])
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if name in components:
            problems.append(f"{name}: wheel cardinality drifted")
            continue
        components[name] = {
            "name": name, "version": metadata["Version"], "license": _metadata_license(metadata),
            "wheel": wheel.name, "sha256": "sha256:" + digest,
        }
        raw_dependencies[name] = metadata.get_all("Requires-Dist", [])
        row = expected.get(name)
        if row is None:
            problems.append(f"{name}: wheel is not present in {parsed['profile']} lock")
        elif metadata["Version"] != row["version"] or digest not in row["hashes"]:
            problems.append(f"{name}: selected wheel version/hash drifted")
        elif _metadata_license(metadata) != row["license"]:
            problems.append(f"{name}: wheel license metadata drifted")
    if set(components) != set(expected):
        problems.append("wheelhouse package set does not equal the complete lock graph")
    environment = default_environment()
    environment.update(TARGETS[target])
    edges: set[tuple[str, str, str]] = set()
    requested_extras = {
        name: set() for name, row in expected.items() if row["role"] == "direct"
    }
    pending = list(requested_extras)
    processed: dict[str, frozenset[str]] = {}
    while pending:
        parent = pending.pop()
        extras = frozenset(requested_extras[parent])
        if processed.get(parent) == extras:
            continue
        processed[parent] = extras
        for raw in raw_dependencies.get(parent, []):
            requirement = Requirement(raw)
            marker_contexts = ["", *sorted(extras)]
            if requirement.marker and not any(
                requirement.marker.evaluate({**environment, "extra": extra})
                for extra in marker_contexts
            ):
                continue
            child = canonicalize_name(requirement.name)
            edges.add((parent, child, str(requirement.specifier)))
            child_row = expected.get(child)
            if child_row is None or not requirement.specifier.contains(child_row["version"], prereleases=True):
                problems.append(f"{parent}: active dependency {raw!r} is not reconciled by the lock")
                continue
            previous = requested_extras.setdefault(child, set())
            updated = previous | set(requirement.extras)
            if child not in processed or updated != previous:
                requested_extras[child] = updated
                pending.append(child)
    return {
        "schema_version": "jc/supply-chain-sbom/1.0", "profile": parsed["profile"],
        "target": target, "status": "PASS" if not problems else "FAIL",
        "components": [components[name] for name in sorted(components)],
        "reachable_packages": sorted(requested_extras),
        "dependencies": [
            {"from": parent, "to": child, "specifier": specifier}
            for parent, child, specifier in sorted(edges)
        ],
        "problems": problems,
    }


def _summarize_stderr(stderr: str, limit: int = 500) -> str:
    summary = " ".join(stderr.split())
    return summary if len(summary) <= limit else summary[: limit - 3] + "..."


def _vulnerability_count(stdout: str) -> int | None:
    try:
        payload: Any = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    dependencies = payload.get("dependencies") if isinstance(payload, dict) else payload
    if not isinstance(dependencies, list):
        return None
    count = 0
    for dependency in dependencies:
        if not isinstance(dependency, dict) or not isinstance(dependency.get("vulns"), list):
            return None
        count += len(dependency["vulns"])
    return count


def _blocked_reason(stderr: str) -> str:
    normalized = stderr.lower()
    if "proxy" in normalized:
        return "proxy_error"
    if any(marker in normalized for marker in ("ssl", "tls", "certificate_verify_failed")):
        return "tls_error"
    return "audit_error"


def run_supply_chain_gate(
    requirements: str | Path = "requirements/core.lock",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    command = [
        sys.executable, "-m", "pip_audit", "--requirement", str(requirements),
        "--format", "json", "--progress-spinner", "off", "--strict", "--disable-pip",
    ]
    try:
        completed = runner(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return {"command": command, "status": "BLOCKED", "return_code": None, "stderr_summary": _summarize_stderr(str(exc)), "vulnerability_count": None, "reason": "execution_error"}
    vulnerability_count = _vulnerability_count(completed.stdout)
    blocked_reason = _blocked_reason(completed.stderr)
    reason = blocked_reason if blocked_reason != "audit_error" else ("invalid_output" if vulnerability_count is None else "audit_error")
    report = {"command": command, "status": "BLOCKED", "return_code": completed.returncode, "stderr_summary": _summarize_stderr(completed.stderr), "vulnerability_count": vulnerability_count, "reason": reason}
    if completed.returncode == 0 and vulnerability_count == 0:
        report.update(status="PASS", reason="no_vulnerabilities")
    elif completed.returncode == 1 and vulnerability_count and vulnerability_count > 0:
        report.update(status="FAIL", reason="vulnerabilities_found")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", default="requirements/core.lock")
    parser.add_argument("--lock-root", default="requirements")
    parser.add_argument("--pyproject", default="pyproject.toml")
    parser.add_argument("--all-profiles", action="store_true")
    parser.add_argument("--skip-audit", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.all_profiles:
        static = verify_lock_profiles(args.lock_root, args.pyproject)
        audits = {} if args.skip_audit else {
            profile: run_supply_chain_gate(Path(args.lock_root) / filename)
            for profile, filename in PROFILE_FILES.items()
        }
        status = "PASS" if static["status"] == "PASS" and all(row["status"] == "PASS" for row in audits.values()) else "FAIL"
        report: dict[str, Any] = {"schema_version": "jc/supply-chain-gate/1.0", "status": status, "static": static, "audits": audits}
    else:
        report = run_supply_chain_gate(args.requirements)
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
