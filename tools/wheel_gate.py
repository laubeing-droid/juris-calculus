#!/usr/bin/env python3
"""Build from a clean generated tree, inspect the wheel, and smoke-install it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {
    "compiler_core/post_freeze_surface.py",
    "compiler_core/automated_pipeline.py",
    "compiler_core/batch_processor.py",
    "compiler_core/language_renderer.py",
    "compiler_core/litigation_renderer.py",
    "compiler_core/multi_jurisdiction_orchestrator.py",
    "compiler_core/multi_solver_router.py",
    "compiler_core/parallax_inference.py",
    "compiler_core/proof_trace_renderer.py",
    "compiler_core/lsc_boundary_status.py",
}


def run_gate(out_dir: Path, *, no_isolation: bool = False) -> dict[str, object]:
    """删除仅限仓库内生成缓存，构建并验证wheel不会复活旧模块。"""

    for target in [ROOT / "build", *ROOT.glob("*.egg-info")]:
        resolved = target.resolve()
        if target.exists():
            resolved.relative_to(ROOT)
            shutil.rmtree(resolved)
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir)]
    if no_isolation:
        command.insert(4, "--no-isolation")
    build_env = dict(os.environ)
    # Wheel ZIP timestamps must be source-bound; wall-clock timestamps break byte-for-byte rebuilds.
    build_env["SOURCE_DATE_EPOCH"] = subprocess.check_output(
        ["git", "log", "-1", "--format=%ct"], cwd=ROOT, text=True
    ).strip()
    subprocess.run(command, cwd=ROOT, env=build_env, check=True)
    wheels = sorted(out_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("expected exactly one wheel")
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        resurrected = sorted(FORBIDDEN & names)
        if resurrected:
            raise RuntimeError(f"forbidden wheel modules: {resurrected}")
        if "addons/workbuddy_mcp.py" not in names:
            raise RuntimeError("WorkBuddy adapter missing from wheel")
    with tempfile.TemporaryDirectory(prefix="jc-wheel-smoke-") as temp:
        target = Path(temp) / "site"
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheel)], check=True)
        code = (
            "from addons.workbuddy_mcp import manifest_document;"
            "m=manifest_document();"
            "assert len(m['tools'])==4 and not m['resources'];"
            "from compiler_core.version import __version__;print(__version__)"
        )
        subprocess.run([sys.executable, "-I", "-c", f"import sys;sys.path.insert(0,{str(target)!r});{code}"], cwd=temp, check=True)
    return {
        "status": "PASS",
        "wheel": wheel.name,
        "size_bytes": wheel.stat().st_size,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "forbidden_module_count": 0,
        "workbuddy_tools": 4,
        "resources": 0,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI wrapper for local and CI clean-wheel gates."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--no-isolation", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_gate(args.out_dir, no_isolation=args.no_isolation)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        report = {"status": "FAIL", "reason": type(exc).__name__}
    encoded = json.dumps(report, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
