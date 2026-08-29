#!/usr/bin/env python3
"""Current-state V4 checks driven by Git, the local AST, and repo files only.

Subcommands:
  machine-paths  no fixed machine directory may appear in tracked files
  cleanup        retired modules, shims, and dated documents stay deleted
  doc-links      every relative link inside tracked Markdown resolves
  generated      committed schema/manifest publications match compiler_core.mcp
  manifest       tests/required-v4-tests.json selectors exist and are declared
  wheel          clean git-archive wheel build plus isolated installed-wheel
                 verification of the official YAML admission cases

Every subprocess boundary is UTF-8 strict; no external CodeGraph database or
fixed machine state root is consulted.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.remediation.process import child_environment, git_tracked_paths, run_command

ROOT = Path(__file__).resolve().parents[2]
EXIT_OK = 0
EXIT_FAILURE = 1

MACHINE_PATH_MARKERS = (
    b"d:" + b"\\codex",
    b"d:" + b"/codex",
    b"juris-calculus-v4-" + b"production-state",
)
MACHINE_PATH_EXEMPT = frozenset({"remediation/v4/tasks.json"})

RETIRED_TEXT_FILES = (
    *(
        f"compiler_core/{name}.py"
        for name in (
            "classifier", "invariance_metrics", "kg_recall", "legal_memory",
            "result_diff", "result_exporter", "proof_trace_visualizer",
            "banach_verifier", "breakthrough_verification", "cross_jurisdiction_compare",
            "incremental_grounded", "defeasible_priority", "g8_evaluator_patch",
            "grounded_smt_verifier", "universal_grounded_smt", "output_firewall",
            "review_packet", "validity_state_machine", "smt_sidecar",
            "breakthrough_candidates", "horn_completeness", "stratified_evaluator",
            "cross_jurisdiction_router",
        )
    ),
    "pipeline/llm_client.py",
    "tools/remediate_v4_verify.py",
    "tests/unit/test_remediation_graph_map.py",
    "tests/unit/test_remediation_legacy_cn_corpus.py",
    "tests/contract/test_v4_foundation_contract.py",
)
RETIRED_DATED_DOCS = (
    "20260815_juris-calculus理论成果全量吸收施工方案.md",
    "20260819_juris-calculus_V4单主链全量切换与生产投产施工方案.md",
    "20260819_juris-calculus_V4单主链生产投产全量代码审计.md",
    "20260819_juris-calculus_V4单主链生产投产全自动整治施工方案.md",
    "20260824_juris-calculus_V4生产运行闭环彻底整治施工方案.md",
    "20260824_juris-calculus_V4生产运行闭环Goal模式启动提示词.md",
)
RETIRED_TOPIC_DOCS = (
    "docs/audits/branch-adoption-decision.md",
    "docs/audits/current-head-baseline.json",
    "docs/construction/S11-JC-STATUS.md",
    "docs/operations/V3_HISTORICAL_REPLAY.md",
)
RETIRED_FILES = (*RETIRED_TEXT_FILES, *RETIRED_DATED_DOCS, *RETIRED_TOPIC_DOCS)

_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)<>\s]+)>?(?:\s+\"[^\"]*\")?\s*\)")


def _tracked_text_files(root: Path) -> list[tuple[str, bytes]]:
    rows: list[tuple[str, bytes]] = []
    for path in git_tracked_paths(root):
        payload = (root / path).read_bytes()
        rows.append((path, payload))
    return rows


def machine_paths_problems(root: Path) -> list[str]:
    problems: list[str] = []
    for path, payload in _tracked_text_files(root):
        if path in MACHINE_PATH_EXEMPT:
            continue
        lowered = payload.lower()
        for marker in MACHINE_PATH_MARKERS:
            if marker in lowered:
                problems.append(f"{path} contains fixed machine path marker {marker.decode('ascii')!r}")
    return sorted(problems)


def cleanup_problems(root: Path) -> list[str]:
    problems: list[str] = []
    for relative in RETIRED_FILES:
        if (root / relative).exists():
            problems.append(f"retired file is still present: {relative}")
    return problems


def doc_links_problems(root: Path) -> list[str]:
    problems: list[str] = []
    for path, payload in _tracked_text_files(root):
        if not path.endswith(".md"):
            continue
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            problems.append(f"{path} is not strict UTF-8 Markdown")
            continue
        base = (root / path).parent
        for match in _MARKDOWN_LINK.finditer(text):
            target = match.group(1).strip()
            if not target or target.startswith("#"):
                continue
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue
            resolved = base / Path(target.split("#", 1)[0])
            if not resolved.exists():
                problems.append(f"{path} links to missing target: {target}")
    return sorted(set(problems))


def generated_problems(
    root: Path,
    schema_path: Path | None = None,
    manifest_path: Path | None = None,
) -> list[str]:
    """Compare committed publications with the in-tree typed emitters."""

    from compiler_core.canonical_serialization import canonical_bytes
    from compiler_core import mcp as authority

    schema_path = schema_path or root / "schemas/jc-v4.schema.json"
    manifest_path = manifest_path or root / "mcp_manifest.json"
    problems: list[str] = []
    pairs = (
        ("schemas/jc-v4.schema.json", schema_path, authority.schema_bytes()),
        ("mcp_manifest.json", manifest_path, authority.manifest_bytes()),
    )
    documents: dict[str, Any] = {}
    for relative, path, expected in pairs:
        try:
            observed = path.read_bytes()
        except OSError as exc:
            problems.append(f"{relative} is unreadable: {type(exc).__name__}")
            continue
        if observed != expected:
            problems.append(f"{relative} differs from the deterministic typed emitter")
        try:
            document = json.loads(observed.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            problems.append(f"{relative} is not strict UTF-8 JSON: {type(exc).__name__}")
            continue
        documents[relative] = document
        if canonical_bytes(document) != observed:
            problems.append(f"{relative} is not exact canonical UTF-8 bytes")
    try:
        import jsonschema
    except ImportError:
        problems.append("jsonschema is required for the generated publication check")
    else:
        schema = documents.get("schemas/jc-v4.schema.json")
        if isinstance(schema, dict):
            try:
                jsonschema.Draft202012Validator.check_schema(schema)
            except jsonschema.SchemaError as exc:
                problems.append(f"schema publication is invalid Draft 2020-12: {exc.message}")
    manifest = documents.get("mcp_manifest.json")
    if isinstance(manifest, dict) and manifest != authority.runtime_tools_list():
        problems.append("mcp_manifest.json differs from the runtime tools/list document")
    return sorted(set(problems))


def _selector_file(selector: Any) -> str | None:
    if not isinstance(selector, str) or not selector:
        return None
    path = selector.split("::", 1)[0]
    if (
        "\\" in path
        or path.startswith("/")
        or re.match(r"^[A-Za-z]:", path)
        or not path.endswith(".py")
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        return None
    return path


def selector_problems(root: Path, selector: Any, label: str) -> list[str]:
    """A selector must point at a tracked file that declares its symbols."""

    relative = _selector_file(selector)
    if relative is None:
        return [f"{label} selector is not a repo-relative test path: {selector!r}"]
    path = root / relative
    if not path.is_file():
        return [f"{label} selector file is missing: {relative}"]
    parts = [part.split("[", 1)[0] for part in str(selector).split("::")[1:]]
    if not parts:
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=relative)
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label} selector file cannot be parsed: {relative}: {exc}"]
    body: list[ast.stmt] = tree.body
    for part in parts:
        match = next(
            (
                node for node in body
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == part
            ),
            None,
        )
        if match is None:
            return [f"{label} selector symbol is missing: {selector}"]
        body = match.body if isinstance(match, ast.ClassDef) else []
    return []


def manifest_problems(root: Path) -> list[str]:
    """Validate the required-test manifest against the current tree."""

    path = root / "tests/required-v4-tests.json"
    problems: list[str] = []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"required test manifest is unreadable: {type(exc).__name__}: {exc}"]
    expected_fields = {
        "schema_version", "required_policy", "pytest_config", "red_sentinel_selector",
        "suite_aliases", "suites", "required_now", "evidence_tracks",
        "audit_mutations", "rewrite_at_task",
    }
    if not isinstance(document, dict) or set(document) != expected_fields:
        return [f"manifest fields must be exactly {sorted(expected_fields)}"]
    if document["schema_version"] != "jc/v4-required-test-manifest/1.0":
        problems.append("unexpected manifest schema_version")
    suite_ids = {
        suite.get("id")
        for suite in document["suites"]
        if isinstance(suite, dict)
    } if isinstance(document["suites"], list) else set()
    for suite in document["suites"] if isinstance(document["suites"], list) else []:
        if not isinstance(suite, dict) or not {"id", "path", "proof_obligation"} <= set(suite):
            problems.append("suite entries must declare id, path, and proof_obligation")
            continue
        if not (root / suite["path"]).is_dir():
            problems.append(f"suite directory is missing: {suite['path']}")
    for alias, target in (document.get("suite_aliases") or {}).items():
        if target not in suite_ids:
            problems.append(f"suite alias {alias} points at unknown suite {target}")
    if not (root / document["pytest_config"]).is_file():
        problems.append(f"pytest_config is missing: {document['pytest_config']}")
    problems.extend(selector_problems(root, document["red_sentinel_selector"], "red_sentinel_selector"))
    sections = (
        ("required_now", document["required_now"]),
        ("evidence_tracks", document["evidence_tracks"]),
        ("audit_mutations", document["audit_mutations"]),
        ("rewrite_at_task", document["rewrite_at_task"]),
    )
    for label, entries in sections:
        if not isinstance(entries, list):
            problems.append(f"{label} must be an array")
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("selector"), str):
                problems.append(f"{label} entries must be objects with a selector")
                continue
            problems.extend(selector_problems(root, entry["selector"], label))
            if "suite" in entry and entry["suite"] not in suite_ids:
                problems.append(f"{label} entry points at unknown suite: {entry['suite']}")
    return sorted(set(problems))


def _extract_git_archive(root: Path, target: Path) -> None:
    completed = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=root, capture_output=True, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace").strip())
    members_ok: list[tarfile.TarInfo] = []
    with tarfile.open(fileobj=io.BytesIO(completed.stdout)) as archive:
        for member in archive.getmembers():
            pure = PurePosixPath(member.name)
            if member.name.startswith("/") or ".." in pure.parts:
                raise RuntimeError(f"unsafe archive member: {member.name}")
            members_ok.append(member)
        archive.extractall(target, members=members_ok)


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _wheel_installed_official_check(
    root: Path, work: Path, wheel: Path, output: list[str],
) -> None:
    """Install the wheel with its dependency lock into a fresh venv and run
    the installed official YAML admission cases from outside the source tree."""

    venv = work / "venv"
    completed = run_command(
        [sys.executable, "-B", "-m", "venv", str(venv)],
        cwd=work, timeout_seconds=600,
    )
    if not completed.passed:
        raise RuntimeError(f"venv creation failed: {completed.stderr[-2000:]}")
    python = _venv_python(venv)
    environment = child_environment({
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    completed = run_command(
        [str(python), "-B", "-m", "pip", "install", "--disable-pip-version-check",
         "--require-hashes", "--requirement", str(root / "requirements/test.lock")],
        cwd=work, timeout_seconds=1800, env=environment,
    )
    if not completed.passed:
        raise RuntimeError(f"dependency install failed: {completed.stderr[-2000:]}")
    completed = run_command(
        [str(python), "-B", "-m", "pip", "install", "--disable-pip-version-check",
         "--no-index", "--no-deps", str(wheel)],
        cwd=work, timeout_seconds=600, env=environment,
    )
    if not completed.passed:
        raise RuntimeError(f"wheel install failed: {completed.stderr[-2000:]}")
    harness = work / "harness"
    harness.mkdir()
    (harness / "conftest.py").write_text(
        "from pathlib import Path\n"
        "import importlib.util, os, sys\n"
        "import compiler_core\n"
        "env_root = Path(os.environ['JC_INSTALLED_ENV_ROOT']).resolve()\n"
        "assert Path(compiler_core.__file__).resolve().is_relative_to(env_root)\n"
        "assert not (Path(__file__).resolve().parent / 'compiler_core').exists()\n"
        "assert importlib.util.find_spec('compiler_core.types') is None\n",
        encoding="utf-8",
    )
    shutil.copyfile(
        root / "tests/packaging/test_installed_official_yaml.py",
        harness / "test_installed_official_yaml.py",
    )
    completed = run_command(
        [str(python), "-I", "-B", "-m", "pytest", "-q", "--color=no",
         "-p", "no:cacheprovider", str(harness / "test_installed_official_yaml.py")],
        cwd=harness, timeout_seconds=900,
        env=child_environment({
            "JC_INSTALLED_ENV_ROOT": str(venv.resolve()),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }),
    )
    output.append(completed.stdout[-2000:])
    if not completed.passed:
        raise RuntimeError(f"installed official YAML verification failed:\n{completed.stdout[-2000:]}\n{completed.stderr[-2000:]}")


def wheel_check(root: Path, out_dir: Path | None) -> int:
    """Build the wheel from a git-archive clean source and verify it end to end."""

    from tools.wheel_gate import run_gate

    with tempfile.TemporaryDirectory(prefix="jc-v4-wheel-check-") as raw:
        work = Path(raw)
        source = work / "source"
        source.mkdir()
        _extract_git_archive(root, source)
        epoch = int(
            subprocess.run(
                ["git", "show", "-s", "--format=%ct", "HEAD"],
                cwd=root, capture_output=True, check=True,
            ).stdout.decode("ascii").strip()
        )
        dist = (out_dir or work / "dist").resolve()
        dist.mkdir(parents=True, exist_ok=True)
        report = run_gate(source, dist, source_date_epoch=epoch)
        if report.get("status") != "PASS":
            raise RuntimeError(f"wheel gate failed: {report}")
        wheel = next(dist.glob("*.whl"))
        notes: list[str] = []
        _wheel_installed_official_check(root, work, wheel, notes)
    print(
        f"wheel check OK: {report['wheel']} sha256={report['sha256']} "
        f"entries={report['entry_count']}"
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=(
        "machine-paths", "cleanup", "doc-links", "generated", "manifest", "wheel",
    ))
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="optional wheel output directory (wheel check)")
    args = parser.parse_args(argv)
    if args.check == "wheel":
        try:
            return wheel_check(ROOT, args.out_dir)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError,
                tarfile.TarError) as exc:
            print(f"wheel check failed: {exc}", file=sys.stderr)
            return EXIT_FAILURE
    handlers = {
        "machine-paths": machine_paths_problems,
        "cleanup": cleanup_problems,
        "doc-links": doc_links_problems,
        "generated": generated_problems,
        "manifest": manifest_problems,
    }
    problems = handlers[args.check](ROOT)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_FAILURE
    print(f"{args.check} OK")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
