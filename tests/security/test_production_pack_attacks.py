from __future__ import annotations

from base64 import b64decode, b64encode
from pathlib import Path

import pytest

from compiler_core.canonical_serialization import canonical_bytes, parse_json_document
from compiler_core.contracts import CanonicalTimeV4, ContractV4Error
from compiler_core.production_pack import load_production_pack


PRODUCTION = Path(r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-production-state")


def _copies(tmp_path: Path) -> tuple[Path, Path, Path]:
    paths = tuple(tmp_path / name for name in ("pack.json", "trust.json", "key.json"))
    sources = (
        PRODUCTION / "packs/cn-official-local-4.0.0.json",
        PRODUCTION / "trust/cn-official-local.json",
        PRODUCTION / "identity/service-runtime.json",
    )
    for source, target in zip(sources, paths, strict=True):
        target.write_bytes(source.read_bytes())
    return paths


def _rewrite(path: Path, edit) -> None:
    value = parse_json_document(path.read_bytes())
    edit(value)
    path.write_bytes(canonical_bytes(value))


def test_pack_artifact_bit_flip_is_rejected(tmp_path: Path) -> None:
    pack, trust, key = _copies(tmp_path)

    def flip(value):
        raw = bytearray(b64decode(value["artifacts"][0]["content_base64"], validate=True))
        raw[0] ^= 1
        value["artifacts"][0]["content_base64"] = b64encode(raw).decode("ascii")

    _rewrite(pack, flip)
    with pytest.raises(ContractV4Error):
        load_production_pack(pack, trust, key)


def test_service_private_key_bit_flip_is_rejected(tmp_path: Path) -> None:
    pack, trust, key = _copies(tmp_path)

    def flip(value):
        raw = bytearray(b64decode(value["private_seed_base64"], validate=True))
        raw[0] ^= 1
        value["private_seed_base64"] = b64encode(raw).decode("ascii")

    _rewrite(key, flip)
    with pytest.raises(ContractV4Error, match="PRODUCTION_SERVICE_KEY_MISMATCH"):
        load_production_pack(pack, trust, key)


def test_expiry_is_checked_against_current_time_not_build_time(tmp_path: Path) -> None:
    pack, trust, key = _copies(tmp_path)
    with pytest.raises(ContractV4Error, match="TRUST_POLICY_INACTIVE"):
        load_production_pack(
            pack, trust, key, now=CanonicalTimeV4("2037-01-01T00:00:00Z")
        )


def test_revoked_or_nonproduction_service_key_is_rejected(tmp_path: Path) -> None:
    pack, trust, key = _copies(tmp_path)

    def revoke(value):
        value["trust_policy"]["trusted_key_ids"].remove("local-production-release-key")
        value["trust_policy"]["revoked_key_ids"].append("local-production-release-key")

    _rewrite(trust, revoke)
    with pytest.raises(ContractV4Error):
        load_production_pack(pack, trust, key)


def test_loader_has_no_tools_or_tests_dependency() -> None:
    source = (Path(__file__).parents[2] / "compiler_core/production_pack.py").read_text("utf-8")
    assert "from tools" not in source
    assert "import tools" not in source
    assert "from tests" not in source
