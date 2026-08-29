"""Shared pytest fixtures for the V4 test suite.

The production material fixture builds a complete, signed local-production
pack, trust context, and service identity inside the pytest temporary tree on
every session, using the same builders and HKDF identity derivation as the
repository tools. No test reads a fixed machine directory.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

import pytest

from compiler_core.canonical_serialization import canonical_bytes, parse_json_document

REPO = Path(__file__).resolve().parents[1]

# The installed-wheel admission harness copies this file into an isolated
# directory and sets JC_INSTALLED_ENV_ROOT; never collect it in source state.
if not os.environ.get("JC_INSTALLED_ENV_ROOT"):
    collect_ignore = ["packaging/test_installed_official_yaml.py"]


@dataclass(frozen=True)
class ProductionMaterial:
    root: Path
    identity_path: Path
    pack_path: Path
    trust_path: Path
    service_key_path: Path

    @property
    def pack_relative(self) -> str:
        return self.pack_path.relative_to(self.root).as_posix()

    @property
    def trust_relative(self) -> str:
        return self.trust_path.relative_to(self.root).as_posix()

    @property
    def service_key_relative(self) -> str:
        return self.service_key_path.relative_to(self.root).as_posix()


@pytest.fixture(scope="session")
def production_material(tmp_path_factory: pytest.TempPathFactory) -> ProductionMaterial:
    from tools.build_cn_official_pack import build_document
    from tools.build_local_production_pack import (
        LocalProductionPackBuilder,
        ensure_identity,
    )
    from tools.local_production import initialize_service_key

    root = tmp_path_factory.mktemp("production-material")
    identity_path = root / "identity" / "root.json"
    identity = ensure_identity(identity_path)
    source = parse_json_document(
        (REPO / "tests/fixtures/cn_official/pipl-source.json").read_bytes()
    )
    candidate = build_document(source)
    pack, trust = LocalProductionPackBuilder(candidate, identity).build()
    pack_path = root / "packs" / "cn-official-local-4.0.0.json"
    trust_path = root / "trust" / "cn-official-local.json"
    pack_path.parent.mkdir()
    trust_path.parent.mkdir()
    pack_path.write_bytes(canonical_bytes(pack))
    trust_path.write_bytes(canonical_bytes(trust))
    service_key_path = root / "identity" / "service-runtime.json"
    initialize_service_key(identity_path, service_key_path, trust_path)
    return ProductionMaterial(
        root=root,
        identity_path=identity_path,
        pack_path=pack_path,
        trust_path=trust_path,
        service_key_path=service_key_path,
    )
