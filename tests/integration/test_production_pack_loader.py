from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from compiler_core.canonical_serialization import DigestV4
from compiler_core.contracts import CanonicalTimeV4, ContractV4Error
from compiler_core.production_pack import ProductionIdentityPinsV4, load_production_pack


PRODUCTION = Path(r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus-v4-production-state")


def _load(**kwargs):
    return load_production_pack(
        PRODUCTION / "packs/cn-official-local-4.0.0.json",
        PRODUCTION / "trust/cn-official-local.json",
        PRODUCTION / "identity/service-runtime.json",
        **kwargs,
    )


def test_real_local_pack_loads_six_formal_rules_at_current_time() -> None:
    loaded = _load()
    assert loaded.formal_rule_ids == (
        "PIPL-ART-013", "PIPL-ART-014", "PIPL-ART-015",
        "PIPL-ART-016", "PIPL-ART-017", "PIPL-ART-018",
    )
    assert loaded.verified_at != CanonicalTimeV4.from_dict(
        __import__("json").loads((PRODUCTION / "trust/cn-official-local.json").read_text("utf-8"))[
            "verification_time"
        ]
    )
    trusted = next(key for key in loaded.keys if key.key_id == loaded.service_key.key_id)
    assert trusted.public_key == loaded.service_key.public_key


def test_runtime_loader_never_reads_root_seed() -> None:
    opened: list[Path] = []
    original = Path.read_bytes

    def monitored(path: Path) -> bytes:
        opened.append(path)
        return original(path)

    with patch.object(Path, "read_bytes", monitored):
        _load()
    assert PRODUCTION / "identity/root.json" not in opened
    assert PRODUCTION / "identity/service-runtime.json" in opened


def test_installed_identity_drift_is_rejected() -> None:
    loaded = _load()
    wrong = ProductionIdentityPinsV4(
        loaded.identity.engine_api,
        DigestV4.from_bytes(b"wrong-build"),
        loaded.identity.source_tree_digest,
        loaded.identity.schema_digest,
    )
    with pytest.raises(ContractV4Error, match="PRODUCTION_IDENTITY_DRIFT"):
        _load(expected_identity=wrong)
