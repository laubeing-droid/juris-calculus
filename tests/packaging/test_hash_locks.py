from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tools.supply_chain_gate import (
    PROFILE_FILES, _root_metadata_names, parse_lock, profile_reachability_problems,
    verify_lock_profiles,
)


ROOT = Path(__file__).resolve().parents[2]


def _copy_contract(tmp_path: Path) -> tuple[Path, Path]:
    lock_root = tmp_path / "requirements"
    lock_root.mkdir()
    for filename in PROFILE_FILES.values():
        shutil.copyfile(ROOT / "requirements" / filename, lock_root / filename)
    pyproject = tmp_path / "pyproject.toml"
    shutil.copyfile(ROOT / "pyproject.toml", pyproject)
    return lock_root, pyproject


def _problems(lock_root: Path, pyproject: Path) -> list[str]:
    return verify_lock_profiles(lock_root, pyproject)["problems"]


def test_all_profiles_are_transitively_hash_locked() -> None:
    report = verify_lock_profiles(ROOT / "requirements", ROOT / "pyproject.toml")
    assert report["status"] == "PASS", report["problems"]
    assert {name: row["package_count"] for name, row in report["profiles"].items()} == {
        "build": 6, "production": 4, "release": 38, "source-tool": 16, "test": 12,
    }


def test_distribution_metadata_is_core_only() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert "optional-dependencies" not in text
    assert not any(name in text for name in ("jinja2", "pydantic", "python-docx", "pdfplumber", "hypothesis"))


def test_profile_ownership_is_exact() -> None:
    profiles = {
        name: set(parse_lock(ROOT / "requirements" / filename)["packages"])
        for name, filename in PROFILE_FILES.items()
    }
    assert profiles["production"] == {"pyyaml", "cryptography", "cffi", "pycparser"}
    assert {"pydantic", "python-docx", "pdfplumber"} <= profiles["source-tool"]
    assert "hypothesis" in profiles["test"]
    assert "filelock" in profiles["release"]
    assert {"ruff", "mypy", "mypy-extensions", "pathspec"} <= profiles["release"]
    assert all("jinja2" not in packages and "markupsafe" not in packages for packages in profiles.values())


def test_removed_target_wheel_hash_fails_closed(tmp_path: Path) -> None:
    lock_root, pyproject = _copy_contract(tmp_path)
    path = lock_root / "core.lock"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.remove(next(line for line in lines if "06a32a980526a6ab" in line))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert any("manifest digest drifted" in problem for problem in _problems(lock_root, pyproject))


def test_license_mutation_fails_closed(tmp_path: Path) -> None:
    lock_root, pyproject = _copy_contract(tmp_path)
    path = lock_root / "build.lock"
    path.write_text(path.read_text(encoding="utf-8").replace("# license: MIT", "# license: GPL-3.0", 1), encoding="utf-8")
    assert any("denied or unknown licenses" in problem for problem in _problems(lock_root, pyproject))


def test_pin_mutation_fails_closed(tmp_path: Path) -> None:
    lock_root, pyproject = _copy_contract(tmp_path)
    path = lock_root / "test.lock"
    path.write_text(path.read_text(encoding="utf-8").replace("pytest==9.1.1", "pytest==9.1.0", 1), encoding="utf-8")
    assert any("manifest digest drifted" in problem for problem in _problems(lock_root, pyproject))


def test_legacy_profile_file_fails_closed(tmp_path: Path) -> None:
    lock_root, pyproject = _copy_contract(tmp_path)
    (lock_root / "render.lock").write_text("Jinja2==3.1.6\n", encoding="utf-8")
    assert any("lock file set drifted" in problem for problem in _problems(lock_root, pyproject))


def test_transitive_package_deletion_fails_closed(tmp_path: Path) -> None:
    lock_root, pyproject = _copy_contract(tmp_path)
    path = lock_root / "build.lock"
    path.write_text(path.read_text(encoding="utf-8").split("# package: colorama", 1)[0], encoding="utf-8")
    assert any("package count drifted" in problem for problem in _problems(lock_root, pyproject))


def test_unannotated_or_floating_requirement_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid.lock"
    path.write_text("# profile: invalid\ndemo>=1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid requirement"):
        parse_lock(path)
    assert _root_metadata_names([
        "setuptools-83.0.0.dist-info/METADATA",
        "setuptools/_vendor/wheel-0.46.3.dist-info/METADATA",
    ]) == ["setuptools-83.0.0.dist-info/METADATA"]
    assert profile_reachability_problems([
        {"reachable_packages": ["build"]},
        {"reachable_packages": ["build", "colorama"]},
    ], {"build", "colorama"}) == []
    assert profile_reachability_problems([
        {"reachable_packages": ["build"]},
    ], {"build", "colorama"})
