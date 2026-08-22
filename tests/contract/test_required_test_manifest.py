"""Mutation tests for the V4 required-test manifest gate."""
from __future__ import annotations

import copy
import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "tests" / "required-v4-tests.json"
ISSUE_MAP = REPO / "remediation" / "v4" / "issue-map.json"
PLAN = REPO / "remediation" / "v4" / "tasks.json"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "remediate_v4_required_test_manifest", REPO / "tools" / "remediate_v4.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner()


def _baseline() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _problems(payload: dict) -> list[str]:
    return RUNNER._required_test_manifest_problems(
        payload,
        root=REPO,
        issue_map=json.loads(ISSUE_MAP.read_text(encoding="utf-8")),
        plan=json.loads(PLAN.read_text(encoding="utf-8")),
    )


def test_committed_required_test_manifest_is_structurally_valid() -> None:
    assert _problems(_baseline()) == []


def test_suite_taxonomy_is_exact_and_backed_by_tracked_skeletons() -> None:
    payload = _baseline()
    payload["suites"].pop()
    assert any("suite taxonomy" in problem for problem in _problems(payload))

    payload = _baseline()
    payload["suites"][0]["path"] = "tests/unit"
    assert any("suite path" in problem for problem in _problems(payload))

    payload = _baseline()
    payload["required_now"][1]["expected_tests"] = 1
    assert any("exact W0-04 executable set" in problem for problem in _problems(payload))


def test_every_audit_mutation_is_covered_exactly_once() -> None:
    payload = _baseline()
    payload["audit_mutations"].pop()
    assert any("audit mutation coverage" in problem for problem in _problems(payload))

    payload = _baseline()
    payload["audit_mutations"].append(copy.deepcopy(payload["audit_mutations"][0]))
    assert any("audit mutation coverage" in problem for problem in _problems(payload))

    payload = _baseline()
    payload["audit_mutations"][1]["selector"] = payload["audit_mutations"][0]["selector"]
    assert any("mutation selectors are duplicated" in problem for problem in _problems(payload))


def test_future_required_tests_are_explicit_red_work_owned_by_an_allowed_task() -> None:
    payload = _baseline()
    payload["audit_mutations"][0]["state"] = "PLANNED"
    payload["audit_mutations"][0]["red_failure"] = ""
    assert any("must be RED_AT_TASK" in problem for problem in _problems(payload))
    assert any("red failure" in problem for problem in _problems(payload))

    payload = _baseline()
    payload["audit_mutations"][0]["owner_task"] = "H6-02"
    assert any("AUTO owner task" in problem for problem in _problems(payload))

    payload = _baseline()
    payload["red_sentinel_selector"] = "tests/missing_red_sentinels.py"
    assert any("red sentinel" in problem for problem in _problems(payload))

    payload = _baseline()
    domain_patch = next(
        item for item in payload["audit_mutations"] if item["audit_id"] == "P1-07"
    )
    domain_patch["owner_task"] = "W4-07"
    assert any("registered closure task" in problem for problem in _problems(payload))


def test_self_contained_and_pinned_companion_oracles_remain_independent() -> None:
    payload = _baseline()
    payload["evidence_tracks"][1]["selector"] = payload["evidence_tracks"][0]["selector"]
    payload["evidence_tracks"][1]["source_kind"] = payload["evidence_tracks"][0]["source_kind"]
    assert any("differential evidence tracks" in problem for problem in _problems(payload))


def test_rewrite_queue_binds_live_wrong_behavior_to_an_allowed_replacement() -> None:
    payload = _baseline()
    payload["rewrite_at_task"][0]["selector"] = (
        "tests/unit/missing_wrong_behavior.py::test_missing"
    )
    assert any("canonical projection drifted" in problem for problem in _problems(payload))

    payload = _baseline()
    payload["rewrite_at_task"][0]["replacement_selector"] = (
        "compiler_core/not_a_test.py::test_wrong_scope"
    )
    assert any("replacement selector is outside" in problem for problem in _problems(payload))

    payload = _baseline()
    payload["rewrite_at_task"][1]["selector"] = payload["rewrite_at_task"][0]["selector"]
    assert any("rewrite selectors are duplicated" in problem for problem in _problems(payload))

    payload = _baseline()
    first = payload["rewrite_at_task"][8]
    second = payload["rewrite_at_task"][9]
    first["replacement_selector"], second["replacement_selector"] = (
        second["replacement_selector"], first["replacement_selector"]
    )
    assert any("canonical projection drifted" in problem for problem in _problems(payload))

    payload = _baseline()
    payload["rewrite_at_task"][-1]["retirement_task"] = "W5-03"
    assert any("after retirement" in problem for problem in _problems(payload))


def test_required_pytest_controls_reject_skip_xfail_and_unittest_bypasses(
    tmp_path: Path, monkeypatch,
) -> None:
    source = """
import pytest as pt
import unittest as ut
from pytest import importorskip as ios
from unittest import skipIf as usi
pytestmark = pt.mark.skip(reason="hidden")
pt.mark.skipif(True, reason="hidden")
pt.mark.xfail(reason="hidden")
pt.skip("runtime")
pt.xfail("runtime")
ios("missing")
ut.skip("hidden")
usi(True, "hidden")
ut.skipUnless(False, "hidden")
ut.expectedFailure
raise ut.SkipTest("hidden")
__unittest_skip__ = True

def nested_alias_bypass():
    import pytest as hidden_pt
    return hidden_pt.mark.xfail(strict=False)
"""
    assert set(RUNNER._forbidden_test_controls(source)) == {
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
        "pytest.importorskip",
        "pytest.skip",
        "pytest.xfail",
        "unittest.expectedFailure",
        "unittest.skip",
        "unittest.skipIf",
        "unittest.skipUnless",
        "unittest.SkipTest",
        "__unittest_skip__",
    }

    config_text = (REPO / "tests" / "pytest.ini").read_text(encoding="utf-8")
    assert RUNNER._pytest_config_problems(config_text, "required_red_sentinels.py") == []
    broad_discovery = config_text.replace(
        "python_files = test_*.py *_test.py", "python_files = *.py"
    )
    assert any(
        "discovery" in problem
        for problem in RUNNER._pytest_config_problems(
            broad_discovery, "required_red_sentinels.py"
        )
    )

    monkeypatch.setenv("PYTEST_ADDOPTS", "--runxfail")
    monkeypatch.setenv("PYTEST_PLUGINS", "hostile_plugin")
    monkeypatch.setenv("PYTHONPATH", "hostile-import-root")
    environment = RUNNER._required_pytest_environment()
    assert "PYTEST_ADDOPTS" not in environment
    assert "PYTEST_PLUGINS" not in environment
    assert "PYTHONPATH" not in environment
    assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert environment["PYTHONIOENCODING"] == "utf-8"

    stdout = tmp_path / "w0-04-stdout.bin"
    stdout.write_text(
        "JC_ARTIFACT\tw0-04-required-tests\tX:/state/evidence.json\tsha256:"
        + "a" * 64
        + "\n"
        "test governance skeleton OK: 11 suites; 44 audit groups registered; "
        "25 rewrites queued; 12 required governance tests passed; "
        "46 future obligations explicitly RED; 0 skip/xfail/xpass/collection errors\n",
        encoding="utf-8",
    )
    reports = RUNNER._structured_test_reports([{
        "argv": ["py", "tools/remediate_v4.py", "verify-wave", "W0-04"],
        "exit_code": 0,
        "stdout": {"path": str(stdout), "sha256": "b" * 64},
        "stderr": {"path": str(tmp_path / "stderr.bin"), "sha256": "c" * 64},
    }])
    assert reports == [{
        "command_index": 1,
        "kind": "pytest-governance",
        "exit_code": 0,
        "stdout_sha256": "b" * 64,
        "stderr_sha256": "c" * 64,
        "suites": 11,
        "audit_groups": 44,
        "rewrites": 25,
        "required_passed": 12,
        "future_red": 46,
        "bypass_or_collection_errors": 0,
        "evidence_label": "w0-04-required-tests",
        "evidence_sha256": "sha256:" + "a" * 64,
    }]
    empty_stdout = tmp_path / "old-w0-04-stdout.bin"
    empty_stdout.write_bytes(b"")
    assert RUNNER._structured_test_reports([{
        "argv": ["py", "tools/remediate_v4.py", "verify-wave", "W0-04"],
        "exit_code": 4,
        "stdout": {"path": str(empty_stdout), "sha256": "d" * 64},
        "stderr": {"path": str(tmp_path / "old-stderr.bin"), "sha256": "e" * 64},
    }]) == []

    evidence_path, evidence_digest = RUNNER._write_content_addressed_json(
        tmp_path / "evidence", {"test": "immutable"}
    )
    repeated_path, repeated_digest = RUNNER._write_content_addressed_json(
        tmp_path / "evidence", {"test": "immutable"}
    )
    assert repeated_path == evidence_path
    assert repeated_digest == evidence_digest
    assert evidence_path.name == evidence_digest.removeprefix("sha256:") + ".json"

    expected = {
        "V4-P0-01-EXAMPLE": "UNIMPLEMENTED:V4-P0-01-EXAMPLE:W4-05",
        "V4-P0-02-EXAMPLE": "UNIMPLEMENTED:V4-P0-02-EXAMPLE:W4-07",
    }

    def case(red_id: str, failure_text: str) -> ET.Element:
        item = ET.Element(
            "testcase",
            name=f"test_red_at_task_is_explicitly_unimplemented[{red_id}]",
        )
        ET.SubElement(item, "failure", message=failure_text)
        return item

    counts = {"tests": 2, "skipped": 0, "failures": 2, "errors": 0}
    valid = [case(red_id, marker) for red_id, marker in expected.items()]
    assert RUNNER._red_junit_problems(counts, valid, expected) == []

    cross_bound = [
        case("V4-P0-01-EXAMPLE", " ".join(expected.values())),
        case("V4-P0-02-EXAMPLE", "arbitrary failure"),
    ]
    assert any(
        "uniquely bound" in problem
        for problem in RUNNER._red_junit_problems(counts, cross_bound, expected)
    )
