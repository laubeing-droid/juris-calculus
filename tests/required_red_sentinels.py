"""Explicit RED_AT_TASK failures; selected only by the W0-04 verifier."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


MANIFEST = Path(__file__).with_name("required-v4-tests.json")
PAYLOAD = json.loads(MANIFEST.read_text(encoding="utf-8"))


def _red_obligations() -> list[tuple[str, str]]:
    obligations = [
        (item["id"], item["owner_task"])
        for item in PAYLOAD["evidence_tracks"]
        if item["state"] == "RED_AT_TASK"
    ]
    obligations.extend(
        (item["test_id"], item["owner_task"])
        for item in PAYLOAD["audit_mutations"]
        if item["state"] == "RED_AT_TASK"
    )
    return obligations


RED_OBLIGATIONS = _red_obligations()


@pytest.mark.parametrize(
    ("red_id", "owner_task"),
    RED_OBLIGATIONS,
    ids=[red_id for red_id, _ in RED_OBLIGATIONS],
)
def test_red_at_task_is_explicitly_unimplemented(red_id: str, owner_task: str) -> None:
    pytest.fail(f"UNIMPLEMENTED:{red_id}:{owner_task}", pytrace=False)
