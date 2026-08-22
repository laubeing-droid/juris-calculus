"""Static release-engineering gates for pinned CI and reproducible core dependencies."""

import base64
import hashlib
import json
import subprocess

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.build_provenance import SPEC_COMMIT
from tools.wheel_gate import FORBIDDEN


ROOT = Path(__file__).resolve().parents[2]


def test_core_lock_has_target_wheel_hashes_and_matches_runtime_dependency() -> None:
    """Every direct and transitive core wheel must be hash-pinned."""

    lock = (ROOT / "requirements" / "core.lock").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "PyYAML==6.0.3" in lock
    assert "cryptography==50.0.0" in lock
    assert "cffi==2.1.1" in lock
    assert "pycparser==3.0" in lock
    assert lock.count("--hash=sha256:") == 13
    assert '"PyYAML>=6.0"' in pyproject
    assert '"cryptography==50.0.0"' in pyproject
    assert 'requires = ["setuptools==83.0.0", "wheel==0.47.0"]' in pyproject


def test_committed_ed25519_key_is_cryptographically_valid_and_test_only() -> None:
    """The only committed private key is an explicitly non-production fixture."""

    fixture = json.loads(
        (ROOT / "tests/fixtures/keys/v4-test-ed25519.json").read_text(encoding="utf-8")
    )
    private_bytes = base64.b64decode(fixture["private_key_base64"], validate=True)
    public_bytes = base64.b64decode(fixture["public_key_base64"], validate=True)

    assert fixture["algorithm"] == "Ed25519"
    assert fixture["scope"] == "test-only"
    assert fixture["production_allowed"] is False
    assert fixture["private_key_sha256"] == "sha256:" + hashlib.sha256(private_bytes).hexdigest()
    assert fixture["public_key_sha256"] == "sha256:" + hashlib.sha256(public_bytes).hexdigest()

    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    assert private_key.public_key().public_bytes_raw() == public_bytes
    payload = b"juris-calculus-v4-test-only"
    private_key.public_key().verify(private_key.sign(payload), payload)

    tracked = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout.split(b"\0")
    fixture_path = b"tests/fixtures/keys/v4-test-ed25519.json"
    for encoded_path in tracked:
        if not encoded_path or encoded_path == fixture_path:
            continue
        contents = (ROOT / encoded_path.decode("utf-8")).read_bytes()
        assert private_bytes not in contents, encoded_path
        assert fixture["private_key_base64"].encode("ascii") not in contents, encoded_path


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
    assert "compiler_core/ddl_preclassifier.py" in FORBIDDEN
    assert "compiler_core/neural_leaf.py" in FORBIDDEN
    assert "compiler_core/shadow_state.py" in FORBIDDEN
    assert "pipeline/build_ocr_index.py" in FORBIDDEN
