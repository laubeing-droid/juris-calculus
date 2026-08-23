#!/usr/bin/env python3
"""Build and validate the exact formal-only wheel from a clean source archive."""

from __future__ import annotations

import argparse
import base64
import configparser
import csv
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile


PRODUCTION_CLASSES = frozenset({"FORMAL_CORE", "PUBLIC_ADAPTER", "RUNTIME_OUTPUT"})
EXPLICIT_RESOURCE_PATHS = frozenset({
    "configs/__init__.py",
    "configs/render_profiles/neutral.yaml",
    "schemas/jc-v4.schema.json",
})
BUILD_INPUT_PATHS = ("pyproject.toml", "README.md", "LICENSE")
DIST_INFO_SUFFIXES = frozenset({
    "METADATA",
    "WHEEL",
    "entry_points.txt",
    "licenses/LICENSE",
    "top_level.txt",
    "RECORD",
})
REJECTED_CONTENT_MARKERS = (
    b"cn-legacy-corpus",
    b"configs/zh_CN/rules.yaml",
    b"compat_v3_v4",
    b"schemas/jc-v3.schema.json",
    b"schemas/w1b/",
    b"addons.workbuddy_mcp",
    b"DEFAULT_MANIFEST",
)
REJECTED_IMPORTS = (
    "addons",
    "pipeline",
    "compiler_core.adapter_base",
    "compiler_core.analysis",
    "compiler_core.compat_v3_v4",
    "compiler_core.contracts_v4",
    "schemas.w1b",
)
INSTALLED_HARNESS_PATHS = (
    "tests/contract/test_application.py",
    "tests/integration/test_trust_chain.py",
    "tests/formal_e2e/test_positive_vertical_slice.py",
    "tests/formal_e2e/test_three_entrypoint_error_matrix.py",
    "tests/formal_e2e/test_installed_production.py",
    "tests/security/test_vertical_slice_attacks.py",
    "tests/storage_chaos/test_vertical_slice_recovery.py",
    "tests/fixtures/keys/v4-synthetic-trust.json",
    "tests/fixtures/keys/v4-test-ed25519.json",
    "tests/fixtures/packs/synthetic/signed-pack.json",
    "tools/build_synthetic_pack.py",
    "tools/wheel_gate.py",
)
INSTALLED_TEST_SELECTORS = (
    "tests/formal_e2e/test_positive_vertical_slice.py",
    (
        "tests/formal_e2e/test_three_entrypoint_error_matrix.py::"
        "test_canonical_result_matrix_across_cli_client_and_stdio_mcp"
    ),
    (
        "tests/formal_e2e/test_three_entrypoint_error_matrix.py::"
        "test_contract_error_code_is_identical_across_entrypoints"
    ),
    (
        "tests/formal_e2e/test_three_entrypoint_error_matrix.py::"
        "test_storage_error_is_typed_retryable_redacted_and_uncommitted"
    ),
    "tests/security/test_vertical_slice_attacks.py",
    "tests/storage_chaos/test_vertical_slice_recovery.py",
    (
        "tests/formal_e2e/test_installed_production.py::"
        "test_installed_required_suites_have_zero_skip_or_xfail"
    ),
)
INSTALLED_TEST_CASE_COUNT = 27
INSTALLED_TEST_CASE_IDS_SHA256 = (
    "sha256:12c563b67fe1c06ff1f7be0114b3105394d03e747115c40592f480f91bf56708"
)


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _policy(source: Path) -> dict[str, object]:
    path = source / "docs/architecture/module-authority.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "jc/module-authority/1.0":
        raise RuntimeError("module-authority schema drifted")
    classes = document.get("classes")
    rows = document.get("path_rules")
    if not isinstance(classes, dict) or not isinstance(rows, list):
        raise RuntimeError("module-authority is malformed")
    observed = {
        name for name, row in classes.items()
        if isinstance(row, dict) and row.get("production_wheel") is True
    }
    if observed != PRODUCTION_CLASSES:
        raise RuntimeError("production class policy drifted")
    return document


def expected_payload_paths(source: Path) -> frozenset[str]:
    """Derive executable wheel paths from the sole manual authority registry."""

    source = source.resolve()
    policy = _policy(source)
    classes = policy["classes"]
    selected: set[str] = set(EXPLICIT_RESOURCE_PATHS)
    seen: set[str] = set()
    for row in policy["path_rules"]:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise RuntimeError("module-authority path rule is malformed")
        path = row["path"].replace("\\", "/")
        if path in seen:
            raise RuntimeError(f"duplicate module-authority path: {path}")
        seen.add(path)
        class_name = row.get("class")
        if class_name not in classes:
            raise RuntimeError(f"unknown module-authority class: {class_name}")
        if classes[class_name].get("production_wheel") is True:
            selected.add(path)
    for relative in sorted(selected):
        path = source / PurePosixPath(relative)
        if not path.is_file():
            raise RuntimeError(f"declared wheel input is missing: {relative}")
    return frozenset(selected)


def _copy_build_tree(source: Path, destination: Path) -> frozenset[str]:
    payload = expected_payload_paths(source)
    for relative in (*BUILD_INPUT_PATHS, *sorted(payload)):
        source_path = source / PurePosixPath(relative)
        if not source_path.is_file():
            raise RuntimeError(f"build input is missing: {relative}")
        target = destination / PurePosixPath(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)
    return payload


def _normalized_names(archive: zipfile.ZipFile) -> list[str]:
    raw = [item.filename for item in archive.infolist()]
    if len(raw) != len(set(raw)):
        raise RuntimeError("wheel contains duplicate ZIP names")
    names: list[str] = []
    for name in raw:
        path = PurePosixPath(name)
        if (
            not name or name.endswith("/") or "\\" in name or name.startswith("/")
            or ":" in name or any(part in {"", ".", ".."} for part in path.parts)
            or path.as_posix() != name
        ):
            raise RuntimeError(f"wheel contains unsafe or non-normalized name: {name!r}")
        names.append(name)
    if len({name.casefold() for name in names}) != len(names):
        raise RuntimeError("wheel contains case-colliding names")
    return names


def _dist_info_prefix(names: list[str]) -> str:
    prefixes = {name.split("/", 1)[0] for name in names if ".dist-info/" in name}
    if len(prefixes) != 1:
        raise RuntimeError("wheel must contain exactly one dist-info directory")
    prefix = prefixes.pop()
    if prefix != "juris_calculus-4.0.0rc1.dist-info":
        raise RuntimeError(f"wheel dist-info identity drifted: {prefix}")
    return prefix


def _validate_record(archive: zipfile.ZipFile, names: list[str], prefix: str) -> None:
    record_name = f"{prefix}/RECORD"
    try:
        rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
    except (KeyError, UnicodeError, csv.Error) as exc:
        raise RuntimeError("wheel RECORD is unreadable") from exc
    if any(len(row) != 3 for row in rows):
        raise RuntimeError("wheel RECORD row width drifted")
    record_names = [row[0] for row in rows]
    if len(record_names) != len(set(record_names)) or set(record_names) != set(names):
        raise RuntimeError("wheel ZIP and RECORD names differ")
    for name, digest, size_wire in rows:
        if name == record_name:
            if digest or size_wire:
                raise RuntimeError("wheel RECORD self-row must be unhashed")
            continue
        payload = archive.read(name)
        expected_digest = base64.urlsafe_b64encode(
            hashlib.sha256(payload).digest()
        ).rstrip(b"=").decode("ascii")
        if digest != f"sha256={expected_digest}" or size_wire != str(len(payload)):
            raise RuntimeError(f"wheel RECORD digest/size drifted: {name}")


def _validate_metadata(archive: zipfile.ZipFile, prefix: str, source: Path) -> None:
    document = BytesParser().parsebytes(archive.read(f"{prefix}/METADATA"))
    if (
        document.get("Name") != "juris-calculus"
        or document.get("Version") != "4.0.0rc1"
        or document.get("Requires-Python") != "<3.13,>=3.11"
    ):
        raise RuntimeError("wheel METADATA identity drifted")
    wheel = archive.read(f"{prefix}/WHEEL").decode("utf-8")
    if "Tag: py3-none-any" not in wheel or "Root-Is-Purelib: true" not in wheel:
        raise RuntimeError("wheel tag/root identity drifted")
    parser = configparser.ConfigParser()
    parser.optionxform = str
    parser.read_string(archive.read(f"{prefix}/entry_points.txt").decode("utf-8"))
    if dict(parser.items("console_scripts")) != {"jc": "compiler_core.cli:main"}:
        raise RuntimeError("wheel console entrypoint drifted")
    top_level = set(archive.read(f"{prefix}/top_level.txt").decode("utf-8").splitlines())
    if top_level != {"compiler_core", "configs", "mcp_server", "schemas"}:
        raise RuntimeError("wheel top-level package set drifted")
    if archive.read(f"{prefix}/licenses/LICENSE") != (source / "LICENSE").read_bytes():
        raise RuntimeError("wheel license bytes drifted")
    joined = b"\n".join(archive.read(name) for name in archive.namelist())
    for marker in REJECTED_CONTENT_MARKERS:
        if marker in joined:
            raise RuntimeError(f"retired production marker present: {marker.decode('ascii')}")


def validate_wheel(source: Path, wheel: Path) -> dict[str, object]:
    source = source.resolve()
    payload = expected_payload_paths(source)
    with zipfile.ZipFile(wheel) as archive:
        names = _normalized_names(archive)
        prefix = _dist_info_prefix(names)
        expected = set(payload) | {f"{prefix}/{suffix}" for suffix in DIST_INFO_SUFFIXES}
        if set(names) != expected:
            missing = sorted(expected - set(names))
            extra = sorted(set(names) - expected)
            raise RuntimeError(f"wheel file set drifted: missing={missing}; extra={extra}")
        _validate_record(archive, names, prefix)
        _validate_metadata(archive, prefix, source)
    return {
        "wheel": wheel.name,
        "size_bytes": wheel.stat().st_size,
        "sha256": "sha256:" + hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "entry_count": len(names),
        "entry_names_sha256": _canonical_digest(sorted(names)),
        "payload_count": len(payload),
        "payload_names_sha256": _canonical_digest(sorted(payload)),
    }


def _smoke_install(source: Path, wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="jc-wheel-install-") as raw:
        temporary = Path(raw)
        wheelhouse = temporary / "wheelhouse"
        wheelhouse.mkdir()
        target = temporary / "site"
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        subprocess.run(
            [
                sys.executable, "-B", "-m", "pip", "download",
                "--disable-pip-version-check", "--require-hashes",
                "--dest", str(wheelhouse), "--requirement",
                str(source / "requirements/core.lock"),
            ],
            cwd=temporary, env=environment, capture_output=True, text=True,
            check=True, timeout=300,
        )
        subprocess.run(
            [
                sys.executable, "-B", "-m", "pip", "install",
                "--disable-pip-version-check", "--no-index", "--require-hashes",
                "--find-links", str(wheelhouse), "--target", str(target),
                "--requirement", str(source / "requirements/core.lock"),
            ],
            cwd=temporary, env=environment, capture_output=True, text=True,
            check=True, timeout=300,
        )
        subprocess.run(
            [sys.executable, "-B", "-m", "pip", "install", "--no-deps",
             "--disable-pip-version-check", "--no-index", "--target", str(target),
             str(wheel)],
            cwd=temporary, env=environment, capture_output=True, text=True,
            check=True, timeout=120,
        )
        code = (
            "import importlib.util,pathlib,sys;"
            f"t=pathlib.Path({str(target)!r}).resolve();sys.path.insert(0,str(t));"
            "import compiler_core,mcp_server;"
            "from compiler_core.version import __version__;"
            "assert __version__=='4.0.0rc1';"
            "assert pathlib.Path(compiler_core.__file__).resolve().is_relative_to(t);"
            "assert pathlib.Path(mcp_server.__file__).resolve().is_relative_to(t);"
            "assert importlib.util.find_spec('compiler_core.analysis') is None;"
            "assert importlib.util.find_spec('compiler_core.compat_v3_v4') is None;"
            "print(__version__)"
        )
        subprocess.run(
            [sys.executable, "-I", "-B", "-c", code], cwd=temporary,
            env=environment, capture_output=True, text=True, check=True, timeout=120,
        )


def _venv_python(environment_root: Path) -> Path:
    return environment_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _venv_script(environment_root: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return environment_root / ("Scripts" if os.name == "nt" else "bin") / f"{name}{suffix}"


def _run_process(
    label: str,
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    expected: tuple[int, ...] = (0,),
    input_text: str | None = None,
    timeout: int = 300,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )
    if completed.returncode not in expected:
        detail = " ".join((completed.stderr or completed.stdout).split())[-1600:]
        raise RuntimeError(f"{label} failed ({completed.returncode}): {detail}")
    return completed, {
        "label": label,
        "return_code": completed.returncode,
        "stdout_sha256": "sha256:" + hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "stderr_sha256": "sha256:" + hashlib.sha256(completed.stderr.encode()).hexdigest(),
    }


def _copy_installed_harness(source: Path, destination: Path) -> None:
    for relative in INSTALLED_HARNESS_PATHS:
        source_path = source / PurePosixPath(relative)
        if not source_path.is_file():
            raise RuntimeError(f"installed harness input is missing: {relative}")
        target = destination / PurePosixPath(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)
    for relative in (
        "tests/__init__.py",
        "tests/contract/__init__.py",
        "tests/integration/__init__.py",
        "tests/formal_e2e/__init__.py",
        "tools/__init__.py",
    ):
        target = destination / PurePosixPath(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")
    (destination / "conftest.py").write_text(
        "from pathlib import Path\n"
        "import os\n"
        "import compiler_core\n"
        "ENV_ROOT = Path(os.environ['JC_INSTALLED_ENV_ROOT']).resolve()\n"
        "HARNESS_ROOT = Path(__file__).resolve().parent\n"
        "assert Path(compiler_core.__file__).resolve().is_relative_to(ENV_ROOT)\n"
        "assert not (HARNESS_ROOT / 'compiler_core').exists()\n",
        encoding="utf-8",
    )


def _junit_summary(path: Path) -> dict[str, object]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    counts = {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "skipped", "failures", "errors")
    }
    case_ids = sorted(
        f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}"
        for case in root.iter("testcase")
    )
    if (
        counts != {
            "tests": INSTALLED_TEST_CASE_COUNT,
            "skipped": 0,
            "failures": 0,
            "errors": 0,
        }
        or len(case_ids) != INSTALLED_TEST_CASE_COUNT
        or len(set(case_ids)) != INSTALLED_TEST_CASE_COUNT
    ):
        raise RuntimeError(f"installed-wheel JUnit drifted: {counts}; cases={len(case_ids)}")
    payload = path.read_bytes()
    return {
        **counts,
        "case_ids_sha256": _canonical_digest(case_ids),
        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
    }


def validate_installed_e2e_report(
    report: object,
    *,
    wheel_digest: str,
    lock_digest: str,
) -> list[str]:
    if not isinstance(report, dict):
        return ["installed-wheel report is not an object"]
    expected = {
        "schema_version": "jc/installed-wheel-e2e/1.0",
        "status": "PASS",
        "wheel_sha256": wheel_digest,
        "test_lock_sha256": lock_digest,
        "installed_version": "4.0.0rc1",
        "source_tree_absent": True,
        "imports_from_fresh_environment": True,
        "network_disabled_during_install_and_execution": True,
        "rejected_imports": list(REJECTED_IMPORTS),
        "cli_version": "jc 4.0.0rc1",
        "cli_capabilities_error": "RUNTIME_NOT_CONFIGURED",
        "mcp_server_version": "4.0.0rc1",
        "mcp_tools": [
            "jc_capabilities", "jc_evaluate", "jc_verify_run", "jc_read_artifact",
        ],
        "mcp_capabilities_error": "RUNTIME_NOT_CONFIGURED",
    }
    problems = [
        f"installed-wheel report {key} drifted"
        for key, value in expected.items() if report.get(key) != value
    ]
    junit = report.get("formal_e2e")
    if (
        not isinstance(junit, dict)
        or junit.get("tests") != INSTALLED_TEST_CASE_COUNT
        or any(junit.get(key) != 0 for key in ("skipped", "failures", "errors"))
        or junit.get("case_ids_sha256") != INSTALLED_TEST_CASE_IDS_SHA256
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(junit.get("sha256"))) is None
    ):
        problems.append("installed-wheel formal E2E JUnit drifted")
    commands = report.get("commands")
    if (
        not isinstance(commands, list)
        or [row.get("label") for row in commands if isinstance(row, dict)] != [
            "create-venv", "install-test-lock", "install-wheel", "pip-check",
            "origin-and-retirement-probe", "cli-version", "cli-capabilities",
            "mcp-stdio-lifecycle", "formal-e2e",
        ]
        or any(
            not isinstance(row, dict)
            or row.get("return_code") not in ({6} if row.get("label") == "cli-capabilities" else {0})
            or re.fullmatch(r"sha256:[0-9a-f]{64}", str(row.get("stdout_sha256"))) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", str(row.get("stderr_sha256"))) is None
            for row in commands
        )
    ):
        problems.append("installed-wheel command evidence drifted")
    if (
        not isinstance(report.get("wheelhouse"), dict)
        or not isinstance(report["wheelhouse"].get("file_count"), int)
        or report["wheelhouse"]["file_count"] < 4
        or re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            str(report["wheelhouse"].get("manifest_sha256")),
        ) is None
    ):
        problems.append("installed-wheel wheelhouse evidence drifted")
    return problems


def run_installed_e2e(
    source: Path,
    wheel: Path,
    test_lock: Path,
    wheelhouse: Path,
    work_dir: Path,
) -> dict[str, object]:
    source = source.resolve()
    wheel = wheel.resolve()
    test_lock = test_lock.resolve()
    wheelhouse = wheelhouse.resolve()
    work_dir = work_dir.resolve()
    if not source.is_dir() or (source / ".git").exists():
        raise RuntimeError("installed E2E source must be a gitless archive")
    if not wheel.is_file() or not test_lock.is_file() or not wheelhouse.is_dir():
        raise RuntimeError("installed E2E inputs are incomplete")
    if work_dir == source or work_dir.is_relative_to(source) or source.is_relative_to(work_dir):
        raise RuntimeError("installed E2E work directory must be outside the source tree")
    if work_dir.exists() and any(work_dir.iterdir()):
        raise RuntimeError("installed E2E work directory is not empty")
    work_dir.mkdir(parents=True, exist_ok=True)
    installable_wheel = work_dir / "juris_calculus-4.0.0rc1-py3-none-any.whl"
    shutil.copyfile(wheel, installable_wheel)
    validate_wheel(source, installable_wheel)

    environment_root = work_dir / "venv"
    harness = work_dir / "harness"
    junit = work_dir / "installed-e2e.xml"
    commands: list[dict[str, object]] = []
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.update({
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INDEX": "1",
        "PIP_FIND_LINKS": str(wheelhouse),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    })

    completed, summary = _run_process(
        "create-venv",
        [sys.executable, "-B", "-m", "venv", str(environment_root)],
        cwd=work_dir,
        environment=environment,
        timeout=180,
    )
    commands.append(summary)
    python = _venv_python(environment_root)
    if not python.is_file():
        raise RuntimeError("fresh environment Python is missing")
    environment["JC_INSTALLED_ENV_ROOT"] = str(environment_root)

    completed, summary = _run_process(
        "install-test-lock",
        [
            str(python), "-B", "-m", "pip", "install", "--no-index",
            "--find-links", str(wheelhouse), "--require-hashes",
            "--requirement", str(test_lock),
        ],
        cwd=work_dir,
        environment=environment,
        timeout=300,
    )
    commands.append(summary)
    completed, summary = _run_process(
        "install-wheel",
        [
            str(python), "-B", "-m", "pip", "install", "--no-index", "--no-deps",
            str(installable_wheel),
        ],
        cwd=work_dir,
        environment=environment,
        timeout=180,
    )
    commands.append(summary)
    completed, summary = _run_process(
        "pip-check", [str(python), "-B", "-m", "pip", "check"],
        cwd=work_dir, environment=environment,
    )
    commands.append(summary)

    origin_code = (
        "import importlib.resources,importlib.util,json,pathlib,sys;"
        "import compiler_core,configs,mcp_server,schemas;"
        "from compiler_core.version import __version__;"
        "root=pathlib.Path(sys.prefix).resolve();"
        "mods=(compiler_core,configs,mcp_server,schemas);"
        "origins=[pathlib.Path(m.__file__).resolve() for m in mods];"
        "assert all(p.is_relative_to(root) for p in origins);"
        f"rejected={REJECTED_IMPORTS!r};"
        "observed=[];"
        "\nfor name in rejected:\n"
        " try: spec=importlib.util.find_spec(name)\n"
        " except ModuleNotFoundError: spec=None\n"
        " assert spec is None,name;observed.append(name)\n"
        "schema=importlib.resources.files('schemas').joinpath('jc-v4.schema.json');"
        "assert schema.is_file();"
        "print(json.dumps({'version':__version__,'origins_in_environment':True,"
        "'rejected_imports':observed,'schema_sha256':__import__('hashlib').sha256(schema.read_bytes()).hexdigest()}))"
    )
    completed, summary = _run_process(
        "origin-and-retirement-probe", [str(python), "-I", "-B", "-c", origin_code],
        cwd=work_dir, environment=environment,
    )
    commands.append(summary)
    origin = json.loads(completed.stdout)
    if origin != {
        "version": "4.0.0rc1",
        "origins_in_environment": True,
        "rejected_imports": list(REJECTED_IMPORTS),
        "schema_sha256": hashlib.sha256((source / "schemas/jc-v4.schema.json").read_bytes()).hexdigest(),
    }:
        raise RuntimeError("installed origin/resource/retirement probe drifted")

    completed, summary = _run_process(
        "cli-version", [str(_venv_script(environment_root, "jc")), "--version"],
        cwd=work_dir, environment=environment,
    )
    commands.append(summary)
    cli_version = completed.stdout.strip()
    if cli_version != "jc 4.0.0rc1":
        raise RuntimeError("installed CLI version drifted")
    completed, summary = _run_process(
        "cli-capabilities",
        [str(_venv_script(environment_root, "jc")), "capabilities", "--json"],
        cwd=work_dir, environment=environment, expected=(6,),
    )
    commands.append(summary)
    cli_error = json.loads(completed.stderr)
    if cli_error.get("code") != "RUNTIME_NOT_CONFIGURED":
        raise RuntimeError("installed CLI capabilities failure is not typed")

    mcp_requests = (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "jc_capabilities", "arguments": {}}},
    )
    completed, summary = _run_process(
        "mcp-stdio-lifecycle", [str(python), "-I", "-B", "-m", "mcp_server"],
        cwd=work_dir,
        environment=environment,
        input_text="".join(json.dumps(row, separators=(",", ":")) + "\n" for row in mcp_requests),
    )
    commands.append(summary)
    mcp = [json.loads(line) for line in completed.stdout.splitlines()]
    mcp_tools = [row["name"] for row in mcp[1]["result"]["tools"]]
    mcp_error = mcp[2]["result"]["structuredContent"]["error"]["code"]
    if (
        len(mcp) != 3
        or mcp[0]["result"]["serverInfo"] != {"name": "juris-calculus", "version": "4.0.0rc1"}
        or mcp_tools != ["jc_capabilities", "jc_evaluate", "jc_verify_run", "jc_read_artifact"]
        or mcp[2]["result"]["isError"] is not True
        or mcp_error != "RUNTIME_NOT_CONFIGURED"
    ):
        raise RuntimeError("installed MCP stdio lifecycle drifted")

    harness.mkdir()
    _copy_installed_harness(source, harness)
    completed, summary = _run_process(
        "formal-e2e",
        [
            str(python), "-I", "-B", "-m", "pytest", "-q", "--color=no",
            "-p", "no:cacheprovider", "--basetemp", str(work_dir / "pytest"),
            "--junitxml", str(junit), *INSTALLED_TEST_SELECTORS,
        ],
        cwd=harness,
        environment=environment,
        timeout=900,
    )
    commands.append(summary)
    formal_e2e = _junit_summary(junit)

    completed, _ = _run_process(
        "installed-distributions",
        [str(python), "-I", "-B", "-m", "pip", "list", "--format=json"],
        cwd=work_dir,
        environment=environment,
    )
    distributions = sorted(
        (str(row["name"]).lower(), str(row["version"]))
        for row in json.loads(completed.stdout)
    )
    wheelhouse_rows = [
        {"name": path.name, "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(wheelhouse.iterdir(), key=lambda item: item.name.casefold())
        if path.is_file()
    ]
    wheel_digest = "sha256:" + hashlib.sha256(wheel.read_bytes()).hexdigest()
    lock_digest = "sha256:" + hashlib.sha256(test_lock.read_bytes()).hexdigest()
    report = {
        "schema_version": "jc/installed-wheel-e2e/1.0",
        "status": "PASS",
        "wheel_sha256": wheel_digest,
        "test_lock_sha256": lock_digest,
        "wheelhouse": {
            "file_count": len(wheelhouse_rows),
            "manifest_sha256": _canonical_digest(wheelhouse_rows),
        },
        "installed_distributions": {
            "count": len(distributions),
            "sha256": _canonical_digest(distributions),
        },
        "installed_version": origin["version"],
        "source_tree_absent": not (harness / "compiler_core").exists(),
        "imports_from_fresh_environment": origin["origins_in_environment"],
        "network_disabled_during_install_and_execution": environment["PIP_NO_INDEX"] == "1",
        "rejected_imports": origin["rejected_imports"],
        "cli_version": cli_version,
        "cli_capabilities_error": cli_error["code"],
        "mcp_server_version": mcp[0]["result"]["serverInfo"]["version"],
        "mcp_tools": mcp_tools,
        "mcp_capabilities_error": mcp_error,
        "formal_e2e": formal_e2e,
        "commands": commands,
    }
    problems = validate_installed_e2e_report(
        report, wheel_digest=wheel_digest, lock_digest=lock_digest,
    )
    if problems:
        raise RuntimeError("; ".join(problems))
    return report


def run_gate(
    source: Path,
    out_dir: Path,
    *,
    source_date_epoch: int,
    no_isolation: bool = False,
) -> dict[str, object]:
    source = source.resolve()
    if not source.is_dir() or (source / ".git").exists():
        raise RuntimeError("source must be an extracted clean archive without .git")
    if source_date_epoch < 315_532_800:
        raise RuntimeError("SOURCE_DATE_EPOCH must be an explicit post-1980 timestamp")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if list(out_dir.glob("*.whl")):
        raise RuntimeError("wheel output directory is not empty")
    with tempfile.TemporaryDirectory(prefix="jc-formal-build-") as raw:
        build_tree = Path(raw) / "source"
        build_tree.mkdir()
        payload = _copy_build_tree(source, build_tree)
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.update({
            "SOURCE_DATE_EPOCH": str(source_date_epoch),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        })
        command = [sys.executable, "-B", "-m", "build", "--wheel", "--outdir", str(out_dir)]
        if no_isolation:
            command.append("--no-isolation")
        subprocess.run(
            command, cwd=build_tree, env=environment, capture_output=True,
            text=True, check=True, timeout=300,
        )
    wheels = sorted(out_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("build must produce exactly one wheel")
    result = validate_wheel(source, wheels[0])
    _smoke_install(source, wheels[0])
    return {
        "schema_version": "jc/formal-wheel-gate/1.0",
        "status": "PASS",
        "source_has_git": False,
        "source_date_epoch": source_date_epoch,
        "authority": "docs/architecture/module-authority.json",
        "payload_count": len(payload),
        **result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--source-date-epoch", type=int)
    parser.add_argument("--no-isolation", action="store_true")
    parser.add_argument("--installed-wheel", type=Path)
    parser.add_argument("--test-lock", type=Path)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.installed_wheel is not None:
            if None in (args.test_lock, args.wheelhouse, args.work_dir):
                raise RuntimeError(
                    "installed E2E requires --test-lock, --wheelhouse, and --work-dir"
                )
            if args.out_dir is not None or args.source_date_epoch is not None or args.no_isolation:
                raise RuntimeError("build and installed E2E arguments cannot be mixed")
            report = run_installed_e2e(
                args.source,
                args.installed_wheel,
                args.test_lock,
                args.wheelhouse,
                args.work_dir,
            )
        else:
            if args.out_dir is None or args.source_date_epoch is None:
                raise RuntimeError("wheel build requires --out-dir and --source-date-epoch")
            report = run_gate(
                args.source, args.out_dir, source_date_epoch=args.source_date_epoch,
                no_isolation=args.no_isolation,
            )
    except (OSError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, UnicodeError, ValueError, zipfile.BadZipFile) as exc:
        detail = (
            exc.stderr.strip()
            if isinstance(exc, subprocess.CalledProcessError) and exc.stderr
            else str(exc)
        )
        report = {
            "schema_version": (
                "jc/installed-wheel-e2e/1.0"
                if args.installed_wheel is not None
                else "jc/formal-wheel-gate/1.0"
            ),
            "status": "FAIL",
            "reason": f"{type(exc).__name__}:{detail}",
        }
    encoded = json.dumps(report, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
