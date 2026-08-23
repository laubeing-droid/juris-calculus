"""Mutation tests for the V4 required-test manifest gate."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace


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
    payload = _baseline()
    assert _problems(payload) == []
    application_required = [
        (item["id"], item["suite"], item["expected_tests"])
        for item in payload["required_now"]
        if item["id"].startswith("W4-APPLICATION-")
    ]
    assert application_required == [
        ("W4-APPLICATION-CONTRACT", "contract", 7),
        ("W4-APPLICATION-FORMAL-E2E", "formal_e2e", 2),
        ("W4-APPLICATION-ATTACKS", "security", 1),
    ]
    runtime_required = [
        (item["id"], item["suite"], item["expected_tests"])
        for item in payload["required_now"]
        if item["id"].startswith("W4-RUNTIME-")
    ]
    assert runtime_required == [
        ("W4-RUNTIME-PRIVACY-FIREWALL", "security", 7),
        ("W4-RUNTIME-RESOURCE-LIMITS", "security", 7),
    ]
    vertical_required = [
        (item["id"], item["suite"], item["expected_tests"])
        for item in payload["required_now"]
        if item["id"].startswith("W4-VERTICAL-")
    ]
    assert vertical_required == [
        ("W4-VERTICAL-POSITIVE", "formal_e2e", 3),
        ("W4-VERTICAL-PUBLIC-INPUTS", "formal_e2e", 7),
        ("W4-VERTICAL-ATTACKS", "security", 8),
        ("W4-VERTICAL-RECOVERY", "storage_chaos", 3),
    ]
    formal_wheel = next(
        item for item in payload["required_now"]
        if item["id"] == "W6-FORMAL-WHEEL-GATE"
    )
    assert (
        formal_wheel["suite"], formal_wheel["selector"],
        formal_wheel["expected_tests"],
    ) == ("packaging", "tests/packaging/test_wheel_gate_v4.py", 9)
    hash_locks = next(
        item for item in payload["required_now"] if item["id"] == "W6-HASH-LOCKS"
    )
    assert (
        hash_locks["suite"], hash_locks["selector"], hash_locks["expected_tests"],
    ) == ("packaging", "tests/packaging/test_hash_locks.py", 9)
    installed_wheel = next(
        item for item in payload["required_now"]
        if item["id"] == "W6-INSTALLED-WHEEL-E2E"
    )
    assert (
        installed_wheel["suite"], installed_wheel["selector"],
        installed_wheel["expected_tests"],
    ) == ("packaging", "tests/packaging/test_wheel_exact_set.py", 8)
    mutations = {
        item["test_id"]: (item["owner_task"], item["state"], item["selector"])
        for item in payload["audit_mutations"]
    }
    assert mutations["V4-P0-01-ENTRYPOINT-V3"] == (
        "W5-CUTOVER",
        "ACTIVE_REQUIRED",
        "tests/formal_e2e/w5_entrypoint_red.py::test_public_entrypoints_reject_v3_route",
    )
    assert mutations["V4-P0-09-MCP-ERROR-SEMANTICS"] == (
        "W5-01",
        "ACTIVE_REQUIRED",
        "tests/mcp_protocol/w5_transport_red.py::"
        "test_blocked_and_engine_error_are_protocol_errors",
    )
    assert mutations["V4-P0-14-WHEEL-INJECTION"] == (
        "W6-04",
        "ACTIVE_REQUIRED",
        "tests/packaging/test_wheel_exact_set.py::"
        "test_nonformal_module_injection_fails_exact_record_gate",
    )
    assert mutations["V4-P0-02-POSITIVE-PRODUCTION"] == (
        "W4-07",
        "ACTIVE_REQUIRED",
        "tests/formal_e2e/test_positive_vertical_slice.py::"
        "test_signed_pack_produces_verified_result",
    )
    assert mutations["V4-P0-08-ADVISORY-BOOLEAN"][:2] == (
        "W4-05", "ACTIVE_REQUIRED",
    )
    assert mutations["V4-P1-07-DOMAIN-PATCH"] == (
        "W4-05",
        "ACTIVE_REQUIRED",
        "tests/contract/test_application.py::"
        "test_signed_domain_config_has_no_global_fallback",
    )
    assert mutations["V4-P1-15-RESOURCE-BUDGET"][:2] == (
        "W5-CUTOVER",
        "RED_AT_TASK",
    )
    assert mutations["V4-P1-17-PATH-PRIVACY"] == (
        "W4-06",
        "ACTIVE_REQUIRED",
        "tests/security/test_privacy_firewall.py::"
        "test_capabilities_and_errors_never_leak_absolute_paths",
    )
    assert mutations["V4-P1-18-STORAGE-ERROR-CLASS"] == (
        "W4-06",
        "ACTIVE_REQUIRED",
        "tests/security/test_privacy_firewall.py::"
        "test_enospc_and_eacces_keep_retryable_storage_class",
    )
    assert mutations["V4-P1-19-WHEEL-POSITIVE-SET"] == (
        "W6-01",
        "ACTIVE_REQUIRED",
        "tests/packaging/test_wheel_gate_v4.py::"
        "test_exact_synthetic_wheel_is_accepted",
    )
    assert mutations["V4-P2-06-NO-GIT-ARCHIVE"] == (
        "W6-01",
        "ACTIVE_REQUIRED",
        "tests/packaging/test_wheel_gate_v4.py::"
        "test_gate_requires_a_gitless_source_and_has_no_static_blacklist",
    )
    assert mutations["V4-P1-20-HASH-LOCKS"] == (
        "W6-03",
        "ACTIVE_REQUIRED",
        "tests/packaging/test_hash_locks.py::test_all_profiles_are_transitively_hash_locked",
    )
    assert mutations["V4-P2-03-DERIVED-TRUST"] == (
        "W5-01",
        "ACTIVE_REQUIRED",
        "tests/formal_e2e/w5_entrypoint_red.py::"
        "test_vertical_slice_derives_trust_instead_of_accepting_caller_pass",
    )
    w6_04_task = next(
        item for item in json.loads(PLAN.read_text(encoding="utf-8"))["tasks"]
        if item["id"] == "W6-04"
    )
    assert w6_04_task["allowed_paths"] == list(RUNNER.W6_04_ALLOWED_PATHS)
    assert w6_04_task["terminal_states"] == [
        "LOCKED_DUAL_BUILD_IDENTICAL", "CLEAN_INSTALLED_WHEEL_E2E_GREEN",
    ]
    assert RUNNER._w6_04_contract_problems() == []


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
    active = next(
        item for item in payload["audit_mutations"] if item["owner_task"] == "W1-01"
    )
    active["state"] = "PLANNED"
    active["red_failure"] = ""
    assert any(
        "must be RED_AT_TASK or ACTIVE_REQUIRED" in problem
        for problem in _problems(payload)
    )
    assert any("red failure" in problem for problem in _problems(payload))

    payload = _baseline()
    active = next(
        item for item in payload["audit_mutations"] if item["owner_task"] == "W1-01"
    )
    active["state"] = "RED_AT_TASK"
    assert any(
        "claims RED_AT_TASK but selector is active" in problem
        for problem in _problems(payload)
    )

    payload = _baseline()
    future = next(
        item for item in payload["audit_mutations"] if item["state"] == "RED_AT_TASK"
    )
    future["state"] = "ACTIVE_REQUIRED"
    assert any(
        "claims ACTIVE_REQUIRED but selector is not declared" in problem
        for problem in _problems(payload)
    )

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
    monkeypatch.setenv("LEGAL_MATH_MODELING_ROOT", "hostile-companion-root")
    environment = RUNNER._required_pytest_environment()
    assert "PYTEST_ADDOPTS" not in environment
    assert "PYTEST_PLUGINS" not in environment
    assert "PYTHONPATH" not in environment
    assert "LEGAL_MATH_MODELING_ROOT" not in environment
    assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert environment["PYTHONIOENCODING"] == "utf-8"

    companion = tmp_path / "state" / "inputs" / "legal-math-modeling"
    reference = companion / "theory" / "spec" / "reference_semantics.py"
    certificate = companion / "theory" / "spec" / "certificate_schema.py"
    reference.parent.mkdir(parents=True)
    reference.write_text("REFERENCE = 1\n", encoding="utf-8")
    certificate.write_text("CERTIFICATE = 1\n", encoding="utf-8")

    def companion_git(*argv: str) -> str:
        return subprocess.run(
            ["git", "-C", str(companion), *argv],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    subprocess.run(
        ["git", "init", "--quiet", str(companion)],
        capture_output=True,
        text=True,
        check=True,
    )
    companion_git("add", ".")
    companion_git(
        "-c", "user.name=V4 Test", "-c", "user.email=v4@example.invalid",
        "commit", "--quiet", "-m", "pinned",
    )
    companion_binding = {
        "commit": companion_git("rev-parse", "HEAD"),
        "tree": companion_git("rev-parse", "HEAD^{tree}"),
        "required_files": {
            "theory/spec/reference_semantics.py": RUNNER.sha256_hex(reference.read_bytes()),
            "theory/spec/certificate_schema.py": RUNNER.sha256_hex(certificate.read_bytes()),
        },
    }
    assert RUNNER._companion_checkout_problems(companion, companion_binding) == []
    assert RUNNER._companion_checkout_problems(
        tmp_path / "missing-companion", companion_binding,
    ) == ["pinned companion checkout is missing"]

    production_companion_binding = RUNNER.W0_B02_COMPANION_BINDING
    monkeypatch.setattr(RUNNER, "W0_B02_COMPANION_BINDING", companion_binding)
    attempt_dir = tmp_path / "companion-attempt"
    attempt_dir.mkdir()
    companion_command = RUNNER._run_argv(
        [
            "{python}", "-B", "-c",
            "import os; print(os.environ['LEGAL_MATH_MODELING_ROOT'])",
            "tests/unit/test_spec_shadow_harness.py",
        ],
        0,
        attempt_dir,
        1,
        30,
        tmp_path / "state",
    )
    assert companion_command["exit_code"] == 0
    assert Path(companion_command["stdout"]["path"]).read_text(
        encoding="utf-8",
    ).strip() == str(companion.resolve())

    reference.write_text("REFERENCE = 2\n", encoding="utf-8")
    dirty_problems = RUNNER._companion_checkout_problems(companion, companion_binding)
    assert "pinned companion checkout is dirty" in dirty_problems
    assert any("required file drifted" in item for item in dirty_problems)
    dirty_command = RUNNER._run_argv(
        [
            "{python}", "-B", "-c", "raise SystemExit(0)",
            "tests/unit/test_spec_shadow_harness.py",
        ],
        0,
        attempt_dir,
        2,
        30,
        tmp_path / "state",
    )
    assert dirty_command["exit_code"] == RUNNER.EXIT_GATE_FAIL
    assert "dirty" in Path(dirty_command["stderr"]["path"]).read_text(encoding="utf-8")

    reference.write_text("REFERENCE = 1\n", encoding="utf-8")
    extra = companion / "extra.txt"
    extra.write_text("new tree\n", encoding="utf-8")
    companion_git("add", "extra.txt")
    companion_git(
        "-c", "user.name=V4 Test", "-c", "user.email=v4@example.invalid",
        "commit", "--quiet", "-m", "repointed",
    )
    repointed = RUNNER._companion_checkout_problems(companion, companion_binding)
    assert "pinned companion commit drifted" in repointed
    assert "pinned companion tree drifted" in repointed
    monkeypatch.setattr(
        RUNNER, "W0_B02_COMPANION_BINDING", production_companion_binding,
    )

    stdout = tmp_path / "w0-04-stdout.bin"
    stdout.write_text(
        "JC_ARTIFACT\tw0-04-required-tests\tX:/state/evidence.json\tsha256:"
        + "a" * 64
        + "\n"
        "test governance skeleton OK: 11 suites; 44 audit groups registered; "
        "25 rewrites queued; 13 required governance tests passed; "
        "39 future obligations explicitly RED; 0 skip/xfail/xpass/collection errors\n",
        encoding="utf-8",
    )
    w0_governance_commands = [{
        "argv": ["py", "tools/remediate_v4.py", "verify-wave", "W0-04"],
        "exit_code": 0,
        "stdout": {"path": str(stdout), "sha256": "b" * 64},
        "stderr": {"path": str(tmp_path / "stderr.bin"), "sha256": "c" * 64},
    }]
    reports = RUNNER._structured_test_reports(w0_governance_commands)
    assert reports == [{
        "command_index": 1,
        "kind": "pytest-governance",
        "exit_code": 0,
        "stdout_sha256": "b" * 64,
        "stderr_sha256": "c" * 64,
        "suites": 11,
        "audit_groups": 44,
        "rewrites": 25,
        "required_passed": 13,
        "future_red": 39,
        "bypass_or_collection_errors": 0,
        "evidence_label": "w0-04-required-tests",
        "evidence_sha256": "sha256:" + "a" * 64,
    }]
    assert RUNNER._structured_test_reports(
        w0_governance_commands, runner_version="0.4.0"
    ) == []
    assert RUNNER._structured_test_reports(
        w0_governance_commands, runner_version="0.5.0"
    ) == reports
    empty_stdout = tmp_path / "old-w0-04-stdout.bin"
    empty_stdout.write_bytes(b"")
    assert RUNNER._structured_test_reports([{
        "argv": ["py", "tools/remediate_v4.py", "verify-wave", "W0-04"],
        "exit_code": 4,
        "stdout": {"path": str(empty_stdout), "sha256": "d" * 64},
        "stderr": {"path": str(tmp_path / "old-stderr.bin"), "sha256": "e" * 64},
    }]) == []

    w1_pytest_stdout = tmp_path / "w1-01-pytest-stdout.bin"
    w1_pytest_stdout.write_text("38 passed in 7.00s\n", encoding="utf-8")
    w1_node_stdout = tmp_path / "w1-01-node-stdout.bin"
    w1_node_stdout.write_text(
        "PASS jcs_node_oracle runtime=v24.16.0 "
        "schema_version=jc/v4-jcs-vectors/1.0 positive=9 negative=16 "
        "canonical_bytes=295 float_tokens=raw-lexical "
        "duplicate_key=declaration-only\n",
        encoding="utf-8",
    )
    w1_commands = [
        {
            "argv": ["py", "-m", "pytest", "tests/contract/test_jcs_v4.py"],
            "exit_code": 0,
            "stdout": {"path": str(w1_pytest_stdout), "sha256": "f" * 64},
            "stderr": {"path": str(tmp_path / "w1-pytest-stderr.bin"), "sha256": "0" * 64},
        },
        {
            "argv": ["node", "tests/contract/jcs_node_oracle.mjs", "vectors.json"],
            "exit_code": 0,
            "stdout": {"path": str(w1_node_stdout), "sha256": "1" * 64},
            "stderr": {"path": str(tmp_path / "w1-node-stderr.bin"), "sha256": "2" * 64},
        },
    ]
    w1_reports = RUNNER._structured_test_reports(w1_commands)
    assert RUNNER._w1_01_test_report_problems(w1_reports) == []
    assert all(
        field in w1_reports[0]
        for field in ("failed", "errors", "skipped", "xfailed", "xpassed", "collection_errors")
    )
    runner_0_7_reports = RUNNER._structured_test_reports(
        w1_commands,
        runner_version="0.7.0",
    )
    assert all(
        field not in runner_0_7_reports[0]
        for field in ("failed", "errors", "skipped", "xfailed", "xpassed", "collection_errors")
    )
    legacy_reports = RUNNER._structured_test_reports(
        w1_commands,
        runner_version="0.3.0",
    )
    assert "float_tokens" not in legacy_reports[1]
    assert "duplicate_key" not in legacy_reports[1]
    try:
        RUNNER._structured_test_reports(w1_commands, runner_version="0.44.0")
    except ValueError as exc:
        assert "unsupported structured report runner version" in str(exc)
    else:
        raise AssertionError("unknown runner versions must fail closed")
    assert RUNNER.KNOWN_RUNNER_VERSIONS == frozenset({
        "0.2.0", "0.2.1", "0.3.0", "0.4.0", "0.5.0", "0.6.0", "0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.20.0", "0.21.0", "0.22.0", "0.23.0", "0.24.0", "0.25.0", "0.26.0", "0.27.0", "0.28.0", "0.29.0", "0.30.0", "0.31.0", "0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0",
    })
    tampered_reports = copy.deepcopy(w1_reports)
    tampered_reports[0]["passed"] = 37
    tampered_reports[1]["runtime"] = "v23.0.0"
    assert len(RUNNER._w1_01_test_report_problems(tampered_reports)) == 2

    w1_02_stdout = tmp_path / "w1-02-pytest-stdout.bin"
    w1_02_stdout.write_text("173 passed in 3.00s\n", encoding="utf-8")
    w1_02_reports = RUNNER._structured_test_reports([{
        "argv": ["py", "-m", "pytest", "tests/contract/test_contracts.py"],
        "exit_code": 0,
        "stdout": {"path": str(w1_02_stdout), "sha256": "3" * 64},
        "stderr": {"path": str(tmp_path / "w1-02-stderr.bin"), "sha256": "4" * 64},
    }])
    assert any(
        "junit" in problem
        for problem in RUNNER._w1_02_test_report_problems(w1_02_reports)
    )
    w1_02_junit = tmp_path / "w1-02-junit.xml"
    w1_02_junit.write_text(
        '<testsuites><testsuite tests="1" skipped="0" failures="0" errors="0">'
        '<testcase classname="contract.test_contracts" name="test_probe" />'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    parsed_junit_report = RUNNER._structured_test_reports([{
        "argv": [
            "py", "-m", "pytest", "tests/contract/test_contracts.py",
            "--junitxml", str(w1_02_junit),
        ],
        "exit_code": 0,
        "stdout": {"path": str(w1_02_stdout), "sha256": "a" * 64},
        "stderr": {"path": str(tmp_path / "w1-02-stderr.bin"), "sha256": "b" * 64},
    }])[0]
    assert (
        parsed_junit_report["junit_valid"],
        parsed_junit_report["junit_tests"],
        parsed_junit_report["junit_cases"],
        parsed_junit_report["junit_unique_cases"],
    ) == (True, 1, 1, 1)
    w1_02_reports[0].update({
        "junit_valid": True,
        "junit_sha256": "9" * 64,
        "junit_tests": 173,
        "junit_skipped": 0,
        "junit_failures": 0,
        "junit_errors": 0,
        "junit_cases": 173,
        "junit_unique_cases": 173,
        "junit_case_ids_digest": RUNNER.W1_02_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w1_02_test_report_problems(w1_02_reports) == []

    w1_03_reports = copy.deepcopy(w1_02_reports)
    w1_03_reports[0].update({
        "passed": 237,
        "junit_tests": 237,
        "junit_cases": 237,
        "junit_unique_cases": 237,
        "junit_case_ids_digest": RUNNER.W1_03_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w1_03_test_report_problems(w1_03_reports) == []
    w1_03_reports[0]["junit_case_ids_digest"] = "sha256:" + "0" * 64
    assert RUNNER._w1_03_test_report_problems(w1_03_reports) == [
        "W1-03 pytest junit_case_ids_digest drifted: "
        f"{'sha256:' + '0' * 64!r} != {RUNNER.W1_03_TEST_CASE_IDS_DIGEST!r}"
    ]

    w1_04_reports = copy.deepcopy(w1_02_reports)
    w1_04_reports[0].update({
        "passed": 472,
        "junit_tests": 472,
        "junit_cases": 472,
        "junit_unique_cases": 472,
        "junit_case_ids_digest": RUNNER.W1_04_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w1_04_test_report_problems(w1_04_reports) == []
    w1_04_reports[0]["junit_cases"] = 471
    assert RUNNER._w1_04_test_report_problems(w1_04_reports) == [
        "W1-04 pytest junit_cases drifted: 471 != 472"
    ]

    w1_05_reports = copy.deepcopy(w1_02_reports)
    w1_05_reports[0].update({
        "passed": 36,
        "junit_tests": 36,
        "junit_cases": 36,
        "junit_unique_cases": 36,
        "junit_case_ids_digest": RUNNER.W1_05_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w1_05_test_report_problems(w1_05_reports) == []
    w1_05_reports[0]["junit_cases"] = 35
    assert RUNNER._w1_05_test_report_problems(w1_05_reports) == [
        "W1-05 pytest junit_cases drifted: 35 != 36"
    ]

    w1_06_reports = copy.deepcopy(w1_02_reports)
    w1_06_reports[0].update({
        "passed": 521,
        "junit_tests": 521,
        "junit_cases": 521,
        "junit_unique_cases": 521,
        "junit_case_ids_digest": RUNNER.W1_06_TEST_CASE_IDS_DIGEST,
    })
    w1_06_reports.append(copy.deepcopy(w1_reports[1]))
    assert RUNNER._w1_06_test_report_problems(w1_06_reports) == []
    w1_06_reports[1]["negative"] = 15
    assert RUNNER._w1_06_test_report_problems(w1_06_reports) == [
        "W1-06 Node oracle negative drifted: 15 != 16"
    ]

    w2_01_reports = copy.deepcopy(w1_02_reports)
    w2_01_reports[0].update({
        "passed": 31,
        "junit_tests": 31,
        "junit_cases": 31,
        "junit_unique_cases": 31,
        "junit_case_ids_digest": RUNNER.W2_01_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w2_01_test_report_problems(w2_01_reports) == []
    w2_01_reports[0]["junit_unique_cases"] = 30
    assert RUNNER._w2_01_test_report_problems(w2_01_reports) == [
        "W2-01 pytest junit_unique_cases drifted: 30 != 31"
    ]

    w2_02_reports = copy.deepcopy(w1_02_reports)
    w2_02_reports[0].update({
        "passed": RUNNER.W2_02_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W2_02_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W2_02_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W2_02_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W2_02_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w2_02_test_report_problems(w2_02_reports) == []
    w2_02_reports[0]["junit_failures"] = 1
    assert RUNNER._w2_02_test_report_problems(w2_02_reports) == [
        "W2-02 pytest junit_failures drifted: 1 != 0"
    ]

    w2_03_reports = copy.deepcopy(w1_02_reports)
    w2_03_reports[0].update({
        "passed": RUNNER.W2_03_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W2_03_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W2_03_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W2_03_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W2_03_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w2_03_test_report_problems(w2_03_reports) == []
    w2_03_reports[0]["junit_errors"] = 1
    assert RUNNER._w2_03_test_report_problems(w2_03_reports) == [
        "W2-03 pytest junit_errors drifted: 1 != 0"
    ]

    w2_04_reports = copy.deepcopy(w1_02_reports)
    w2_04_reports[0].update({
        "passed": RUNNER.W2_04_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W2_04_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W2_04_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W2_04_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W2_04_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w2_04_test_report_problems(w2_04_reports) == []
    w2_04_reports[0]["junit_skipped"] = 1
    assert RUNNER._w2_04_test_report_problems(w2_04_reports) == [
        "W2-04 pytest junit_skipped drifted: 1 != 0"
    ]
    w2_04_task = next(
        item
        for item in json.loads(RUNNER.DEFAULT_PLAN.read_text(encoding="utf-8"))["tasks"]
        if item["id"] == "W2-04"
    )
    assert RUNNER._auto_receipt_resume_problems(
        w2_04_task,
        {
            "command_results": [],
            "completion_assertions": [
                {"id": "all-commands-passed", "ok": True},
                {"id": "w2-04-exact-snapshot-reports", "ok": True},
                {"id": "w2-04-exact-committed-scope", "ok": True},
            ],
            "runner_version": RUNNER.RUNNER_VERSION,
        },
        tmp_path,
    ) == ["AUTO receipt command count does not match the task"]
    assert RUNNER._auto_receipt_resume_problems(
        w2_04_task,
        {
            "command_results": [],
            "completion_assertions": [
                {"id": "runner-state-artifact-recovery", "ok": True},
            ],
            "runner_version": RUNNER.RUNNER_VERSION,
        },
        tmp_path,
    ) == ["state-artifact recovery assertion is only valid for W1-06"]

    w2_05_reports = copy.deepcopy(w1_02_reports)
    w2_05_reports[0].update({
        "passed": RUNNER.W2_05_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W2_05_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W2_05_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W2_05_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W2_05_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w2_05_test_report_problems(w2_05_reports) == []
    w2_05_reports[0]["junit_errors"] = 1
    assert RUNNER._w2_05_test_report_problems(w2_05_reports) == [
        "W2-05 pytest junit_errors drifted: 1 != 0"
    ]
    w2_05_task = next(
        item
        for item in json.loads(RUNNER.DEFAULT_PLAN.read_text(encoding="utf-8"))["tasks"]
        if item["id"] == "W2-05"
    )
    assert RUNNER._expected_auto_completion_assertion_ids(
        w2_05_task,
        "w2-05-exact-synthetic-pack-reports",
        "w2-05-exact-fixture-binding",
        "w2-05-exact-committed-scope",
    ) == [
        "all-commands-passed",
        "runner-clean-worktree",
        "runner-committed-delta",
        "runner-state-artifacts",
        "w2-05-exact-synthetic-pack-reports",
        "w2-05-exact-fixture-binding",
        "w2-05-exact-committed-scope",
    ]
    assert RUNNER._auto_receipt_resume_problems(
        w2_05_task,
        {
            "command_results": [],
            "completion_assertions": [
                {"id": "all-commands-passed", "ok": True},
                {"id": "w2-05-exact-synthetic-pack-reports", "ok": True},
                {"id": "w2-05-exact-fixture-binding", "ok": True},
                {"id": "w2-05-exact-committed-scope", "ok": True},
            ],
            "runner_version": RUNNER.RUNNER_VERSION,
        },
        tmp_path,
    ) == ["AUTO receipt command count does not match the task"]
    assert RUNNER._auto_receipt_resume_problems(
        w2_05_task,
        {
            "command_results": [],
            "completion_assertions": [
                {"id": "runner-state-artifact-recovery", "ok": True},
            ],
            "runner_version": RUNNER.RUNNER_VERSION,
        },
        tmp_path,
    ) == ["state-artifact recovery assertion is only valid for W1-06"]

    w2_06_reports = copy.deepcopy(w1_02_reports)
    w2_06_reports[0].update({
        "passed": RUNNER.W2_06_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W2_06_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W2_06_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W2_06_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W2_06_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w2_06_test_report_problems(w2_06_reports) == []
    w2_06_reports[0]["passed"] -= 1
    assert RUNNER._w2_06_test_report_problems(w2_06_reports) == [
        "W2-06 pytest passed drifted: "
        f"{RUNNER.W2_06_TEST_CASE_COUNT - 1} != {RUNNER.W2_06_TEST_CASE_COUNT}"
    ]
    w2_06_reports[0]["passed"] = RUNNER.W2_06_TEST_CASE_COUNT
    wrong_w2_06_digest = "sha256:" + "f" * 64
    if wrong_w2_06_digest == RUNNER.W2_06_TEST_CASE_IDS_DIGEST:
        wrong_w2_06_digest = "sha256:" + "e" * 64
    w2_06_reports[0]["junit_case_ids_digest"] = wrong_w2_06_digest
    assert RUNNER._w2_06_test_report_problems(w2_06_reports) == [
        "W2-06 pytest junit_case_ids_digest drifted: "
        f"{wrong_w2_06_digest!r} != {RUNNER.W2_06_TEST_CASE_IDS_DIGEST!r}"
    ]
    w2_06_reports[0]["junit_case_ids_digest"] = RUNNER.W2_06_TEST_CASE_IDS_DIGEST
    w2_06_task = next(
        item
        for item in json.loads(RUNNER.DEFAULT_PLAN.read_text(encoding="utf-8"))["tasks"]
        if item["id"] == "W2-06"
    )
    assert list(RUNNER.W2_06_CHANGED_PATHS) == w2_06_task["allowed_paths"]
    w2_06_assertion_ids = [
        "all-commands-passed",
        "runner-clean-worktree",
        "runner-committed-delta",
        "runner-state-artifacts",
        "w2-06-exact-trust-chain-reports",
        "w2-06-exact-committed-scope",
    ]
    assert RUNNER._expected_auto_completion_assertion_ids(
        w2_06_task,
        "w2-06-exact-trust-chain-reports",
        "w2-06-exact-committed-scope",
    ) == w2_06_assertion_ids

    def stream(name: str, payload: bytes = b"") -> dict:
        path = tmp_path / f"{name}.bin"
        path.write_bytes(payload)
        return {"path": str(path), "sha256": RUNNER.sha256_hex(payload), "bytes": len(payload)}

    w2_06_commands = [
        {
            "argv": RUNNER._expanded_argv(argv, tmp_path),
            "expected_exit_code": expected,
            "exit_code": expected,
            "timed_out": False,
            "stdout": stream(f"w2-06-{index}-stdout"),
            "stderr": stream(f"w2-06-{index}-stderr"),
        }
        for index, (argv, expected) in enumerate(
            zip(w2_06_task["argv"], w2_06_task["expected_exit_codes"]), 1
        )
    ]
    w2_06_receipt = {
        "command_results": w2_06_commands,
        "test_reports": copy.deepcopy(w2_06_reports),
        "changed_paths": list(RUNNER.W2_06_CHANGED_PATHS),
        "artifact_digests": {
            f"result-path:{path}": "sha256:" + "a" * 64
            for path in RUNNER.W2_06_CHANGED_PATHS
        },
        "completion_assertions": [
            {"id": assertion_id, "ok": True}
            for assertion_id in w2_06_assertion_ids
        ],
        "runner_version": RUNNER.RUNNER_VERSION,
    }
    with monkeypatch.context() as resume_patch:
        resume_patch.setattr(
            RUNNER,
            "_structured_test_reports",
            lambda *_args, **_kwargs: copy.deepcopy(w2_06_reports),
        )
        assert RUNNER._auto_receipt_resume_problems(
            w2_06_task, w2_06_receipt, tmp_path,
        ) == []

        wrong_command = copy.deepcopy(w2_06_receipt)
        wrong_command["command_results"][0]["argv"] = ["wrong-command"]
        assert any(
            "command 1" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w2_06_task, wrong_command, tmp_path,
            )
        )

        wrong_report = copy.deepcopy(w2_06_receipt)
        wrong_report["test_reports"][0]["passed"] -= 1
        assert "AUTO receipt structured reports drifted" in (
            RUNNER._auto_receipt_resume_problems(w2_06_task, wrong_report, tmp_path)
        )

        wrong_paths = copy.deepcopy(w2_06_receipt)
        wrong_paths["changed_paths"].pop()
        assert any(
            "exact" in problem and "committed paths" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w2_06_task, wrong_paths, tmp_path,
            )
        )

        wrong_assertion = copy.deepcopy(w2_06_receipt)
        wrong_assertion["completion_assertions"][-1]["ok"] = False
        assert any(
            "completion assertions" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w2_06_task, wrong_assertion, tmp_path,
            )
        )

    w3_01_reports = copy.deepcopy(w1_02_reports)
    w3_01_reports[0].update({
        "passed": RUNNER.W3_01_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W3_01_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W3_01_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W3_01_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W3_01_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w3_01_test_report_problems(w3_01_reports) == []
    w3_01_reports[0]["junit_cases"] -= 1
    assert RUNNER._w3_01_test_report_problems(w3_01_reports) == [
        "W3-01 pytest junit_cases drifted: "
        f"{RUNNER.W3_01_TEST_CASE_COUNT - 1} != {RUNNER.W3_01_TEST_CASE_COUNT}"
    ]
    w3_01_reports[0]["junit_cases"] = RUNNER.W3_01_TEST_CASE_COUNT
    wrong_w3_01_digest = "sha256:" + "f" * 64
    if wrong_w3_01_digest == RUNNER.W3_01_TEST_CASE_IDS_DIGEST:
        wrong_w3_01_digest = "sha256:" + "e" * 64
    w3_01_reports[0]["junit_case_ids_digest"] = wrong_w3_01_digest
    assert RUNNER._w3_01_test_report_problems(w3_01_reports) == [
        "W3-01 pytest junit_case_ids_digest drifted: "
        f"{wrong_w3_01_digest!r} != {RUNNER.W3_01_TEST_CASE_IDS_DIGEST!r}"
    ]
    w3_01_reports[0]["junit_case_ids_digest"] = RUNNER.W3_01_TEST_CASE_IDS_DIGEST
    w3_01_task = next(
        item
        for item in json.loads(RUNNER.DEFAULT_PLAN.read_text(encoding="utf-8"))["tasks"]
        if item["id"] == "W3-01"
    )
    assert list(RUNNER.W3_01_CHANGED_PATHS) == w3_01_task["allowed_paths"]
    w3_01_assertion_ids = [
        "all-commands-passed",
        "runner-clean-worktree",
        "runner-committed-delta",
        "runner-state-artifacts",
        "w3-01-exact-lossless-ir-reports",
        "w3-01-exact-committed-scope",
    ]
    assert RUNNER._expected_auto_completion_assertion_ids(
        w3_01_task,
        "w3-01-exact-lossless-ir-reports",
        "w3-01-exact-committed-scope",
    ) == w3_01_assertion_ids
    w3_01_commands = [
        {
            "argv": RUNNER._expanded_argv(argv, tmp_path),
            "expected_exit_code": expected,
            "exit_code": expected,
            "timed_out": False,
            "stdout": stream(f"w3-01-{index}-stdout"),
            "stderr": stream(f"w3-01-{index}-stderr"),
        }
        for index, (argv, expected) in enumerate(
            zip(w3_01_task["argv"], w3_01_task["expected_exit_codes"]), 1
        )
    ]
    w3_01_receipt = {
        "command_results": w3_01_commands,
        "test_reports": copy.deepcopy(w3_01_reports),
        "changed_paths": list(RUNNER.W3_01_CHANGED_PATHS),
        "artifact_digests": {
            f"result-path:{path}": "sha256:" + "a" * 64
            for path in RUNNER.W3_01_CHANGED_PATHS
        },
        "completion_assertions": [
            {"id": assertion_id, "ok": True}
            for assertion_id in w3_01_assertion_ids
        ],
        "runner_version": RUNNER.RUNNER_VERSION,
    }
    with monkeypatch.context() as resume_patch:
        resume_patch.setattr(
            RUNNER,
            "_structured_test_reports",
            lambda *_args, **_kwargs: copy.deepcopy(w3_01_reports),
        )
        assert RUNNER._auto_receipt_resume_problems(
            w3_01_task, w3_01_receipt, tmp_path,
        ) == []

        wrong_command = copy.deepcopy(w3_01_receipt)
        wrong_command["command_results"][1]["argv"] = ["wrong-pytest-command"]
        assert any(
            "command 2" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w3_01_task, wrong_command, tmp_path,
            )
        )

        wrong_report = copy.deepcopy(w3_01_receipt)
        wrong_report["test_reports"][0]["passed"] -= 1
        assert "AUTO receipt structured reports drifted" in (
            RUNNER._auto_receipt_resume_problems(w3_01_task, wrong_report, tmp_path)
        )

        wrong_paths = copy.deepcopy(w3_01_receipt)
        wrong_paths["changed_paths"].pop()
        assert any(
            "exact" in problem and "committed paths" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w3_01_task, wrong_paths, tmp_path,
            )
        )

        wrong_assertion = copy.deepcopy(w3_01_receipt)
        wrong_assertion["completion_assertions"][-2]["id"] = "wrong-report-assertion"
        assert any(
            "completion assertions" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w3_01_task, wrong_assertion, tmp_path,
            )
        )

    w3_02_reports = copy.deepcopy(w1_02_reports)
    w3_02_reports[0].update({
        "passed": RUNNER.W3_02_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W3_02_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W3_02_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W3_02_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W3_02_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w3_02_test_report_problems(w3_02_reports) == []
    w3_02_reports[0]["junit_cases"] -= 1
    assert RUNNER._w3_02_test_report_problems(w3_02_reports) == [
        "W3-02 pytest junit_cases drifted: "
        f"{RUNNER.W3_02_TEST_CASE_COUNT - 1} != {RUNNER.W3_02_TEST_CASE_COUNT}"
    ]
    w3_02_reports[0]["junit_cases"] = RUNNER.W3_02_TEST_CASE_COUNT
    wrong_w3_02_digest = "sha256:" + "f" * 64
    if wrong_w3_02_digest == RUNNER.W3_02_TEST_CASE_IDS_DIGEST:
        wrong_w3_02_digest = "sha256:" + "e" * 64
    w3_02_reports[0]["junit_case_ids_digest"] = wrong_w3_02_digest
    assert RUNNER._w3_02_test_report_problems(w3_02_reports) == [
        "W3-02 pytest junit_case_ids_digest drifted: "
        f"{wrong_w3_02_digest!r} != {RUNNER.W3_02_TEST_CASE_IDS_DIGEST!r}"
    ]
    w3_02_reports[0]["junit_case_ids_digest"] = RUNNER.W3_02_TEST_CASE_IDS_DIGEST
    w3_02_task = next(
        item
        for item in json.loads(RUNNER.DEFAULT_PLAN.read_text(encoding="utf-8"))["tasks"]
        if item["id"] == "W3-02"
    )
    assert list(RUNNER.W3_02_CHANGED_PATHS) == w3_02_task["allowed_paths"]
    w3_02_assertion_ids = [
        "all-commands-passed",
        "runner-clean-worktree",
        "runner-committed-delta",
        "runner-state-artifacts",
        "w3-02-exact-argumentation-reports",
        "w3-02-exact-committed-scope",
    ]
    assert RUNNER._expected_auto_completion_assertion_ids(
        w3_02_task,
        "w3-02-exact-argumentation-reports",
        "w3-02-exact-committed-scope",
    ) == w3_02_assertion_ids
    w3_02_commands = [
        {
            "argv": RUNNER._expanded_argv(argv, tmp_path),
            "expected_exit_code": expected,
            "exit_code": expected,
            "timed_out": False,
            "stdout": stream(f"w3-02-{index}-stdout"),
            "stderr": stream(f"w3-02-{index}-stderr"),
        }
        for index, (argv, expected) in enumerate(
            zip(w3_02_task["argv"], w3_02_task["expected_exit_codes"]), 1
        )
    ]
    w3_02_receipt = {
        "command_results": w3_02_commands,
        "test_reports": copy.deepcopy(w3_02_reports),
        "changed_paths": list(RUNNER.W3_02_CHANGED_PATHS),
        "artifact_digests": {
            f"result-path:{path}": "sha256:" + "a" * 64
            for path in RUNNER.W3_02_CHANGED_PATHS
        },
        "completion_assertions": [
            {"id": assertion_id, "ok": True}
            for assertion_id in w3_02_assertion_ids
        ],
        "runner_version": RUNNER.RUNNER_VERSION,
    }
    with monkeypatch.context() as resume_patch:
        resume_patch.setattr(
            RUNNER,
            "_structured_test_reports",
            lambda *_args, **_kwargs: copy.deepcopy(w3_02_reports),
        )
        resume_patch.setattr(
            RUNNER, "_live_b02_binding", lambda _state_root: {"state": "pinned"},
        )
        assert RUNNER._auto_receipt_resume_problems(
            w3_02_task, w3_02_receipt, tmp_path,
        ) == []

        for drift in ("missing", "dirty", "repointed"):
            def reject_live_binding(_state_root, detail=drift):
                raise ValueError(detail)

            resume_patch.setattr(RUNNER, "_live_b02_binding", reject_live_binding)
            assert RUNNER._auto_receipt_resume_problems(
                w3_02_task, w3_02_receipt, tmp_path,
            ) == [
                "W3-02 live companion binding is invalid: ValueError: " + drift,
            ]
        resume_patch.setattr(
            RUNNER, "_live_b02_binding", lambda _state_root: {"state": "pinned"},
        )

        wrong_command = copy.deepcopy(w3_02_receipt)
        wrong_command["command_results"][1]["argv"] = ["wrong-pytest-command"]
        assert any(
            "command 2" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w3_02_task, wrong_command, tmp_path,
            )
        )

        wrong_report = copy.deepcopy(w3_02_receipt)
        wrong_report["test_reports"][0]["passed"] -= 1
        assert "AUTO receipt structured reports drifted" in (
            RUNNER._auto_receipt_resume_problems(w3_02_task, wrong_report, tmp_path)
        )

        wrong_paths = copy.deepcopy(w3_02_receipt)
        wrong_paths["changed_paths"].pop()
        assert any(
            "exact" in problem and "committed paths" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w3_02_task, wrong_paths, tmp_path,
            )
        )

        wrong_assertion = copy.deepcopy(w3_02_receipt)
        wrong_assertion["completion_assertions"][-2]["id"] = "wrong-report-assertion"
        assert any(
            "completion assertions" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w3_02_task, wrong_assertion, tmp_path,
            )
        )

    w3_04_reports = copy.deepcopy(w1_02_reports)
    w3_04_reports[0].update({
        "passed": RUNNER.W3_04_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W3_04_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W3_04_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W3_04_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W3_04_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w3_04_test_report_problems(w3_04_reports) == []

    wrong_w3_04_count = copy.deepcopy(w3_04_reports)
    wrong_w3_04_count[0]["passed"] = RUNNER.W3_04_TEST_CASE_COUNT + 1
    assert RUNNER._w3_04_test_report_problems(wrong_w3_04_count) == [
        "W3-04 pytest passed drifted: "
        f"{RUNNER.W3_04_TEST_CASE_COUNT + 1} != {RUNNER.W3_04_TEST_CASE_COUNT}"
    ]

    wrong_w3_04_digest = "sha256:" + "f" * 64
    if wrong_w3_04_digest == RUNNER.W3_04_TEST_CASE_IDS_DIGEST:
        wrong_w3_04_digest = "sha256:" + "e" * 64
    wrong_digest_report = copy.deepcopy(w3_04_reports)
    wrong_digest_report[0]["junit_case_ids_digest"] = wrong_w3_04_digest
    assert RUNNER._w3_04_test_report_problems(wrong_digest_report) == [
        "W3-04 pytest junit_case_ids_digest drifted: "
        f"{wrong_w3_04_digest!r} != {RUNNER.W3_04_TEST_CASE_IDS_DIGEST!r}"
    ]

    for bypass_field in (
        "failed", "errors", "skipped", "xfailed", "xpassed", "collection_errors",
        "junit_skipped", "junit_failures", "junit_errors",
    ):
        bypass_report = copy.deepcopy(w3_04_reports)
        bypass_report[0][bypass_field] = 1
        assert any(
            f"W3-04 pytest {bypass_field} drifted" in problem
            for problem in RUNNER._w3_04_test_report_problems(bypass_report)
        )

    w3_04_task = next(
        item
        for item in json.loads(RUNNER.DEFAULT_PLAN.read_text(encoding="utf-8"))["tasks"]
        if item["id"] == "W3-04"
    )
    assert list(RUNNER.W3_04_CHANGED_PATHS) == w3_04_task["allowed_paths"]
    w3_04_assertion_ids = [
        "all-commands-passed",
        "runner-clean-worktree",
        "runner-committed-delta",
        "runner-state-artifacts",
        "w3-04-exact-checker-reports",
        "w3-04-exact-independence",
        "w3-04-exact-committed-scope",
    ]
    assert RUNNER._expected_auto_completion_assertion_ids(
        w3_04_task,
        "w3-04-exact-checker-reports",
        "w3-04-exact-independence",
        "w3-04-exact-committed-scope",
    ) == w3_04_assertion_ids
    w3_04_commands = [
        {
            "argv": RUNNER._expanded_argv(argv, tmp_path),
            "expected_exit_code": expected,
            "exit_code": expected,
            "timed_out": False,
            "stdout": stream(f"w3-04-{index}-stdout"),
            "stderr": stream(f"w3-04-{index}-stderr"),
        }
        for index, (argv, expected) in enumerate(
            zip(w3_04_task["argv"], w3_04_task["expected_exit_codes"]), 1
        )
    ]
    w3_04_receipt = {
        "command_results": w3_04_commands,
        "test_reports": copy.deepcopy(w3_04_reports),
        "changed_paths": list(RUNNER.W3_04_CHANGED_PATHS),
        "artifact_digests": {
            f"result-path:{path}": "sha256:" + "a" * 64
            for path in RUNNER.W3_04_CHANGED_PATHS
        },
        "completion_assertions": [
            {"id": assertion_id, "ok": True}
            for assertion_id in w3_04_assertion_ids
        ],
        "runner_version": RUNNER.RUNNER_VERSION,
    }
    with monkeypatch.context() as resume_patch:
        resume_patch.setattr(
            RUNNER,
            "_structured_test_reports",
            lambda *_args, **_kwargs: copy.deepcopy(w3_04_reports),
        )
        resume_patch.setattr(RUNNER, "_w3_04_independence_problems", lambda: [])
        assert RUNNER._auto_receipt_resume_problems(
            w3_04_task, w3_04_receipt, tmp_path,
        ) == []

        wrong_report = copy.deepcopy(w3_04_receipt)
        wrong_report["test_reports"][0]["passed"] = RUNNER.W3_04_TEST_CASE_COUNT + 1
        assert "AUTO receipt structured reports drifted" in (
            RUNNER._auto_receipt_resume_problems(w3_04_task, wrong_report, tmp_path)
        )

        missing_path = copy.deepcopy(w3_04_receipt)
        missing_path["changed_paths"].pop()
        assert any(
            "exact 11 committed paths" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w3_04_task, missing_path, tmp_path,
            )
        )

        wrong_assertion = copy.deepcopy(w3_04_receipt)
        wrong_assertion["completion_assertions"][-2]["id"] = "wrong-independence"
        assert any(
            "completion assertions" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w3_04_task, wrong_assertion, tmp_path,
            )
        )

        resume_patch.setattr(
            RUNNER,
            "_w3_04_independence_problems",
            lambda: ["forced independence drift"],
        )
        assert "forced independence drift" in RUNNER._auto_receipt_resume_problems(
            w3_04_task, w3_04_receipt, tmp_path,
        )

    w4_01_reports = copy.deepcopy(w1_02_reports)
    w4_01_reports[0].update({
        "passed": RUNNER.W4_01_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W4_01_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W4_01_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W4_01_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W4_01_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w4_01_test_report_problems(w4_01_reports) == []

    w4_01_task = next(
        item
        for item in json.loads(RUNNER.DEFAULT_PLAN.read_text(encoding="utf-8"))["tasks"]
        if item["id"] == "W4-01"
    )
    assert list(RUNNER.W4_01_ALLOWED_PATHS) == w4_01_task["allowed_paths"]
    assert set(RUNNER.W4_01_CHANGED_PATHS) == (
        set(RUNNER.W4_01_ALLOWED_PATHS) - {"mcp_manifest.json"}
    )
    w4_01_assertion_ids = [
        "all-commands-passed",
        "runner-clean-worktree",
        "runner-committed-delta",
        "runner-state-artifacts",
        "w4-01-exact-run-identity-reports",
        "w4-01-complete-identity-state-contract",
        "w4-01-exact-committed-scope",
    ]
    assert RUNNER._expected_auto_completion_assertion_ids(
        w4_01_task,
        "w4-01-exact-run-identity-reports",
        "w4-01-complete-identity-state-contract",
        "w4-01-exact-committed-scope",
    ) == w4_01_assertion_ids
    w4_01_commands = [
        {
            "argv": RUNNER._expanded_argv(argv, tmp_path),
            "expected_exit_code": expected,
            "exit_code": expected,
            "timed_out": False,
            "stdout": stream(f"w4-01-{index}-stdout"),
            "stderr": stream(f"w4-01-{index}-stderr"),
        }
        for index, (argv, expected) in enumerate(
            zip(w4_01_task["argv"], w4_01_task["expected_exit_codes"]), 1
        )
    ]
    w4_01_receipt = {
        "command_results": w4_01_commands,
        "test_reports": copy.deepcopy(w4_01_reports),
        "changed_paths": list(RUNNER.W4_01_CHANGED_PATHS),
        "artifact_digests": {
            **{
                f"result-path:{path}": "sha256:" + "a" * 64
                for path in RUNNER.W4_01_CHANGED_PATHS
            },
            "publication:schemas/jc-v4.schema.json": (
                "sha256:" + RUNNER.W4_01_SCHEMA_SHA256
            ),
            "publication:mcp_manifest.json": (
                "sha256:" + RUNNER.W4_01_MANIFEST_SHA256
            ),
            "publication:tool-spec": RUNNER.W4_01_TOOL_SPEC_DIGEST,
        },
        "completion_assertions": [
            {"id": assertion_id, "ok": True}
            for assertion_id in w4_01_assertion_ids
        ],
        "runner_version": RUNNER.RUNNER_VERSION,
    }
    with monkeypatch.context() as resume_patch:
        resume_patch.setattr(
            RUNNER,
            "_structured_test_reports",
            lambda *_args, **_kwargs: copy.deepcopy(w4_01_reports),
        )
        assert RUNNER._auto_receipt_resume_problems(
            w4_01_task, w4_01_receipt, tmp_path,
        ) == []

        missing_path = copy.deepcopy(w4_01_receipt)
        missing_path["changed_paths"].pop()
        assert any(
            "exact 18 committed paths" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_01_task, missing_path, tmp_path,
            )
        )

        wrong_publication = copy.deepcopy(w4_01_receipt)
        wrong_publication["artifact_digests"][
            "publication:schemas/jc-v4.schema.json"
        ] = "sha256:" + "f" * 64
        assert any(
            "publication digest drifted" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_01_task, wrong_publication, tmp_path,
            )
        )

        wrong_assertion = copy.deepcopy(w4_01_receipt)
        wrong_assertion["completion_assertions"][-2]["id"] = "wrong-state-contract"
        assert any(
            "completion assertions" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_01_task, wrong_assertion, tmp_path,
            )
        )

    w4_02_reports = copy.deepcopy(w1_02_reports)
    w4_02_reports[0].update({
        "passed": RUNNER.W4_02_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W4_02_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W4_02_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W4_02_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W4_02_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w4_02_test_report_problems(w4_02_reports) == []
    w4_02_task = next(
        item
        for item in json.loads(RUNNER.DEFAULT_PLAN.read_text(encoding="utf-8"))["tasks"]
        if item["id"] == "W4-02"
    )
    assert list(RUNNER.W4_02_ALLOWED_PATHS) == w4_02_task["allowed_paths"]
    assert set(RUNNER.W4_02_CHANGED_PATHS) == (
        set(RUNNER.W4_02_ALLOWED_PATHS) - {"compiler_core/artifact_store.py"}
    )
    w4_02_assertion_ids = [
        "all-commands-passed",
        "runner-clean-worktree",
        "runner-committed-delta",
        "runner-state-artifacts",
        "w4-02-exact-storage-reports",
        "w4-02-durable-isolated-storage-contract",
        "w4-02-exact-committed-scope",
    ]
    assert RUNNER._expected_auto_completion_assertion_ids(
        w4_02_task,
        "w4-02-exact-storage-reports",
        "w4-02-durable-isolated-storage-contract",
        "w4-02-exact-committed-scope",
    ) == w4_02_assertion_ids
    w4_02_commands = [
        {
            "argv": RUNNER._expanded_argv(argv, tmp_path),
            "expected_exit_code": expected,
            "exit_code": expected,
            "timed_out": False,
            "stdout": stream(f"w4-02-{index}-stdout"),
            "stderr": stream(f"w4-02-{index}-stderr"),
        }
        for index, (argv, expected) in enumerate(
            zip(w4_02_task["argv"], w4_02_task["expected_exit_codes"]), 1
        )
    ]
    w4_02_receipt = {
        "command_results": w4_02_commands,
        "test_reports": copy.deepcopy(w4_02_reports),
        "changed_paths": list(RUNNER.W4_02_CHANGED_PATHS),
        "artifact_digests": {
            **{
                f"result-path:{path}": "sha256:" + "a" * 64
                for path in RUNNER.W4_02_CHANGED_PATHS
            },
            "publication:compiler_core/artifact_store.py": (
                RUNNER.W4_02_ARTIFACT_STORE_SHA256
            ),
        },
        "completion_assertions": [
            {"id": assertion_id, "ok": True}
            for assertion_id in w4_02_assertion_ids
        ],
        "runner_version": RUNNER.RUNNER_VERSION,
    }
    with monkeypatch.context() as resume_patch:
        resume_patch.setattr(
            RUNNER,
            "_structured_test_reports",
            lambda *_args, **_kwargs: copy.deepcopy(w4_02_reports),
        )
        resume_patch.setattr(RUNNER, "_w4_02_storage_contract_problems", lambda: [])
        assert RUNNER._auto_receipt_resume_problems(
            w4_02_task, w4_02_receipt, tmp_path,
        ) == []

        missing_path = copy.deepcopy(w4_02_receipt)
        missing_path["changed_paths"].pop()
        assert any(
            "exact 13 committed paths" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_02_task, missing_path, tmp_path,
            )
        )

        wrong_publication = copy.deepcopy(w4_02_receipt)
        wrong_publication["artifact_digests"][
            "publication:compiler_core/artifact_store.py"
        ] = "sha256:" + "f" * 64
        assert any(
            "artifact resolver digest" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_02_task, wrong_publication, tmp_path,
            )
        )

        wrong_assertion = copy.deepcopy(w4_02_receipt)
        wrong_assertion["completion_assertions"][-2]["id"] = "wrong-storage-contract"
        assert any(
            "completion assertions" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_02_task, wrong_assertion, tmp_path,
            )
        )

    w4_03_reports = copy.deepcopy(w1_02_reports)
    w4_03_reports[0].update({
        "passed": RUNNER.W4_03_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W4_03_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W4_03_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W4_03_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W4_03_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w4_03_test_report_problems(w4_03_reports) == []
    w4_03_task = next(
        item
        for item in json.loads(RUNNER.DEFAULT_PLAN.read_text(encoding="utf-8"))["tasks"]
        if item["id"] == "W4-03"
    )
    assert list(RUNNER.W4_03_ALLOWED_PATHS) == w4_03_task["allowed_paths"]
    assert set(RUNNER.W4_03_CHANGED_PATHS) == (
        set(RUNNER.W4_03_ALLOWED_PATHS) - set(RUNNER.W4_03_BYTE_STABLE_DIGESTS)
    )
    w4_03_assertion_ids = [
        "all-commands-passed",
        "runner-clean-worktree",
        "runner-committed-delta",
        "runner-state-artifacts",
        "w4-03-exact-audit-reports",
        "w4-03-independent-atomic-bundle-contract",
        "w4-03-exact-committed-scope",
    ]
    assert RUNNER._expected_auto_completion_assertion_ids(
        w4_03_task,
        "w4-03-exact-audit-reports",
        "w4-03-independent-atomic-bundle-contract",
        "w4-03-exact-committed-scope",
    ) == w4_03_assertion_ids
    w4_03_commands = [
        {
            "argv": RUNNER._expanded_argv(argv, tmp_path),
            "expected_exit_code": expected,
            "exit_code": expected,
            "timed_out": False,
            "stdout": stream(f"w4-03-{index}-stdout"),
            "stderr": stream(f"w4-03-{index}-stderr"),
        }
        for index, (argv, expected) in enumerate(
            zip(w4_03_task["argv"], w4_03_task["expected_exit_codes"]), 1
        )
    ]
    w4_03_receipt = {
        "command_results": w4_03_commands,
        "test_reports": copy.deepcopy(w4_03_reports),
        "changed_paths": list(RUNNER.W4_03_CHANGED_PATHS),
        "artifact_digests": {
            **{
                f"result-path:{path}": "sha256:" + "a" * 64
                for path in RUNNER.W4_03_CHANGED_PATHS
            },
            **{
                f"publication:{path}": digest
                for path, digest in RUNNER.W4_03_BYTE_STABLE_DIGESTS.items()
            },
        },
        "completion_assertions": [
            {"id": assertion_id, "ok": True}
            for assertion_id in w4_03_assertion_ids
        ],
        "runner_version": RUNNER.RUNNER_VERSION,
    }
    with monkeypatch.context() as resume_patch:
        resume_patch.setattr(
            RUNNER,
            "_structured_test_reports",
            lambda *_args, **_kwargs: copy.deepcopy(w4_03_reports),
        )
        resume_patch.setattr(RUNNER, "_w4_03_audit_contract_problems", lambda: [])
        assert RUNNER._auto_receipt_resume_problems(
            w4_03_task, w4_03_receipt, tmp_path,
        ) == []

        missing_path = copy.deepcopy(w4_03_receipt)
        missing_path["changed_paths"].pop()
        assert any(
            "exact 11 committed paths" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_03_task, missing_path, tmp_path,
            )
        )

        wrong_publication = copy.deepcopy(w4_03_receipt)
        first_prerequisite = next(iter(RUNNER.W4_03_BYTE_STABLE_DIGESTS))
        wrong_publication["artifact_digests"][
            f"publication:{first_prerequisite}"
        ] = "sha256:" + "f" * 64
        assert any(
            "byte-stable prerequisite digest" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_03_task, wrong_publication, tmp_path,
            )
        )

        wrong_assertion = copy.deepcopy(w4_03_receipt)
        wrong_assertion["completion_assertions"][-2]["id"] = "wrong-audit-contract"
        assert any(
            "completion assertions" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_03_task, wrong_assertion, tmp_path,
            )
        )

    w4_04_reports = copy.deepcopy(w4_03_reports)
    w4_04_reports[0].update({
        "passed": RUNNER.W4_04_TEST_CASE_COUNT,
        "junit_tests": RUNNER.W4_04_TEST_CASE_COUNT,
        "junit_cases": RUNNER.W4_04_TEST_CASE_COUNT,
        "junit_unique_cases": RUNNER.W4_04_TEST_CASE_COUNT,
        "junit_case_ids_digest": RUNNER.W4_04_TEST_CASE_IDS_DIGEST,
    })
    assert RUNNER._w4_04_test_report_problems(w4_04_reports) == []
    w4_04_task = next(
        item
        for item in json.loads(RUNNER.DEFAULT_PLAN.read_text(encoding="utf-8"))["tasks"]
        if item["id"] == "W4-04"
    )
    assert list(RUNNER.W4_04_ALLOWED_PATHS) == w4_04_task["allowed_paths"]
    assert set(RUNNER.W4_04_CHANGED_PATHS) == (
        set(RUNNER.W4_04_ALLOWED_PATHS) - set(RUNNER.W4_04_BYTE_STABLE_DIGESTS)
    )
    w4_04_assertion_ids = [
        "all-commands-passed",
        "runner-clean-worktree",
        "runner-committed-delta",
        "runner-state-artifacts",
        "w4-04-exact-certificate-reports",
        "w4-04-bundle-bound-certificate-contract",
        "w4-04-exact-committed-scope",
    ]
    assert RUNNER._expected_auto_completion_assertion_ids(
        w4_04_task,
        "w4-04-exact-certificate-reports",
        "w4-04-bundle-bound-certificate-contract",
        "w4-04-exact-committed-scope",
    ) == w4_04_assertion_ids
    w4_04_commands = [
        {
            "argv": RUNNER._expanded_argv(argv, tmp_path),
            "expected_exit_code": expected,
            "exit_code": expected,
            "timed_out": False,
            "stdout": stream(f"w4-04-{index}-stdout"),
            "stderr": stream(f"w4-04-{index}-stderr"),
        }
        for index, (argv, expected) in enumerate(
            zip(w4_04_task["argv"], w4_04_task["expected_exit_codes"]), 1
        )
    ]
    w4_04_receipt = {
        "command_results": w4_04_commands,
        "test_reports": copy.deepcopy(w4_04_reports),
        "changed_paths": list(RUNNER.W4_04_CHANGED_PATHS),
        "artifact_digests": {
            **{
                f"result-path:{path}": "sha256:" + "a" * 64
                for path in RUNNER.W4_04_CHANGED_PATHS
            },
            **{
                f"publication:{path}": digest
                for path, digest in RUNNER.W4_04_BYTE_STABLE_DIGESTS.items()
            },
        },
        "completion_assertions": [
            {"id": assertion_id, "ok": True}
            for assertion_id in w4_04_assertion_ids
        ],
        "runner_version": RUNNER.RUNNER_VERSION,
    }
    with monkeypatch.context() as resume_patch:
        resume_patch.setattr(
            RUNNER,
            "_structured_test_reports",
            lambda *_args, **_kwargs: copy.deepcopy(w4_04_reports),
        )
        resume_patch.setattr(
            RUNNER, "_w4_04_certificate_contract_problems", lambda: [],
        )
        assert RUNNER._auto_receipt_resume_problems(
            w4_04_task, w4_04_receipt, tmp_path,
        ) == []

        missing_path = copy.deepcopy(w4_04_receipt)
        missing_path["changed_paths"].pop()
        assert any(
            "exact 11 committed paths" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_04_task, missing_path, tmp_path,
            )
        )

        wrong_publication = copy.deepcopy(w4_04_receipt)
        first_prerequisite = next(iter(RUNNER.W4_04_BYTE_STABLE_DIGESTS))
        wrong_publication["artifact_digests"][
            f"publication:{first_prerequisite}"
        ] = "sha256:" + "f" * 64
        assert any(
            "byte-stable prerequisite digest" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_04_task, wrong_publication, tmp_path,
            )
        )

        wrong_assertion = copy.deepcopy(w4_04_receipt)
        wrong_assertion["completion_assertions"][-2]["id"] = "wrong-certificate-contract"
        assert any(
            "completion assertions" in problem
            for problem in RUNNER._auto_receipt_resume_problems(
                w4_04_task, wrong_assertion, tmp_path,
            )
        )

    lost_junit = tmp_path / "evidence" / "lost.xml"
    lost_junit.parent.mkdir(parents=True, exist_ok=True)
    lost_junit.write_text("overwritten", encoding="utf-8")
    historical_task = {
        "id": "W1-06",
        "argv": [
            ["py", "gate"],
            [
                "py", "-m", "pytest", "--basetemp", str(tmp_path / "tmp" / "W1-06"),
                "--junitxml", str(lost_junit),
            ],
            ["node", "oracle"],
        ],
        "expected_exit_codes": [0, 0, 0],
    }
    task_digest = RUNNER._task_digest(historical_task)
    lost_commands = [
        {
            "argv": argv, "expected_exit_code": 0, "exit_code": 0, "timed_out": False,
            "stdout": stream(f"lost-{index}-stdout"),
            "stderr": stream(f"lost-{index}-stderr"),
        }
        for index, argv in enumerate(historical_task["argv"], 1)
    ]
    recorded_state = {"state-artifact:pytest-junit-002": "sha256:" + "1" * 64}
    observed_state = {
        "state-artifact:pytest-junit-002": "sha256:" + RUNNER.sha256_hex(lost_junit.read_bytes())
    }
    assertion = {
        "id": "all-commands-passed", "kind": "all_commands_passed",
        "ok": True, "detail": "all exit codes matched",
    }
    lost_receipt = {
        "schema_version": "jc/remediation-v4-receipt/2.1",
        "task_digest": task_digest,
        "run_id": "test-run",
        "task_id": "W1-06",
        "attempt": 2,
        "status": "COMPLETED",
        "input_receipt_digests": {},
        "start_commit": "start",
        "start_tree": "start-tree",
        "result_commit": "result",
        "result_tree": "result-tree",
        "command_results": lost_commands,
        "changed_paths": [],
        "allowlist": {"allowed": True, "violations": []},
        "test_reports": [],
        "artifact_digests": recorded_state,
        "completion_assertions": [assertion],
        "previous_receipt_digest": None,
        "runner_version": "0.13.0",
    }
    lost_receipt["receipt_digest"] = RUNNER._receipt_digest(lost_receipt)

    with monkeypatch.context() as recovery_patch:
        old_plan_bytes = json.dumps({"tasks": [historical_task]}).encode("utf-8")
        recovery_patch.setattr(RUNNER, "_git_path_bytes", lambda *_args: old_plan_bytes)
        recovery_patch.setattr(RUNNER, "_w1_06_test_report_problems", lambda _reports: [])
        recovery_patch.setattr(RUNNER, "_validate_git_binding", lambda *_args: True)
        recovery_patch.setattr(RUNNER, "_committed_delta", lambda *_args: ([], {}))
        _, replay_argvs = RUNNER._state_artifact_recovery_replay(
            lost_receipt, tmp_path, 3,
        )
        replay_junit = RUNNER._pytest_junit_path(replay_argvs[1])
        assert replay_junit is not None
        replay_junit.parent.mkdir(parents=True, exist_ok=True)
        replay_junit.write_text(
            '<testsuites><testsuite tests="1" skipped="0" failures="0" errors="0">'
            '<testcase classname="recovery" name="test_replay" />'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        replay_commands = [
            {
                "argv": argv, "expected_exit_code": 0, "exit_code": 0,
                "timed_out": False,
                "stdout": stream(
                    f"replay-{index}-stdout",
                    b"1 passed in 0.01s\n" if index == 2 else b"",
                ),
                "stderr": stream(f"replay-{index}-stderr"),
            }
            for index, argv in enumerate(replay_argvs, 1)
        ]
        replay_reports = RUNNER._structured_test_reports(replay_commands)
        replay_state = RUNNER._declared_state_artifacts(replay_commands, tmp_path)
        artifact_key = "state-artifact:pytest-junit-002"
        recovery_record = {
            "schema_version": "jc/state-artifact-recovery/1.0",
            "task_id": "W1-06",
            "lost_attempt": 2,
            "lost_receipt_digest": lost_receipt["receipt_digest"],
            "artifact_key": artifact_key,
            "artifact_path": str(lost_junit.resolve()),
            "expected_digest": recorded_state[artifact_key],
            "observed_digest": observed_state[artifact_key],
            "action": "REPLAY_AT_RESULT_COMMIT",
            "replay_commit": "result",
            "replay_attempt": 3,
            "replay_argv_digest": RUNNER._digest_object(replay_argvs),
            "replacement_digest": replay_state[artifact_key],
        }
        _, recovery_record_digest = RUNNER._write_content_addressed_json(
            tmp_path / "evidence" / "state-recoveries", recovery_record,
        )
        recovery_receipt = {
            **{key: value for key, value in lost_receipt.items() if key != "receipt_digest"},
            "attempt": 3,
            "command_results": replay_commands,
            "test_reports": replay_reports,
            "artifact_digests": {
                **replay_state,
                "recovery-record": recovery_record_digest,
                "recovery-source-receipt": lost_receipt["receipt_digest"],
                "recovery-loss-observation": RUNNER._digest_object({
                    "recorded": recorded_state,
                    "observed": observed_state,
                }),
            },
            "completion_assertions": [{
                "id": "runner-state-artifact-recovery", "kind": "artifact_binding",
                "ok": True, "detail": "historical replay bound",
            }],
            "previous_receipt_digest": lost_receipt["receipt_digest"],
        }
        recovery_receipt["receipt_digest"] = RUNNER._receipt_digest(recovery_receipt)
        assert RUNNER._state_artifact_recovery_matches(
            lost_receipt, recorded_state, observed_state, recovery_receipt, tmp_path,
        )

        forged_replay = copy.deepcopy(recovery_receipt)
        forged_replay["command_results"][0]["argv"] = ["not-a-replay"]
        forged_replay["receipt_digest"] = RUNNER._receipt_digest(forged_replay)
        assert not RUNNER._state_artifact_recovery_matches(
            lost_receipt, recorded_state, observed_state, forged_replay, tmp_path,
        )
        missing_node_lane = copy.deepcopy(recovery_receipt)
        missing_node_lane["command_results"].pop()
        assert not RUNNER._state_artifact_recovery_matches(
            lost_receipt, recorded_state, observed_state, missing_node_lane, tmp_path,
        )
        wrong_replay_digest = copy.deepcopy(recovery_receipt)
        wrong_replay_digest["artifact_digests"][artifact_key] = "sha256:" + "6" * 64
        assert not RUNNER._state_artifact_recovery_matches(
            lost_receipt, recorded_state, observed_state, wrong_replay_digest, tmp_path,
        )
        wrong_task = copy.deepcopy(recovery_receipt)
        wrong_task["task_id"] = "W2-01"
        assert not RUNNER._state_artifact_recovery_matches(
            lost_receipt, recorded_state, observed_state, wrong_task, tmp_path,
        )
        recovery_patch.setattr(
            RUNNER, "_w1_06_test_report_problems", lambda _reports: ["bad W1-06 replay"],
        )
        assert not RUNNER._state_artifact_recovery_matches(
            lost_receipt, recorded_state, observed_state, recovery_receipt, tmp_path,
        )
        recovery_patch.setattr(RUNNER, "_w1_06_test_report_problems", lambda _reports: [])
        forged_observed = dict(observed_state)
        forged_observed[artifact_key] = "sha256:" + "5" * 64
        assert not RUNNER._state_artifact_recovery_matches(
            lost_receipt, recorded_state, forged_observed, recovery_receipt, tmp_path,
        )
        forged_record = copy.deepcopy(recovery_receipt)
        forged_record["artifact_digests"]["recovery-record"] = "sha256:../../escape"
        assert not RUNNER._state_artifact_recovery_matches(
            lost_receipt, recorded_state, observed_state, forged_record, tmp_path,
        )

        task_dir = tmp_path / "tasks" / "W1-06"
        (task_dir / "2").mkdir(parents=True)
        (task_dir / "3").mkdir()
        (task_dir / "2" / "receipt.json").write_text(
            json.dumps(lost_receipt), encoding="utf-8",
        )
        (task_dir / "3" / "receipt.json").write_text(
            json.dumps(forged_replay), encoding="utf-8",
        )
        try:
            RUNNER._receipt_history("W1-06", tmp_path)
        except ValueError as exc:
            assert "state artifact binding mismatch" in str(exc)
        else:
            raise AssertionError("non-replay recovery receipt must not wash lost state evidence")

    w1_02_reports[0]["skipped"] = 1
    assert RUNNER._w1_02_test_report_problems(w1_02_reports) == [
        "W1-02 pytest skipped drifted: 1 != 0"
    ]
    w1_02_stdout.write_text(
        "1 passed in 0.01s\n173 passed in 3.00s\n", encoding="utf-8"
    )
    forged_reports = RUNNER._structured_test_reports([{
        "argv": ["py", "-m", "pytest", "tests/contract/test_contracts.py"],
        "exit_code": 0,
        "stdout": {"path": str(w1_02_stdout), "sha256": "5" * 64},
        "stderr": {"path": str(tmp_path / "w1-02-stderr.bin"), "sha256": "6" * 64},
    }])
    assert any(
        "terminal_summaries" in problem
        for problem in RUNNER._w1_02_test_report_problems(forged_reports)
    )

    w1_02_stdout.write_text(
        "38 passed in 1.00s\n37 passed in 2.00s\n", encoding="utf-8"
    )
    old_parser_reports = RUNNER._structured_test_reports(
        [{
            "argv": ["py", "-m", "pytest", "tests/contract/test_contracts.py"],
            "exit_code": 0,
            "stdout": {"path": str(w1_02_stdout), "sha256": "7" * 64},
            "stderr": {"path": str(tmp_path / "w1-02-stderr.bin"), "sha256": "8" * 64},
        }],
        runner_version="0.7.0",
    )
    assert old_parser_reports[0]["passed"] == 38

    captured_environment: dict[str, str] = {}

    def fake_run(*_args, **kwargs):
        captured_environment.update(kwargs["env"])
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    attempt_dir = tmp_path / "runner-attempt"
    attempt_dir.mkdir()
    monkeypatch.setattr(RUNNER.subprocess, "run", fake_run)
    RUNNER._run_argv(
        ["py", "-m", "pytest", "tests/contract/test_jcs_v4.py"],
        0,
        attempt_dir,
        1,
        10,
        tmp_path,
    )
    assert "PYTEST_ADDOPTS" not in captured_environment
    assert "PYTEST_PLUGINS" not in captured_environment
    assert "PYTHONPATH" not in captured_environment
    assert captured_environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"

    monkeypatch.setenv("NODE_OPTIONS", "--require hostile-preload.js")
    monkeypatch.setenv("NODE_PATH", "hostile-node-modules")
    captured_environment.clear()
    RUNNER._run_argv(
        ["node", "tests/contract/jcs_node_oracle.mjs", "vectors.json"],
        0,
        attempt_dir,
        2,
        10,
        tmp_path,
    )
    assert "NODE_OPTIONS" not in captured_environment
    assert "NODE_PATH" not in captured_environment

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
