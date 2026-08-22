"""Differential and identity properties for the V4 canonical byte authority."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from hypothesis import given, settings, strategies as st

from compiler_core.canonical_serialization import canonical_bytes, digest_value, semantic_digest


REPO = Path(__file__).parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "golden" / "jcs-v4-vectors.json"
NODE_ORACLE = REPO / "tests" / "contract" / "jcs_node_oracle.mjs"
SAFE_INTEGER = st.integers(min_value=-(2**53) + 1, max_value=(2**53) - 1)
JSON_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    max_size=10,
)
JSON_SCALAR = st.none() | st.booleans() | SAFE_INTEGER | JSON_TEXT
JSON_VALUE = st.recursive(
    JSON_SCALAR,
    lambda children: st.lists(children, max_size=4)
    | st.dictionaries(JSON_TEXT, children, max_size=4),
    max_leaves=16,
)
JSON_DOCUMENT = st.lists(JSON_VALUE, max_size=4) | st.dictionaries(
    JSON_TEXT, JSON_VALUE, max_size=4
)


@given(value=JSON_DOCUMENT)
@settings(max_examples=24, deadline=None, derandomize=True)
def test_rfc8785_cross_language_property_vectors(value: object) -> None:
    node = shutil.which("node")
    assert node is not None, "Node 22/24 contract oracle is required"
    encoded = canonical_bytes(value)
    frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))
    dynamic = {
        "schema_version": frozen["schema_version"],
        "digest_grammar": frozen["digest_grammar"],
        "integer_minimum": frozen["integer_minimum"],
        "integer_maximum": frozen["integer_maximum"],
        "positive": [
            {
                "id": "hypothesis-document",
                "input": value,
                "canonical_utf8_hex": encoded.hex(),
                "sha256": str(digest_value(value)),
            }
        ],
        "negative": frozen["negative"],
    }
    with tempfile.TemporaryDirectory(prefix="jc-w1-jcs-") as temporary:
        path = Path(temporary) / "dynamic-jcs-vectors.json"
        path.write_text(json.dumps(dynamic, ensure_ascii=False) + "\n", encoding="utf-8")
        checked = subprocess.run(
            [node, str(NODE_ORACLE), str(path)],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert checked.returncode == 0, checked.stderr


def test_every_identity_field_changes_digest() -> None:
    baseline = {
        "request_digest": "sha256:" + "0" * 64,
        "engine_digest": "sha256:" + "1" * 64,
        "schema_digest": "sha256:" + "2" * 64,
        "tool_spec_digest": "sha256:" + "3" * 64,
        "pack_digest": "sha256:" + "4" * 64,
        "trust_policy_digest": "sha256:" + "5" * 64,
        "algorithm_profile_digest": "sha256:" + "6" * 64,
        "lock_digest": "sha256:" + "7" * 64,
    }

    for index, field in enumerate(baseline, start=8):
        replacement = "sha256:" + format(index, "x") * 64
        changed = {**baseline, field: replacement}
        assert digest_value(changed) != digest_value(baseline), field
        assert semantic_digest(changed) != semantic_digest(baseline), field


@given(value=JSON_DOCUMENT)
@settings(max_examples=100, deadline=None, derandomize=True)
def test_canonicalization_is_idempotent_and_does_not_mutate(value: object) -> None:
    snapshot = json.loads(json.dumps(value, ensure_ascii=False))
    first = canonical_bytes(value)

    assert canonical_bytes(json.loads(first)) == first
    assert value == snapshot
