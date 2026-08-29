"""Generated file-disposition contract: Git tracked python × module-authority."""
from __future__ import annotations

import json
from pathlib import Path

from tools.build_file_disposition import OUT, build_document, canonical_bytes
from tools.remediation.process import git_tracked_paths

REPO = Path(__file__).resolve().parents[2]


def test_document_covers_exactly_the_tracked_python_files() -> None:
    document = build_document(REPO)
    tracked = git_tracked_paths(REPO, "*.py")
    assert document["schema_version"] == "jc/file-disposition/2.0"
    assert document["count"] == len(tracked) == len(document["paths"])
    assert [row["path"] for row in document["paths"]] == tracked
    assert all(set(row) == {"path", "authority_class", "production_wheel"} for row in document["paths"])


def test_classes_and_wheel_flags_match_module_authority() -> None:
    document = build_document(REPO)
    policy = json.loads(
        (REPO / "docs/architecture/module-authority.json").read_text(encoding="utf-8")
    )
    classes = policy["classes"]
    for row in document["paths"]:
        assert row["authority_class"] in classes
        expected = bool(classes[row["authority_class"]]["production_wheel"])
        assert row["production_wheel"] is expected


def test_retired_zero_consumer_modules_are_absent() -> None:
    document = build_document(REPO)
    retired = {
        "compiler_core/classifier.py", "compiler_core/smt_sidecar.py",
        "compiler_core/validity_state_machine.py", "compiler_core/review_packet.py",
    }
    assert not retired & {row["path"] for row in document["paths"]}


def test_committed_file_is_current() -> None:
    document = build_document(REPO)
    assert OUT.is_file()
    assert OUT.read_bytes() == canonical_bytes(document)
