from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "tools" / "remediate_v4.py"
JCS = REPO / "tests" / "fixtures" / "golden" / "jcs-v4-vectors.json"
FOUNDATION = REPO / "tests" / "fixtures" / "golden" / "v4-foundation-contract.json"
NODE_ORACLE = REPO / "tests" / "contract" / "jcs_node_oracle.mjs"
PROBE = REPO / "tests" / "fixtures" / "golden" / "v4-resource-limit-probe.json"
ARTIFACT_PAGE_PROBE = (
    REPO / "tests" / "fixtures" / "golden" / "v4-artifact-page-probe.json"
)


def _runner_module():
    spec = importlib.util.spec_from_file_location("v4_foundation_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(RUNNER), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_w0_foundation_gate_passes() -> None:
    result = _runner("verify-wave", "W0-02")
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "13 benchmarked admission limits" in result.stdout
    assert "1 bounded artifact page" in result.stdout
    assert "5 explicit deferred operational limits" in result.stdout


def test_node_oracle_matches_python_positive_bytes_and_discloses_parser_boundary() -> None:
    node = shutil.which("node")
    assert node is not None, "Node is required for the W0-02 cross-language oracle"
    result = subprocess.run(
        [node, str(NODE_ORACLE), str(JCS)],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "runtime=v" in result.stdout
    assert "positive=9" in result.stdout
    assert "float_tokens=raw-lexical" in result.stdout
    assert "duplicate_key=declaration-only" in result.stdout


def test_w0_foundation_gate_rejects_contract_mutations(tmp_path: Path) -> None:
    baseline = json.loads(FOUNDATION.read_text(encoding="utf-8"))
    mutations = []

    time_offset = json.loads(json.dumps(baseline))
    time_offset["time_policy"]["positive"][0]["wire"] = "1970-01-01T00:00:00+00:00"
    mutations.append(time_offset)

    money_float = json.loads(json.dumps(baseline))
    money_float["numeric_policy"]["positive"][2]["value"]["minor_units"] = 0.01
    mutations.append(money_float)

    unsupported_limit = json.loads(json.dumps(baseline))
    unsupported_limit["resource_limit_policy"]["benchmarked_limits"][0]["hard_max"] += 1
    mutations.append(unsupported_limit)

    unsupported_artifact_page = json.loads(json.dumps(baseline))
    unsupported_artifact_page["resource_limit_policy"]["artifact_page_policy"][
        "hard_max"
    ] += 1
    mutations.append(unsupported_artifact_page)

    deferred_magic_value = json.loads(json.dumps(baseline))
    deferred_magic_value["resource_limit_policy"]["deferred_limits"][0]["value"] = 65536
    mutations.append(deferred_magic_value)

    platform_overclaim = json.loads(json.dumps(baseline))
    platform_overclaim["platform_matrix"]["claim"] = "VERIFIED"
    mutations.append(platform_overclaim)

    duplicated_vector = json.loads(json.dumps(baseline))
    duplicated_vector["time_policy"]["positive"].append(
        duplicated_vector["time_policy"]["positive"][0]
    )
    mutations.append(duplicated_vector)

    for index, payload in enumerate(mutations):
        path = tmp_path / f"foundation-invalid-{index}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = _runner(
            "foundation-contract", "--jcs", str(JCS), "--foundation", str(path)
        )
        assert result.returncode != 0, f"foundation mutation {index} unexpectedly passed"


def test_w0_jcs_gate_rejects_byte_and_digest_mutations(tmp_path: Path) -> None:
    baseline = json.loads(JCS.read_text(encoding="utf-8"))
    mutations = []

    byte_flip = json.loads(json.dumps(baseline))
    byte_flip["positive"][0]["canonical_utf8_hex"] = "7b7e"
    mutations.append(byte_flip)

    old_digest_grammar = json.loads(json.dumps(baseline))
    old_digest_grammar["digest_grammar"] = "^sha256-[0-9a-f]{64}$"
    mutations.append(old_digest_grammar)

    for index, payload in enumerate(mutations):
        path = tmp_path / f"jcs-invalid-{index}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = _runner(
            "foundation-contract", "--jcs", str(path), "--foundation", str(FOUNDATION)
        )
        assert result.returncode != 0, f"JCS mutation {index} unexpectedly passed"


def test_resource_probe_reproduction_rejects_observation_and_timing_mutations() -> None:
    baseline = json.loads(PROBE.read_text(encoding="utf-8"))
    runner = _runner_module()
    assert runner._probe_sample_problems(baseline) == []

    observation_mutation = json.loads(json.dumps(baseline))
    sample = next(
        item for item in observation_mutation["samples"] if item["name"] == "depth_32"
    )
    sample["observed"]["max_depth"] = 999_999
    assert any(
        "depth_32 structural observation mismatch" in problem
        for problem in runner._probe_sample_problems(observation_mutation)
    )

    timing_mutation = json.loads(json.dumps(baseline))
    sample = next(
        item for item in timing_mutation["samples"] if item["name"] == "nodes_50001"
    )
    sample["timing_ms"]["total_p95_nearest_rank"] = -1
    assert any(
        "nodes_50001 timing values are invalid" in problem
        for problem in runner._probe_sample_problems(timing_mutation)
    )


def test_artifact_page_probe_reproduction_rejects_byte_and_timing_mutations() -> None:
    baseline = json.loads(ARTIFACT_PAGE_PROBE.read_text(encoding="utf-8"))
    foundation = json.loads(FOUNDATION.read_text(encoding="utf-8"))
    policy = foundation["resource_limit_policy"]["artifact_page_policy"]
    runner = _runner_module()
    assert runner._artifact_page_probe_problems(policy) == []

    byte_mutation = json.loads(json.dumps(baseline))
    byte_mutation["samples"][1]["base64_bytes"] += 1
    problems = runner._artifact_page_probe_problems(
        policy, probe_override=byte_mutation
    )
    assert any("sample 65536 bytes or digest drifted" in item for item in problems)

    timing_mutation = json.loads(json.dumps(baseline))
    timing_mutation["samples"][0]["timing_ns_per_operation"]["sha256_hex"][
        "median"
    ] += 1
    problems = runner._artifact_page_probe_problems(
        policy, probe_override=timing_mutation
    )
    assert any("sha256_hex summary drifted" in item for item in problems)
