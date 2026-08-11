"""W1b-JC 合同测试：四件 schema、capabilities、JCS golden vectors、schema digest。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler_core import cli
from compiler_core.jcs import jcs, jcs_digest
from compiler_core.version import __version__

ROOT = Path(__file__).resolve().parents[2]
W1B_SCHEMAS = ROOT / "schemas" / "w1b"
GOLDEN = ROOT / "tests" / "fixtures" / "golden" / "jcs-vectors.json"


def _load(name: str):
    return json.loads((W1B_SCHEMAS / name).read_text(encoding="utf-8"))


class TestJcsGoldenVectors:
    def test_all_vectors_byte_exact(self):
        data = json.loads(GOLDEN.read_text(encoding="utf-8"))
        for v in data["vectors"]:
            assert jcs(v["input"]) == v["expected"], "JCS mismatch for %s" % v["name"]

    def test_top_level_scalar_rejected(self):
        for bad in [None, True, "x", 1, 1.5]:
            with pytest.raises(ValueError):
                jcs(bad)

    def test_circular_rejected(self):
        a: dict = {}
        a["self"] = a
        with pytest.raises(ValueError):
            jcs(a)

    def test_digest_format(self):
        d = jcs_digest({"a": 1})
        assert d.startswith("sha256-")
        assert len(d) == 7 + 64


class TestW1bSchemas:
    def test_all_four_schemas_present_and_valid(self):
        for name in ["case-request", "proof-bundle-ref", "rule-admission-request", "admission-result"]:
            doc = _load(name + ".schema.json")
            assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"
            assert doc["type"] == "object"
            assert doc["additionalProperties"] is False
            assert isinstance(doc["required"], list)

    def test_case_request_required_fields(self):
        doc = _load("case-request.schema.json")
        assert doc["properties"]["schema_version"]["const"] == "3.0"
        assert "facts" in doc["required"]

    def test_admission_result_produced_by_const_jc(self):
        doc = _load("admission-result.schema.json")
        assert doc["properties"]["produced_by"]["const"] == "jc"
        assert "result_digest" in doc["required"]

    def test_schema_digests_are_stable(self):
        digests = {name: jcs_digest(_load(name)) for name in
                   ["case-request.schema.json", "proof-bundle-ref.schema.json",
                    "rule-admission-request.schema.json", "admission-result.schema.json"]}
        again = {name: jcs_digest(_load(name)) for name in digests}
        assert digests == again
        assert all(v.startswith("sha256-") for v in digests.values())


class TestCapabilitiesCli:
    def test_capabilities_json_output(self, capsys):
        assert cli.main(["capabilities", "--json"]) == cli.EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["product_id"] == "jc"
        assert payload["contract_version"] == "1.0.0"
        assert payload["product_version"] == __version__
        assert "capabilities" in payload
        assert payload["capabilities"]["read_only"]
        assert payload["capabilities"]["writable"]
        assert len(payload["schema_digests"]) == 4

    def test_capabilities_schema_digests_match_files(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert cli.main(["capabilities", "--json"]) == cli.EXIT_OK
        payload = json.loads(buf.getvalue())
        expected = {name: jcs_digest(_load(name)) for name in
                    ["case-request.schema.json", "proof-bundle-ref.schema.json",
                     "rule-admission-request.schema.json", "admission-result.schema.json"]}
        assert payload["schema_digests"] == expected
