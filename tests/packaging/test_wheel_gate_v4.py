from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("jc_wheel_gate", ROOT / "tools/wheel_gate.py")
assert SPEC is not None and SPEC.loader is not None
WHEEL_GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WHEEL_GATE)
DIST = "juris_calculus-4.0.0.dist-info"


def _record_row(name: str, payload: bytes) -> list[str]:
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
    return [name, f"sha256={digest}", str(len(payload))]


def _wheel(tmp_path: Path, mutation: str = "valid") -> Path:
    entries = {
        path: (ROOT / path).read_bytes()
        for path in WHEEL_GATE.expected_payload_paths(ROOT)
    }
    entries.update({
        f"{DIST}/METADATA": (
            b"Metadata-Version: 2.4\r\nName: juris-calculus\r\n"
            b"Version: 4.0.0\r\nRequires-Python: <3.13,>=3.11\r\n\r\n"
        ),
        f"{DIST}/WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: setuptools (83.0.0)\n"
            b"Root-Is-Purelib: true\nTag: py3-none-any\n"
        ),
        f"{DIST}/entry_points.txt": (
            b"[console_scripts]\njc = compiler_core.cli:main\n"
            b"jc-formal = compiler_core.formal_bridge:main\n"
        ),
        f"{DIST}/licenses/LICENSE": (ROOT / "LICENSE").read_bytes(),
        f"{DIST}/top_level.txt": b"compiler_core\nconfigs\nmcp_server\nschemas\n",
    })
    if mutation == "extra":
        entries["compiler_core/analysis.py"] = b"candidate"
    elif mutation == "missing":
        del entries["compiler_core/contracts.py"]
    elif mutation == "unsafe":
        entries["../escape.py"] = b"escape"
    elif mutation == "legacy":
        entries["compiler_core/version.py"] += b"\n# cn-legacy-corpus\n"

    rows = [_record_row(name, payload) for name, payload in sorted(entries.items())]
    rows.append([f"{DIST}/RECORD", "", ""])
    if mutation == "record":
        rows[0][1] = "sha256=invalid"
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    entries[f"{DIST}/RECORD"] = stream.getvalue().encode()

    wheel = tmp_path / "juris_calculus-4.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
        if mutation == "duplicate":
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr(
                    "compiler_core/version.py", entries["compiler_core/version.py"],
                )
    return wheel


def test_payload_is_derived_from_the_manual_production_classes() -> None:
    payload = WHEEL_GATE.expected_payload_paths(ROOT)
    assert len(payload) == 32
    assert "compiler_core/application.py" in payload
    assert "configs/render_profiles/neutral.yaml" in payload
    assert "schemas/jc-v4.schema.json" in payload
    assert not any(path.startswith(("addons/", "pipeline/", "tests/", "tools/")) for path in payload)


def test_exact_synthetic_wheel_is_accepted(tmp_path: Path) -> None:
    report = WHEEL_GATE.validate_wheel(ROOT, _wheel(tmp_path))
    assert report["entry_count"] == 38


@pytest.mark.parametrize("mutation", ["extra", "missing", "duplicate", "unsafe", "record"])
def test_zip_and_record_set_mutations_are_rejected(tmp_path: Path, mutation: str) -> None:
    with pytest.raises(RuntimeError):
        WHEEL_GATE.validate_wheel(ROOT, _wheel(tmp_path, mutation))


def test_retired_corpus_marker_is_rejected_even_in_an_allowed_path(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="retired production marker"):
        WHEEL_GATE.validate_wheel(ROOT, _wheel(tmp_path, "legacy"))


def test_gate_requires_a_gitless_source_and_has_no_static_blacklist(tmp_path: Path) -> None:
    source = (ROOT / "tools/wheel_gate.py").read_text(encoding="utf-8")
    assert "FORBIDDEN" not in source
    with pytest.raises(RuntimeError, match="without \\.git"):
        WHEEL_GATE.run_gate(ROOT, tmp_path / "dist", source_date_epoch=1_787_498_554)
