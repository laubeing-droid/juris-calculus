"""W6-08 contract for build-once artifact promotion."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
PROMOTION = ROOT / ".github" / "workflows" / "auto-release.yml"
ACTION_PIN = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def _document(path: Path, text: str | None = None) -> dict[str, Any]:
    return yaml.load(
        path.read_text(encoding="utf-8") if text is None else text,
        Loader=yaml.BaseLoader,
    )


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(step.get("run", "") for step in job.get("steps", []))


def _step_uses(document: dict[str, Any]) -> list[str]:
    return [
        step["uses"]
        for job in document.get("jobs", {}).values()
        for step in job.get("steps", [])
        if "uses" in step
    ]


def _promotion_problems(
    ci_text: str | None = None,
    promotion_text: str | None = None,
) -> list[str]:
    ci_text = CI.read_text(encoding="utf-8") if ci_text is None else ci_text
    promotion_text = (
        PROMOTION.read_text(encoding="utf-8")
        if promotion_text is None
        else promotion_text
    )
    ci = _document(CI, ci_text)
    promotion = _document(PROMOTION, promotion_text)
    problems: list[str] = []
    push = ci.get("on", {}).get("push", {})
    promote = ci.get("jobs", {}).get("promote", {})
    if push.get("tags") != ["v*"]:
        problems.append("tag-trigger")
    if (
        promote.get("needs") != "package"
        or promote.get("uses") != "./.github/workflows/auto-release.yml"
        or promote.get("secrets") != "inherit"
        or "refs/tags/v" not in promote.get("if", "")
    ):
        problems.append("caller")
    package = ci.get("jobs", {}).get("package", {})
    upload = next(
        (step for step in package.get("steps", []) if step.get("name") == "Upload exact release candidate"),
        {},
    )
    upload_paths = upload.get("with", {}).get("path", "")
    if (
        "work/dist-a/*.whl" not in upload_paths
        or "work/dist-b/*.whl" not in upload_paths
        or "reports/" not in upload_paths
        or upload.get("with", {}).get("if-no-files-found") != "error"
    ):
        problems.append("artifact")
    if set(promotion.get("on", {})) != {"workflow_call"}:
        problems.append("reusable-only")
    called = promotion.get("on", {}).get("workflow_call", {})
    if (
        called.get("inputs", {}).get("artifact-name", {}).get("required") != "true"
        or called.get("secrets", {}).get("JC_RELEASE_ED25519_KEY_JSON", {}).get("required")
        != "true"
    ):
        problems.append("required-inputs")
    job = promotion.get("jobs", {}).get("promote", {})
    if (
        promotion.get("permissions", {}).get("contents") != "read"
        or job.get("permissions", {}).get("contents") != "write"
        or job.get("environment") != "release"
    ):
        problems.append("permissions")
    uses = _step_uses(ci) + _step_uses(promotion)
    if not uses or any(ACTION_PIN.fullmatch(value) is None for value in uses):
        problems.append("action-pin")
    runs = _runs(job)
    required = (
        "GITHUB_REF_TYPE", "GITHUB_REF_NAME", "GITHUB_SHA", "refs/tags/",
        "work/dist-a", "work/dist-b", "cmp \"$wheel_a\" \"$wheel_b\"",
        "JC_RELEASE_ED25519_KEY_JSON", "build_provenance.py create",
        "build_provenance.py verify", "--require-tag-ref", "gh release create",
        "--verify-tag", "SHA256SUMS", "release-sbom.json", "build-provenance.json",
    )
    if any(marker not in promotion_text and marker not in runs for marker in required):
        problems.append("identity-or-assets")
    forbidden = (
        "tests/fixtures/keys/v4-test-ed25519.json", "--allow-test-key",
        "--release-candidate", "wheel_gate.py", "python -m build",
    )
    if any(marker in runs for marker in forbidden):
        problems.append("unsafe-promotion")
    return problems


def test_tag_ci_calls_reusable_promotion_only_after_package() -> None:
    ci = _document(CI)
    assert _promotion_problems() == []
    promote = ci["jobs"]["promote"]
    assert promote["needs"] == "package"
    assert promote["permissions"] == {"contents": "write"}


def test_ci_uploads_both_identical_wheels_and_all_release_evidence() -> None:
    package = _document(CI)["jobs"]["package"]
    upload = next(step for step in package["steps"] if step["name"] == "Upload exact release candidate")
    assert upload["uses"] == "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    assert upload["with"]["path"].splitlines() == [
        "work/dist-a/*.whl", "work/dist-b/*.whl", "reports/",
    ]


def test_promotion_is_reusable_and_release_environment_protected() -> None:
    document = _document(PROMOTION)
    assert set(document["on"]) == {"workflow_call"}
    assert document["permissions"] == {"contents": "read"}
    assert document["jobs"]["promote"]["environment"] == "release"


def test_production_signing_has_no_test_key_or_test_mode_fallback() -> None:
    text = PROMOTION.read_text(encoding="utf-8")
    runs = _runs(_document(PROMOTION)["jobs"]["promote"])
    assert "JC_RELEASE_ED25519_KEY_JSON" in text
    assert "--require-tag-ref" in runs
    assert "--allow-test-key" not in runs
    assert "--release-candidate" not in runs
    assert "v4-test-ed25519" not in text


def test_tag_version_commit_and_ab_wheel_identity_are_checked() -> None:
    runs = _runs(_document(PROMOTION)["jobs"]["promote"])
    for marker in ("GITHUB_REF_TYPE", "v$version", "refs/tags/", "GITHUB_SHA", "dist-a", "dist-b", "cmp"):
        assert marker in runs


def test_promotion_does_not_rebuild_and_releases_exact_evidence_set() -> None:
    runs = _runs(_document(PROMOTION)["jobs"]["promote"])
    assert "wheel_gate.py" not in runs and "python -m build" not in runs
    for asset in ("$wheel_a", "SHA256SUMS", "release-sbom.json", "build-provenance.json"):
        assert asset in runs
    assert "gh release create" in runs and "--verify-tag" in runs


def test_all_external_actions_are_commit_pinned() -> None:
    uses = _step_uses(_document(CI)) + _step_uses(_document(PROMOTION))
    assert uses and all(ACTION_PIN.fullmatch(value) for value in uses)


def test_release_contract_mutations_fail_closed() -> None:
    ci = CI.read_text(encoding="utf-8")
    promotion = PROMOTION.read_text(encoding="utf-8")
    mutations = (
        (ci.replace("    tags: ['v*']\n", "", 1), promotion),
        (ci.replace("            work/dist-b/*.whl", "            work/dist-a/*.whl", 1), promotion),
        (ci, promotion.replace("  workflow_call:", "  push:", 1)),
        (ci, promotion.replace("environment: release", "environment: staging", 1)),
        (ci, promotion.replace("actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093", "actions/download-artifact@v4", 1)),
        (ci, promotion.replace("--require-tag-ref", "--allow-test-key", 1)),
    )
    assert all(_promotion_problems(*mutation) for mutation in mutations)
