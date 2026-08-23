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
import shutil
import subprocess
import sys
import tempfile
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


def _smoke_install(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="jc-wheel-install-") as raw:
        temporary = Path(raw)
        target = temporary / "site"
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        subprocess.run(
            [sys.executable, "-B", "-m", "pip", "install", "--no-deps",
             "--disable-pip-version-check", "--target", str(target), str(wheel)],
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
    _smoke_install(wheels[0])
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
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--source-date-epoch", type=int, required=True)
    parser.add_argument("--no-isolation", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
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
            "schema_version": "jc/formal-wheel-gate/1.0",
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
