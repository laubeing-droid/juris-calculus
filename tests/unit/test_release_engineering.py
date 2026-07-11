"""Static release-engineering gates for pinned CI and reproducible core dependencies."""

from pathlib import Path

from tools.build_provenance import SPEC_COMMIT
from tools.wheel_gate import FORBIDDEN


ROOT = Path(__file__).resolve().parents[2]


def test_core_lock_has_target_wheel_hashes_and_matches_runtime_dependency() -> None:
    """All four supported OS/Python wheel variants must be hash-pinned."""

    lock = (ROOT / "requirements-core.lock").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "PyYAML==6.0.3" in lock
    assert lock.count("--hash=sha256:") == 4
    assert '"PyYAML>=6.0"' in pyproject
    assert 'requires = ["setuptools==83.0.0", "wheel==0.47.0"]' in pyproject


def test_ci_pins_actions_and_spec_commit_without_floating_main() -> None:
    """CI执行依赖不得跟随大版本tag或上游main漂移。"""

    for relative in (".github/workflows/ci.yml", ".github/workflows/auto-release.yml"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "actions/checkout@v" not in text
        assert "actions/setup-python@v" not in text
        assert f"ref: {SPEC_COMMIT}" in text


def test_clean_wheel_gate_rejects_known_deleted_runtime_modules() -> None:
    """曾被stale build复活的入口必须留在wheel禁止清单。"""

    assert "compiler_core/post_freeze_surface.py" in FORBIDDEN
    assert "compiler_core/litigation_renderer.py" in FORBIDDEN
    assert "compiler_core/automated_pipeline.py" in FORBIDDEN
