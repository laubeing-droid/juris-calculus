#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.relevance_dataset_builder import load_manifest, sample_dataset, validate_dataset


def test_manifest_loads():
    manifest = load_manifest()
    assert manifest["version"] == "1.0.0"
    assert "contract" in manifest["domains"]
    assert "SHOULD_NOT_CHANGE" in manifest["kinds"]


def test_validate_existing_fixtures_passes():
    report = validate_dataset("tests/relevance_sensitivity")
    assert report["status"] == "PASS"
    assert report["case_count"] >= 1
    assert "SHOULD_NOT_CHANGE" in report["by_kind"]


def test_validate_empty_directory_warns(tmp_path):
    report = validate_dataset(str(tmp_path))
    assert report["case_count"] == 0
    assert report["fixture_count"] == 0
    assert not any(f["issue"].startswith("UNKNOWN_") for f in report["findings"])


def test_validate_flags_unknown_kind(tmp_path):
    fixture = tmp_path / "bad.yaml"
    fixture.write_text(yaml.safe_dump({"cases": [{"id": "c1", "kind": "BAD_KIND", "split": "gold"}]}, allow_unicode=True), encoding="utf-8")
    report = validate_dataset(str(tmp_path))
    assert any("UNKNOWN_KIND" in f["issue"] for f in report["findings"])


def test_sample_returns_subset(tmp_path):
    fixture = tmp_path / "sample.yaml"
    cases = [{"id": f"c{i}", "kind": "SHOULD_NOT_CHANGE", "split": "gold", "domain": "contract"} for i in range(10)]
    fixture.write_text(yaml.safe_dump({"cases": cases}, allow_unicode=True), encoding="utf-8")
    report = sample_dataset(str(tmp_path), size=5)
    assert report["sample_size"] == 5
    assert report["gold_available"] == 10
