"""真实CLI evaluate/replay、默认official阻断和JSON framing门禁。"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

from compiler_core.contracts import CaseRequest, SCHEMA_VERSION
from compiler_core.resources import configs_root
from compiler_core.rule_packs import RulePackRegistry
from compiler_core.types import FactTrustStatus, LegalFact
from tests.unit.test_audit_bundle import _fixture


ROOT = Path(__file__).resolve().parents[2]


def _run(*arguments: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """在仓库根启动真实模块CLI。"""

    return subprocess.run(
        [sys.executable, "-m", "compiler_core.cli", *arguments],
        cwd=ROOT,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )


def test_cli_evaluate_writes_bundle_then_replay_passes(tmp_path) -> None:
    """显式development official fixture可通过CLI落包并离线replay。"""

    _, request = _fixture(tmp_path / "configs")
    state_root = tmp_path / "state"
    evaluated = _run(
        "evaluate",
        "--input", "-",
        "--development",
        "--config-root", str(tmp_path / "configs"),
        "--audit-out", str(state_root),
        "--json",
        stdin=json.dumps(request.to_dict(), ensure_ascii=False),
    )
    payload = json.loads(evaluated.stdout)

    assert evaluated.returncode == 0
    assert evaluated.stderr == ""
    assert payload["canonical_result"]["semantic"]["result_status"] == "accepted_formal_result"
    assert all(not ref.startswith(("C:", "D:", "/")) for ref in payload["canonical_result"]["artifact_refs"])
    replayed = _run("replay", payload["run_id"], "--audit-out", str(state_root), "--json")
    replay_payload = json.loads(replayed.stdout)
    assert replayed.returncode == 0
    assert replayed.stderr == ""
    assert replay_payload["status"] == "PASS"
    assert replay_payload["bundle_digest"] == payload["bundle_digest"]

    pack_digest = payload["canonical_result"]["semantic"]["pack_digest"]
    shutil.rmtree(state_root / "packs" / pack_digest)
    missing = _run("replay", payload["run_id"], "--audit-out", str(state_root), "--json")
    assert missing.returncode == 6
    assert missing.stdout == ""
    assert json.loads(missing.stderr)["code"] == "REPLAY_MATERIAL_MISSING"


def test_default_empty_cn_official_returns_admission_exit_3(tmp_path) -> None:
    """正式默认包为空时CLI不得回退cn-legacy-corpus。"""

    official = RulePackRegistry(configs_root()).verify("cn-official")
    fact = LegalFact(
        id="fact::a",
        value=True,
        status=FactTrustStatus.VERIFIED_FACT,
        source_ids=("evidence::1",),
        human_reviewed=True,
    )
    request = CaseRequest(
        SCHEMA_VERSION,
        "CN",
        "PRC",
        "2026-07-11",
        (fact,),
        official.pack_id,
        official.version,
        official.content_digest,
    )
    completed = _run(
        "evaluate", "--input", "-", "--audit-out", str(tmp_path / "state"), "--json",
        stdin=json.dumps(request.to_dict(), ensure_ascii=False),
    )

    assert completed.returncode == 3
    assert completed.stdout == ""
    assert json.loads(completed.stderr)["code"] == "PACK_NOT_REASONING_READY"
    assert not (tmp_path / "state" / "runs").exists()


def test_evaluate_invalid_json_returns_exit_2_without_traceback(tmp_path) -> None:
    """输入解析错误不创建run且不泄漏traceback。"""

    completed = _run(
        "evaluate", "--input", "-", "--audit-out", str(tmp_path / "state"), "--json",
        stdin="{broken",
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert json.loads(completed.stderr)["code"] == "INVALID_JSON"
    assert "Traceback" not in completed.stderr
