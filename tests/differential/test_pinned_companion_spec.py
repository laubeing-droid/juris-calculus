"""B02-bound differential oracle that never needs a personal checkout."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import compiler_core.spec_shadow_harness as shadow


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests/fixtures/companion_spec"
LIST_FIELDS = (
    "facts",
    "horn_rules_fired",
    "arguments_constructed",
    "attacks_constructed",
    "attack_kinds",
    "accepted_argument_ids",
)
SCALAR_FIELDS = ("schema_version", "status", "fail_closed_reason")


def _load() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    oracle = json.loads((FIXTURE_ROOT / "oracle.json").read_text(encoding="utf-8"))
    return manifest, oracle


def _differences(expected: Mapping[str, Any], observed: Mapping[str, Any]) -> list[str]:
    differences = [
        field for field in SCALAR_FIELDS if expected.get(field) != observed.get(field)
    ]
    differences.extend(
        field
        for field in LIST_FIELDS
        if sorted(set(expected.get(field, []))) != sorted(set(observed.get(field, [])))
    )
    return differences


def _current_cases() -> list[dict[str, Any]]:
    fixtures = (
        shadow._build_contract_fixture(False),
        shadow._build_contract_fixture(True),
        shadow._build_license_fixture(True),
        shadow._build_license_fixture(False),
        shadow._build_tort_fixture(False),
        shadow._build_tort_fixture(True),
        shadow._build_criminal_fixture(False),
        shadow._build_criminal_fixture(True),
        shadow._build_admin_fixture(True),
        shadow._build_admin_fixture(False),
    )
    return [shadow.build_jc_shadow_payload(fixture) for fixture in fixtures]


def test_companion_oracle_is_available_without_personal_checkout(
    monkeypatch,
) -> None:
    monkeypatch.delenv("LEGAL_MATH_MODELING_ROOT", raising=False)
    manifest, oracle = _load()
    raw = (FIXTURE_ROOT / "oracle.json").read_bytes()
    source = manifest["source"]

    assert manifest["schema_version"] == "jc/pinned-companion-fixture/1.0"
    assert source["commit"] == "a3a015941f75091c87d57aa956e712f1546dd7d4"
    assert source["tree"] == "2d0b1bb9c4f4cd82a9a4452b96ab1d05c0d1ed99"
    assert manifest["oracle_sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert (FIXTURE_ROOT / "NOTICE.md").is_file()
    assert oracle["source_commit"] == source["commit"]
    assert len(oracle["cases"]) == 10
    assert len({(row["fixture_id"], row["variant"]) for row in oracle["cases"]}) == 10
    assert "spec_repo_root" not in json.dumps((manifest, oracle)).lower()


def test_pinned_companion_oracle_detects_mutations(monkeypatch) -> None:
    monkeypatch.setattr(
        shadow,
        "_load_spec_modules",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("external load")),
    )
    _, oracle = _load()
    expected = {
        (row["fixture_id"], row["variant"]): row for row in oracle["cases"]
    }
    observed = {
        (row["fixture_id"], row["variant"]): row for row in _current_cases()
    }
    assert set(observed) == set(expected)
    assert all(_differences(expected[key], observed[key]) == [] for key in expected)

    for field in (*SCALAR_FIELDS, *LIST_FIELDS):
        mutated = deepcopy(observed[("contract_breach", "plain")])
        if field in LIST_FIELDS:
            mutated[field] = [*mutated[field], "MUTATED"]
        else:
            mutated[field] = "MUTATED"
        assert field in _differences(expected[("contract_breach", "plain")], mutated)
